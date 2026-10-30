"""Obsidian archive shared with the existing collector; no scheduler or agent state."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import unicodedata
from urllib.parse import quote, unquote, urlsplit
from zoneinfo import ZoneInfo

import yaml
from markdown_it import MarkdownIt


SECTIONS = {
    'abstract': '摘要', 'background': '背景', 'motivation': '动机与挑战',
    'contributions': '解决措施与贡献点', 'design': '设计框架与创新细节',
    'experiments': '实验结果与消融', 'limitations': '结果边界与局限',
    'connections': '研究联系与整理者分析',
}


def stamp():
    return datetime.now(ZoneInfo('Asia/Singapore')).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def title_key(value):
    return ''.join(c for c in unicodedata.normalize('NFKC', str(value)).casefold() if c.isalnum())


def identities(paper):
    keys = {('title', title_key(t)) for t in [paper.get('title', ''), *paper.get('aliases', [])] if t}
    arxiv = re.sub(r'^https?://arxiv.org/(abs|pdf)/', '', str(paper.get('arxiv_id') or '').strip(), flags=re.I)
    arxiv = re.sub(r'v\d+$', '', arxiv.removesuffix('.pdf')).lower()
    doi = re.sub(r'^(https?://(dx\.)?doi.org/|doi:\s*)', '', str(paper.get('doi') or '').strip(), flags=re.I).lower()
    if arxiv:
        keys.add(('arxiv', arxiv))
    if doi:
        keys.add(('doi', doi))
    return keys


def split_note(text):
    if text.startswith('---\n'):
        end = text.find('\n---', 4)
        if end < 0:
            raise ValueError('报告 frontmatter 未闭合')
        meta = yaml.safe_load(text[4:end]) or {}
        if not isinstance(meta, dict):
            raise ValueError('报告 frontmatter 格式错误')
        return meta, text[end + 4:].lstrip('\n')
    return {}, text


def safe_name(value):
    return re.sub(r'[\x00-\x1f\\/:*?"<>|#\[\]]', '-', value).strip(' .')[:80] or '论文精读'


class ReadingArchive:
    def __init__(self, vault, prefix='AI安全', include_existing_notes=False):
        self.vault = Path(vault).expanduser().resolve()
        if not prefix or Path(prefix).is_absolute() or '..' in Path(prefix).parts:
            raise ValueError('归档专区必须是仓库中的相对目录')
        self.root = (self.vault / prefix).resolve()
        if not self.root.is_relative_to(self.vault) or any(p.startswith('.') and p != '.' for p in Path(prefix).parts):
            raise ValueError('归档专区超出仓库')
        self.include_existing_notes = include_existing_notes
        self.index_path = self.root / '系统/collection-index.json'

    def config(self):
        return {'vault_root': str(self.vault), 'prefix': self.root.relative_to(self.vault).as_posix(),
                'include_existing_notes': self.include_existing_notes}

    def same_location(self, other):
        return (self.vault, self.root) == (other.vault, other.root)

    def path(self, relative):
        path = (self.vault / relative).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise ValueError('文件超出论文专区')
        return path

    def rel(self, path):
        path = self.path(Path(path).relative_to(self.vault))
        return path.relative_to(self.vault).as_posix()

    def stored_index(self):
        if not self.index_path.exists():
            # Existing reports without their authoritative index must never imply no duplicates.
            if any((self.root / '01-报告').glob('*.md')):
                raise ValueError('已有报告但缺少累计索引，请恢复 系统/collection-index.json 后再收集')
            return {'schema': 'ai-safety-obsidian/1', 'records': []}
        data = json.loads(self.path(self.index_path.relative_to(self.vault)).read_text(encoding='utf-8'))
        if not isinstance(data, dict) or not isinstance(data.get('records'), list) or any(
                not isinstance(r, dict) or not r.get('title') for r in data['records']):
            raise ValueError('累计索引格式错误；已停止归档以保护旧论文')
        return data

    def notes(self):
        """Read selected notes in place; never copy or modify the user's corpus."""
        if not self.include_existing_notes:
            return sorted((self.root / '01-报告').glob('*.md'), reverse=True)
        notes = []
        for directory, dirs, files in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d != '系统'
                             and not (Path(directory) / d).is_symlink())
            for name in sorted(files):
                path = Path(directory) / name
                if not name.startswith('.') and path.suffix.lower() == '.md' and not path.is_symlink():
                    notes.append(path)
                    if len(notes) > 2000:
                        raise ValueError('所选范围超过 2000 篇笔记，请选择更小的子目录')
        return sorted(notes, reverse=True)

    def imported_records(self):
        records = []
        if not self.include_existing_notes:
            return records
        for path in self.notes():
            try:
                if path.stat().st_size > 2_000_000:
                    continue
                meta, _ = split_note(path.read_text(encoding='utf-8'))
                # Only explicit paper metadata participates; citations in prose do not.
                title = meta.get('paper_title') or meta.get('title') or path.stem
                arxiv = str(meta.get('arxiv_id') or '')
                doi = str(meta.get('doi') or '')
                if arxiv and not re.fullmatch(r'(?:https?://arxiv.org/(?:abs|pdf)/)?(?:\d{4}\.\d{4,5}|[a-zA-Z.-]+/\d{7})(?:v\d+)?(?:\.pdf)?', arxiv):
                    arxiv = ''
                if doi and not re.fullmatch(r'(?:https?://(?:dx\.)?doi.org/|doi:\s*)?10\.\d{4,9}/\S+', doi, re.I):
                    doi = ''
                if not (meta.get('paper_title') or meta.get('type') == 'paper' or arxiv or doi):
                    continue
                records.append({'title': str(title), 'arxiv_id': arxiv, 'doi': doi,
                                'status': 'local_note', 'note_file': self.rel(path)})
            except (OSError, ValueError, yaml.YAMLError):
                continue
        return records

    def index(self):
        data = self.stored_index()
        existing = set().union(*(identities(r) for r in data['records'])) if data['records'] else set()
        for record in self.imported_records():
            keys = identities(record)
            if not keys & existing:
                data['records'].append(record)
                existing |= keys
        return data

    @contextmanager
    def locked(self):
        system = self.path((self.root / '系统').relative_to(self.vault))
        system.mkdir(parents=True, exist_ok=True)
        # Same lock as obsidian_sync.py, including its 13:00 graph export.
        with self.path((system / '.sync.lock').relative_to(self.vault)).open('a+b') as lock:
            if os.name == 'nt':
                import msvcrt
                lock.seek(0)
                if not lock.read(1):
                    lock.write(b'\0')
                    lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                if os.name == 'nt':
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock, fcntl.LOCK_UN)

    def uri(self, path=None):
        return 'obsidian://open?path=' + quote(str(path or self.root), safe='')

    def reports(self):
        rows = []
        for path in self.notes():
            try:
                path = self.path(path.relative_to(self.vault))
                if path.stat().st_size > 2_000_000:
                    continue
                meta, _ = split_note(path.read_text(encoding='utf-8'))
                rows.append({'path': self.rel(path), 'title': str(meta.get('title') or path.stem),
                             'date': str(meta.get('reading_date') or datetime.fromtimestamp(path.stat().st_mtime).date()),
                             'complete': meta.get('complete'), 'obsidian_url': self.uri(path)})
            except (ValueError, OSError, yaml.YAMLError):
                continue
        return rows

    def public_file(self, relative):
        path = self.path(relative)
        allowed = {'01-报告', '02-论文', '附件'}
        parts = path.relative_to(self.root).parts
        if (any(p.startswith('.') or p == '系统' for p in parts)
                or (not self.include_existing_notes and parts[0] not in allowed)) or path.suffix.lower() not in {
                '.md', '.pdf', '.png', '.jpg', '.jpeg', '.webp'} or not path.is_file():
            raise ValueError('文件不可预览')
        return path

    def preview(self, relative):
        path = self.public_file(relative)
        if path.suffix.lower() != '.md' or path.stat().st_size > 2_000_000:
            raise ValueError('请选择 Markdown 报告（最大 2 MB）')
        _, body = split_note(path.read_text(encoding='utf-8'))
        # HTML is disabled; file links are resolved inside the configured archive.
        md = MarkdownIt('commonmark', {'html': False}).enable('table')
        def wikilink(state, silent):
            match = re.match(r'(!?)\[\[([^\]\n]+)\]\]', state.src[state.pos:])
            if not match:
                return False
            if not silent:
                target, _, label = match[2].partition('|')
                target = target.split('#', 1)[0]
                local = None
                for base in (path.parent, self.root):
                    candidate = base / target
                    if not candidate.suffix:
                        candidate = candidate.with_suffix('.md')
                    try:
                        local = self.public_file(candidate.relative_to(self.vault))
                        break
                    except (ValueError, OSError):
                        continue
                if local:
                    href = quote(os.path.relpath(local, path.parent).replace(os.sep, '/'), safe='/')
                    if match[1] and local.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp'}:
                        token = state.push('image', 'img', 0)
                        token.attrSet('src', href)
                        token.attrSet('alt', label or target)
                        token.content = label or target
                    else:
                        token = state.push('link_open', 'a', 1)
                        token.attrSet('href', href)
                        state.push('text', '', 0).content = label or target
                        state.push('link_close', 'a', -1)
                else:
                    state.push('text', '', 0).content = match[0]
            state.pos += len(match[0])
            return True
        md.inline.ruler.before('link', 'obsidian_wikilink', wikilink)
        tokens = md.parse(body)
        def visit(items):
            for token in items:
                attr = 'src' if token.type == 'image' else 'href' if token.type == 'link_open' else None
                if attr:
                    value = token.attrGet(attr) or ''
                    parsed = urlsplit(value)
                    if not parsed.scheme and not parsed.netloc and not value.startswith('#'):
                        try:
                            local = self.public_file((path.parent / unquote(parsed.path)).resolve().relative_to(self.vault))
                            token.attrSet(attr, '/api/reading/file?path=' + quote(self.rel(local), safe=''))
                        except (OSError, ValueError):
                            token.attrSet(attr, '')
                    elif token.type == 'image' or (parsed.scheme and parsed.scheme not in {'https', 'http'}):
                        token.attrSet(attr, '')
                    if token.type == 'link_open':
                        token.attrSet('target', '_blank')
                        token.attrSet('rel', 'noopener noreferrer')
                visit(token.children or [])
        visit(tokens)
        return md.renderer.render(tokens, md.options, {})

    def receipt(self, source_id):
        if not re.fullmatch('[a-f0-9]{32}', source_id):
            raise ValueError('Invalid source ID')
        return self.path((self.root / '系统' / ('reading-' + source_id + '.json')).relative_to(self.vault))

    def verify(self, source_id):
        receipt = json.loads(self.receipt(source_id).read_text(encoding='utf-8'))
        for relative, expected in receipt['files'].items():
            if digest(self.path(relative)) != expected:
                raise ValueError('归档文件已改变：' + relative)
        matches = [r for r in self.index()['records'] if r.get('source_id') == source_id]
        if len(matches) != receipt['paper_count']:
            raise ValueError('累计索引未完整登记此次报告')
        return receipt

    def commit_receipt(self, receipt):
        """Finish an interrupted publication without losing or duplicating index entries."""
        for relative, expected in receipt['files'].items():
            if digest(self.path(relative)) != expected:
                raise ValueError('归档文件已改变：' + relative)
        index = self.stored_index()
        imported = self.imported_records()
        for paper in receipt['records']:
            matches = [r for r in index['records'] if identities(paper) & identities(r)]
            if matches:
                if len(matches) != 1 or any(matches[0].get(k) != paper.get(k) for k in ('source_id', 'pdf_local', 'report_file', 'sha256')):
                    raise ValueError('论文已被其他任务归档：' + paper['title'])
            else:
                if any(identities(paper) & identities(r) for r in imported):
                    raise ValueError('论文已有本地笔记：' + paper['title'])
                index['records'].append(paper)
        index['updated_at'] = stamp()
        atomic_json(self.index_path, index)
        return self.verify(receipt['source_id'])

    def publish(self, source_id, keywords, papers, sources, figures):
        """Inputs are validated workspace evidence, not arbitrary filesystem paths."""
        with self.locked():
            if self.receipt(source_id).is_file():
                return self.commit_receipt(json.loads(self.receipt(source_id).read_text(encoding='utf-8')))
            index = self.index()
            existing = set().union(*(identities(p) for p in index['records'])) if index['records'] else set()
            for paper in papers:
                keys = identities(paper)
                if existing & keys:
                    raise ValueError('论文已归档（包括 awaiting_graph）：' + paper['title'])
                existing |= keys
            if not self.index_path.exists():
                atomic_json(self.index_path, self.stored_index())
            date = stamp()[:10]
            name = f'{date}｜专题精读：{safe_name(keywords)}-{source_id[:8]}.md'
            report = self.path((self.root / '01-报告' / name).relative_to(self.vault))
            if report.exists():
                # An interrupted pre-index publication can be retried only if bytes match below.
                meta, _ = split_note(report.read_text(encoding='utf-8'))
                if meta.get('source_id') != source_id:
                    raise ValueError('报告路径已存在，不能覆盖个人笔记')
            file_hashes, records, manifest = {}, [], []
            meta = {'type': 'report', 'source_id': source_id, 'title': name[:-3], 'reading_date': date,
                    'complete': True, 'keywords': keywords, 'tags': ['ai-safety', 'report', 'keyword-reading']}
            lines = ['---', yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip(), '---', '',
                     '# ' + name[:-3], '', '按关键词筛选并精读；实验数字来自作者原文，未重新运行实验。',
                     '图像为固定阅读版本的原文 PDF 页面截图。图表解释结合 PDF 提取文本；未进行独立视觉复核。', '']
            def install(source, target):
                target = self.path(target.relative_to(self.vault))
                target.parent.mkdir(parents=True, exist_ok=True)
                data = source.read_bytes()
                if target.exists() and target.read_bytes() != data:
                    raise ValueError('归档路径已存在且内容不同：' + str(target))
                if not target.exists():
                    with target.open('xb') as output:
                        output.write(data)
                file_hashes[self.rel(target)] = digest(target)
                return quote(os.path.relpath(target, report.parent).replace(os.sep, '/'), safe='/')
            for n, paper in enumerate(papers, 1):
                source = sources[paper['pdf_path']]
                pdf = self.root / '附件/PDF' / f'{source_id}-{n}.pdf'
                pdf_link = install(source['file'], pdf)
                selected = [figures[fid] for fid in paper['figures']]
                lines += [f'## 论文{n}：{paper["title"]}', '',
                          f'- 发表日期：{paper["publication_date"]} · 发表渠道：{paper["venue"]}',
                          f'- 固定阅读版本：{paper["read_version"]}',
                          f'- [原文]({source["url"]}) · [本地 PDF]({pdf_link})', '']
                for section, label in SECTIONS.items():
                    lines += [f'### {label}', '', paper['sections'][section], '']
                    for figure in [f for f in selected if f['section'] == section]:
                        target = self.root / '附件/图表' / date / f'{source_id}-{figure["id"]}.png'
                        link = install(figure['file'], target)
                        lines += [f'![{figure["label"]}]({link})', '',
                                  f'**{paper["title"]} · {figure["label"]} · 物理 PDF 第 {figure["page"]} 页** · [原文]({source["url"]})',
                                  '', figure['caption'], '', figure['explanation'], '']
                        manifest.append({k: v for k, v in figure.items() if k != 'file'})
                        manifest[-1].update(file=self.rel(target), pdf=self.rel(pdf), source_url=source['url'], title=paper['title'])
                if not selected:
                    lines += ['### 原图获取情况', '', paper['figure_unavailable_reason'], '']
                lines += ['### 来源与核验', '', paper['evidence_notes'], '']
                records.append({'title': paper['title'], 'arxiv_id': next((v for k, v in identities(paper) if k == 'arxiv'), None),
                                'doi': next((v for k, v in identities(paper) if k == 'doi'), None),
                                'read_version': paper['read_version'], 'source_url': source['url'],
                                'collected_on': date, 'source_id': source_id, 'status': 'awaiting_graph',
                                'pdf_local': self.rel(pdf), 'report_file': self.rel(report),
                                'sha256': file_hashes[self.rel(pdf)], 'keywords': keywords})
            manifest_path = self.path((self.root / '附件/资料' / source_id / 'figure_manifest.json').relative_to(self.vault))
            atomic_json(manifest_path, manifest)
            file_hashes[self.rel(manifest_path)] = digest(manifest_path)
            report.parent.mkdir(parents=True, exist_ok=True)
            body = '\n'.join(lines)
            if report.exists() and report.read_text(encoding='utf-8') != body:
                raise ValueError('已存在的报告正文不同，保留原内容，请人工处理')
            report.write_text(body, encoding='utf-8')
            file_hashes[self.rel(report)] = digest(report)
            # Every local Markdown image/PDF must resolve before index commit.
            for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', body):
                if not urlsplit(target).scheme:
                    linked = self.path((report.parent / unquote(target)).resolve().relative_to(self.vault))
                    if not linked.is_file() or self.rel(linked) not in file_hashes:
                        raise ValueError('报告引用文件缺失：' + target)
            receipt = {'source_id': source_id, 'paper_count': len(papers), 'report_file': self.rel(report),
                       'files': file_hashes, 'records': records, 'obsidian_url': self.uri(report), 'completed_at': stamp()}
            # Write the recovery receipt before committing the index. On restart publication
            # rechecks hashes/duplicates and can finish either side of this crash boundary.
            atomic_json(self.receipt(source_id), receipt)
            return self.commit_receipt(receipt)
