#!/usr/bin/env python3
"""Obsidian is canonical; versioned graph and Canvas are derived, auditable views."""
import argparse, copy, datetime as dt, hashlib, html, json, os, re, shutil, sys, uuid
from pathlib import Path
from urllib.parse import quote, unquote, urlparse
import yaml
import graph_sync as graph
from runtime_support import (file_lock, load_config, validate_config, storage_names, domain_tag, domain_view,
                             canonical_arxiv, canonical_doi, canonical_pmid)
START = '<!-- RESEARCH:GENERATED:START -->'
END = '<!-- RESEARCH:GENERATED:END -->'
# Match both generations without changing the captured content or content hashes.
REGION = re.compile(r'<!-- (?:RESEARCH|AI-SAFETY):GENERATED:START -->\n?([\s\S]*?)\n?<!-- (?:RESEARCH|AI-SAFETY):GENERATED:END -->')
KIND_DIR = {'paper': '02-论文', 'domain': '03-领域', 'concept': '04-知识/概念', 'method': '04-知识/方法', 'benchmark': '04-知识/基准', 'dataset': '04-知识/数据集', 'theory': '04-知识/理论', 'finding': '04-知识/发现'}

def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))

def write(p, d):
    graph.write(p, d)

def sha(s):
    return hashlib.sha256(s if isinstance(s, bytes) else s.encode()).hexdigest()

def clean(s):
    return re.sub('[\\[\\]#|^:/\\\\?*<>\\x00-\\x1f]', '-', str(s)).strip().rstrip('.')

def split_note(text):
    if text.startswith('---\n'):
        end = text.find('\n---', 4)
        if end < 0:
            raise ValueError('Unclosed YAML frontmatter')
        meta = yaml.safe_load(text[4:end]) or {}
        if not isinstance(meta, dict):
            raise ValueError('Frontmatter must be a mapping')
        return (meta, text[end + 4:].lstrip('\n'))
    return ({}, text)

def front(meta):
    return '---\n' + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip() + '\n---\n\n'

def strip_generated(text):
    return REGION.sub('', text).strip()

def wiki(p, label=None, embed=False):
    return ('!' if embed else '') + '[[' + str(p).removesuffix('.md') + ('|' + label if label else '') + ']]'

def uri(p):
    return 'obsidian://open?path=' + quote(str(Path(p).resolve()), safe='')

