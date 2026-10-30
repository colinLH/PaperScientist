#!/usr/bin/env python3
"""Versioned local reports -> property graph -> optional website snapshot."""
import argparse, copy, datetime as dt, hashlib, json, os, re, shutil, tempfile, unicodedata, zipfile
from urllib.parse import quote
from collections import Counter
from pathlib import Path
from runtime_support import file_lock, load_config
SCHEMA = 2
KINDS = {'paper', 'domain', 'concept', 'method', 'benchmark', 'source'}
DEFAULT_CATEGORIES = {'redteam': {'name': '自动化红队评估', 'color': '#e0ae66'}, 'attack': {'name': '注入机制与攻击', 'color': '#e17e80'}, 'alignment': {'name': '模型对齐防御', 'color': '#b2a3f7'}, 'control': {'name': '执行边界与自主性', 'color': '#65c8ad'}, 'general': {'name': '跨领域概念', 'color': '#92b2c5'}}

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def dumps(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

def digest(x):
    return hashlib.sha256((x if isinstance(x, str) else dumps(x)).encode()).hexdigest()

def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))

def write(p, x):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    t = p.with_name(p.name + '.tmp')
    t.write_text(json.dumps(x, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(t, p)

def norm(s):
    return ''.join((c for c in unicodedata.normalize('NFKC', str(s)).casefold() if c.isalnum()))

def slug(s):
    return re.sub('[^a-z0-9]+', '_', str(s).lower()).strip('_')

def url_ok(s):
    return bool(re.match('https?://', s or ''))

def unwrap(d):
    if d.get('structuredContent'):
        return d['structuredContent']
    if d.get('content') and (not d.get('text')):
        return json.loads(next((x['text'] for x in d['content'] if x['type'] == 'text')))
    return d

def source(d):
    d = unwrap(d)
    if d.get('truncated') or d.get('unknown_block_count', 0) or d.get('unknown_block_ids'):
        raise ValueError('Incomplete source; refusing to replace last good source')
    text = d.get('text', '')
    m = re.search('<content>\\s*([\\s\\S]*?)\\s*</content>', text)
    body = (m.group(1) if m else text).replace('\r\n', '\n').strip()
    if not body:
        raise ValueError('Empty source')
    pid = re.sub('[^a-f0-9]', '', d['id'].lower())
    if len(pid) != 32:
        raise ValueError('Expected a stable 32-character source UUID')
    title = d['title'].lstrip('📚📁 ').strip()
    match = re.search('20\\d\\d-\\d\\d-\\d\\d', title)
    date = d.get('reading_date') or (match.group() if match else (d.get('page_last_edited_at') or now())[:10])
    source_type = d.get('source_type', 'notion')
    url = 'https://app.notion.com/p/' + pid
    if source_type == 'obsidian':
        vault = Path(d['vault_root']).resolve()
        file = (vault / d['relative_path']).resolve()
        if not file.is_relative_to(vault) or not file.is_file():
            raise ValueError('Missing or invalid Obsidian source path')
        url = 'obsidian://open?path=' + quote(str(file), safe='')
    elif source_type != 'notion':
        raise ValueError('Unsupported source type')
    result = {'id': pid, 'url': url, 'source_type': source_type, 'title': title, 'date': date, 'last_edited_at': d.get('page_last_edited_at'), 'text': text, 'body': body, 'hash': digest({'title': title, 'body': body}), 'captured_at': now()}
    for key in ['vault_root', 'relative_path', 'original_notion_url', 'original_notion_hash']:
        if d.get(key):
            result[key] = d[key]
    return result

def identity(s, n):
    kind = n.get('kind')
    label = n.get('label', '').strip()
    if kind not in KINDS or not label:
        raise ValueError('Invalid entity kind or missing label')
    if not re.fullmatch('[a-z][a-z0-9_]{0,48}', n.get('category', 'general')):
        raise ValueError('Invalid category key')
    ident = n.get('identity', {})
    paper = kind == 'paper'
    keys = []
    strong = {}
    if paper:
        arxiv = ident.get('arxiv') or n.get('arxiv_id')
        if not arxiv:
            m = re.search('(?:arxiv\\.org/(?:abs|pdf)/|arxiv:)(\\d{4}\\.\\d{4,5})', n.get('paper_url', ''), re.I)
            arxiv = m.group(1) if m else None
        if arxiv:
            arxiv = re.sub('v\\d+$', '', arxiv.removeprefix('arXiv:').strip(), flags=re.I)
            if not re.fullmatch('\\d{4}\\.\\d{4,5}', arxiv):
                raise ValueError('Invalid arxiv id')
            strong['arxiv'] = arxiv
            keys.append('paper:arxiv:' + arxiv)
        doi = ident.get('doi') or n.get('doi')
        if doi:
            doi = re.sub('^https?://(?:dx\\.)?doi\\.org/', '', doi.strip(), flags=re.I).lower()
            if not doi.startswith('10.'):
                raise ValueError('Invalid DOI')
            strong['doi'] = doi
            keys.append('paper:doi:' + doi)
        full = n.get('full_title') or ident.get('title')
        if full:
            keys.append('paper:title:' + norm(full))
        for alias in n.get('verified_title_aliases', []):
            keys.append('paper:title:' + norm(alias))
        if not keys:
            raise ValueError('Paper requires verified arxiv, DOI or full_title: ' + label)
    else:
        keys = ['entity:' + kind + ':' + norm(label)]
    for alias in n.get('aliases', []):
        if not paper:
            keys.append('entity:' + kind + ':' + norm(alias))
    candidates = {s['alias_index'][k] for k in keys if k in s['alias_index']}
    same = ident.get('same_as')
    if same:
        if same not in s['entities'] or not ident.get('reason'):
            raise ValueError('Explicit promotion needs an existing id and source-supported reason')
        candidates.add(same)
    if len(candidates) > 1:
        raise ValueError('Identity collision requires review: ' + label)
    if candidates:
        nid = candidates.pop()
        old = s['entities'][nid]
        for (k, v) in strong.items():
            if k in old.get('strong', {}) and old['strong'][k] != v:
                raise ValueError('Conflicting identifiers: ' + label)
    else:
        if strong.get('arxiv'):
            nid = 'paper_arxiv_' + slug(strong['arxiv'])
        elif strong.get('doi'):
            nid = 'paper_doi_' + digest(strong['doi'])[:20]
        else:
            nid = kind + '_' + digest(keys[0])[:20]
        s['entities'][nid] = {'kind': kind, 'strong': {}, 'template': {}}
    ent = s['entities'][nid]
    ent['strong'].update(strong)
    if paper:
        ent['kind'] = 'paper'
    ent['template'] = {**ent['template'], **n, 'id': nid, 'kind': ent['kind']}
    for k in keys:
        s['alias_index'][k] = nid
    return nid

def blank():
    return {'schema_version': SCHEMA, 'created_at': now(), 'updated_at': None, 'entities': {}, 'alias_index': {}, 'legacy_ids': {}, 'sources': {}, 'discovery_baseline': {}, 'schedule': {'status': 'not_registered'}}

def paths(workspace, site=None):
    w = Path(workspace).resolve()
    return {'w': w, 'site': Path(site).resolve() if site else w / 'work/site', 'sync': w / 'work/sync', 'out': w / 'outputs/ai-safety-graph'}

def load(p):
    pointer = p['sync'] / 'current.json'
    if pointer.exists():
        return read(p['sync'] / 'generations' / read(pointer)['generation'] / 'state.json')
    fallback = p['site'] / 'data/state.json'
    return read(fallback) if fallback.exists() else blank()

def add_revision(state, doc, extraction):
    if extraction.get('complete') is not True:
        raise ValueError('Extraction must explicitly declare complete=true')
    if extraction.get('source_id', '').replace('-', '') != doc['id'] or extraction.get('content_hash') != doc['hash']:
        raise ValueError('Extraction is not bound to fetched content hash')
    if not isinstance(extraction.get('nodes'), list) or not isinstance(extraction.get('edges'), list):
        raise ValueError('Missing extraction lists')
    if not extraction['nodes']:
        raise ValueError('Empty extraction cannot replace last good content')
    old = state['sources'].get(doc['id'])
    if old and old['current_hash'] == doc['hash']:
        return False
    local = {}
    for n in extraction['nodes']:
        if n['id'] in local:
            raise ValueError('Duplicate local node id')
        local[n['id']] = identity(state, n)

    def resolve(ref):
        if ref in local:
            return local[ref]
        if ref in state['legacy_ids']:
            return state['legacy_ids'][ref]
        if ref in state['entities']:
            return ref
        raise ValueError('Dangling endpoint ' + str(ref))
    canonical = copy.deepcopy(extraction)
    for n in canonical['nodes']:
        n['id'] = local[n['id']]
    for e in canonical['edges']:
        e['source'] = resolve(e['source'])
        e['target'] = resolve(e['target'])
        if e['source'] == e['target']:
            raise ValueError('Self-loop after identity merge')
        if e.get('confidence') not in {'EXTRACTED', 'INFERRED', 'AMBIGUOUS'}:
            raise ValueError('Missing confidence')
        if e.get('confidence') == 'EXTRACTED' and e.get('confidence_score') != 1:
            raise ValueError('Explicit source confidence must be 1')
        if not e.get('evidence') or not url_ok(e.get('evidence_url')) or (not e.get('source_location')):
            raise ValueError('Every edge needs evidence, evidence_url and source_location')
        if not e.get('relation') or not e.get('basis'):
            raise ValueError('Missing relation or basis')
    record = state['sources'].setdefault(doc['id'], {'current_hash': None, 'revisions': {}})
    record['revisions'][doc['hash']] = {'source': doc, 'extraction': canonical, 'ingested_at': now()}
    record['current_hash'] = doc['hash']
    return True

def aggregate(state):
    nodes = {}
    edges = {}
    sources = []
    for (pid, record) in sorted(state['sources'].items()):
        version = record['revisions'][record['current_hash']]
        doc = version['source']
        x = version['extraction']
        sources.append({k: doc[k] for k in ['id', 'title', 'date', 'url', 'hash', 'last_edited_at']})
        ref = {'page_id': pid, 'title': doc['title'], 'url': doc['url'], 'content_hash': doc['hash'], 'last_edited_at': doc['last_edited_at'], 'reading_date': doc['date'], 'captured_at': doc['captured_at']}
        for n in x['nodes']:
            nid = n['id']
            current = nodes.setdefault(nid, {**state['entities'][nid]['template'], 'id': nid, 'source_refs': [], 'reading_dates': []})
            if not (state['entities'][nid]['kind'] == 'paper' and n.get('kind') != 'paper'):
                current.update({k: v for (k, v) in n.items() if v is not None and k not in {'id', 'date', 'source_refs', 'reading_dates'}})
            current['kind'] = state['entities'][nid]['kind']
            if ref not in current['source_refs']:
                current['source_refs'].append(ref)
            if current.get('kind') == 'paper':
                current['reading_dates'] = sorted(set(current['reading_dates'] + [doc['date']]))
                current['date'] = current['reading_dates'][0]
        for e in x['edges']:
            for nid in [e['source'], e['target']]:
                if nid not in nodes:
                    nodes[nid] = {**state['entities'][nid]['template'], 'id': nid, 'source_refs': [], 'reading_dates': []}
            key = [e['source'], e['relation'], e['target'], e['confidence'], e['basis']]
            eid = 'rel_' + digest(key)[:20]
            edge = edges.setdefault(eid, {**e, 'id': eid, 'provenance': []})
            prov = {**ref, 'evidence': e['evidence'], 'evidence_url': e['evidence_url'], 'source_location': e['source_location'], 'confidence': e['confidence'], 'basis': e['basis']}
            prov['id'] = 'evidence_' + digest([pid, doc['hash'], key, prov['evidence'], prov['source_location']])[:24]
            if not any((p['id'] == prov['id'] for p in edge['provenance'])):
                edge['provenance'].append(prov)
    for n in nodes.values():
        if n.get('source_refs'):
            n['source_url'] = n['source_refs'][0]['url']
        n.pop('_origin', None)
    categories = copy.deepcopy(DEFAULT_CATEGORIES)
    for n in nodes.values():
        cat = n.get('category', 'general')
        if cat not in categories:
            categories[cat] = {'name': next((m['label'] for m in nodes.values() if m.get('kind') == 'domain' and m.get('category') == cat), cat), 'color': '#a5b3c7'}
    graph_hash = digest({'nodes': nodes, 'edges': edges, 'sources': sources})
    return {'metadata': {'title': 'AI安全文献知识图谱', 'schema_version': SCHEMA, 'updated_at': state['updated_at'], 'snapshot_date': max((d['date'] for d in sources), default=now()[:10]), 'timezone': state['schedule'].get('timezone', 'UTC'), 'papers': sum((n.get('kind') == 'paper' for n in nodes.values())), 'source_pages': len(sources), 'source_revisions': sum((len(s['revisions']) for s in state['sources'].values())), 'storage': 'LadybugDB 0.17.0', 'automatic_sync': state['schedule'].get('status') == 'ACTIVE', 'sync_execution': 'Codex automation', 'schedule': state['schedule'], 'graph_hash': graph_hash, 'exported_from_persisted_database': True}, 'nodes': sorted(nodes.values(), key=lambda n: n['id']), 'edges': sorted(edges.values(), key=lambda e: e['id']), 'sources': sources, 'categories': categories}

def database(path, atlas):
    import ladybug
    db = ladybug.Database(path, buffer_pool_size=128 * 1024 * 1024, max_num_threads=2, backend='pybind')
    c = ladybug.Connection(db)
    c.execute('CREATE NODE TABLE Entity(id STRING PRIMARY KEY, label STRING, kind STRING, category STRING, date STRING, description STRING, sourceUrl STRING, attributes STRING)')
    c.execute('CREATE REL TABLE Link(FROM Entity TO Entity, id STRING, relation STRING, label STRING, confidence STRING, confidenceScore DOUBLE, basis STRING, evidence STRING, evidenceUrl STRING, sourceFile STRING, sourceLocation STRING, attributes STRING)')
    for n in atlas['nodes']:
        c.execute('CREATE (n:Entity {id:$id,label:$label,kind:$kind,category:$category,date:$date,description:$description,sourceUrl:$sourceUrl,attributes:$attributes})', {'id': n['id'], 'label': n['label'], 'kind': n['kind'], 'category': n.get('category', 'general'), 'date': n.get('date') or '', 'description': n.get('description') or '', 'sourceUrl': n.get('source_url') or '', 'attributes': 'json:' + dumps(n)})
    for e in atlas['edges']:
        props = {'source': e['source'], 'target': e['target'], 'id': e['id'], 'relation': e['relation'], 'label': e.get('label', e['relation']), 'confidence': e['confidence'], 'confidenceScore': float(e.get('confidence_score', 0)), 'basis': e['basis'], 'evidence': e['evidence'], 'evidenceUrl': e['evidence_url'], 'sourceFile': e.get('source_file', ''), 'sourceLocation': e['source_location'], 'attributes': 'json:' + dumps(e)}
        c.execute('MATCH (a:Entity {id:$source}), (b:Entity {id:$target}) CREATE (a)-[:Link {id:$id,relation:$relation,label:$label,confidence:$confidence,confidenceScore:$confidenceScore,basis:$basis,evidence:$evidence,evidenceUrl:$evidenceUrl,sourceFile:$sourceFile,sourceLocation:$sourceLocation,attributes:$attributes}]->(b)', props)
    c.execute('CHECKPOINT')
    c.close()
    db.close()
    db = ladybug.Database(path, read_only=True, buffer_pool_size=128 * 1024 * 1024, backend='pybind')
    c = ladybug.Connection(db)
    stored_nodes = [json.loads(r[0][5:]) for r in c.execute('MATCH (n:Entity) RETURN n.attributes').get_all()]
    stored_edges = [json.loads(r[0][5:]) for r in c.execute('MATCH (:Entity)-[r:Link]->(:Entity) RETURN r.attributes').get_all()]
    assert len(stored_nodes) == len(atlas['nodes']) and len(stored_edges) == len(atlas['edges'])
    assert all((e['provenance'] for e in stored_edges))
    atlas['nodes'] = stored_nodes
    atlas['edges'] = stored_edges
    c.close()
    db.close()
    return {'reopened': True, 'nodes': len(stored_nodes), 'edges': len(stored_edges), 'provenance_assertions': sum((len(e['provenance']) for e in stored_edges))}

def native(atlas, path):
    if not atlas['nodes']:
        (path / 'graphify.html').write_text('<!doctype html><meta charset="utf-8"><p>暂无已同步论文。</p>', encoding='utf-8')
        write(path / 'graphify.json', {'nodes': [], 'edges': []})
        return 0
    import networkx as nx
    from graphify.cluster import cluster
    from graphify.export import to_html, to_json
    g = nx.DiGraph()
    for n in atlas['nodes']:
        g.add_node(n['id'], **{k: v for (k, v) in n.items() if k not in {'id', 'file_type'}}, file_type='paper' if n['kind'] == 'paper' else 'concept')
    for e in atlas['edges']:
        if g.has_edge(e['source'], e['target']):
            previous = g[e['source']][e['target']]
            previous['relation'] += ' / ' + e['relation']
            previous['confidence'] = 'MIXED'
        else:
            g.add_edge(e['source'], e['target'], **{k: v for (k, v) in e.items() if k not in {'source', 'target'}})
    communities = cluster(g)
    labels = {cid: Counter((atlas['categories'].get(g.nodes[n].get('category'), {'name': '跨领域'})['name'] for n in ns)).most_common(1)[0][0] for (cid, ns) in communities.items()}
    assert to_html(g, communities, str(path / 'graphify.html'), community_labels=labels)
    to_json(g, communities, str(path / 'graphify.json'), force=True, community_labels=labels)
    for (cid, ns) in communities.items():
        for nid in ns:
            next((n for n in atlas['nodes'] if n['id'] == nid)).update(community=cid, community_name=labels[cid])
    return len(communities)

def commit(p, state, reason):
    state['updated_at'] = now()
    if os.environ.get('AI_SAFETY_OBSIDIAN_CONFIG'):
        config = load_config()
        state['schedule'].update(timezone=config['timezone'], collect_at=config['collect_at'], sync_at=config['sync_at'])
    atlas = aggregate(state)
    generation = now().replace(':', '').replace('.', '') + '_' + atlas['metadata']['graph_hash'][:10]
    dest = p['sync'] / 'generations' / generation
    dest.mkdir(parents=True)
    try:
        native(atlas, dest)
        validation = database(dest / 'ai-safety.lbug', atlas)
        validation.update(verified_at=now(), reason=reason, graph_hash=atlas['metadata']['graph_hash'], source_pages=len(state['sources']), source_revisions=atlas['metadata']['source_revisions'])
        write(dest / 'atlas.json', atlas)
        write(dest / 'state.json', state)
        write(dest / 'validation.json', validation)
        write(p['sync'] / 'current.json', {'generation': generation, 'graph_hash': atlas['metadata']['graph_hash']})
    except Exception:
        shutil.rmtree(dest)
        raise
    export(p)
    return validation

def export(p):
    current = read(p['sync'] / 'current.json')
    gen = p['sync'] / 'generations' / current['generation']
    p['out'].mkdir(parents=True, exist_ok=True)
    for name in ['atlas.json', 'ai-safety.lbug', 'validation.json', 'graphify.html', 'graphify.json']:
        tmp = p['out'] / (name + '.tmp')
        shutil.copy(gen / name, tmp)
        os.replace(tmp, p['out'] / name)
    for name in ['atlas.json', 'graphify.html']:
        target = p['site'] / 'dist' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(gen / name, target)
    write(p['site'] / 'data/state.json', read(gen / 'state.json'))
    write(p['site'] / 'data/sync-status.json', {'generation': current['generation'], 'graph_hash': current['graph_hash']})
    docs = p['out'] / 'sources'
    docs.mkdir(exist_ok=True)
    state = read(gen / 'state.json')
    for (pid, r) in state['sources'].items():
        for (h, v) in r['revisions'].items():
            write(docs / pid / (h + '.json'), v['source'])
    write(p['out'] / 'provenance-registry.json', state)
    for name in ['index.html', 'style.css', 'app.js', 'obsidian-links.json']:
        if (p['site'] / 'dist' / name).exists():
            shutil.copy(p['site'] / 'dist' / name, p['out'] / name)
    automation = p['out'] / 'automation'
    automation.mkdir(exist_ok=True)
    for name in ['graph_sync.py', 'obsidian_sync.py', 'requirements.txt']:
        if (p['site'] / 'scripts' / name).exists():
            shutil.copy(p['site'] / 'scripts' / name, automation / name)
    if (p['site'] / 'AUTOMATION.md').exists():
        shutil.copy(p['site'] / 'AUTOMATION.md', automation / 'RUNBOOK.md')
    atlas = read(gen / 'atlas.json')
    payload = {'nodes': [{'id': n['id'], 'props': {**{k: v for (k, v) in n.items() if isinstance(v, (str, int, float, bool))}, 'sourceRefsJson': dumps(n.get('source_refs', []))}} for n in atlas['nodes']], 'edges': [{'id': e['id'], 'source': e['source'], 'target': e['target'], 'props': {**{k: v for (k, v) in e.items() if k not in {'id', 'source', 'target'} and isinstance(v, (str, int, float, bool))}, 'provenanceJson': dumps(e['provenance'])}} for e in atlas['edges']]}
    write(p['out'] / 'neo4j-data.json', payload)
    write(p['out'] / 'neo4j-schema.json', {'schema_retrieved_at': now(), 'status': 'defined, not connected to live Neo4j', 'node_labels': {'Entity': sorted({'id'} | {k for n in payload['nodes'] for k in n['props']})}, 'relationship_types': {'LINK': {'from': 'Entity', 'to': 'Entity', 'properties': sorted({k for e in payload['edges'] for k in e['props']})}}, 'constraints': ['Entity.id UNIQUE']})
    import networkx as nx
    g = nx.DiGraph()
    for n in atlas['nodes']:
        g.add_node(n['id'], label=n['label'], kind=n['kind'], category=n.get('category', 'general'))
    for e in atlas['edges']:
        g.add_edge(e['source'], e['target'], relation=e['relation'], confidence=e['confidence'], provenance=dumps(e['provenance']))
    nx.write_graphml(g, p['out'] / 'graph.graphml')
    (p['out'] / 'GRAPH_REPORT.md').write_text(f"# AI安全图谱自动更新\n\n更新时间：{atlas['metadata']['updated_at']}\n\n论文 {atlas['metadata']['papers']} 篇，节点 {len(atlas['nodes'])}，关系 {len(atlas['edges'])}，来源页面 {len(atlas['sources'])}，版本 {atlas['metadata']['source_revisions']}。\n\n每条关系的 provenance 数组记录页面、内容哈希、证据、原文链接和位置。历史更正保存在 provenance-registry.json，当前图只采用每页的最新成功版本。原生 Graphify / GraphML 为每对端点的聚合视图；完整关系类型与所有出处以 atlas.json 和图数据库为准。\n\nToken成本不可从Agent工具可靠取得。\n", encoding='utf-8')
    down = p['site'] / 'dist/downloads'
    down.mkdir(parents=True, exist_ok=True)
    readme = p['out'] / 'README.md'
    if not readme.exists():
        shutil.copy(Path(__file__).resolve().parents[1] / 'assets/EXPORT_README.md', readme)
    for name in ['validation.json', 'README.md']:
        shutil.copy(p['out'] / name, down / name)
    archive = p['w'] / 'outputs/ai-safety-graph.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for file in sorted(p['out'].rglob('*')):
            if file.is_file():
                z.write(file, Path('ai-safety-graph') / file.relative_to(p['out']))
    shutil.copy(archive, down / archive.name)
    links = p['site'] / 'dist/obsidian-links.json'
    write(p['sync'] / 'last-bundle.json', {
        'graph_hash': current['graph_hash'],
        'links_hash': digest(read(links)) if links.exists() else None,
        'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
    })
    config = load_config() if os.environ.get('AI_SAFETY_OBSIDIAN_CONFIG') else {}
    site = config.get('site', {})
    if not site.get('enabled'):
        return
    pending_file = p['sync'] / 'pending-publication.json'
    previous = read(pending_file) if pending_file.exists() else {}
    if previous.get('generation') == current['generation']:
        return
    if previous:
        write(p['sync'] / 'publication-history' / (previous['generation'] + '.json'), previous)
    write(pending_file, {'graph_hash': current['graph_hash'], 'generation': current['generation'], 'project_id': site['project_id'], 'status': 'needs_publication'})

def export_current(p):
    pointer = p['sync'] / 'current.json'
    if not pointer.exists():
        return True
    marker = p['sync'] / 'last-bundle.json'
    archive = p['w'] / 'outputs/ai-safety-graph.zip'
    links = p['site'] / 'dist/obsidian-links.json'
    if not marker.exists() or not archive.exists():
        return False
    saved = read(marker)
    return (saved.get('graph_hash') == read(pointer)['graph_hash']
            and saved.get('links_hash') == (digest(read(links)) if links.exists() else None)
            and saved.get('archive_sha256') == hashlib.sha256(archive.read_bytes()).hexdigest())

def plan(p, inbox):
    s = load(p)
    rows = []
    for f in sorted(Path(inbox).glob('*.json')):
        doc = source(read(f))
        previous = s['sources'].get(doc['id'])
        status = 'unchanged' if previous and previous['current_hash'] == doc['hash'] else 'changed' if previous else 'new'
        rows.append({'page_id': doc['id'], 'title': doc['title'], 'hash': doc['hash'], 'status': status, 'fetch_file': str(f.resolve())})
    result = {'checked_at': now(), 'pages': rows, 'needs_extraction': [r for r in rows if r['status'] != 'unchanged']}
    write(p['sync'] / 'plan.json', result)
    write(p['sync'] / 'last-check.json', {'checked_at': now(), 'checked_pages': len(rows), 'needs_extraction': len(result['needs_extraction'])})
    return result

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workspace', required=True)
    ap.add_argument('--site')
    sub = ap.add_subparsers(dest='command', required=True)
    q = sub.add_parser('plan')
    q.add_argument('--inbox', required=True)
    a = sub.add_parser('apply')
    a.add_argument('--batch', required=True)
    sub.add_parser('export')
    sub.add_parser('status')
    cs = sub.add_parser('configure-schedule')
    cs.add_argument('--automation-id', required=True)
    m = sub.add_parser('mark-published')
    m.add_argument('--receipt', required=True)
    args = ap.parse_args()
    p = paths(args.workspace, args.site)
    p['sync'].mkdir(parents=True, exist_ok=True)
    with file_lock(p['sync'] / 'lock'):
        if args.command == 'plan':
            result = plan(p, args.inbox)
        elif args.command == 'configure-schedule':
            state = load(p)
            state['schedule'].update(status='ACTIVE', automation_id=args.automation_id)
            result = commit(p, state, 'registered Codex automation')
        elif args.command == 'apply':
            state = load(p)
            changes = 0
            for row in read(args.batch):
                doc = source(read(row['fetch_file']))
                if doc['source_type'] == 'obsidian':
                    from obsidian_sync import Vault
                    current_docs, errors = Vault(load_config()).report_descriptors()
                    if errors or current_docs.get(doc['id'], {}).get('doc', {}).get('hash') != doc['hash']:
                        raise ValueError('Source changed or became invalid after plan; regenerate plan and extraction')
                changes += add_revision(state, doc, read(row['extraction_file']))
            result = commit(p, state, f'{changes} changed source pages') if changes else {'changed': False, 'message': 'No changes; graph and publication unchanged'}
        elif args.command == 'export':
            export(p)
            result = {'exported': True}
        elif args.command == 'mark-published':
            receipt = read(args.receipt)
            pending = read(p['sync'] / 'pending-publication.json')
            if receipt.get('status') != 'succeeded' or any((not pending.get(k) or receipt.get(k) != pending[k] for k in ['graph_hash', 'project_id', 'commit_sha', 'version_id'])) or (not receipt.get('deployment_id')) or (receipt.get('url') != load_config()['site']['url']):
                raise ValueError('Verified matching deployment receipt required')
            write(p['sync'] / 'last-publication.json', receipt)
            (p['sync'] / 'pending-publication.json').unlink()
            result = {'published': True, 'url': receipt['url']}
        else:
            state = load(p)
            result = {'sources': len(state['sources']), 'source_revisions': sum((len(r['revisions']) for r in state['sources'].values())), 'papers': sum((n['kind'] == 'paper' for n in aggregate(state)['nodes'])), 'current': read(p['sync'] / 'current.json') if (p['sync'] / 'current.json').exists() else None, 'pending_publication': read(p['sync'] / 'pending-publication.json') if (p['sync'] / 'pending-publication.json').exists() else None}
        print(json.dumps(result, ensure_ascii=False, indent=2))
if __name__ == '__main__':
    main()
