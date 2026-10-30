"""Evidence checks shared by ordinary specialist turns and durable web runs."""
from __future__ import annotations

from pathlib import Path


def manuscript_layout(phase, context, rule):
    from .manuscript_layout import validate
    if phase != 'completion' and not (phase == 'after_tool' and context.get('tool_name') == 'compile_latex'):
        return {'ok': True}
    actions = context.get('actions', [])
    paths = set()
    for action in actions:
        if action.get('status') != 'success':
            continue
        args, result = action.get('input', {}), action.get('result', {})
        if action.get('name') in {'configure_manuscript_layout', 'compile_latex', 'validate_manuscript_layout'}:
            if args.get('main_path'):
                paths.add(args['main_path'])
        if action.get('name') == 'assemble_manuscript' and isinstance(result, dict) and result.get('directory'):
            paths.add(result['directory'].rstrip('/') + '/main.tex')
        if action.get('name') in {'write_file', 'edit_file'} and str(args.get('path', '')).endswith('.tex'):
            path = context['store'].file(context['session']['id'], args['path'])
            if path.is_file() and '\\documentclass' in path.read_text(encoding='utf-8', errors='replace'):
                paths.add(args['path'])
    if phase == 'after_tool' and context.get('tool_name') == 'compile_latex':
        paths.add(context['tool_input']['main_path'])
    if rule.get('main_path'):
        paths.add(rule['main_path'])
    # Artifact declarations also cover unchanged files delivered after a restart.
    for path in context.get('deliverables', []):
        if str(path).endswith(('.pdf', '.tex')):
            source = str(Path(path).with_suffix('.tex')).replace('\\', '/')
            if context['store'].file(context['session']['id'], source).is_file():
                paths.add(source)
    reports = {path: validate(context['store'], context['session']['id'], path,
                             require_pdf=rule.get('require_pdf', True)) for path in sorted(paths)}
    invalid = {path: report for path, report in reports.items() if report.get('status') != 'passed'}
    diagnostics = []
    if invalid:
        result = context.get('tool_result', {})
        if phase == 'after_tool' and isinstance(result, dict):
            # The runtime wraps rejected tool results in HarnessViolation. Retain
            # the actual compiler/layout failure so repair is possible without
            # weakening the gate or mistaking an after-tool failure for a deadlock.
            if result.get('status') == 'layout_blocked':
                diagnostics.extend(f"{i.get('code')}: {i.get('message')}"
                                   for i in result.get('layout', {}).get('issues', [])[:6])
            elif result.get('status') in {'error', 'unavailable'}:
                diagnostics.append(str(result.get('message') or result.get('log') or result['status'])[-2000:])
        for path, report in invalid.items():
            diagnostics.extend(f"{path}: {i.get('code')}: {i.get('message')}"
                               for i in report.get('issues', [])[:3])
    return {'ok': not invalid, 'reports': reports,
            'reason': ('Manuscript layout is not validated: ' + ', '.join(invalid) +
                       ('\n' + '\n'.join(diagnostics) if diagnostics else '')) if invalid else ''}


def benchmark_evidence(phase, context, rule):
    from .benchmarks import audit_benchmarks
    relevant = {'plan_benchmark', 'run_benchmark', 'record_benchmark_result'}
    if not rule.get('always') and not any(a.get('name') in relevant for a in context.get('actions', [])):
        return {'ok': True, 'reason': 'No benchmark protocol selected in this task.'}
    report = audit_benchmarks(context['store'], context['session']['id'])
    ok = (report.get('all_selected_protocols_complete') if report['results'] else
          not report['pending_plans'] and report.get('integrity_valid', True))
    return {'ok': ok, 'audit': report,
            'reason': '' if ok else 'Selected benchmark protocol has missing/failed cases or invalid execution evidence. Repair it or explicitly report the task as blocked; do not claim full evaluation.'}


def register(registry):
    registry.register_harness('manuscript_layout', manuscript_layout)
    registry.register_harness('benchmark_evidence', benchmark_evidence)