class Vault:

    def __init__(self, config=None):
        self.c = validate_config(config) if config else load_config()
        self.vault = Path(self.c['vault_root']).resolve()
        self.root = self.vault / self.c['prefix']
        self.work = Path(self.c['workspace'])
        self.system = self.root / '系统'
        self.system.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.system / 'sync-ledger.json'
        self.ledger = read(self.ledger_path) if self.ledger_path.exists() else {'schema': 1, 'sources': {}, 'generated': {}, 'paths': {}, 'conflicts': []}
        self.paths = graph.paths(self.work, config=self.c)
        self.state = graph.load(self.paths)

    def save(self):
        write(self.ledger_path, self.ledger)

    def rel(self, p):
        return Path(p).resolve().relative_to(self.vault).as_posix()

    def report_descriptors(self):
        docs = {}
        errors = []
        seen = set()
        duplicates = set()
        for p in sorted((self.root / '01-报告').glob('*.md')):
            try:
                (meta, body) = split_note(p.read_text(encoding='utf-8'))
                if meta.get('research_domain', self.c['domain']['name']) != self.c['domain']['name']:
                    raise ValueError('Report belongs to another research domain')
                sid = str(meta.get('source_id', '')).replace('-', '')
                if not re.fullmatch('[a-f0-9]{32}', sid):
                    raise ValueError('Missing stable source_id UUID')
                if sid in seen:
                    duplicates.add(sid)
                    docs.pop(sid, None)
                    raise ValueError('Duplicate source_id: ' + sid)
                seen.add(sid)
                body = strip_generated(body)
                if meta.get('complete') is not True or len(body) < 80:
                    raise ValueError('Incomplete or empty report; previous graph retained')
                descriptor = {'id': sid, 'title': str(meta.get('title') or p.stem), 'text': body, 'source_type': 'obsidian', 'vault_root': str(self.vault), 'relative_path': self.rel(p), 'reading_date': str(meta.get('reading_date') or meta.get('date') or p.stem[:10]), 'page_last_edited_at': dt.datetime.fromtimestamp(p.stat().st_mtime, dt.timezone.utc).isoformat()}
                for key in ['original_notion_url', 'original_notion_hash']:
                    if meta.get(key):
                        descriptor[key] = meta[key]
                doc = graph.source(descriptor)
                docs[sid] = {'path': p, 'meta': meta, 'body': body, 'descriptor': descriptor, 'doc': doc, 'vault_hash': sha(body)}
            except Exception as e:
                errors.append({'path': str(p), 'error': str(e)})
        for sid in duplicates:
            docs.pop(sid, None)
        for (sid, old) in self.ledger['sources'].items():
            if sid not in docs:
                errors.append({'source_id': sid, 'path': old.get('path'), 'error': 'Previously indexed source missing or invalid; graph retained'})
        return (docs, errors)

    def plan(self, output):
        (docs, errors) = self.report_descriptors()
        errors += self.managed_conflicts()
        rows = []
        inbox = Path(output).with_suffix('') / 'inbox'
        for (sid, item) in docs.items():
            previous = self.ledger['sources'].get(sid)
            known = self.state['sources'].get(sid)
            unchanged = previous and previous['vault_hash'] == item['vault_hash'] and (previous['title'] == item['doc']['title']) and known and (known['current_hash'] == previous['graph_content_hash'])
            status = 'unchanged' if unchanged else 'changed' if known else 'new'
            row = {'source_id': sid, 'title': item['doc']['title'], 'status': status, 'vault_hash': item['vault_hash'], 'content_hash': item['doc']['hash'], 'path': str(item['path'])}
            if not unchanged:
                file = inbox / (sid + '.json')
                write(file, item['descriptor'])
                row['fetch_file'] = str(file.resolve())
            rows.append(row)
        result = {'checked_at': graph.now(), 'source': 'obsidian', 'reports': rows, 'needs_extraction': [r for r in rows if r['status'] != 'unchanged'], 'errors': errors}
        pointer = self.paths['sync'] / 'current.json'
        result['needs_finalize'] = pointer.exists() and (
            self.ledger.get('graph_hash') != read(pointer)['graph_hash'] or
            any(not (self.vault / rel).exists() for rel in
                list(self.ledger['generated']) + list(self.ledger.get('generated_json', {}))))
        result['needs_export'] = not graph.export_current(self.paths)
        result['needs_rebuild'] = pointer.exists() and self.state.get('research_domain') != domain_view(self.c)
        write(output, result)
        return result

    def ack(self, plan):
        (docs, errors) = self.report_descriptors()
        if errors:
            raise ValueError(str(errors))
        for row in plan['reports']:
            if row['status'] == 'unchanged':
                continue
            sid = row['source_id']
            item = docs[sid]
            if item['vault_hash'] != row['vault_hash'] or item['doc']['hash'] != row['content_hash'] or self.state['sources'].get(sid, {}).get('current_hash') != row['content_hash']:
                raise ValueError('Source changed during extraction or was not applied: ' + sid)
            self.ledger['sources'][sid] = {'path': self.rel(item['path']), 'title': item['doc']['title'], 'vault_hash': item['vault_hash'], 'graph_content_hash': row['content_hash']}
        self.save()

    def managed_conflicts(self):
        errors = []
        for (rel, expected) in self.ledger.get('generated', {}).items():
            path = self.vault / rel
            if not path.exists():
                continue
            found = REGION.search(path.read_text(encoding='utf-8'))
            if not found or sha(found.group(1).strip()) != expected:
                errors.append({'path': rel, 'error': 'Generated section edited; preserve it and resolve explicitly'})
        for (rel, expected) in self.ledger.get('generated_json', {}).items():
            path = self.vault / rel
            if path.exists() and sha(path.read_bytes()) != expected:
                errors.append({'path': rel, 'error': 'Generated Canvas edited; preserve it and resolve explicitly'})
        return errors

    def managed_json(self, path, value):
        path = Path(path)
        if not path.resolve().is_relative_to(self.vault):
            raise ValueError('Generated file escapes the vault')
        rel = self.rel(path)
        previous = self.ledger.setdefault('generated_json', {}).get(rel)
        if path.exists() and (previous is None or sha(path.read_bytes()) != previous):
            raise ValueError('Untracked or edited Canvas preserved: ' + rel)
        write(path, value)
        self.ledger['generated_json'][rel] = sha(path.read_bytes())
        self.save()

    def managed(self, path, body, meta=None):
        path = Path(path)
        if not path.resolve().is_relative_to(self.vault):
            raise ValueError('Generated file escapes the vault')
        path.parent.mkdir(parents=True, exist_ok=True)
        rel = self.rel(path)
        body = body.strip()
        marker = storage_names(self.c)['marker']
        block = '<!-- ' + marker + ':GENERATED:START -->\n' + body + '\n<!-- ' + marker + ':GENERATED:END -->'
        if path.exists():
            text = path.read_text(encoding='utf-8')
            found = REGION.search(text)
            if found:
                previous = self.ledger['generated'].get(rel)
                if (previous is None or sha(found.group(1).strip()) != previous) and found.group(1).strip() != body:
                    self.ledger['conflicts'].append(rel)
                    write(self.system / 'conflicts.json', self.ledger['conflicts'])
                    raise ValueError('Generated section was edited; preserved for review: ' + rel)
                text = REGION.sub(lambda _: block, text, count=1)
            else:
                text = text.rstrip() + '\n\n' + block + '\n'
        else:
            text = (front(meta) if meta else '') + block + '\n\n## 我的笔记\n\n'
        if not path.exists() or path.read_text(encoding='utf-8') != text:
            graph_path = path.with_suffix(path.suffix + '.tmp')
            graph_path.write_text(text, encoding='utf-8')
            os.replace(graph_path, path)
        self.ledger['generated'][rel] = sha(body)
        self.save()

    def export(self):
        conflicts = self.managed_conflicts()
        if conflicts:
            raise ValueError(str(conflicts))
        current = read(self.paths['sync'] / 'current.json')
        gen = self.paths['sync'] / 'generations' / current['generation']
        atlas = read(gen / 'atlas.json')
        self.categories = atlas['categories']
        nodes = {n['id']: n for n in atlas['nodes']}
        (docs, errors) = self.report_descriptors()
        if errors:
            raise ValueError(str(errors))
        paths = self.ledger['paths']
        report_paths = {sid: self.rel(x['path']) for (sid, x) in docs.items()}
        for (nid, n) in nodes.items():
            if n['kind'] == 'source':
                sid = next((r['page_id'] for r in n.get('source_refs', []) if r['page_id'] in report_paths), None)
                if sid:
                    paths[nid] = report_paths[sid]
                    continue
            if nid not in paths:
                paths[nid] = self.c['prefix'] + '/' + KIND_DIR.get(n['kind'], '04-知识/来源') + '/' + clean(n['label']) + '.md'
        if len(set(paths.values())) != len(paths):
            raise ValueError('Entity filenames collide')
        collection = read(self.system / 'collection-index.json') if (self.system / 'collection-index.json').exists() else {'records': []}
        old_records = {graph.norm(r.get('title', '')): r for r in collection['records']}
        records = []
        for (nid, n) in nodes.items():
            outgoing = [e for e in atlas['edges'] if e['source'] == nid]
            incoming = [e for e in atlas['edges'] if e['target'] == nid]
            links = []
            for e in outgoing:
                label = '事实' if e['confidence'] == 'EXTRACTED' else '归纳 / 待验证'
                ep = self.c['prefix'] + '/06-关系证据/' + e['id'] + '.md'
                links.append('- **' + label + ' · ' + e['label'] + '** → ' + wiki(paths[e['target']], nodes[e['target']]['label']) + ' · ' + wiki(ep, '证据 ' + str(len(e['provenance']))) + ' ^' + e['id'])
            if n['kind'] == 'source':
                self.managed(self.vault / paths[nid], '## 知识图链接\n\n' + '\n'.join(links))
                continue
            lines = ['# ' + n['label'], '', '## 概览', '', n.get('summary') or n.get('description', '')]
            if n.get('full_title'):
                lines += ['', '完整题名：' + n['full_title']]
            if n.get('limitation'):
                lines += ['', '> [!important] 证据边界', '> ' + n['limitation']]
            if n.get('paper_url'):
                lines += ['', '[论文原文](' + n['paper_url'] + ')']
            for r in n.get('source_refs', []):
                if r['page_id'] in report_paths:
                    lines += ['', '阅读来源：' + wiki(report_paths[r['page_id']], r['title']) + ' · 原来源内容版本 `' + r['content_hash'] + '`']
            if n['kind'] == 'paper':
                record = copy.deepcopy(old_records.get(graph.norm(n.get('full_title', '')), {}))
                record.update(title=n.get('full_title', n['label']), normalized_title=graph.norm(n.get('full_title', n['label'])), arxiv_id=n.get('identity', {}).get('arxiv'), doi=n.get('identity', {}).get('doi'), pmid=n.get('identity', {}).get('pmid'), aliases=n.get('aliases', []), graph_id=nid, obsidian_file=paths[nid], status='archived_in_obsidian', reading_dates=n.get('reading_dates', []))
                if record.get('pdf_local'):
                    lines += ['', '本地 PDF：' + wiki(record['pdf_local'], '打开固定阅读版本')]
                report = next((r for r in n.get('source_refs', []) if r['page_id'] in docs), None)
                if report:
                    sid = report['page_id']
                    headers = re.findall(r'^##\s+(.+)$', docs[sid]['body'], re.M)
                    title = n.get('full_title', '')
                    candidate = next((h for h in headers if title.lower() in h.lower() or n['label'].replace('（论文）', '').lower() in h.lower()), None)
                    if not candidate:
                        candidate = next((h for h in headers if any((a.lower() in h.lower() for a in n.get('aliases', []) if len(a) > 3))), None)
                    target = report_paths[sid].removesuffix('.md') + ('#' + candidate if candidate else '')
                    lines += ['', '## 完整精读报告', '', wiki(target, embed=True)]
                    record['report_file'] = report_paths[sid]
                    record['report_heading'] = candidate
                lines += ['', '## 单篇关系画布', '', wiki(self.c['prefix'] + '/05-图谱/单篇/' + clean(n['label']) + '.canvas', '展开这篇论文的关系')]
                records.append(record)
            lines += ['', '## 出向关系与出处', ''] + (links or ['暂无出向关系；可用 Obsidian 反向链接查看关联笔记。'])
            meta = {'type': n['kind'], 'graph_id': nid, 'title': n.get('full_title', n['label']), 'aliases': n.get('aliases', []), 'category': n.get('category', 'general'), 'research_domain': self.c['domain']['name'], 'tags': ['research', domain_tag(self.c), n['kind'], n.get('category', 'general')]}
            self.managed(self.vault / paths[nid], '\n'.join(lines), meta)
        for e in atlas['edges']:
            lines = ['# ' + nodes[e['source']]['label'] + ' → ' + nodes[e['target']]['label'], '', wiki(paths[e['source']]) + ' → ' + wiki(paths[e['target']]), '', '- 关系：' + e['label'], '- 类型：`' + e['relation'] + '`', '- 层级：' + e['confidence'] + ' / ' + e['basis'], '- 稳定关系 ID：`' + e['id'] + '`', '', e['evidence']]
            for (i, p) in enumerate(e['provenance'], 1):
                local = wiki(report_paths[p['page_id']], p['title']) if p['page_id'] in report_paths else p['title']
                lines += ['', '## 来源 ' + str(i), '', '- 本地报告：' + local, '- 原始来源：[' + p['title'] + '](' + p['url'] + ')', '- 来源 ID：`' + p['page_id'] + '`', '- 内容版本：`' + p['content_hash'] + '`', '- 证据 ID：`' + p['id'] + '`', '- 编辑时间：' + str(p['last_edited_at']), '- 采集时间：' + p['captured_at'], '- 位置：' + p['source_location'], '- [对应原文](' + p['evidence_url'] + ')', '', '> ' + p['evidence'].replace('\n', '\n> ')]
            self.managed(self.root / '06-关系证据' / (e['id'] + '.md'), '\n'.join(lines), {'type': 'evidence', 'relation_id': e['id'], 'confidence': e['confidence']})
        titles = {graph.norm(r['title']) for r in records}
        pending = [r for r in collection['records'] if graph.norm(r['title']) not in titles]
        write(self.system / 'collection-index.json', {'schema': 'ai-safety-obsidian/1' if self.c['schema'] == 1 else 'research-obsidian/2', 'updated_at': graph.now(), 'dedup_rule': 'Verified canonical arXiv ID, DOI, PMID, full title; aliases require identity verification. Version updates are the same paper.', 'records': records + pending})
        self.canvas(atlas, paths, False)
        self.canvas(atlas, paths, True)
        home = ['# ' + self.c['domain']['name'] + '知识库', '', '主存储：Obsidian 本地 Markdown；图谱为可追溯的派生视图。', '', '## 开始浏览', '', wiki(self.c['prefix'] + '/05-图谱/论文总览 · 展开版.canvas', '论文总览 · 展开版') + ' · ' + wiki(self.c['prefix'] + '/05-图谱/跨论文关系.canvas', '跨论文关系') + ' · ' + wiki(self.c['prefix'] + '/05-图谱/完整知识图谱.canvas', '完整连接图'), '', '总览只放论文与领域；跨论文比较单独按行展开。每篇论文还有独立的关系画布，适合查看方法、概念和出处。绿色是事实，紫色是归纳。完整连接图隐藏密集边标签，关系名称和证据见单篇详图与证据卡。', '', '## 论文目录', '']
        for r in sorted(records, key=lambda r: (r.get('reading_dates') or [''])[0], reverse=True):
            home.append('- ' + wiki(r['obsidian_file'], nodes[r['graph_id']]['label']) + ' · ' + wiki(self.c['prefix'] + '/05-图谱/单篇/' + clean(nodes[r['graph_id']]['label']) + '.canvas', '关系详图') + ' · ' + (r.get('arxiv_id') or r.get('doi') or r.get('pmid') or '完整题名去重'))
        home += ['', '## 研究领域', ''] + ['- ' + wiki(paths[n['id']], n['label']) for n in atlas['nodes'] if n['kind'] == 'domain']
        home += ['', '## 阅读报告', ''] + ['- ' + wiki(p) for p in sorted(report_paths.values(), reverse=True)]
        if pending:
            home += ['', '## 新归档，待关系提取', ''] + ['- ' + r['title'] + ' · ' + wiki(r['report_file'], '阅读报告') for r in pending if r.get('report_file')]
        home += ['', '## 保存与更新', '', '已归档论文 ' + str(len(records) + len(pending)) + ' 篇；当前已入图 ' + str(len(records)) + ' 篇；知识节点 ' + str(len(atlas['nodes'])) + ' 个；关系 ' + str(len(atlas['edges'])) + ' 条。', '', '- 收集目标：每次 ' + str(self.c['papers_per_day']) + ' 篇；建议时刻 ' + self.c['collect_at'] + '（' + self.c['timezone'] + '）。', '- 图谱建议同步时刻：' + self.c['sync_at'] + '；实际是否启用以 Codex 定时任务为准。', '- 可直接编辑 `01-报告` 中的正文；下次同步按正文版本重新提取。', '- `我的笔记` 区域属于你，自动生成区若被修改会保留现场并报告冲突。', '- 删除/缺失文件不会被当作删除已有图谱的指令。', '', '' + wiki(self.c['prefix'] + '/使用说明')]
        self.managed(self.root / '00-首页.md', '\n'.join(home), {'type': 'index', 'research_domain': self.c['domain']['name'], 'tags': ['research', domain_tag(self.c)]})
        db = self.system / '图数据库'
        db.mkdir(exist_ok=True)
        for name in [self.paths['database'], 'atlas.json', 'state.json', 'validation.json']:
            if (gen / name).exists():
                shutil.copy2(gen / name, db / name)
        shutil.copy2(self.paths['out'] / 'provenance-registry.json', db / 'provenance-registry.json')
        for (sid, record) in self.state['sources'].items():
            for (h, version) in record['revisions'].items():
                write(self.system / '来源历史' / sid / (h + '.json'), version)
        write(self.paths['site'] / 'dist/obsidian-links.json', {'entities': {nid: uri(self.vault / path) for (nid, path) in paths.items()}, 'sources': {sid: uri(self.vault / path) for (sid, path) in report_paths.items()}})
        self.ledger['graph_hash'] = current['graph_hash']
        self.save()
        result = {'papers': len(records), 'nodes': len(atlas['nodes']), 'edges': len(atlas['edges']), 'sources': len(docs), 'vault': str(self.vault), 'home': str(self.root / '00-首页.md'), 'graph_hash': current['graph_hash']}
        write(self.system / 'last-export.json', result)
        return result

    def canvas(self, atlas, paths, overview):
        selected = [n for n in atlas['nodes'] if not overview or n['kind'] in {'paper', 'domain'}]
        ids = {n['id'] for n in selected}
        groups = []
        cards = []
        y = 0
        self.categories = atlas['categories']
        order = list(dict.fromkeys(list(self.c['domain']['categories']) + ['general']))
        cats = [c for c in order if any((n.get('category', 'general') == c for n in selected))] + sorted({n.get('category', 'general') for n in selected} - set(order))
        for i in range(0, len(cats), 2):
            rowheight = 0
            for (j, cat) in enumerate(cats[i:i + 2]):
                ns = sorted([n for n in selected if n.get('category', 'general') == cat], key=lambda n: ({'domain': 0, 'paper': 1, 'benchmark': 2}.get(n['kind'], 3), n['label']))
                x = j * 2900
                if overview:
                    domains = [n for n in ns if n['kind'] == 'domain']
                    papers = [n for n in ns if n['kind'] == 'paper']
                    cols = min(3, max(1, len(papers)))
                    domain_height = max(200, len(domains) * 200)
                    h = 160 + domain_height + (len(papers) + cols - 1) // cols * 380
                    for (k, n) in enumerate(domains):
                        cards.append(self.card(n, paths, x + 930, y + 65 + k * 200, 560, 150, brief=True))
                    for (k, n) in enumerate(papers):
                        cards.append(self.card(n, paths, x + 100 + (2400 - cols * 720) // 2 + k % cols * 720, y + 130 + domain_height + k // cols * 380, 560, 220, brief=True))
                else:
                    h = 160 + (len(ns) + 2) // 3 * 440
                    for (k, n) in enumerate(ns):
                        cards.append(self.card(n, paths, x + 100 + k % 3 * 800, y + 90 + k // 3 * 440, 620, 250, brief=True))
                rowheight = max(rowheight, h)
                groups.append({'id': 'group_' + cat, 'type': 'group', 'x': x, 'y': y, 'width': 2500, 'height': h, 'label': atlas['categories'].get(cat, {}).get('name', cat), 'color': atlas['categories'].get(cat, {}).get('color', '#92b2c5')})
            y += rowheight + 700
        edges = [{'id': e['id'], 'fromNode': e['source'], 'fromSide': 'top', 'toNode': e['target'], 'toSide': 'bottom', 'toEnd': 'arrow', 'color': '6'} for e in atlas['edges'] if e['source'] in ids and e['target'] in ids and (next((n for n in selected if n['id'] == e['source']))['kind'] == 'paper') and (next((n for n in selected if n['id'] == e['target']))['kind'] == 'domain')] if overview else [{'id': e['id'], 'fromNode': e['source'], 'fromSide': 'right', 'toNode': e['target'], 'toSide': 'left', 'toEnd': 'arrow', 'color': '4' if e['confidence'] == 'EXTRACTED' else '6'} for e in atlas['edges']]
        result = {'nodes': groups + cards, 'edges': edges}
        self.managed_json(self.root / '05-图谱' / ('论文与领域.canvas' if overview else '完整知识图谱.canvas'), result)
        if overview:
            self.managed_json(self.root / '05-图谱/论文总览 · 展开版.canvas', result)
            self.focus_canvases(atlas, paths)

    def card(self, n, paths, x, y, width, height, brief=False, id=None):
        summary = (n.get('summary') or n.get('description') or '').replace('\n', ' ')
        limit = 45 if brief else 82
        if len(summary) > limit:
            summary = summary[:limit - 1] + '…'
        text = '## ' + wiki(paths[n['id']], n['label']) + '\n\n' + summary
        if n['kind'] == 'paper':
            text += '\n\n' + wiki(self.c['prefix'] + '/05-图谱/单篇/' + clean(n['label']) + '.canvas', '查看单篇关系 →')
        return {'id': id or n['id'], 'type': 'text', 'text': text, 'x': x, 'y': y, 'width': width, 'height': height, 'color': self.atlas_category_color(n)}

    def atlas_category_color(self, n):
        categories = getattr(self, 'categories', self.c['domain']['categories'])
        return categories.get(n.get('category', 'general'), {}).get('color', '#92b2c5')

    def focus_canvases(self, atlas, paths):
        nodes = {n['id']: n for n in atlas['nodes']}
        cross = [e for e in atlas['edges'] if nodes[e['source']]['kind'] == 'paper' and nodes[e['target']]['kind'] == 'paper']
        cards = []
        edges = []
        for (i, e) in enumerate(cross):
            y = i * 600
            left = 'left_' + str(i)
            right = 'right_' + str(i)
            middle = 'evidence_' + str(i)
            cards += [self.card(nodes[e['source']], paths, 0, y, 580, 250, id=left), self.card(nodes[e['target']], paths, 1900, y, 580, 250, id=right)]
            cards.append({'id': middle, 'type': 'text', 'x': 850, 'y': y, 'width': 780, 'height': 300, 'color': '4' if e['confidence'] == 'EXTRACTED' else '6', 'text': '### ' + e['label'] + '\n\n**' + e['basis'] + '**\n\n' + e['evidence'] + '\n\n' + wiki(self.c['prefix'] + '/06-关系证据/' + e['id'] + '.md', '查看版本和原文出处')})
            color = '4' if e['confidence'] == 'EXTRACTED' else '6'
            edges += [{'id': e['id'] + '_a', 'fromNode': left, 'fromSide': 'right', 'toNode': middle, 'toSide': 'left', 'color': color}, {'id': e['id'] + '_b', 'fromNode': middle, 'fromSide': 'right', 'toNode': right, 'toSide': 'left', 'color': color}]
        self.managed_json(self.root / '05-图谱/跨论文关系.canvas', {'nodes': cards, 'edges': edges})
        for paper in [n for n in atlas['nodes'] if n['kind'] == 'paper']:
            related = [e for e in atlas['edges'] if paper['id'] in (e['source'], e['target'])]
            outgoing = {}
            incoming = {}
            for e in related:
                other = e['target'] if e['source'] == paper['id'] else e['source']
                (outgoing if e['source'] == paper['id'] else incoming).setdefault(other, []).append(e)
            height = max(len(outgoing), len(incoming), 1) * 430
            hub = 'hub'
            cards = [self.card(paper, paths, 0, (height - 260) // 2, 620, 260, id=hub)]
            edges = []
            for (side, entries) in [('in', incoming), ('out', outgoing)]:
                for (k, (other, es)) in enumerate(entries.items()):
                    cid = side + '_' + other
                    x = -1550 if side == 'in' else 1800
                    y = k * 430
                    card = self.card(nodes[other], paths, x, y, 650, 270, id=cid)
                    card['text'] += '\n\n' + ' · '.join((wiki(self.c['prefix'] + '/06-关系证据/' + e['id'] + '.md', '证据' + str(i + 1)) for (i, e) in enumerate(es)))
                    cards.append(card)
                    extracted = all((e['confidence'] == 'EXTRACTED' for e in es))
                    edges.append({'id': side + '_' + es[0]['id'], 'fromNode': cid if side == 'in' else hub, 'fromSide': 'right', 'toNode': hub if side == 'in' else cid, 'toSide': 'left', 'color': '4' if extracted else '6', 'label': ('事实 · ' if extracted else '归纳 · ') + ' / '.join((e['label'] for e in es))})
            self.managed_json(self.root / '05-图谱/单篇' / (clean(paper['label']) + '.canvas'), {'nodes': cards, 'edges': edges})

    def validate(self):
        failures = []
        wiki_count = 0
        image_count = 0
        for p in self.root.rglob('*.md'):
            if '系统' in p.relative_to(self.root).parts:
                continue
            text = p.read_text(encoding='utf-8')
            for target in re.findall('!?\\[\\[([^\\]]+)\\]\\]', text):
                wiki_count += 1
                target = target.split('|')[0]
                (file, _, heading) = target.partition('#')
                q = self.vault / file
                if not q.is_file():
                    q = Path(str(q) + '.md')
                if not q.is_file():
                    failures.append({'file': self.rel(p), 'target': target, 'error': 'Unresolved internal link'})
                elif heading and (not heading.startswith('^')) and (q.suffix == '.md') and (heading not in re.findall('^#{1,6}\\s+(.+?)\\s*$', q.read_text(encoding='utf-8'), re.M)):
                    failures.append({'file': self.rel(p), 'target': target, 'error': 'Missing embedded heading'})
            for target in re.findall('!\\[[^\\]]*\\]\\(([^)]+)\\)', text):
                image_count += 1
                target = unquote(target.split('#')[0])
                if re.match('[a-z]+:', target):
                    failures.append({'file': self.rel(p), 'target': target, 'error': 'Report image is not local'})
                elif not (p.parent / target).resolve().is_file():
                    failures.append({'file': self.rel(p), 'target': target, 'error': 'Missing image'})
        for p in (self.root / '05-图谱').rglob('*.canvas'):
            d = read(p)
            ids = {n['id'] for n in d['nodes']}
            if len(ids) != len(d['nodes']):
                failures.append({'file': str(p), 'error': 'Duplicate Canvas node IDs'})
            for n in d['nodes']:
                if n['type'] == 'file' and (not (self.vault / n['file']).is_file()):
                    failures.append({'file': str(p), 'error': 'Canvas file missing: ' + n['file']})
                if n['type'] == 'text':
                    for target in re.findall('!?\\[\\[([^\\]]+)\\]\\]', n['text']):
                        target = target.split('|')[0].split('#')[0]
                        q = self.vault / target
                        if not q.is_file() and (not Path(str(q) + '.md').is_file()):
                            failures.append({'file': str(p), 'error': 'Canvas note link missing: ' + target})
            boxes = [n for n in d['nodes'] if n['type'] != 'group']
            for (i, a) in enumerate(boxes):
                for b in boxes[i + 1:]:
                    if a['x'] < b['x'] + b['width'] and b['x'] < a['x'] + a['width'] and (a['y'] < b['y'] + b['height']) and (b['y'] < a['y'] + a['height']):
                        failures.append({'file': str(p), 'error': 'Overlapping Canvas cards: ' + a['id'] + ' / ' + b['id']})
            for e in d['edges']:
                if e['fromNode'] not in ids or e['toNode'] not in ids:
                    failures.append({'file': str(p), 'error': 'Dangling Canvas edge'})
        for p in (self.root / '附件/PDF').glob('*.pdf'):
            if not p.read_bytes().startswith(b'%PDF-'):
                failures.append({'file': str(p), 'error': 'Invalid PDF'})
        for p in (self.root / '附件/图表').rglob('*.png'):
            if not p.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):
                failures.append({'file': str(p), 'error': 'Invalid PNG'})
        (docs, errors) = self.report_descriptors()
        failures += errors
        index = read(self.system / 'collection-index.json')
        for key, canonicalize in [('arxiv_id', canonical_arxiv), ('doi', canonical_doi), ('pmid', canonical_pmid)]:
            try:
                identifiers = [canonicalize(r[key]) for r in index['records'] if r.get(key)]
                if len(set(identifiers)) != len(identifiers):
                    failures.append({'error': 'Duplicate paper identifiers: ' + key})
            except ValueError as error:
                failures.append({'error': str(error), 'field': key})
        result = {'checked_at': graph.now(), 'papers': len(index['records']), 'reports': len(docs), 'wikilinks': wiki_count, 'local_report_images': image_count, 'png_files': len(list((self.root / '附件/图表').rglob('*.png'))), 'pdf_files': len(list((self.root / '附件/PDF').glob('*.pdf'))), 'failures': failures}
        write(self.system / 'last-validation.json', result)
        if failures:
            raise ValueError(json.dumps(result, ensure_ascii=False))
        return result

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='command', required=True)
    p = sub.add_parser('plan')
    p.add_argument('--output', required=True)
    sub.add_parser('export')
    sub.add_parser('validate')
    f = sub.add_parser('finalize')
    f.add_argument('--plan', required=True)
    n = sub.add_parser('new-report')
    n.add_argument('--date', required=True)
    n.add_argument('--title', required=True)
    r = sub.add_parser('register')
    r.add_argument('--file', required=True)
    a = ap.parse_args()
    v = Vault()
    with file_lock(v.system / '.sync.lock'):
        if a.command == 'plan':
            result = v.plan(a.output)
        elif a.command == 'validate':
            result = v.validate()
        elif a.command == 'finalize':
            plan = read(a.plan)
            if plan.get('errors'):
                raise ValueError('Resolve plan errors before finalizing')
            result = v.export()
            v.validate()
            v.ack(plan)
        elif a.command == 'new-report':
            dt.date.fromisoformat(a.date)
            folder = v.root / '01-报告'
            folder.mkdir(exist_ok=True)
            existing = list(folder.glob(a.date + '｜*.md'))
            if len(existing) > 1:
                raise ValueError('Multiple reports for this date; inspect and resume the intended source')
            p = existing[0] if existing else folder / (a.date + '｜' + clean(v.c['domain']['name']) + '论文日报.md')
            if not p.exists():
                p.write_text(front({'type': 'report', 'source_id': uuid.uuid4().hex, 'title': a.date + '｜' + a.title, 'reading_date': a.date, 'complete': False, 'research_domain': v.c['domain']['name'], 'tags': ['research', domain_tag(v.c), 'report']}) + '# ' + a.title + '\n\n待完成正文、来源和本地附件后，将 complete 改为 true。\n', encoding='utf-8')
            result = {'path': str(p), 'source_id': split_note(p.read_text(encoding='utf-8'))[0]['source_id']}
        elif a.command == 'register':
            index_path = v.system / 'collection-index.json'
            index = read(index_path)
            candidates = read(a.file)
            added = 0
            skipped = 0
            if not isinstance(candidates, list):
                raise ValueError('Expected a paper record array')
            for r in candidates:
                if not r.get('title') or not r.get('read_version') or (not graph.url_ok(r.get('source_url'))):
                    raise ValueError('Full title, fixed read_version and original source_url are required')
                dt.date.fromisoformat(r['collected_on'])
                for k in ['pdf_local', 'report_file']:
                    p = (v.vault / r[k]).resolve()
                    if not p.is_relative_to(v.vault) or not p.is_file():
                        raise ValueError('Missing local ' + k)
                    r[k] = v.rel(p)
                if not (v.vault / r['pdf_local']).read_bytes().startswith(b'%PDF-'):
                    raise ValueError('Invalid PDF')
                (meta, body) = split_note((v.vault / r['report_file']).read_text(encoding='utf-8'))
                if meta.get('research_domain', v.c['domain']['name']) != v.c['domain']['name']:
                    raise ValueError('Report belongs to another research domain')
                if len(strip_generated(body)) < 80:
                    raise ValueError('Incomplete report body')
                for target in re.findall('!\\[[^\\]]*\\]\\(([^)]+)\\)', body):
                    image = (v.vault / r['report_file']).parent / unquote(target)
                    if re.match('[a-z]+:', target) or not image.resolve().is_relative_to(v.vault) or (not image.is_file()):
                        raise ValueError('Missing or nonlocal report image: ' + target)
                if meta.get('complete') is not True:
                    raise ValueError('Report is not marked complete')
                if not re.fullmatch('[a-f0-9]{32}', str(meta.get('source_id', '')).replace('-', '')):
                    raise ValueError('Missing stable source_id')
                if (v.vault / r['report_file']).parent.resolve() != (v.root / '01-报告').resolve():
                    raise ValueError('Report must be in the canonical reports directory')
                arxiv = canonical_arxiv(r.get('arxiv_id'))
                r['arxiv_id'] = arxiv or None
                if r.get('doi'):
                    r['doi'] = canonical_doi(r['doi'])
                if r.get('pmid'):
                    r['pmid'] = canonical_pmid(r['pmid'])
                duplicate = False
                for old in index['records']:
                    same = (bool({graph.norm(t) for t in [old['title']] + old.get('verified_title_aliases', [])} & {graph.norm(t) for t in [r['title']] + r.get('verified_title_aliases', [])})
                            or bool(arxiv and canonical_arxiv(old.get('arxiv_id')) == arxiv)
                            or bool(r.get('doi') and canonical_doi(old.get('doi')) == r['doi'])
                            or bool(r.get('pmid') and canonical_pmid(old.get('pmid')) == r['pmid']))
                    if same:
                        if all((old.get(k) == r.get(k) for k in ['title', 'report_file', 'pdf_local', 'read_version'])):
                            duplicate = True
                            break
                        raise ValueError('Paper already archived; update its existing report instead: ' + old['title'])
                if duplicate:
                    skipped += 1
                    continue
                added += 1
                r.update(normalized_title=graph.norm(r['title']), status='awaiting_graph')
                index['records'].append(r)
            index['updated_at'] = graph.now()
            write(index_path, index)
            result = {'registered': added, 'already_registered': skipped, 'total': len(index['records'])}
        else:
            result = v.export()
    print(json.dumps(result, ensure_ascii=False, indent=2))
if __name__ == '__main__':
    main()
