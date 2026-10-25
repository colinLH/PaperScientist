import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from langchain_core.messages import AIMessage
from paperscientist.config import Settings
from paperscientist.runtime import AgentService


def call(name, args, ident):
    return {'name': name, 'args': args, 'id': ident, 'type': 'tool_call'}


class Model:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.bound = set()

    def bind_tools(self, tools):
        self.bound = {t.name for t in tools}
        return self

    async def ainvoke(self, messages):
        return next(self.responses)


class DurableHarnesses(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cfg = Settings(data_dir=Path(self.temp.name), model='test:model', extract_memory=False, skill_roots=())

    def service(self, model, hook=None):
        service = AgentService(self.cfg, model_factory=lambda _: model)
        self.addAsyncCleanup(service.close)
        if hook:
            service.profiles.register_harness('test_hook', hook)
            base = service.profiles.get()
            service.profiles.profiles['orchestrator'] = replace(base, harnesses=({'name': 'test_hook'},))
        return service

    async def done(self, service, rid):
        await asyncio.wait_for(service.runs.tasks[rid], 15)
        return service.runs.db.get(rid)

    async def test_custom_precheck_prevents_effect_and_aftercheck_runs(self):
        phases = []
        def hook(phase, context, rule):
            phases.append((phase, context.get('tool_name')))
            return {'ok': not (phase == 'before_tool' and context.get('tool_name') == 'write_file'), 'reason': 'denied write'}
        model = Model([AIMessage(content='', tool_calls=[call('write_file', {'path':'bad.txt','content':'x'}, 'w')]),
                       AIMessage(content='', tool_calls=[call('list_files', {}, 'l')]),
                       AIMessage(content='', tool_calls=[call('finish_research', {'summary':'checked','artifacts':[],'limitations':[]}, 'f')])])
        service = self.service(model, hook)
        run = await service.runs.start('s', 'Check denied write')
        self.assertEqual((await self.done(service, run['id']))['status'], 'completed')
        self.assertFalse(service.store.file('s', 'bad.txt').exists())
        self.assertIn(('after_tool', 'list_files'), phases)
        self.assertIn(('completion', None), phases)

    async def test_receipt_actions_survive_interrupt_restart(self):
        def hook(phase, context, rule):
            if phase == 'completion':
                return {'ok': any(a['name']=='write_file' and a['status']=='success'
                                  and a['input']['path']=='evidence.txt' for a in context['actions']),
                        'reason': 'durable evidence missing'}
            return {'ok': True}
        first = self.service(Model([AIMessage(content='', tool_calls=[
            call('write_file', {'path':'evidence.txt','content':'saved'}, 'w'),
            call('ask_user_question', {'question':'Continue?','options':['Yes']}, 'q')])]), hook)
        run = await first.runs.start('s', 'Persist hook evidence')
        self.assertEqual((await self.done(first, run['id']))['status'], 'waiting_input')
        await first.close()
        second = self.service(Model([AIMessage(content='', tool_calls=[
            call('finish_research', {'summary':'verified','artifacts':['evidence.txt'],'limitations':[]}, 'f')])]), hook)
        await second.runs.answer(run['id'], 'q', 'Yes')
        result = await self.done(second, run['id'])
        self.assertEqual(result['status'], 'completed', result)

    async def test_disallowed_special_and_native_calls_cannot_bypass_binding(self):
        model = Model([AIMessage(content='', tool_calls=[
            call('write_file', {'path':'bad.txt','content':'x'}, 'w'),
            call('ask_user_question', {'question':'Should not pause'}, 'q'),
            call('finish_research', {'summary':'not allowed','artifacts':[],'limitations':[]}, 'f')]),
            AIMessage(content='Allowed text response')])
        service = self.service(model)
        service.profiles.profiles['orchestrator'] = replace(service.profiles.get(), tools=frozenset({'list_files'}))
        run = await service.runs.start('s', 'Read-only request', continuous=False)
        result = await self.done(service, run['id'])
        self.assertEqual(result['status'], 'completed', result)
        self.assertEqual(model.bound, {'list_files'})
        self.assertFalse(service.store.file('s', 'bad.txt').exists())
        self.assertIsNone(result['pending'])

    async def test_unknown_hook_blocks_plain_completion(self):
        service = self.service(Model([AIMessage(content='Cannot certify completion')]))
        service.profiles.profiles['orchestrator'] = replace(service.profiles.get(),
            harnesses=({'name': 'missing_hook', 'phases': ['completion']},))
        run = await service.runs.start('s', 'Check missing extension', continuous=False)
        result = await self.done(service, run['id'])
        self.assertEqual(result['status'], 'paused', result)
        self.assertEqual(result['outcome']['reason'], 'harness')


if __name__ == '__main__':
    unittest.main()
