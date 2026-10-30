import asyncio
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from paperscientist.config import Settings
from paperscientist.reading import ReadingService, PaperReview
from paperscientist.reading_archive import ReadingArchive, SECTIONS, identities, stamp
from paperscientist.reading_api import mount_reading_api
from paperscientist.tools import ToolSet


TITLE = 'A Primary Paper About Prompt Injection'


def pdf_bytes(pages=1):
    writer = PdfWriter()
    for i in range(pages):
        page = writer.add_blank_page(width=600, height=800)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        content = DecodedStreamObject()
        content.set_data(f'BT /F1 16 Tf 40 700 Td ({TITLE}) Tj 0 -50 Td (Figure {i+1}: results from the primary source.) Tj ET'.encode())
        page[NameObject('/Contents')] = writer._add_object(content)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def review(path, figure):
    return {'title': TITLE, 'pdf_path': path, 'arxiv_id': '2601.12345v2', 'read_version': 'arXiv v2',
            'publication_date': '2026-01-20', 'venue': 'arXiv preprint (test fixture)',
            'sections': {key: ('这里是测试报告的实质章节，描述原文证据、作者结果、实验条件和整理者的分析，引用物理 PDF 第 1 页。' * 2) for key in SECTIONS},
            'figures': [figure], 'evidence_notes': '测试数据与模拟模型仅验证归档流程，未进行真实科研评测，所有截图来自固定测试 PDF 第 1 页，不代表模型的科学理解质量。'}


class ReadingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = Settings(data_dir=self.root / 'service', model='test:model', skill_roots=(), extract_memory=False)
        self.archive = ReadingArchive(self.root / 'vault')
        self.service = ReadingService(self.settings, self.archive)
        self.addAsyncCleanup(self.service.close)
        self.sid = 'a' * 32
        self.session = self.service.store.session(self.sid, project_id='reading-' + self.sid)
        with self.service.store.connect() as db:
            db.execute('INSERT INTO reading_jobs VALUES(?,?,?,?)', (self.sid, 'prompt injection', 1, stamp()))
        self.tools = {t.name: t for t in ToolSet(self.service, self.session, self.service.settings, self.service.scheduler).tools}

    async def prepare(self, pages=1):
        with patch('paperscientist.reading.network.fetch_public', return_value=(pdf_bytes(pages), 'application/pdf', 'https://example.org/original.pdf')):
            source = await self.tools['read_source_pdf'].ainvoke({'url': 'https://example.org/original.pdf', 'max_pages': 1})
        figure = await self.tools['capture_paper_figure'].ainvoke({'pdf_path': source['path'], 'page': 1, 'label': 'Figure 1',
                 'caption': '论文测试图表的中文说明与出处。', 'explanation': '这是来自原文物理第一页的结果截图，仅作为归档功能验证，不代表真实实验。'})
        return source, figure, review(source['path'], figure['id'])

    async def test_full_publication_preserves_index_and_retries_without_duplicates(self):
        self.archive.index_path.parent.mkdir(parents=True)
        old = {'title': 'An older paper', 'status': 'awaiting_graph', 'personal': 'keep me'}
        self.archive.index_path.write_text(json.dumps({'records': [old], 'custom': 'preserved'}))
        source, figure, paper = await self.prepare()
        receipt = await self.tools['publish_reading_report'].ainvoke({'papers': [paper]})
        self.assertEqual(receipt['paper_count'], 1)
        text = self.archive.path(receipt['report_file']).read_text()
        self.assertIn('complete: true', text)
        self.assertIn('Figure 1', text)
        self.assertIn('物理 PDF 第 1 页', text)
        for label in SECTIONS.values():
            self.assertIn('### ' + label, text)
        index = self.archive.index()
        self.assertEqual(index['records'][0], old)
        self.assertEqual(index['custom'], 'preserved')
        self.assertEqual(index['records'][1]['arxiv_id'], '2601.12345')
        self.assertEqual(index['records'][1]['status'], 'awaiting_graph')
        self.assertEqual(await self.tools['publish_reading_report'].ainvoke({'papers': [paper]}), receipt)
        self.assertEqual(len(self.archive.index()['records']), 2)
        self.assertEqual(self.service.store.root, (self.settings.data_dir / 'reading').resolve())
        self.assertTrue(self.service.store.file(self.sid, 'report.md').is_file())
        html = self.archive.preview(receipt['report_file'])
        self.assertIn('/api/reading/file?path=', html)

    async def test_rejects_incomplete_reading_sections_wrong_title_and_tampered_figures(self):
        source, figure, paper = await self.prepare(pages=2)
        with self.assertRaisesRegex(ValueError, '分页读完'):
            await self.tools['publish_reading_report'].ainvoke({'papers': [paper]})
        await self.tools['read_source_pdf'].ainvoke({'path': source['path'], 'start_page': 2})
        with self.assertRaisesRegex(ValueError, '题名'):
            await self.tools['publish_reading_report'].ainvoke({'papers': [paper | {'title': 'An unrelated paper title'}]})
        with self.assertRaisesRegex(ValueError, '章节'):
            await self.tools['publish_reading_report'].ainvoke({'papers': [paper | {'sections': {'abstract': 'too short'}}]})
        self.service.store.file(self.sid, figure['path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, '原图文件'):
            await self.tools['publish_reading_report'].ainvoke({'papers': [paper]})
        self.assertEqual(self.archive.index()['records'], [])

    async def test_canonical_ids_aliases_and_pending_graph_are_duplicates(self):
        self.assertTrue(identities({'arxiv_id': 'https://arxiv.org/abs/2601.12345v2'}) & identities({'arxiv_id': '2601.12345'}))
        self.assertTrue(identities({'doi': 'https://doi.org/10.1000/ABC'}) & identities({'doi': 'doi:10.1000/abc'}))
        self.assertTrue(identities({'title': 'A: Primary-Paper'}) & identities({'title': 'different', 'aliases': ['A Primary Paper']}))
        source, figure, paper = await self.prepare()
        self.archive.index_path.parent.mkdir(parents=True)
        self.archive.index_path.write_text(json.dumps({'records': [{'title': 'Conference version', 'arxiv_id': '2601.12345', 'status': 'awaiting_graph'}]}))
        matches = await self.tools['check_reading_archive'].ainvoke({'candidates': [paper]})
        self.assertEqual(matches['matches'][0]['duplicates'], ['Conference version'])
        with self.assertRaisesRegex(ValueError, '已归档'):
            await self.tools['publish_reading_report'].ainvoke({'papers': [paper]})
        self.assertEqual(len(self.archive.index()['records']), 1)

    async def test_resume_publication_after_crash_before_index_commit(self):
        _, _, paper = await self.prepare()
        real = self.archive.commit_receipt
        with patch.object(self.archive, 'commit_receipt', side_effect=OSError('simulated crash')):
            with self.assertRaises(OSError):
                await self.tools['publish_reading_report'].ainvoke({'papers': [paper]})
        self.assertTrue(self.archive.receipt(self.sid).exists())
        self.assertEqual(len(self.archive.index()['records']), 0)
        receipt = await self.tools['publish_reading_report'].ainvoke({'papers': [paper]})
        self.assertEqual(real(receipt)['files'], receipt['files'])
        self.assertEqual(len(self.archive.index()['records']), 1)

    async def test_profile_isolation_in_binding_and_durable_dispatch(self):
        self.assertNotIn('run_python', self.tools)
        self.assertNotIn('write_file', self.tools)
        self.assertNotIn('spawn_agent', self.tools)
        self.assertNotIn('compile_latex', self.tools)
        self.assertEqual(self.service.profiles.get().name, 'paper_reader')
        calls = iter([
            AIMessage(content='', tool_calls=[{'name': 'write_file', 'args': {'path': 'forbidden.txt', 'content': 'bad'}, 'id': 'bad', 'type': 'tool_call'}]),
            AIMessage(content='', tool_calls=[{'name': 'finish_research', 'args': {'summary': 'fake success', 'artifacts': [], 'limitations': []}, 'id': 'fake', 'type': 'tool_call'}]),
            AIMessage(content='Blocked'), AIMessage(content='Blocked'),
        ])
        class Model:
            def bind_tools(self, tools):
                return self
            async def ainvoke(self, messages):
                return next(calls)
        self.service.model_factory = lambda _: Model()
        run = await self.service.runs.start(self.sid, 'Try forbidden tools', project_id='reading-' + self.sid)
        await asyncio.wait_for(self.service.runs.tasks[run['id']], 15)
        self.assertFalse(self.service.store.file(self.sid, 'forbidden.txt').exists())
        self.assertNotEqual(self.service.runs.require(run['id'])['status'], 'completed')
        results = [e['data'] for e in self.service.store.events(self.sid) if e['kind'] == 'tool_result']
        self.assertEqual(results[0]['status'], 'error')
        self.assertIn('reading_archive', str(results[1]))

    async def test_api_preview_paths_and_xss_are_bounded(self):
        # Malicious source text is displayed as text; local escaping links are never served.
        folder = self.archive.root / '01-报告'
        folder.mkdir(parents=True)
        note = folder / 'malicious.md'
        note.write_text('# Test\n<script>alert(1)</script>\n![secret](../../../secret.png)\n[bad](javascript:alert(1))')
        app = FastAPI()
        mount_reading_api(app, self.service)
        with TestClient(app) as client:
            self.assertEqual(client.get('/reading').status_code, 200)
            self.assertEqual(client.get('/reading-assets/reading.js').status_code, 200)
            self.assertEqual(client.get('/api/reading/file', params={'path': '../secret.png'}).status_code, 404)
            self.assertEqual(client.get('/api/reading/file', params={'path': 'AI安全/系统/collection-index.json'}).status_code, 404)
            html = client.get('/api/reading/report', params={'path': self.archive.rel(note)}).json()['html']
            self.assertNotIn('<script>', html)
            self.assertNotIn('src="../../../', html)
            self.assertNotIn('href="javascript:', html)
            self.assertEqual(client.post('/api/reading/jobs', json={'keywords': 'test'}, headers={'Origin': 'https://evil.example'}).status_code, 403)
            self.assertEqual(client.post('/api/reading/jobs', json={'keywords': 'x'}).status_code, 422)
            self.assertEqual(client.get('/api/reading/jobs/not-a-reading-run').status_code, 404)
        outside = self.root / 'secret.pdf'
        outside.write_bytes(b'private')
        (folder / 'escape.pdf').symlink_to(outside)
        with self.assertRaises(ValueError):
            self.archive.public_file(self.archive.rel(folder) + '/escape.pdf')

    async def test_missing_or_corrupt_index_blocks_new_tasks_and_demo_is_not_success(self):
        folder = self.archive.root / '01-报告'
        folder.mkdir(parents=True)
        (folder / 'old.md').write_text('old report')
        with self.assertRaisesRegex(ValueError, '缺少累计索引'):
            await self.service.start_reading('memory poisoning')
        self.archive.index_path.parent.mkdir(parents=True)
        self.archive.index_path.write_text('{broken')
        with self.assertRaises(ValueError):
            await self.service.start_reading('memory poisoning')
        self.service.settings = self.service.settings.with_overrides(model='demo')
        with self.assertRaisesRegex(ValueError, '演示模式'):
            await self.service.start_reading('memory poisoning')

    async def test_bounded_pdf_pagination_does_not_mark_unseen_text_read(self):
        from unittest.mock import MagicMock
        reader = MagicMock()
        reader.pages = [MagicMock(), MagicMock()]
        reader.pages[0].extract_text.return_value = TITLE + 'A' * 10000
        reader.pages[1].extract_text.return_value = 'Second page text'
        with patch('paperscientist.reading.network.fetch_public', return_value=(pdf_bytes(2), 'application/pdf', 'https://example.org/long.pdf')), patch('pypdf.PdfReader', return_value=reader):
            first = await self.tools['read_source_pdf'].ainvoke({'url': 'https://example.org/long.pdf'})
            self.assertLess(len(json.dumps(first)), 12000)
            self.assertEqual(first['remaining_pages'], [1, 2])
            second = await self.tools['read_source_pdf'].ainvoke(first['next_read'])
            self.assertEqual(second['remaining_pages'], [])
            self.assertIsNone(second['next_read'])

    async def test_existing_collector_lock_blocks_publication_and_retry_succeeds(self):
        _, _, paper = await self.prepare()
        with self.archive.locked():
            with self.assertRaises(OSError):
                await self.tools['publish_reading_report'].ainvoke({'papers': [paper]})
        result = await self.tools['publish_reading_report'].ainvoke({'papers': [paper]})
        self.assertEqual(result['paper_count'], 1)

    async def test_app_keeps_reader_and_manuscript_sessions_separate(self):
        from paperscientist.api import create_app
        from paperscientist.runtime import AgentService
        main = AgentService(self.settings.with_overrides(model='demo'))
        self.addAsyncCleanup(main.close)
        app = create_app(service=main, with_ui=False)
        reader = app.state.reading_service
        self.addAsyncCleanup(reader.close)
        self.assertNotEqual(main.store.root, reader.store.root)
        self.assertEqual(main.profiles.get().name, 'orchestrator')
        self.assertEqual(reader.profiles.get().name, 'paper_reader')
        self.assertEqual(main.store.sessions(), [])
        self.assertFalse(reader.profiles.get().children)

    async def test_saved_draft_survives_restart_and_completes_through_durable_harness(self):
        _, _, paper = await self.prepare()
        await self.tools['save_paper_review'].ainvoke({'paper': paper})
        await self.service.close()
        calls = iter([
            AIMessage(content='', tool_calls=[{'name': 'publish_reading_report', 'args': {}, 'id': 'publish', 'type': 'tool_call'}]),
            AIMessage(content='', tool_calls=[{'name': 'finish_research', 'args': {'summary': 'Archived', 'artifacts': ['report.md'], 'limitations': ['synthetic fixture']}, 'id': 'finish', 'type': 'tool_call'}]),
        ])
        class Model:
            def bind_tools(self, tools):
                return self
            async def ainvoke(self, messages):
                return next(calls)
        resumed = ReadingService(self.settings, self.archive, model_factory=lambda _: Model())
        self.addAsyncCleanup(resumed.close)
        run = await resumed.runs.start(self.sid, 'Finish saved reading', project_id='reading-' + self.sid)
        await asyncio.wait_for(resumed.runs.tasks[run['id']], 15)
        self.assertEqual(resumed.runs.require(run['id'])['status'], 'completed')
        self.assertEqual(resumed.profiles.get().name, 'paper_reader')
        self.assertEqual(self.archive.verify(self.sid)['paper_count'], 1)
        import re
        from urllib.parse import unquote
        report = resumed.store.file(self.sid, 'report.md')
        for link in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', report.read_text()):
            if not link.startswith('http'):
                self.assertTrue((report.parent / unquote(link)).is_file(), link)


if __name__ == '__main__':
    unittest.main()
