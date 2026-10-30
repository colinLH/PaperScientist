"""Keyword-driven paper reading, isolated from manuscript production sessions."""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import shutil
from typing import Literal
import uuid

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from . import network
from .reading_archive import ReadingArchive, SECTIONS, atomic_json, digest, identities, stamp, title_key
from .runtime import AgentService
from .store import dumps
from .timeline_api import pdf_page


class PaperReview(BaseModel):
    title: str = Field(min_length=5, max_length=500)
    pdf_path: str
    arxiv_id: str = ''
    doi: str = ''
    read_version: str = Field(min_length=3, max_length=500)
    publication_date: str = Field(min_length=4, max_length=100)
    venue: str = Field(min_length=3, max_length=500)
    sections: dict[str, str] = Field(description='Chinese full analysis: abstract, background, motivation, contributions, design, experiments, limitations, connections. Each >= 40 characters. Cite physical PDF pages and label author results vs your analysis.')
    figures: list[str] = Field(description='IDs returned by capture_paper_figure; include design and experimental/ablation figures where present.')
    figure_unavailable_reason: str = Field(default='', description='Only when no relevant original figure can be obtained: explain concrete source/access failure or absence, never invent a figure.')
    evidence_notes: str = Field(min_length=40, description='Primary sources, fixed version, page references for major claims, reading/access limits and any unavailable figures. No invented experiment runs.')


