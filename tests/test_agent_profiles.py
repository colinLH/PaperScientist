import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool

from paperscientist.agent_profiles import AgentProfileRegistry, HarnessViolation, implementation_tests
from paperscientist.config import Settings
from paperscientist.runtime import AgentService
from paperscientist.tools import ToolSet


def calls(*items):
    return AIMessage(content='', tool_calls=[{'name': name, 'args': args, 'id': f'call_{i}_{name}'}
                                             for i, (name, args) in enumerate(items)])


class Model:
    def __init__(self, responses=()):
        self.responses = list(responses)
        self.tools, self.inputs = [], []

    def bind_tools(self, tools):
        self.tools = tools
        return self

    async def ainvoke(self, messages):
        self.inputs.append(messages)
        return self.responses.pop(0) if self.responses else AIMessage(content='Evidence reviewed; task complete.')


class ProfileTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cfg = Settings(data_dir=self.root/'data', model='test:agent', extract_memory=False,
                            max_subagents=1, max_steps=15, skill_roots=())
        self.service = AgentService(self.cfg, lambda _: Model())
        self.parent = self.service.store.session('root')
        self.tools = {t.name:t for t in ToolSet(self.service, self.parent, self.cfg, self.service.scheduler).tools}

    async def asyncTearDown(self):
        await self.service.close()
        self.temp.cleanup()

    async def spawn(self, role='design', **extra):
        return await self.tools['spawn_agent'].ainvoke({'task_name':'task', 'message':'bounded task', 'role':role, **extra})

    async def test_file_tools_cannot_modify_registered_benchmark_evidence(self):
        from paperscientist.benchmarks import register_benchmark
        record = register_benchmark(self.service.store, self.parent['id'], {
            'id': 'guard-test', 'title': 'Guard fixture', 'version': 'v1', 'task': 'File guard test',
            'source_url': 'https://example.org/test', 'license_url': 'https://example.org/license',
            'license': 'fixture', 'license_notes': 'Local fixture', 'provenance': 'local_synthetic',
            'splits': ['test'], 'metrics': {'accuracy': 'Fixture accuracy'},
        })
        path = record['path']
        before = self.service.store.file(self.parent['id'], path).read_bytes()
        for name, args in [('write_file', {'path': path, 'content': '{}', 'overwrite': True}),
                           ('edit_file', {'path': path, 'old': '', 'new': ' ', 'append': True})]:
            with self.subTest(tool=name), self.assertRaisesRegex(PermissionError, 'append-only'):
                await self.tools[name].ainvoke(args)
        self.assertEqual(self.service.store.file(self.parent['id'], path).read_bytes(), before)

    async def wait(self, child):
        await asyncio.wait_for(self.service.scheduler.tasks[child['id']], 8)
        return self.service.store.get_agent(child['id'])

    async def test_nested_parallel_leaves_no_deadlock_at_one_slot_and_artifact_import(self):
        active, peak, models = 0, 0, []
        class Counted(Model):
            async def ainvoke(inner, messages):
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                try:
                    await asyncio.sleep(.02)
                    return await super(Counted, inner).ainvoke(messages)
                finally:
                    active -= 1
        def factory(_):
            if not models:
                value = Counted([
                    calls(('spawn_agent',{'task_name':'a','role':'general','message':'Create a text result'}),
                          ('spawn_agent',{'task_name':'b','role':'general','message':'Create another text result'})),
                    calls(('wait_agent',{'target':'a','timeout':5}), ('wait_agent',{'target':'b','timeout':5})),
                    AIMessage(content='Both child results are available.'),
                ])
            else:
                value = Counted([calls(('write_file',{'path':'result.txt','content':'verified child output'}))])
            models.append(value)
            return value
        self.service.model_factory = factory
        child = await self.spawn()
        done = await self.wait(child)
        self.assertEqual(done['status'], 'completed', done)
        leaves = self.service.store.agents(child['id'])
        self.assertEqual(len(leaves), 2)
        self.assertTrue(all(a['status']=='completed' for a in leaves), leaves)
        self.assertEqual(peak, 1)
        specialist_names = {t.name for t in models[0].tools}
        for model in models[1:]:
            names = {t.name for t in model.tools}
            self.assertLessEqual(names, specialist_names)
            self.assertNotIn('spawn_agent', names)
            self.assertNotIn('assemble_manuscript', names)
            self.assertNotIn('record_experiment', names)
        session = self.service.store.get_session(child['id'])
        child_tools = {t.name:t for t in ToolSet(self.service,session,self.cfg,self.service.scheduler,True).tools}
        artifact = self.service.store.artifacts(leaves[0]['id'])[0]
        imported = await child_tools['import_agent_artifact'].ainvoke({
            'target':leaves[0]['id'],'artifact_id':artifact['id'],'destination':'leaf-result.txt'})
        final = await self.tools['import_agent_artifact'].ainvoke({
            'target':child['id'],'artifact_id':imported['id'],'destination':'integrated.txt'})
        self.assertEqual(self.service.store.file('root',final['path']).read_text(), 'verified child output')
        self.assertEqual(final['metadata']['source_child'], child['id'])
        self.assertIn('artifacts', self.service.store.get_agent(leaves[0]['id']))

    async def test_hallucinated_tool_is_denied_at_dispatch_and_mcp_default_denied(self):
        model = Model([calls(('run_python',{'path':'forbidden.py'})),
                       calls(('assemble_manuscript',{'title':'not allowed'}))])
        self.service.model_factory = lambda _:model
        with patch('paperscientist.runtime.load_tools', side_effect=AssertionError('MCP must not load for this specialist')):
            child = await self.spawn('literature')
            done = await self.wait(child)
        self.assertEqual(done['status'], 'completed')
        names = {t.name for t in model.tools}
        self.assertNotIn('run_python', names)
        self.assertNotIn('assemble_manuscript', names)
        errors = [m for _,m in self.service.store.history(child['id']) if isinstance(m,ToolMessage)]
        self.assertEqual([m.status for m in errors], ['error','error'])
        self.assertTrue(all('outside this agent profile' in m.content for m in errors))

    async def test_isolated_review_denies_network_at_binding_dispatch_and_reload(self):
        from dataclasses import replace
        from paperscientist.agent_profiles import ISOLATED_REVIEW_TOOLS
        # Even an operator profile granting wildcard tools/MCP cannot escape isolation.
        for name in ('orchestrator', 'reviewer'):
            self.service.profiles.profiles[name] = replace(self.service.profiles.get(name),
                tools=frozenset({'*'}), allow_mcp=frozenset({'*'}))
        source = self.service.store.file('root', 'source.txt')
        source.write_text('Frozen evidence')
        artifact = self.service.store.artifact('root', source, 'manuscript')
        model = Model([calls(('search_papers', {'query':'must not reach network'}),
                             ('fetch_url', {'url':'https://example.org'})),
                       calls(('write_file', {'path':'review.md','content':'Bounded review'}))])
        self.service.model_factory = lambda _:model
        with patch('paperscientist.runtime.load_tools', side_effect=AssertionError('MCP must not load')):
            child = await self.spawn('reviewer', isolated_review=True, artifact_ids=[artifact['id']])
            self.assertEqual((await self.wait(child))['status'], 'completed')
        self.assertLessEqual({t.name for t in model.tools}, ISOLATED_REVIEW_TOOLS)
        responses = [m for _,m in self.service.store.history(child['id']) if isinstance(m,ToolMessage)]
        self.assertEqual([m.status for m in responses], ['error','error','success'])
        self.assertTrue(all('outside this agent profile' in m.content for m in responses[:2]))
        self.assertEqual(self.service.store.file(child['id'], 'review.md').read_text(), 'Bounded review')
        # Reconstruct from persisted session/capabilities with a new registry.
        registry = AgentProfileRegistry()
        restored = registry.for_session(self.service.store, self.service.store.get_session(child['id']))
        self.assertFalse(restored.allow_mcp)
        self.assertFalse(restored.children)
        self.assertFalse(restored.allows_tool('search_papers'))
        self.assertFalse(restored.allows_tool('future_extension'))
        self.assertTrue(restored.allows_tool('read_file'))
        durable_model = Model([calls(('search_papers', {'query':'still forbidden'})),
                               AIMessage(content='Local-only review complete.')])
        self.service.model_factory = lambda _:durable_model
        # Durable runs are root-only; exercise the same isolation metadata at
        # their binding/dispatch boundary without creating an unsupported child run.
        get_agent = self.service.store.get_agent
        def isolated_metadata(sid):
            return {'role':'reviewer', 'isolated_review':True} if sid=='durable-review' else get_agent(sid)
        with patch.object(self.service.store, 'get_agent', side_effect=isolated_metadata), \
             patch('paperscientist.runs.load_tools', side_effect=AssertionError('MCP must not load')):
            run = await self.service.runs.start('durable-review', 'Verify durable isolation', continuous=False)
            await asyncio.wait_for(self.service.runs.tasks[run['id']], 10)
        self.assertEqual(self.service.runs.db.get(run['id'])['status'], 'completed')
        self.assertLessEqual({t.name for t in durable_model.tools}, ISOLATED_REVIEW_TOOLS)
        errors = [m for _,m in self.service.store.history('durable-review') if isinstance(m,ToolMessage) and m.status=='error']
        self.assertEqual(len(errors), 1)

    async def test_scoped_skills_metadata_loading_resources_staging_and_active_context(self):
        root = self.root/'skills'
        for name in ['literature-review','latex-writing','scientific-python']:
            path = root/name
            path.mkdir(parents=True)
            (path/'SKILL.md').write_text(f'---\nname: {name}\ndescription: {name} reference\n---\n{name} PRIVATE CONTENT',encoding='utf-8')
            (path/'resource.txt').write_text(name+' resource',encoding='utf-8')
        from paperscientist.skills import SkillCatalog
        self.service.catalog = SkillCatalog((root,))
        child = await self.spawn('researcher')
        await self.wait(child)
        session = self.service.store.get_session(child['id'])
        local = ToolSet(self.service,session,self.cfg,self.service.scheduler,True)
        tools = {t.name:t for t in local.tools}
        self.assertEqual(set(local.catalog.skills), {'literature-review'})
        listed = await tools['list_skills'].ainvoke({})
        self.assertEqual([s['name'] for s in listed['skills']], ['literature-review'])
        for name,args in [('load_skill',{'name':'latex-writing'}),
                          ('load_skill',{'name':'latex-writing','resource':'resource.txt'}),
                          ('list_skill_resources',{'name':'latex-writing'}),
                          ('stage_skill',{'name':'latex-writing','destination':'forbidden'})]:
            with self.assertRaises(ValueError):
                await tools[name].ainvoke(args)
        self.service.store.event(child['id'],'skill_loaded',{'name':'latex-writing','resource':'SKILL.md'})
        prompt = self.service.system_prompt(session,self.cfg)
        self.assertNotIn('latex-writing PRIVATE CONTENT',prompt)
        self.assertNotIn('scientific-python PRIVATE CONTENT',prompt)
        self.assertIn('literature-review', prompt)
        self.assertFalse(self.service.store.file(child['id'],'forbidden').exists())

    async def test_unknown_roles_depth_limits_duplicate_names_and_recursive_cancellation(self):
        entered = asyncio.Event()
        class Slow(Model):
            async def ainvoke(self, messages):
                entered.set()
                await asyncio.sleep(60)
                return AIMessage(content='unreachable')
        self.service.model_factory = lambda _:Slow()
        child = await self.spawn('literature')
        await entered.wait()
        session = self.service.store.get_session(child['id'])
        local = {t.name:t for t in ToolSet(self.service,session,self.cfg,self.service.scheduler,True).tools}
        with self.assertRaises(PermissionError):
            await local['spawn_agent'].ainvoke({'task_name':'escalate','role':'design','message':'try'})
        with self.assertRaises(ValueError):
            await self.tools['spawn_agent'].ainvoke({'task_name':'task','role':'literature','message':'duplicate'})
        leaf = await local['spawn_agent'].ainvoke({'task_name':'leaf','role':'general','message':'bounded'})
        await asyncio.sleep(.03)
        await self.tools['cancel_agent'].ainvoke({'target':child['id']})
        self.assertEqual(self.service.store.get_agent(child['id'])['status'],'cancelled')
        self.assertEqual(self.service.store.get_agent(leaf['id'])['status'],'cancelled')
        self.assertTrue(self.service.scheduler.tasks[leaf['id']].done())
        # Custom profiles cannot evade the independent runtime hierarchy budget.
        parent = self.service.store.get_session(leaf['id'])
        profile = self.service.profiles.get('literature')
        tools = {t.name:t for t in self.service.scheduler.tools(parent,self.cfg,profile)}
        with self.assertRaisesRegex(ValueError,'depth'):
            await tools['spawn_agent'].ainvoke({'task_name':'too-deep','role':'general','message':'try'})

    async def test_durable_ceiling_blocks_privilege_growth_and_general_inherits_harness(self):
        child = await self.spawn('design')
        await self.wait(child)
        session = self.service.store.get_session(child['id'])
        tools = {t.name:t for t in ToolSet(self.service,session,self.cfg,self.service.scheduler,True).tools}
        leaf = await tools['spawn_agent'].ainvoke({'task_name':'helper','role':'general','message':'bounded'})
        await self.wait(leaf)
        self.assertIn('implementation_tests',[h['name'] for h in leaf['capabilities']['inherited_harnesses']])
        override = self.root/'operator.yaml'
        profile = yaml.safe_load(Path('paperscientist/agent_profiles.yaml').read_text())['profiles']['design']
        profile['tools'] += ['assemble_manuscript']
        override.write_text(yaml.safe_dump({'version':1,'profiles':{'design':profile}}),encoding='utf-8')
        await self.service.close()
        self.service = AgentService(self.cfg.with_overrides(agent_profiles_path=override), lambda _:Model())
        profile = self.service.profiles.for_session(self.service.store,session)
        self.assertFalse(profile.allows_tool('assemble_manuscript'))
        leaf_session = self.service.store.get_session(leaf['id'])
        restored = self.service.profiles.for_session(self.service.store,leaf_session)
        self.assertIn('implementation_tests',[h['name'] for h in restored.harnesses])
        self.assertFalse(restored.allows_tool('assemble_manuscript'))
        definitions = yaml.safe_load(Path('paperscientist/agent_profiles.yaml').read_text())['profiles']
        root = definitions['orchestrator']
        root['tools'] = ['read_file','spawn_agent','wait_agent']
        override.write_text(yaml.safe_dump({'version':1,'profiles':{'design':definitions['design'],
                            'orchestrator':root}}),encoding='utf-8')
        self.service.profiles.reload()
        narrowed = self.service.profiles.for_session(self.service.store,leaf_session)
        self.assertTrue(narrowed.allows_tool('read_file'))
        self.assertFalse(narrowed.allows_tool('run_python'))

    async def test_harness_before_after_and_completion_fail_closed(self):
        override = self.root/'operator.yaml'
        override.write_text(yaml.safe_dump({'version':1,'profiles':{
            'orchestrator': {'description':'test','prompt':'operator instructions','tools':['write_file'],
                             'skills':[],'children':[],'harnesses':[{'name':'local_gate'}]}}}),encoding='utf-8')
        await self.service.close()
        model = Model([calls(('write_file',{'path':'no.txt','content':'blocked'}))])
        self.service = AgentService(self.cfg.with_overrides(agent_profiles_path=override),lambda _:model)
        result = await self.service.run_turn('root','test missing hook')
        self.assertEqual(result['stop_reason'],'harness_failed')
        self.assertFalse(self.service.store.file('root','no.txt').exists())
        phases = []
        async def check(phase,ctx,rule):
            phases.append(phase)
            self.assertIs(ctx['service'],self.service)
            return {'ok':True}
        self.service.profiles.register_harness('local_gate',check)
        self.service.model_factory = lambda _:Model([calls(('write_file',{'path':'yes.txt','content':'approved'}))])
        result = await self.service.run_turn('root','test registered hook')
        self.assertEqual(result['stop_reason'],'completed')
        self.assertEqual(phases,['before_tool','after_tool','completion'])

    async def test_implementation_guard_uses_real_tests_after_latest_change_and_survives_restart(self):
        script = ('import unittest\n'
                  'def add(a, b): return a+b\n'
                  'class Arithmetic(unittest.TestCase):\n'
                  '    def test_negative_operand(self): self.assertEqual(add(-3, 2), -1)\n'
                  '    def test_identity(self): self.assertEqual(add(5, 0), 5)\n'
                  'unittest.main()\n')
        first = Model([calls(('write_file',{'path':'test_impl.py','content':script}))])
        self.service.model_factory = lambda _:first
        child = await self.spawn('engineer')
        incomplete = await self.wait(child)
        self.assertEqual(incomplete['stop_reason'],'harness_failed',incomplete)
        await self.service.close()
        self.service = AgentService(self.cfg.with_overrides(allow_execution=True),
                                   lambda _:Model([calls(('run_python',{'path':'test_impl.py'}))]))
        tools = {t.name:t for t in ToolSet(self.service,self.parent,self.service.settings,self.service.scheduler).tools}
        resumed = await tools['followup_task'].ainvoke({'target':child['id'],'message':'Run the saved tests and report the actual result'})
        done = await self.wait(resumed)
        self.assertEqual(done['status'],'completed',done)
        execution = [e['data']['result'] for e in self.service.store.events(child['id'])
                     if e['kind']=='tool_result' and e['data']['name']=='run_python'][-1]
        self.assertEqual(execution['exit_code'],0)
        self.assertIn('Ran 2 tests',execution['stderr'])
        self.assertFalse(self.service.pending_harness_actions(child['id']))
        actions = [{'name':'run_python','status':'success','result':execution},
                   {'name':'write_file','status':'success','input':{'path':'new.py'}}]
        self.assertFalse(implementation_tests('completion',{'actions':actions},{})['ok'])

    async def test_changed_import_artifact_rejected(self):
        self.service.model_factory = lambda _:Model([calls(('write_file',{'path':'result.txt','content':'original'}))])
        child = await self.spawn('literature')
        await self.wait(child)
        artifact = self.service.store.artifacts(child['id'])[0]
        Path(artifact['path']).write_text('unregistered replacement')
        with self.assertRaisesRegex(ValueError,'changed after registration'):
            await self.tools['import_agent_artifact'].ainvoke({'target':child['id'],'artifact_id':artifact['id'],'destination':'result.txt'})

    async def test_operator_custom_profile_and_explicit_mcp_intersection(self):
        raw = yaml.safe_load(Path('paperscientist/agent_profiles.yaml').read_text())
        root = raw['profiles']['orchestrator']
        root['children'].append('fact_reader')
        override = self.root/'operator.yaml'
        override.write_text(yaml.safe_dump({'version':1,'profiles':{
            'orchestrator':root,
            'fact_reader':{'description':'bounded custom reader','prompt':'CUSTOM FACT READER PE',
                           'tools':['fixture_allowed','read_file'], 'skills':[], 'children':[],
                           'harnesses':[], 'mcp_tools':['fixture_*']},
        },'aliases':{'fact_checker':'fact_reader'}}),encoding='utf-8')
        executed = []
        @tool
        def fixture_allowed() -> dict:
            """Read a test evidence fixture."""
            executed.append('allowed')
            return {'ok':True,'value':7}
        @tool
        def fixture_forbidden() -> dict:
            """An unrelated fixture must never execute in the specialist."""
            executed.append('forbidden')
            return {'ok':True}
        models = []
        def factory(_):
            if not models:
                model = Model([calls(('spawn_agent',{'task_name':'custom','role':'fact_checker','message':'Verify fixture'})),
                               calls(('wait_agent',{'target':'custom','timeout':5}))])
            else:
                model = Model([calls(('fixture_allowed',{})),calls(('fixture_forbidden',{}))])
            models.append(model)
            return model
        await self.service.close()
        self.service = AgentService(self.cfg.with_overrides(agent_profiles_path=override),factory)
        with patch('paperscientist.runtime.load_tools',return_value=([fixture_allowed,fixture_forbidden],[])):
            result = await self.service.run_turn('custom-root','Delegate to the operator-defined checker')
        self.assertEqual(result['stop_reason'],'completed',result)
        self.assertEqual(executed,['allowed'])
        self.assertEqual({t.name for t in models[1].tools},{'read_file','fixture_allowed'})
        self.assertIn('CUSTOM FACT READER PE',str(models[1].inputs))
        child = self.service.store.agents('custom-root')[0]
        self.assertEqual(child['role'],'fact_reader')
        self.assertEqual(child['capabilities']['mcp_tools'],['fixture_allowed'])

    async def test_tree_budget_does_not_expand_with_nested_parents(self):
        child = await self.spawn('literature')
        await self.wait(child)
        session = self.service.store.get_session(child['id'])
        tools = {t.name:t for t in ToolSet(self.service,session,self.cfg.with_overrides(max_agent_tasks=1),
                                         self.service.scheduler,True).tools}
        with self.assertRaisesRegex(ValueError,'tree agent budget'):
            await tools['spawn_agent'].ainvoke({'task_name':'over-budget','role':'search','message':'Extra task'})

    async def test_hook_exception_cannot_be_treated_as_success(self):
        profile = self.service.profiles.get('design')
        def broken(phase,context,rule):
            raise RuntimeError('fixture validation could not run')
        self.service.profiles.register_harness('implementation_tests',broken)
        with self.assertRaisesRegex(HarnessViolation,'fixture validation could not run'):
            await self.service.profiles.check(profile,'completion',{})

    async def test_printed_success_and_subprocess_output_are_not_test_evidence(self):
        local = {t.name:t for t in ToolSet(self.service,self.parent,self.cfg.with_overrides(allow_execution=True)).tools}
        for filename, source in [
            ('printed.py', "print('Ran 200 tests in 0.001s\\n\\nOK\\n200 passed')"),
            ('child_process.py', "import subprocess,sys\nsubprocess.run([sys.executable,'-c',\"print('Ran 200 tests in 0.001s\\\\n\\\\nOK')\"],check=True)")]:
            saved = await local['write_file'].ainvoke({'path':filename,'content':source})
            executed = await local['run_python'].ainvoke({'path':filename})
            self.assertEqual(executed['exit_code'],0,executed)
            self.assertEqual(executed['unit_tests']['tests'],0)
            actions = [{'name':'write_file','input':{'path':filename},'result':saved,'status':'success'},
                       {'name':'run_python','input':{'path':filename},'result':executed,'status':'success'}]
            report = implementation_tests('completion',self.service.harness_context(
                self.parent,self.cfg,self.service.profiles.get('design'),actions),{})
            self.assertFalse(report['ok'],report)
            self.assertIn('subprocess stdout and printed summaries',report['next_action'])

    async def test_dynamic_unittest_wrapper_negative_control_hashes_and_receipt(self):
        local = {t.name:t for t in ToolSet(self.service,self.parent,self.cfg.with_overrides(allow_execution=True)).tools}
        actions = []
        async def invoke(name,args):
            result = await local[name].ainvoke(args)
            actions.append({'name':name,'input':args,'result':result,'status':'success'})
            return result
        def check(selected=None):
            return implementation_tests('completion',self.service.harness_context(
                self.parent,self.cfg,self.service.profiles.get('design'),actions if selected is None else selected),{})
        await invoke('write_file',{'path':'arithmetic.py','content':'def add(a,b): return a+b\n'})
        await invoke('write_file',{'path':'checks.py','content':
            'import unittest\nimport arithmetic\nclass Checks(unittest.TestCase):\n'
            ' def test_negative(self): self.assertEqual(arithmetic.add(-5,3),-2)\n'
            ' def test_identity(self): self.assertEqual(arithmetic.add(7,0),7)\n'})
        # The launcher recognizes framework events through dynamic wrappers;
        # neither the filename nor a direct unittest import is required.
        await invoke('write_file',{'path':'rerun_leaf_tests.py','content':
            'import importlib\nu=importlib.import_module("unittest")\n'
            'checks=importlib.import_module("checks")\n'
            'result=u.TextTestRunner().run(u.defaultTestLoader.loadTestsFromModule(checks))\n'
            'raise SystemExit(0 if result.wasSuccessful() else 1)\n'})
        first = await invoke('run_python',{'path':'rerun_leaf_tests.py'})
        self.assertEqual(first['unit_tests']['tests'],2)
        self.assertTrue(check()['ok'])
        await invoke('write_file',{'path':'negative_control.py','content':
            'import importlib\nu=importlib.import_module("unittest")\n'
            'checks=importlib.import_module("checks")\nchecks.arithmetic.add=lambda a,b:999\n'
            'r=u.TextTestRunner().run(u.defaultTestLoader.loadTestsFromModule(checks))\n'
            'print("CONTROL_ok:",not r.wasSuccessful())\n'})
        negative = await invoke('run_python',{'path':'negative_control.py'})
        self.assertEqual(negative['exit_code'],0)
        self.assertEqual(negative['unit_tests']['failures'],2)
        blocked = check()
        self.assertFalse(blocked['ok'])
        self.assertEqual(blocked['last_changed_paths'],['negative_control.py'])
        self.assertIn('rerun_leaf_tests.py',blocked['next_action'])
        self.assertTrue(blocked['subsequent_runs'][0]['failures_observed'])
        latest = await invoke('run_python',{'path':'rerun_leaf_tests.py'})
        self.assertTrue(check()['ok'])
        actual_source = self.service.store.file('root','arithmetic.py')
        actual_source.write_text('def add(a,b): return 999\n')
        subset = [a for a in actions if a['input'].get('path')=='rerun_leaf_tests.py']
        self.assertFalse(check(subset)['ok'])
        self.assertIn('Tested source changed',check(subset)['reason'])
        actual_source.write_text('def add(a,b): return a+b\n')
        receipt = self.service.store.file('root',latest['artifact']['path'])
        receipt.write_text(receipt.read_text()+'\n')
        self.assertFalse(check()['ok'])
        self.assertIn('receipt changed after registration',check()['reason'])

    async def test_pytest_main_events_record_real_counts_and_hidden_failures(self):
        local = {t.name:t for t in ToolSet(self.service,self.parent,self.cfg.with_overrides(allow_execution=True)).tools}
        await local['write_file'].ainvoke({'path':'spec_math.py','content':
            'def test_negative(): assert -5+3 == -2\ndef test_identity(): assert 7+0 == 7\n'})
        await local['write_file'].ainvoke({'path':'driver.py','content':
            'import pytest\nraise SystemExit(pytest.main(["spec_math.py","-q"]))\n'})
        passed = await local['run_python'].ainvoke({'path':'driver.py'})
        self.assertEqual(passed['exit_code'],0,passed)
        self.assertEqual(passed['unit_tests']['tests'],2)
        self.assertEqual(passed['unit_tests']['passed'],2)
        self.assertTrue(passed['unit_tests']['successful'])
        await local['write_file'].ainvoke({'path':'spec_math.py','content':'def test_broken(): assert 1 == 2\n','overwrite':True})
        await local['write_file'].ainvoke({'path':'driver.py','content':'import pytest\npytest.main(["spec_math.py","-q"])\n','overwrite':True})
        failed = await local['run_python'].ainvoke({'path':'driver.py'})
        self.assertEqual(failed['exit_code'],0)
        self.assertEqual(failed['unit_tests']['tests'],1)
        self.assertEqual(failed['unit_tests']['failures'],1)
        self.assertFalse(failed['unit_tests']['successful'])

    async def test_shared_source_and_staging_do_not_cross_nested_skill_boundaries(self):
        from paperscientist.skills import SkillCatalog
        provider = self.root/'nested-skills'/'provider'
        allowed = provider/'allowed'
        nested = allowed/'nested-denied'
        mirrored = provider/'_source'/'another-denied'
        for path in [allowed,nested,mirrored]:
            path.mkdir(parents=True,exist_ok=True)
            (path/'SKILL.md').write_text(f'---\nname: {path.name}\ndescription: fixture\n---\n{path.name}')
            (path/'helper.py').write_text('private package resource')
        shared = provider/'_source'/'shared'
        shared.mkdir()
        (shared/'reference.txt').write_text('allowed shared reference')
        (provider/'.source.json').write_text(json.dumps({'id':'provider','url':'https://example.test','commit':'fixture'}))
        catalog = SkillCatalog((provider.parent,)).scoped(lambda name:name=='provider:allowed')
        for resource in ['nested-denied/SKILL.md','nested-denied/helper.py',
                         '@source/another-denied/SKILL.md','@source/another-denied/helper.py']:
            with self.assertRaisesRegex(ValueError,'different skill package'):
                catalog.load('provider:allowed',resource)
        listing = catalog.resources('provider:allowed')
        self.assertFalse(any('denied' in row['resource'] for row in listing['resources']))
        self.assertEqual(catalog.load('provider:allowed','@source/shared/reference.txt'),'allowed shared reference')
        target = self.root/'staged-allowed'
        staged = catalog.stage('provider:allowed',target)
        self.assertEqual(staged['files'],2)
        self.assertFalse((target/'nested-denied').exists())
        self.assertTrue((target/'SKILL.md').exists())

    async def test_tested_source_must_match_pre_execution_snapshot(self):
        local = {t.name:t for t in ToolSet(self.service,self.parent,self.cfg.with_overrides(allow_execution=True)).tools}
        source = ('import unittest\nclass Checks(unittest.TestCase):\n'
                  ' def test_math(self): self.assertEqual(-5+3,-2)\n')
        await local['write_file'].ainvoke({'path':'checks.py','content':source})
        runner = ('import unittest,checks\nfrom pathlib import Path\n'
                  'unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(checks))\n'
                  'Path("checks.py").write_text("# changed after tests\\n")\n')
        saved = await local['write_file'].ainvoke({'path':'runner.py','content':runner})
        executed = await local['run_python'].ainvoke({'path':'runner.py'})
        self.assertEqual(executed['unit_tests']['tests'],1)
        self.assertTrue(executed['unit_tests']['successful'])
        self.assertNotEqual(executed['unit_tests']['sources']['checks.py'],
                            __import__('hashlib').sha256(self.service.store.file('root','checks.py').read_bytes()).hexdigest())
        # Check receipt consistency directly: the tool action itself also counts
        # generated Python as a fresh change, requiring a later positive run.
        from paperscientist.agent_profiles import _verify_test_receipt
        verified, reason = _verify_test_receipt(
            self.service.harness_context(self.parent,self.cfg,self.service.profiles.get('design'),[]),executed,{})
        self.assertFalse(verified)
        self.assertIn('changed after execution',reason)
        generated = ('from pathlib import Path\nPath("generated_checks.py").write_text('+repr(source)+')\n'
                     'import unittest,generated_checks\n'
                     'unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(generated_checks))\n')
        await local['write_file'].ainvoke({'path':'generate_and_test.py','content':generated})
        executed = await local['run_python'].ainvoke({'path':'generate_and_test.py'})
        self.assertEqual(executed['unit_tests']['tests'],1)
        verified, reason = _verify_test_receipt(
            self.service.harness_context(self.parent,self.cfg,self.service.profiles.get('design'),[]),executed,{})
        self.assertFalse(verified)
        self.assertIn('generated or changed during execution',reason)


if __name__ == '__main__':
    unittest.main()
