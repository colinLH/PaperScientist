"""Framework-event observation used only by the trusted Python launcher.

This is execution evidence, not an isolation boundary against hostile Python.
Child processes are intentionally not certified by output or inherited state.
"""
from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import runpy
import sys
import unittest


def execute(script_name, workspace_name, evidence_name):
    script, workspace, evidence = map(lambda name: Path(name).resolve(),
                                      (script_name, workspace_name, evidence_name))
    if not script.is_relative_to(workspace) or not evidence.is_relative_to(workspace):
        raise ValueError('Execution and test evidence must stay within the workspace')
    observed, sources, pytest_runs = {}, {}, []
    pytest_depth = 0
    original_start = unittest.TestResult.startTest

    def capture_source(path):
        try:
            path = Path(path).resolve()
            if path.is_relative_to(workspace) and path.suffix == '.py' and path.is_file():
                sources.setdefault(path.relative_to(workspace).as_posix(),hashlib.sha256(path.read_bytes()).hexdigest())
        except (OSError, TypeError, ValueError):
            pass

    def start_test(result, test):
        if not pytest_depth:
            item = observed.setdefault(id(result), {'result':result, 'events':0})
            item['events'] += 1
        try:
            method = getattr(test, getattr(test, '_testMethodName', ''), test.__class__)
            capture_source(inspect.getsourcefile(method))
        except (TypeError, OSError):
            pass
        return original_start(result, test)

    unittest.TestResult.startTest = start_test
    # Import the framework before adding user workspace paths. No plugin is
    # installed, and scripts that do not use pytest incur no test executions.
    try:
        import pytest
    except ImportError:
        pytest = None
    original_pytest_main = pytest.main if pytest else None

    class PytestEvents:
        def __init__(self):
            self.reports = {}
            self.exit_code = None

        def pytest_runtest_logreport(self, report):
            item = self.reports.setdefault(report.nodeid, {'passed':False, 'failed':False, 'skipped':False})
            item['failed'] |= report.failed
            item['skipped'] |= report.skipped
            if report.when == 'call':
                item['passed'] |= report.passed
            capture_source(workspace / report.location[0])

        def pytest_sessionfinish(self, session, exitstatus):
            self.exit_code = int(exitstatus)

    def pytest_main(args=None, plugins=None):
        nonlocal pytest_depth
        observer = PytestEvents()
        pytest_runs.append(observer)
        pytest_depth += 1
        try:
            return original_pytest_main(args, plugins=[*(plugins or []), observer])
        finally:
            pytest_depth -= 1

    if pytest:
        pytest.main = pytest_main
    sys.path[:0] = [str(script.parent), str(workspace)]
    sys.argv = [str(script)]
    capture_source(script)
    try:
        runpy.run_path(str(script), run_name='__main__')
    finally:
        unittest.TestResult.startTest = original_start
        if pytest:
            pytest.main = original_pytest_main
        records = []
        # Capture separate unittest runs, but avoid double counting TestCase
        # events generated from inside pytest.main itself.
        for item in observed.values():
            result = item['result']
            skipped = len(getattr(result, 'skipped', []))
            failures, errors = len(result.failures), len(result.errors)
            unexpected = len(getattr(result, 'unexpectedSuccesses', []))
            expected = len(getattr(result, 'expectedFailures', []))
            records.append({'framework':'unittest', 'tests':item['events'],
                            'passed':max(0,item['events']-skipped-failures-errors-unexpected-expected),
                            'failures':failures+unexpected, 'errors':errors, 'skipped':skipped,
                            'successful':result.wasSuccessful()})
        for observer in pytest_runs:
            rows = list(observer.reports.values())
            records.append({'framework':'pytest', 'tests':len(rows),
                            'passed':sum(r['passed'] and not r['failed'] for r in rows),
                            'failures':sum(r['failed'] for r in rows), 'errors':0,
                            'skipped':sum(r['skipped'] for r in rows),
                            'successful':observer.exit_code == 0})
        for module in list(sys.modules.values()):
            capture_source(getattr(module, '__file__', None))
        report = {'observer':'paperscientist.test_execution.v1', 'frameworks':records,
                  'tests':sum(r['tests'] for r in records), 'passed':sum(r['passed'] for r in records),
                  'failures':sum(r['failures'] for r in records), 'errors':sum(r['errors'] for r in records),
                  'successful':bool(records) and all(r['successful'] for r in records),
                  'sources':sources, 'scope':'In-process unittest/pytest events; subprocess tests are not certified'}
        evidence.write_text(json.dumps(report,ensure_ascii=False), encoding='utf-8')
