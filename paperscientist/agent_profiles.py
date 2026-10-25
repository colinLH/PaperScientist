"""Operator-defined agent capabilities and executable, fail-closed harness hooks.

Profiles are configuration, never instructions loaded from a conversation. A child
keeps a durable capability ceiling, so reloads/restarts cannot silently grant it
more privileges than its parent delegated.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from fnmatch import fnmatchcase
import hashlib
import inspect
import json
from pathlib import Path
import re
from typing import Callable

import yaml


COORDINATION_TOOLS = frozenset({
    'spawn_agent', 'list_agents', 'wait_agent', 'read_agent', 'followup_task',
    'send_message', 'cancel_agent', 'import_agent_artifact', 'list_agent_profiles',
})
DEFAULT_PATH = Path(__file__).with_name('agent_profiles.yaml')


class HarnessViolation(ValueError):
    pass


def _strings(value, field):
    if not isinstance(value, list) or any(not isinstance(v, str) or not v for v in value):
        raise ValueError(f'{field} must be a list of nonempty strings')
    return frozenset(value)


def permits(patterns, value):
    return any(fnmatchcase(value, p) for p in patterns)


@dataclass(frozen=True)
class AgentProfile:
    name: str
    description: str
    prompt: str
    tools: frozenset[str]
    skills: frozenset[str]
    children: frozenset[str]
    harnesses: tuple[dict, ...] = ()
    allow_mcp: frozenset[str] = frozenset()
    revision: str = ''
    inherited: bool = False
    # These exact names narrow patterns without needing unsafe wildcard algebra.
    tool_ceiling: frozenset[str] | None = None
    skill_ceiling: frozenset[str] | None = None
    grant_parent: AgentProfile | None = None

    def allows_tool(self, name):
        return (permits(self.tools, name) and (self.tool_ceiling is None or name in self.tool_ceiling)
                and (self.grant_parent is None or self.grant_parent.allows_tool(name)))

    def allows_skill(self, name):
        return (permits(self.skills, name) and (self.skill_ceiling is None or name in self.skill_ceiling)
                and (self.grant_parent is None or self.grant_parent.allows_skill(name)))

    def scoped_catalog(self, catalog):
        return catalog.scoped(self.allows_skill)

    def metadata(self):
        return {'name': self.name, 'description': self.description, 'prompt': self.prompt,
                'tools': sorted(self.tools if self.tool_ceiling is None else
                                (n for n in self.tool_ceiling if self.allows_tool(n))),
                'skills': sorted(self.skills if self.skill_ceiling is None else
                                 (n for n in self.skill_ceiling if self.allows_skill(n))),
                'children': sorted(self.children), 'harnesses': list(self.harnesses),
                'mcp_tools': sorted(self.allow_mcp), 'revision': self.revision}


class AgentProfileRegistry:
    """Reads builtin YAML plus an optional trusted operator override file."""

    def __init__(self, override_path=None):
        self.override_path = Path(override_path) if override_path else None
        self.profiles, self.aliases = {}, {}
        self.hooks: dict[str, Callable] = {'implementation_tests': implementation_tests}
        self.reload()

    def reload(self):
        raw = yaml.safe_load(DEFAULT_PATH.read_text(encoding='utf-8'))
        if self.override_path and self.override_path.is_file():
            if self.override_path.stat().st_size > 500_000:
                raise ValueError('Agent profile configuration exceeds 500KB')
            override = yaml.safe_load(self.override_path.read_text(encoding='utf-8'))
            if not isinstance(override, dict) or override.get('version') != 1:
                raise ValueError('Agent profile configuration requires version: 1')
            raw['profiles'].update(override.get('profiles', {}))
            raw['aliases'].update(override.get('aliases', {}))
        revision = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
        profiles = {}
        for name, item in raw['profiles'].items():
            if not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', name) or not isinstance(item, dict):
                raise ValueError('Invalid profile name or definition')
            if set(item) - {'description','prompt','tools','skills','children','harnesses','mcp_tools','inherit_parent'}:
                raise ValueError(f'Unknown fields in profile {name}')
            harnesses = item.get('harnesses', [])
            if not isinstance(harnesses, list) or any(not isinstance(h, dict) or not h.get('name') for h in harnesses):
                raise ValueError('Each harness must have a registered name and optional configuration')
            if len(harnesses)>16:
                raise ValueError('At most 16 harness hooks per profile')
            profiles[name] = AgentProfile(
                name, str(item['description']), str(item['prompt']),
                _strings(item.get('tools', []), 'tools'), _strings(item.get('skills', []), 'skills'),
                _strings(item.get('children', []), 'children'), tuple(harnesses),
                _strings(item.get('mcp_tools', []), 'mcp_tools'), revision,
                bool(item.get('inherit_parent', False)))
        aliases = raw.get('aliases', {})
        if not isinstance(aliases, dict) or any(v not in profiles for v in aliases.values()):
            raise ValueError('Every profile alias must resolve to a defined profile')
        if 'orchestrator' not in profiles or any(c not in profiles for p in profiles.values() for c in p.children):
            raise ValueError('Missing orchestrator or unknown child profile')
        self.profiles, self.aliases, self.revision = profiles, aliases, revision

    def get(self, name=None):
        name = self.aliases.get(name, name) if name else 'orchestrator'
        if name not in self.profiles:
            raise ValueError('Unknown agent profile; use list_agent_profiles')
        return self.profiles[name]

    def for_session(self, store, session, role=None, _seen=None):
        seen = set(_seen or ())
        if session['id'] in seen:
            raise PermissionError('Cyclic agent capability inheritance')
        seen.add(session['id'])
        agent = store.get_agent(session['id'])
        requested = agent.get('role') or role
        if session.get('parent_id') and not requested:
            raise PermissionError('A child session must have a delegated agent profile')
        profile = self.get(requested)
        ceiling = agent.get('capabilities')
        if profile.inherited and not ceiling:
            raise PermissionError('General-purpose leaves require a delegated capability ceiling')
        if ceiling:
            profile = replace(profile, tool_ceiling=frozenset(ceiling['tools']),
                              skill_ceiling=frozenset(ceiling['skills']),
                              children=profile.children.intersection(ceiling.get('children', [])),
                              allow_mcp=frozenset(n for n in ceiling.get('mcp_tools', []) if permits(profile.allow_mcp, n)))
            if profile.inherited:
                profile = replace(profile, harnesses=tuple(ceiling.get('inherited_harnesses', [])))
        if session.get('parent_id'):
            parent = store.get_session(session['parent_id'])
            if parent is None:
                raise PermissionError('Delegating parent session no longer exists')
            parent_profile = self.for_session(store, parent, _seen=seen)
            if profile.name not in parent_profile.children:
                raise PermissionError('Parent profile no longer authorizes this child role')
            profile = replace(profile, grant_parent=parent_profile,
                              allow_mcp=frozenset(n for n in profile.allow_mcp if permits(parent_profile.allow_mcp,n)))
            if profile.inherited:
                rules = {json.dumps(h, sort_keys=True): h for h in (*profile.harnesses, *parent_profile.harnesses)}
                profile = replace(profile, harnesses=tuple(rules.values()))
        return profile

    def delegate(self, parent_profile, role, tool_names, catalog):
        child = self.get(role)
        if child.name not in parent_profile.children:
            raise PermissionError(f'{parent_profile.name} cannot delegate to {child.name}')
        tools = {n for n in tool_names if parent_profile.allows_tool(n)}
        if child.inherited:
            tools -= COORDINATION_TOOLS
            child = replace(child, harnesses=parent_profile.harnesses, allow_mcp=frozenset())
        tools = {n for n in tools if child.allows_tool(n)}
        # Coordination is a granted operation, not a way for leaves to reacquire it.
        if child.children:
            tools.update(COORDINATION_TOOLS.intersection(n for n in tool_names
                         if parent_profile.allows_tool(n) and child.allows_tool(n)))
        skills = {n for n in catalog.skills if parent_profile.allows_skill(n) and child.allows_skill(n)}
        mcp_names = {n for n in tools if permits(parent_profile.allow_mcp,n) and permits(child.allow_mcp,n)}
        return child, {'tools': sorted(tools), 'skills': sorted(skills),
                       'children': sorted(child.children), 'mcp_tools': sorted(mcp_names),
                       'registry_revision': self.revision,
                       'inherited_harnesses': list(child.harnesses) if child.inherited else []}

    def register_harness(self, name, callback):
        """Trusted application extension point; never exposed as an LLM tool."""
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', name) or not callable(callback):
            raise ValueError('Harness needs a safe name and callable implementation')
        self.hooks[name] = callback

    async def check(self, profile, phase, context):
        if phase not in {'before_tool','after_tool','completion'}:
            raise ValueError('Unknown harness phase')
        reports = []
        for rule in profile.harnesses:
            if phase not in rule.get('phases', ['before_tool','after_tool','completion']):
                continue
            hook = self.hooks.get(rule['name'])
            if hook is None:
                raise HarnessViolation(f"Harness {rule['name']} is not registered; execution is blocked")
            try:
                result = hook(phase, context, rule)
                if inspect.isawaitable(result):
                    result = await result
            except Exception as exc:
                raise HarnessViolation(f"Harness {rule['name']} failed: {type(exc).__name__}: {exc}") from exc
            if not isinstance(result, dict) or not isinstance(result.get('ok'), bool):
                raise HarnessViolation(f"Harness {rule['name']} returned an invalid result")
            reports.append({'name': rule['name'], **result})
            if not result['ok']:
                raise HarnessViolation(f"{rule['name']}: {result.get('reason', 'requirements not satisfied')}")
        return reports


def _python_changes(action):
    if action.get('status') != 'success':
        return {}
    result = action.get('result', {})
    changes = {}
    if action.get('name') in {'write_file', 'edit_file', 'import_agent_artifact', 'copy_parent_artifact'}:
        path = action.get('input', {}).get('path') or result.get('path', '')
        if str(path).endswith('.py'):
            changes[str(path)] = result.get('metadata', {}).get('sha256', '')
    if action.get('name') == 'run_python':
        for item in result.get('generated_artifacts', []):
            if str(item.get('path', '')).endswith('.py'):
                changes[item['path']] = item.get('metadata', {}).get('sha256', '')
    return changes


def _test_summary(result):
    observed = result.get('unit_tests', {})
    if observed.get('observer') == 'paperscientist.test_execution.v1':
        failed = bool(observed.get('failures') or observed.get('errors') or not observed.get('successful'))
        return {'tests':observed.get('tests',0), 'passed':bool(observed.get('successful')
                and observed.get('tests',0)>0 and observed.get('passed',0)>0 and not failed),
                'failures_observed':failed, 'certified_events':True}
    output = str(result.get('stdout', ''))+'\n'+str(result.get('stderr', ''))
    unittest_counts = [int(v) for v in re.findall(r'(?m)^Ran (\d+) tests? in ', output)]
    pytest_counts = [int(v) for v in re.findall(r'\b(\d+) passed\b', output)]
    failed = bool(re.search(r'(?m)^FAILED(?: |$)|\b[1-9]\d* (?:failed|errors?)\b|failures=[1-9]\d*|errors=[1-9]\d*', output))
    count = sum(unittest_counts) or sum(pytest_counts)
    # Historical text remains useful diagnosis, but cannot certify execution.
    return {'tests':count, 'passed':False, 'failures_observed':failed, 'certified_events':False}


def _verify_test_receipt(context, result, code_hashes):
    store, session = context.get('store'), context.get('session')
    if store is None or not session:
        return False, 'No persistent execution store was supplied'
    try:
        aid = result.get('artifact', {}).get('id')
        artifact = next((a for a in store.artifacts(session['id']) if a['id'] == aid and a['kind'] == 'execution'), None)
        if artifact is None:
            return False, 'No registered execution receipt'
        path = store.file(session['id'], artifact['path'])
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != artifact['metadata'].get('sha256'):
            return False, 'Execution receipt changed after registration'
        saved = json.loads(payload)
        fields = ('run_id', 'script', 'script_sha256', 'exit_code', 'timed_out', 'stdout', 'stderr', 'unit_tests', 'input_source_hashes')
        if any(saved.get(k) != result.get(k) for k in fields):
            return False, 'Tool result does not match its execution receipt'
        script = store.file(session['id'], result['script'])
        if hashlib.sha256(script.read_bytes()).hexdigest() != result.get('script_sha256'):
            return False, 'Runner changed after this execution'
        for name, expected in code_hashes.items():
            if not expected or hashlib.sha256(store.file(session['id'], name).read_bytes()).hexdigest() != expected:
                return False, 'Python file changed or lacks a registered hash: '+name
        for name, expected in result.get('unit_tests', {}).get('sources', {}).items():
            if result.get('input_source_hashes',{}).get(name) != expected:
                return False, 'Tested source was generated or changed during execution; save it and rerun: '+name
            if hashlib.sha256(store.file(session['id'],name).read_bytes()).hexdigest() != expected:
                return False, 'Tested source changed after execution: '+name
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return False, 'Execution receipt could not be verified: '+str(exc)
    return True, ''


def implementation_tests(phase, context, rule):
    """Require a registered, successful nonempty test run after the latest change.

    Framework events, receipt integrity and source hashes are evidence checks;
    they do not prove test adequacy or provide an adversarial process sandbox.
    """
    if phase != 'completion':
        return {'ok': True}
    actions = context.get('actions', [])
    code_hashes, last_write, changed_paths = {}, -1, []
    for index, action in enumerate(actions):
        changes = _python_changes(action)
        if changes:
            code_hashes.update(changes)
            last_write, changed_paths = index, list(changes)
    if last_write < 0:
        return {'ok': True, 'scope': 'No Python implementation changed in this turn'}
    diagnostics, known_runner = [], None
    for index, action in enumerate(actions):
        if action.get('name') != 'run_python':
            continue
        result = action.get('result', {})
        summary = _test_summary(result)
        verified, problem = _verify_test_receipt(context, result, code_hashes)
        success = (action.get('status') == 'success' and result.get('exit_code') == 0
                   and not result.get('timed_out') and summary['passed'] and verified)
        if success:
            known_runner = result.get('script')
        if index > last_write:
            diagnostics.append({'run_id':result.get('run_id'), 'script':result.get('script'),
                                'exit_code':result.get('exit_code'), **summary, 'receipt_problem':problem})
            if success:
                return {'ok':True, 'tests':summary['tests'], 'run_id':result['run_id'],
                        'scope':'Registered positive test run and current code hashes verified; adequacy still requires review'}
    next_action = ('Re-run the positive test runner '+known_runner+' with run_python, then report completion without further Python edits.'
                   if known_runner else 'Run a saved positive unittest/pytest runner after the latest Python change; exit 0 and nonempty passing tests are required. Use unittest discovery/TextTestRunner or pytest.main in the run_python process; subprocess stdout and printed summaries are not certified test events.')
    reason = ('Latest Python change: '+', '.join(changed_paths)+'. Runs after that change: '+
              json.dumps(diagnostics, ensure_ascii=False)+'. '+next_action+
              ' Expected failures in a negative-control run do not count as a positive passing suite.')
    return {'ok':False, 'reason':reason, 'last_changed_paths':changed_paths,
            'subsequent_runs':diagnostics, 'next_action':next_action}
