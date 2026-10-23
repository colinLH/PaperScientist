import asyncio
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

import httpx
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

from paperscientist.api import create_app
from paperscientist.config import Settings
from paperscientist.runtime import AgentService
from paperscientist.timeline import markdown
from paperscientist.timeline_api import pdf_page, preview


class TimelineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        cfg = Settings(data_dir=Path(self.temp.name), model='test:model', skill_roots=(), extract_memory=False)
        self.service = AgentService(cfg)
        self.addAsyncCleanup(self.service.close)
        self.store = self.service.store
        self.store.session('s')

    def turn(self, question='test'):
        run = self.service.runs.db.create('s', question, {})
        self.service.timeline.begin('s', run['id'], question)
        self.service.runs.db.commit(run['id'], 'input', {}, [HumanMessage(content=question)])
        self.service.versions.begin('s', run['id'])
        return run['id']

    async def test_event_wakeup_is_after_commit_thread_safe_and_unsubscribes(self):
        timeline = self.service.timeline
        calls = []
        # The callback must be able to read the committed row immediately.
        unsubscribe = timeline.subscribe('s', lambda: calls.append(timeline.after('s', 0)[-1]['kind']))
        other_calls = []
        other = timeline.subscribe('other', lambda: other_calls.append(True))
        tid = self.turn()
        self.assertEqual(calls, ['turn'])
        await asyncio.to_thread(timeline.emit, 's', tid, 'note', {'text': 'thread notification'})
        self.assertEqual(calls, ['turn', 'note'])
        self.assertEqual(other_calls, [])
        unsubscribe(); unsubscribe(); other()
        timeline.emit('s', tid, 'note', {'text': 'still durable'})
        self.assertEqual(calls, ['turn', 'note'])
        self.assertEqual(timeline.after('s', 0)[-1]['data']['text'], 'still durable')
        self.assertEqual(timeline._listeners, {})

    async def test_idle_sse_waits_and_new_commits_wake_without_poll_delay(self):
        tid = self.turn()
        timeline = self.service.timeline
        cursor = timeline.after('s', 0)[-1]['id']
        app = create_app(service=self.service, with_ui=False)
        endpoint = next(r.endpoint for r in app.routes if getattr(r, 'path', '') == '/api/sessions/{sid}/events')
        async def disconnected():
            return False
        response = await endpoint('s', SimpleNamespace(headers={}, is_disconnected=disconnected), cursor)
        stream = response.body_iterator
        self.assertIn('retry:', await anext(stream))
        with patch.object(timeline, 'after', wraps=timeline.after) as reads:
            waiting = asyncio.create_task(anext(stream))
            try:
                await asyncio.sleep(.2)
                self.assertEqual(reads.call_count, 1)
                self.assertFalse(waiting.done())
                await asyncio.to_thread(timeline.emit, 's', tid, 'note', {'text': 'wake immediately'})
                event = await asyncio.wait_for(waiting, .75)
                self.assertIn('wake immediately', event)
            finally:
                waiting.cancel()
                await asyncio.gather(waiting, return_exceptions=True)
                await stream.aclose()
        self.assertEqual(timeline._listeners, {})

    async def test_history_avoids_loading_tool_bodies_but_keeps_detail(self):
        self.store.append('s', HumanMessage(content='large result'))
        self.store.append('s', AIMessage(content='', tool_calls=[{'id':'large','name':'read_file','args':{},'type':'tool_call'}]))
        self.store.append('s', ToolMessage(content='large body ' * 100000, artifact={'binary': 'x' * 100000}, tool_call_id='large'))
        from paperscientist.timeline import messages_from_dict as decode
        decoded = []
        def record(rows):
            decoded.extend(rows)
            return decode(rows)
        with patch('paperscientist.timeline.messages_from_dict', side_effect=record):
            result = self.service.timeline.snapshot('s')
        tool = next(row for row in decoded if row['type'] == 'tool')
        self.assertEqual(tool['data']['content'], '')
        self.assertNotIn('artifact', tool['data'])
        call = result['turns'][0]['items'][0]
        self.assertEqual(call['status'], 'success')
        app = create_app(service=self.service, with_ui=False)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
            response = await client.get('/api/sessions/s/tool-detail', params={'message_id':call['detail_message_id']})
        self.assertTrue(response.json()['text'].startswith('large body'))

    async def test_incremental_events_precede_model_completion_and_survive_restart(self):
        first = asyncio.Event()
        proceed = asyncio.Event()
        class Streaming:
            def bind_tools(self, _):
                return self
            async def astream(self, _):
                yield AIMessageChunk(content='第一段', additional_kwargs={'reasoning_content': 'PRIVATE'})
                await asyncio.sleep(.08)
                yield AIMessageChunk(content='，正在继续')
                first.set()
                await proceed.wait()
                yield AIMessageChunk(content='。完整回复。', response_metadata={'finish_reason': 'stop'})
        self.service.model_factory = lambda _: Streaming()
        run = await self.service.runs.start('s', '检查流式', continuous=False)
        await asyncio.wait_for(first.wait(), 5)
        snap = self.service.timeline.snapshot('s')
        text = snap['turns'][0]['items'][0]['text']
        self.assertEqual(text, '第一段，正在继续')
        self.assertFalse(self.service.runs.tasks[run['id']].done())
        self.assertNotIn('PRIVATE', json.dumps(snap))
        cursor = snap['cursor']
        proceed.set()
        await asyncio.wait_for(self.service.runs.tasks[run['id']], 5)
        events = self.service.timeline.after('s', cursor)
        self.assertTrue(any(e['kind'] == 'assistant_commit' for e in events))
        final = self.service.timeline.snapshot('s')
        self.assertEqual(final['turns'][0]['items'][0]['text'], '第一段，正在继续。完整回复。')
        other = AgentService(self.service.settings)
        self.addAsyncCleanup(other.close)
        self.assertEqual(other.timeline.snapshot('s'), final)

    async def test_incomplete_generation_is_replaced_without_executing_tools(self):
        class Model:
            attempts = 0
            def bind_tools(self, _): return self
            async def astream(self, _):
                self.attempts += 1
                yield AIMessageChunk(content='错误残片' if self.attempts == 1 else '完整答案', response_metadata={'finish_reason': 'length' if self.attempts == 1 else 'stop'})
        self.service.model_factory = lambda _: Model()
        r = await self.service.runs.start('s', 'retry', continuous=False)
        await self.service.runs.tasks[r['id']]
        items = [i for i in self.service.timeline.snapshot('s')['turns'][0]['items'] if i['type'] == 'assistant']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['text'], '完整答案')
        self.assertTrue(any(e['kind'] == 'assistant_discard' for e in self.service.timeline.after('s', 0)))

    async def test_history_preserves_last_message_and_tool_results(self):
        self.store.append('s', HumanMessage(content='历史问题'))
        self.store.append('s', AIMessage(content='先检查', tool_calls=[{'id':'c1','name':'read_file','args':{'path':'a.md'},'type':'tool_call'}]))
        self.store.append('s', ToolMessage(content='result', tool_call_id='c1', name='read_file'))
        self.store.append('s', AIMessage(content='历史完整答案'))
        tid = self.turn('下一轮')
        self.service.timeline.emit('s', tid, 'assistant_commit', {'id':'a','text':'新答案'})
        self.service.timeline.end('s', tid)
        turns = self.service.timeline.snapshot('s')['turns']
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]['items'][-1]['text'], '历史完整答案')
        self.assertEqual(turns[0]['items'][1]['status'], 'success')
        self.assertEqual(turns[1]['question'], '下一轮')

    async def test_diff_undo_preserves_later_edits_and_all_files_prechecked(self):
        a = self.store.file('s', 'a.txt'); a.write_text('before\n')
        tid = self.turn()
        a.write_text('after\n')
        b = self.store.file('s', 'b.txt'); b.write_text('new\n')
        self.service.versions.finish('s', tid)
        self.assertIn('+after', self.service.versions.diff('s', tid, 'a.txt')['diff'])
        b.write_text('later edit')
        with self.assertRaises(ValueError): self.service.versions.undo('s', tid)
        self.assertEqual(a.read_text(), 'after\n')
        b.write_text('new\n')
        self.service.versions.undo('s', tid)
        self.assertEqual(a.read_text(), 'before\n')
        self.assertFalse(b.exists())
        self.assertTrue(all(c['undone'] for c in self.service.versions.get('s', tid)['changes']))

    async def test_preview_versions_and_cross_session_guards(self):
        tid = self.turn()
        p = self.store.file('s', 'result.csv'); p.write_text('x,y\n1,2\n', encoding='utf-8')
        self.service.versions.finish('s', tid)
        self.service.runs.db.update(tid, status='completed')
        p.write_text('later')
        app = create_app(service=self.service, with_ui=False)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
            r = await client.get('/api/sessions/s/file-preview', params={'path':'result.csv','turn':tid})
            self.assertEqual(r.json()['rows'], [['x','y'],['1','2']])
            r = await client.get('/api/sessions/s/file-content', params={'path':'../../secret','turn':tid})
            self.assertEqual(r.status_code, 404)
            self.store.session('other')
            r = await client.get('/api/sessions/other/file-diff', params={'path':'result.csv','turn':tid})
            self.assertEqual(r.status_code, 409)
            r = await client.post('/api/sessions/s/undo', json={'turn_id':tid})
            self.assertEqual(r.status_code, 409)
            self.assertEqual(p.read_text(), 'later')

    async def test_interrupted_undo_reconciles_without_overwriting_later_edits(self):
        a = self.store.file('s', 'a.txt'); a.write_text('before')
        b = self.store.file('s', 'b.txt'); b.write_text('before')
        tid = self.turn()
        a.write_text('after'); b.write_text('after')
        self.service.versions.finish('s', tid)
        with self.store.connect() as db:
            db.execute('INSERT INTO file_undo_ops VALUES(?,?,?,?,?)', ('crashed', 's', tid, '["a.txt","b.txt"]', 'pending'))
        a.write_text('before')  # Simulate an exit between restore and its DB acknowledgement.
        b.write_text('later user edit')
        from paperscientist.file_versions import FileVersions
        restored = FileVersions(self.store)
        changes = {c['path']:c for c in restored.get('s', tid)['changes']}
        self.assertTrue(changes['a.txt']['undone'])
        self.assertFalse(changes['b.txt']['undone'])
        self.assertEqual(b.read_text(), 'later user edit')

    async def test_transcript_and_presentation_commit_are_idempotent_together(self):
        tid = self.turn()
        args = (tid, 'node', {'ok': True}, [AIMessage(content='canonical')])
        presentation = [('assistant_commit', {'id':'answer','text':'canonical'})]
        self.service.runs.db.commit(*args, presentation=presentation)
        self.service.runs.db.commit(*args, presentation=presentation)
        self.assertEqual(len(self.store.history('s')), 2)
        self.assertEqual(sum(e['kind']=='assistant_commit' for e in self.service.timeline.after('s', 0)), 1)

    async def test_sse_cursor_replay_and_event_framing(self):
        tid = self.turn()
        cursor = self.service.timeline.emit('s', tid, 'assistant_start', {'id':'a'})
        self.service.timeline.emit('s', tid, 'assistant_delta', {'id':'a','text':'hello\nworld'})
        app = create_app(service=self.service, with_ui=False)
        endpoint = next(r.endpoint for r in app.routes if r.path == '/api/sessions/{sid}/events')
        class Request:
            headers = {'last-event-id': str(cursor)}
            calls = 0
            async def is_disconnected(self):
                self.calls += 1
                return self.calls > 1
        response = await endpoint('s', Request(), after=0)
        chunks = [c async for c in response.body_iterator]
        self.assertEqual(response.media_type, 'text/event-stream')
        self.assertEqual(len(chunks), 2)
        self.assertIn('event: timeline\n', chunks[1])
        row = json.loads(chunks[1].split('data: ')[1])
        self.assertEqual(row['kind'], 'assistant_delta')
        self.assertGreater(row['id'], cursor)

    async def test_markdown_sanitization_and_pdf_preview(self):
        self.store.file('s', 'a.md').write_text('hello')
        rendered = markdown('<script>alert(1)</script>\n\n[x](javascript:alert(1)) ![image](https://example.com/a.png) [file](a.md)', self.store, 's')
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('<img', rendered)
        self.assertNotIn('href="javascript:', rendered)
        self.assertIn('data-file="a.md"', rendered)
        from pypdf import PdfWriter
        import io
        buffer = io.BytesIO(); writer = PdfWriter(); writer.add_blank_page(width=300,height=300); writer.write(buffer)
        self.assertEqual(preview(buffer.getvalue(), 'a.pdf', self.store, 's')['pages'], 1)
        self.assertTrue(pdf_page(buffer.getvalue(), 0).startswith(b'\x89PNG'))


if __name__ == '__main__':
    unittest.main()