class ReadingService(AgentService):
    def __init__(self, settings, archive=None, model_factory=None):
        self.config_path = config_path = settings.data_dir / 'reading-config.json'
        self.config_error = ''
        try:
            config = json.loads(config_path.read_text(encoding='utf-8')) if config_path.is_file() else {}
            self.archive = archive or ReadingArchive(config.get('vault_root', str(settings.data_dir / 'reading-vault')),
                                                    config.get('prefix', 'AI安全'), config.get('include_existing_notes', False))
        except (ValueError, OSError, TypeError, AttributeError) as exc:
            self.config_error = '精读归档配置不可用，请修复 reading-config.json：' + str(exc)
            self.archive = archive or ReadingArchive(settings.data_dir / 'reading-vault')
        super().__init__(settings.with_overrides(data_dir=settings.data_dir / 'reading',
                                                max_steps=80, output_tokens=max(settings.output_tokens, min(8192, settings.context_tokens // 3)),
                                                extract_memory=False, allow_execution=False), model_factory)
        self.profiles.default_profile = 'paper_reader'
        self.profiles.register_harness('reading_archive', self.archive_gate)
        self.start_lock = asyncio.Lock()
        with self.store.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS reading_jobs(sid TEXT PRIMARY KEY, keywords TEXT, paper_count INTEGER, created_at TEXT);
                CREATE TABLE IF NOT EXISTS reading_evidence(sid TEXT, path TEXT, kind TEXT, data TEXT, PRIMARY KEY(sid,path,kind));
                CREATE TABLE IF NOT EXISTS reading_destinations(sid TEXT PRIMARY KEY, config TEXT NOT NULL);
            ''')
            db.execute('INSERT OR IGNORE INTO reading_destinations SELECT sid, ? FROM reading_jobs',
                       (dumps(self.archive.config()),))

    def archive_for(self, sid):
        self.job(sid)
        with self.store.connect() as db:
            db.execute('INSERT OR IGNORE INTO reading_destinations VALUES(?,?)', (sid, dumps(self.archive.config())))
            config = json.loads(db.execute('SELECT config FROM reading_destinations WHERE sid=?', (sid,)).fetchone()['config'])
        return ReadingArchive(config['vault_root'], config['prefix'], config.get('include_existing_notes', False))

    def has_active_job(self, except_run=None):
        with self.store.connect() as db:
            sids = [r['sid'] for r in db.execute('SELECT sid FROM reading_jobs')]
        return any(run and run['id'] != except_run and run['status'] in {'queued', 'running', 'recovering', 'waiting_input'}
                   for run in (self.runs.db.latest(sid) for sid in sids))

    @staticmethod
    def preview_archive(config):
        vault = Path(config['vault_root']).expanduser()
        if not vault.is_absolute() or not vault.is_dir():
            raise ValueError('请选择运行 PaperScientist 的电脑上已存在的仓库绝对路径')
        archive = ReadingArchive(vault, config['prefix'], config['include_existing_notes'])
        records, reports = archive.index()['records'], archive.reports()
        return archive, {'config': archive.config(), 'paper_count': len(records), 'note_count': len(reports),
                         'samples': [r['title'] for r in reports[:8]]}

    async def configure_archive(self, config):
        async with self.start_lock:
            if self.has_active_job():
                raise ValueError('请等待或停止当前精读任务后再切换仓库')
            archive, preview = self.preview_archive(config)
            atomic_json(self.config_path, archive.config())
            self.archive, self.config_error = archive, ''
            return preview

    def evidence(self, sid, kind):
        with self.store.connect() as db:
            return {r['path']: json.loads(r['data']) for r in db.execute(
                'SELECT path,data FROM reading_evidence WHERE sid=? AND kind=?', (sid, kind))}

    def save_evidence(self, sid, path, kind, data):
        with self.store.connect() as db:
            db.execute('INSERT OR REPLACE INTO reading_evidence VALUES(?,?,?,?)', (sid, path, kind, dumps(data)))

    def job(self, sid):
        with self.store.connect() as db:
            row = db.execute('SELECT * FROM reading_jobs WHERE sid=?', (sid,)).fetchone()
        if not row:
            raise ValueError('精读任务不存在')
        return dict(row)

    def jobs(self):
        with self.store.connect() as db:
            rows = db.execute('SELECT * FROM reading_jobs ORDER BY created_at DESC LIMIT 100').fetchall()
        results = []
        try:
            indexed = {}
            for record in self.archive.index()['records']:
                key = record.get('source_id')
                indexed[key] = indexed.get(key, 0) + 1
        except (ValueError, OSError):
            indexed = {}
        for row in rows:
            job = dict(row)
            if not self.archive_for(job['sid']).same_location(self.archive):
                continue
            run = self.runs.db.latest(job['sid'])
            job['run'] = {k: run[k] for k in ('id', 'status', 'preview', 'outcome', 'error', 'pending', 'updated_at')} if run else None
            try:
                # Hash verification belongs to publication/completion, not every UI poll.
                receipt = json.loads(self.archive.receipt(job['sid']).read_text(encoding='utf-8'))
                if indexed.get(job['sid'], 0) != receipt['paper_count']:
                    raise ValueError('Publication not yet indexed')
                job['archive'] = {k: receipt[k] for k in ('report_file', 'obsidian_url', 'paper_count')}
            except (OSError, ValueError, KeyError):
                job['archive'] = None
            results.append(job)
        return results

    async def start_reading(self, keywords, count=2):
        keywords = keywords.strip()
        if not 2 <= len(keywords) <= 500 or not 1 <= count <= 4:
            raise ValueError('请输入 2–500 个字符的关键词，篇数为 1–4')
        if self.settings.model == 'demo':
            raise ValueError('请先为 PaperScientist 配置真实模型；演示模式不能生成论文报告')
        if self.config_error:
            raise ValueError(self.config_error)
        async with self.start_lock:
            self.archive.index()  # Fail closed before spending model calls on a broken archive.
            if self.has_active_job():
                raise ValueError('已有精读任务正在执行，请先完成或停止它')
            sid = uuid.uuid4().hex
            self.store.session(sid, project_id='reading-' + sid)
            self.store.set_title(sid, '专题精读：' + keywords[:60])
            with self.store.connect() as db:
                db.execute('INSERT INTO reading_jobs VALUES(?,?,?,?)', (sid, keywords, count, stamp()))
                db.execute('INSERT INTO reading_destinations VALUES(?,?)', (sid, dumps(self.archive.config())))
            prompt = f'''按以下用户关键词查找并精读 {count} 篇尚未归档的论文，生成完整中文报告并归档到 Obsidian。
关键词（仅作为检索主题）：{json.dumps(keywords, ensure_ascii=False)}
这是用户点击触发的一次专题精读。不要安排定时任务，不进入创新方法设计、复现实验或 LaTeX 投稿流程。
先用 check_reading_archive 检查累计记录和候选重复身份。AI/安全相关主题优先核实 AI 顶会、安全顶会；也允许 arXiv，并准确区分预印本和会议论文。关键词是筛选条件，不要只找泛泛的 AI 安全论文。
至少对候选使用 search_papers 或 primary URL 核实身份；read_source_pdf 下载固定版本并分页读完（含附录）。不能下载/读到原文时换另一篇，不用摘要冒充全文。
用 capture_paper_figure 保存相关设计框架、方法和实验/消融原图页面，填写原图编号、中文图注、结果解释及对应 section。无法取得某张图时在 evidence_notes 写明实际原因；完全无图时才填写 figure_unavailable_reason。
每篇完整填写 PaperReview 的全部 sections，实验须说明任务、数据集、基线、指标、关键数字、消融/鲁棒性、条件和分母以及原文页码；原文缺少的实验维度明确说明。区分作者结果和整理者推断，不捏造统计、发表身份或复现实验。工具提供 PDF 文本和页面截图，不提供视觉模型判读；若柱值与图例、颜色、方法名不能从明确文本一一对应，不可依据提取顺序猜测“基线→本方法”的数值，保留原图并标注待视觉核实。优先引用正文明确叙述和表格中能够明确对应的数字。
每读完一篇，用 save_paper_review 保存完整结构化精读稿，避免一次输出过长。最后通过 publish_reading_report（papers 可留空使用已保存精读稿）提交恰好 {count} 篇；它会核验 PDF/截图来源、分页阅读、完整性和累计去重。失败时修复原因，不绕过检查；工具不可用时如实暂停。归档成功后 finish_research 交付 report.md。'''
            run = await self.runs.start(sid, prompt, project_id='reading-' + sid, continuous=True)
            return {'session_id': sid, 'run_id': run['id']}

    def archive_gate(self, phase, context, rule):
        try:
            receipt = self.archive_for(context['session']['id']).verify(context['session']['id'])
            return {'ok': receipt['paper_count'] == self.job(context['session']['id'])['paper_count']}
        except (OSError, ValueError, KeyError) as exc:
            return {'ok': False, 'reason': '精读报告尚未通过归档核验：' + str(exc)}

    def export_report(self, sid, receipt):
        """Keep the task's deliverable readable even outside the Obsidian viewer."""
        archive = self.archive_for(sid)
        for relative in receipt['files']:
            source = archive.path(relative)
            target = self.store.file(sid, 'export/' + source.relative_to(archive.root).as_posix())
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        local = self.store.file(sid, 'report.md')
        body = archive.path(receipt['report_file']).read_text(encoding='utf-8')
        local.write_text(body.replace('](../附件/', '](export/附件/').replace('](../%E9%99%84%E4%BB%B6/', '](export/%E9%99%84%E4%BB%B6/'), encoding='utf-8')
        self.store.artifact(sid, local, 'reading_report', {'source_id': sid})
        return {**receipt, 'workspace_report': 'report.md'}

    def additional_tools(self, session, settings):
        sid = session['id']
        archive = self.archive_for(sid)

        @tool
        def check_reading_archive(candidates: list[dict] = [], offset: int = 0, limit: int = 30) -> dict:
            """Check duplicates across the entire Obsidian index (including awaiting_graph). Optional candidates: title, arxiv_id, doi, verified aliases. Existing entries are paginated."""
            records = archive.index()['records']
            matches = [{'candidate': p.get('title', ''), 'duplicates': [r['title'] for r in records if identities(p) & identities(r)]}
                       for p in candidates[:30]]
            offset, limit = max(0, offset), max(1, min(50, limit))
            return {'total': len(records), 'matches': matches, 'records': [
                {k: r.get(k) for k in ('title', 'arxiv_id', 'doi', 'aliases', 'status')}
                for r in records[offset:offset + limit]], 'next_offset': offset + limit if offset + limit < len(records) else None}

        @tool
        async def read_source_pdf(url: str = '', path: str = '', start_page: int = 1, max_pages: int = 3, text_offset: int = 0) -> dict:
            """Read a public original PDF in bounded batches. Follow next_read until null (including appendices). One-based physical pages; text_offset continues a long page. Records byte hashes and coverage for archive verification."""
            from pypdf import PdfReader
            if bool(url) == bool(path) or start_page < 1 or not 1 <= max_pages <= 30 or text_offset < 0:
                raise ValueError('Provide exactly one URL/path, positive page and 1–30 max_pages')
            if url:
                data, _, final = await network.fetch_public(url)
                if not data.startswith(b'%PDF-'):
                    raise ValueError('原文地址没有返回 PDF')
                path = 'papers/' + hashlib.sha256(data).hexdigest()[:24] + '.pdf'
                file = self.store.file(sid, path)
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(data)
            else:
                file = self.store.file(sid, path)
                if path not in self.evidence(sid, 'pdf'):
                    raise ValueError('仅可继续阅读本任务下载并登记的原文 PDF')
                final = self.evidence(sid, 'pdf')[path]['url']
            def extract():
                reader = PdfReader(file)
                if not start_page <= len(reader.pages) <= 300:
                    raise ValueError('PDF 页码超出范围或超过 300 页上限')
                pages, available = [], 8500
                for i in range(start_page - 1, min(len(reader.pages), start_page - 1 + max_pages)):
                    text = reader.pages[i].extract_text() or ''
                    offset = text_offset if i == start_page - 1 else 0
                    if not text.strip() or offset >= len(text):
                        raise ValueError(f'PDF 第 {i+1} 页无可提取文本或偏移越界；需要可读原文，不能假装读完扫描件')
                    end = min(len(text), offset + available)
                    pages.append({'page': i + 1, 'text': text[offset:end], 'offset': offset, 'end': end, 'total_chars': len(text)})
                    available -= end - offset
                    if end < len(text) or available < 500:
                        break
                title_text = ' '.join(reader.pages[i].extract_text() or '' for i in range(min(2, len(reader.pages))))
                return len(reader.pages), pages, title_text
            total, pages, title_text = await asyncio.to_thread(extract)
            previous = self.evidence(sid, 'pdf').get(path, {})
            sha = digest(file)
            if previous and previous['sha256'] != sha:
                raise ValueError('原文 PDF 在阅读期间被修改')
            coverage = previous.get('coverage', {})
            visited = set(previous.get('pages', []))
            for page in pages:
                key = str(page['page'])
                spans = sorted(coverage.get(key, []) + [[page['offset'], page['end']]])
                merged = []
                for begin, end in spans:
                    if merged and begin <= merged[-1][1]:
                        merged[-1][1] = max(merged[-1][1], end)
                    else:
                        merged.append([begin, end])
                coverage[key] = merged
                if merged == [[0, page['total_chars']]]:
                    visited.add(page['page'])
            visited = sorted(visited)
            record = {'path': path, 'url': final, 'sha256': sha, 'pages': visited, 'total_pages': total,
                      'title_key': title_key(title_text), 'coverage': coverage}
            self.save_evidence(sid, path, 'pdf', record)
            self.store.artifact(sid, file, 'source_pdf', {'source_url': final})
            last = pages[-1]
            next_read = ({'path': path, 'start_page': last['page'], 'text_offset': last['end']} if last['end'] < last['total_chars'] else
                         {'path': path, 'start_page': last['page'] + 1} if last['page'] < total else None)
            return {k: v for k, v in record.items() if k not in {'title_key', 'coverage'}} | {'pages': pages, 'next_read': next_read, 'remaining_pages': sorted(set(range(1, total + 1)) - set(visited)),
                    'reading_level': 'PDF text extraction; screenshots are original pages, not independent visual interpretation'}

        @tool
        async def capture_paper_figure(pdf_path: str, page: int, label: str, caption: str, explanation: str,
                                       section: Literal['design', 'experiments'] = 'experiments') -> dict:
            """Capture a physical PDF page containing an original figure/table (never generate a replacement). Give original figure number, Chinese caption and evidence-grounded interpretation. Attach to design or experiments."""
            source = self.evidence(sid, 'pdf').get(pdf_path)
            if not source or page not in source['pages'] or digest(self.store.file(sid, pdf_path)) != source['sha256']:
                raise ValueError('先阅读该原文页；只接受已登记且未被修改的 PDF')
            if not label.strip() or len(caption.strip()) < 10 or len(explanation.strip()) < 20:
                raise ValueError('请填写真实图号、中文图注和结果解释')
            fid = hashlib.sha256(dumps([pdf_path, page, label, section]).encode()).hexdigest()[:16]
            target = self.store.file(sid, 'figures/' + fid + '.png')
            target.parent.mkdir(parents=True, exist_ok=True)
            data = await asyncio.to_thread(pdf_page, self.store.file(sid, pdf_path).read_bytes(), page - 1)
            target.write_bytes(data)
            record = {'id': fid, 'path': 'figures/' + fid + '.png', 'pdf_path': pdf_path, 'page': page,
                      'label': label[:200], 'caption': caption, 'explanation': explanation, 'section': section, 'sha256': digest(target)}
            self.save_evidence(sid, fid, 'figure', record)
            self.store.artifact(sid, target, 'paper_figure', record)
            return record

        @tool
        def save_paper_review(paper: PaperReview) -> dict:
            """Save one complete structured Chinese reading draft before publishing the whole batch. Saving the same PDF again revises its draft; it does not archive or bypass verification."""
            for key in SECTIONS:
                if len(paper.sections.get(key, '').strip()) < 40:
                    raise ValueError('报告章节缺少实质内容：' + key)
            if paper.pdf_path not in self.evidence(sid, 'pdf'):
                raise ValueError('请先阅读对应原文 PDF')
            self.save_evidence(sid, paper.pdf_path, 'review', paper.model_dump())
            return {'saved': paper.title, 'draft_count': len(self.evidence(sid, 'review'))}

        @tool
        def publish_reading_report(papers: list[PaperReview] = []) -> dict:
            """Validate and archive the complete Chinese report, PDFs and original figures; atomically register cumulative dedup entries. Publication is idempotent for this task. Do not call before all papers are read."""
            job = self.job(sid)
            if archive.receipt(sid).exists():
                receipt = archive.publish(sid, job['keywords'], [], {}, {})
                return self.export_report(sid, receipt)
            papers = papers or [PaperReview.model_validate(p) for p in self.evidence(sid, 'review').values()]
            if len(papers) != job['paper_count']:
                raise ValueError(f'本次需要完整精读 {job["paper_count"]} 篇；材料不足时暂停，不能标记完成')
            sources, figures = self.evidence(sid, 'pdf'), self.evidence(sid, 'figure')
            for paper in papers:
                for key in SECTIONS:
                    if len(paper.sections.get(key, '').strip()) < 40:
                        raise ValueError('报告章节缺少实质内容：' + key)
                source = sources.get(paper.pdf_path)
                if not source or source['pages'] != list(range(1, source['total_pages'] + 1)):
                    raise ValueError('请分页读完整篇原文（含附录），不能用摘要代替全文')
                source['file'] = self.store.file(sid, paper.pdf_path)
                if title_key(paper.title) not in source['title_key']:
                    raise ValueError('题名与原文前两页不匹配，请核对论文身份和完整题名')
                if digest(source['file']) != source['sha256']:
                    raise ValueError('PDF 已发生改变，停止归档')
                if not paper.figures and len(paper.figure_unavailable_reason.strip()) < 30:
                    raise ValueError('需要原图，或填写具体、可核实的无图/获取失败原因')
                if len(paper.figures) != len(set(paper.figures)):
                    raise ValueError('同一图像不能重复计入')
                for fid in paper.figures:
                    figure = figures.get(fid)
                    if not figure or figure['pdf_path'] != paper.pdf_path:
                        raise ValueError('截图必须来自对应论文原文')
                    figure['file'] = self.store.file(sid, figure['path'])
                    if digest(figure['file']) != figure['sha256']:
                        raise ValueError('原图文件发生改变，停止归档')
            receipt = archive.publish(sid, job['keywords'], [p.model_dump() for p in papers], sources, figures)
            return self.export_report(sid, receipt)

        return [check_reading_archive, read_source_pdf, capture_paper_figure, save_paper_review, publish_reading_report]
