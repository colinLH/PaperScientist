"""Python adapter for Top-Conf Figure Gallery + editable local figure production."""
from __future__ import annotations

import asyncio
from collections import Counter
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory
import time

from . import evidence, figure_render, micu_images

UPSTREAM = 'https://github.com/qwdwqfwq/topconf-paper-figure-gallery'
GALLERY = 'https://qwdwqfwq.github.io/topconf-paper-figure-gallery/'
SOURCE = Path(__file__).resolve().parents[1] / 'external_skills' / 'figureforge'


@lru_cache(maxsize=1)
def _index(path, mtime):
    rows = json.loads(Path(path).read_text(encoding='utf-8'))
    docs = [Counter(re.findall(r'[a-z0-9]+', ' '.join(str(row.get(k,'')) for k in ('title','pattern','venue')).lower())) for row in rows]
    df = Counter(term for doc in docs for term in doc)
    return rows,docs,df,sum(map(lambda d:sum(d.values()),docs))/max(1,len(docs))


def search_references(query, limit=5):
    path = SOURCE / '_source' / 'forge' / 'data' / 'figures.json'
    if not path.is_file():
        return {'available':False,'references':[], 'action':'Run python scripts/install_research_skills.py --source figureforge', 'upstream':UPSTREAM}
    rows,docs,df,avg = _index(str(path),path.stat().st_mtime_ns)
    terms=set(re.findall(r'[a-z0-9]+',query.lower()))
    rankings=[]
    for row,doc in zip(rows,docs):
        score=0
        for term in terms:
            tf=doc.get(term,0)
            score += math.log(1+(len(rows)-df[term]+.5)/(df[term]+.5))*tf*2.2/(tf+1.2*(.25+.75*sum(doc.values())/avg)) if tf else 0
        if score:rankings.append((score,row))
    rankings.sort(key=lambda x:(-x[0],x[1]['id']))
    references=[{**row,'match_score':round(score,3),'image_url':GALLERY+row['image']} for score,row in rankings[:max(1,min(limit,8))]]
    meta=json.loads((SOURCE/'.source.json').read_text(encoding='utf-8'))
    return {'available':True,'upstream':UPSTREAM,'commit':meta['commit'],'catalog_size':len(rows),'references':references,
            'retrieval':'local BM25 over pinned figure metadata; no CLIP/model download',
            'reuse':'Layout inspiration only. Paper images retain their authors’ rights; do not copy scientific content or data.'}


def _prepare_spec(store, sid, spec_path):
    source=store.file(sid,spec_path)
    if source.stat().st_size>500000:
        raise ValueError('Figure spec must be at most 500KB')
    raw = source.read_bytes()
    spec = json.loads(raw)
    if spec.get('type') not in {'results','framework','illustration','framework_plate'}:
        raise ValueError('Figure spec type must be results, framework, framework_plate or illustration; load figure-forge for examples')
    layout_binding = None
    if spec.get('manuscript'):
        from .manuscript_layout import load_contract, dimensions, _contract_path
        manuscript = store.file(sid, spec['manuscript'])
        contract = load_contract(manuscript)
        if not contract:
            raise ValueError('Configure the manuscript layout before producing publication figures')
        scope = spec.get('figure_scope', 'column')
        if scope not in {'column', 'page'}:
            raise ValueError('figure_scope must be column or page')
        if scope == 'page' and contract['columns'] == 'double' and not contract['allow_wide_figures']:
            raise ValueError('The manuscript contract does not authorize spanning figures')
        limits = dimensions(contract)
        width = limits['text_width_inches' if scope == 'page' else 'column_width_inches']
        size = spec.setdefault('size', [round(width, 3), min(5.8, limits['max_figure_height_inches'])])
        if float(size[0]) > width + .015 or float(size[1]) > limits['max_figure_height_inches']:
            raise ValueError(f'Figure must be designed within {width:.3f} × {limits["max_figure_height_inches"]:.3f} inches. Reflow or split panels; do not shrink a wide diagram during inclusion.')
        layout_binding = {'manuscript': spec['manuscript'], 'scope': scope,
                          'target_width_inches': width, 'minimum_font_pt': contract['min_figure_font_pt'],
                          'contract_sha256': hashlib.sha256(_contract_path(manuscript).read_bytes()).hexdigest()}
    return spec, layout_binding, hashlib.sha256(raw).hexdigest()


def create_figure(store, sid, spec_path, brief):
    """Synchronous entry point for local vector figures."""
    spec, layout_binding, digest = _prepare_spec(store, sid, spec_path)
    if spec['type'] in {'illustration', 'framework_plate'}:
        raise ValueError('Use the configured figure_forge agent tool for image generation')
    return _create_vector(store, sid, spec, brief, layout_binding, digest)


async def create_agent_figure(store, sid, spec_path, brief, settings, plot_lock):
    spec, layout_binding, digest = _prepare_spec(store, sid, spec_path)
    if spec['type'] == 'framework_plate':
        from . import micu_plates
        folder, report = await micu_plates.create_plate(
            store, sid, spec, settings, plot_lock, layout_binding, digest)
        report['references'] = await asyncio.to_thread(search_references, brief)
        return _register_bundle(store, sid, folder, report, layout_binding,
                                'Inspect artwork, labels, joins and source relationships at final manuscript size.')
    if spec['type'] != 'illustration':
        async with plot_lock:
            return await asyncio.to_thread(_create_vector, store, sid, spec, brief, layout_binding, digest)
    if any(field in spec for field in ('panels', 'csv', 'nodes', 'edges')):
        raise ValueError('Use results for data panels or framework for editable nodes and edges')
    size = tuple(map(float, spec.get('size', [6.5, 3.5])))
    if len(size) != 2 or not all(math.isfinite(n) and 0.5 <= n <= 20 for n in size):
        raise ValueError('Illustration size must specify width and height in inches between 0.5 and 20')
    prompt = micu_images.illustration_prompt(spec.get('prompt'), size)
    refs = await asyncio.to_thread(search_references, brief)
    data, endpoint = await micu_images.generate(settings, prompt)
    async with plot_lock:
        return await asyncio.to_thread(_save_illustration, store, sid, spec, size, data, prompt,
                                       settings.image_model, endpoint, refs, layout_binding, digest)


def _save_illustration(store, sid, spec, size, data, prompt, model, endpoint, refs, layout_binding, digest):
    folder = store.file(sid, f'figures/forge_{time.time_ns()}')
    folder.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=folder.parent) as tmp:
        bundle = Path(tmp)
        geometry = micu_images.export_illustration(data, size, bundle)
        (bundle/'spec.json').write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding='utf-8')
        report = {'tool':'figure_forge', 'backend':'MicuAPI', 'references':refs, 'panels':[],
                  'image_generation':{'provider':'MicuAPI', 'model':model, 'endpoint':endpoint, 'prompt':prompt,
                                      'source_sha256':hashlib.sha256(data).hexdigest(), **geometry},
                  'source_spec_sha256':digest, 'provenance':'AI-generated conceptual illustration',
                  'status':'generated; visual and scientific review required', 'publication_readiness':'not_assessed',
                  'reproduce':'Reuse figure.png for exact pixels. Regeneration from the saved prompt may differ.'}
        bundle.rename(folder)
    return _register_bundle(store, sid, folder, report, layout_binding,
                            'Review image content, any labels and symbols at final size before including figure.pdf.')


def _create_vector(store, sid, spec, brief, layout_binding, digest):
    refs=search_references(brief)
    if not refs['available']:
        return {'status':'reference_source_missing',**refs}
    folder=store.file(sid,f'figures/forge_{time.time_ns()}');folder.mkdir(parents=True)
    contracts=[]
    for panel in spec.get('panels',[]):
        csv_path=store.file(sid,panel['csv'])
        if csv_path.suffix.lower()!='.csv' or csv_path.stat().st_size>20_000_000:
            raise ValueError('Panels must reference existing workspace CSV files <=20MB')
        contract=evidence.figure_report(store,sid,csv_path,question=panel.get('question',''),
            error=panel.get('error'),sample_size=panel.get('sample_size'),n_definition=panel.get('n_definition',''),
            uncertainty_definition=panel.get('uncertainty_definition',''))
        contract['source_path']=panel['csv']; contracts.append(contract)
        csv_digest=hashlib.sha256(csv_path.read_bytes()).hexdigest()
        contract['source_records']=[{'metadata':a['metadata'],'path':a['path']}
                                    for a in store.artifacts(sid) if a['kind']=='experiment_result'
                                    and a['metadata'].get('sha256')==csv_digest]
        dest=folder/'data'/(csv_digest[:12]+'.csv');dest.parent.mkdir(exist_ok=True);shutil.copyfile(csv_path,dest)
        panel['csv']=dest.relative_to(folder).as_posix()
    unverified=any(c.get('provenance') not in {'measured','user_supplied'} for c in contracts)
    if unverified:
        spec['caption']=(spec.get('caption','')+' | Unverified / synthetic data — pipeline validation only.').strip(' |')
    # Source data is copied, hashed, and relative to the bundle: no site package required for replay.
    (folder/'spec.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8')
    shutil.copyfile(Path(figure_render.__file__),folder/'render.py')
    figure_render.render_document(spec,folder,folder)
    report={'tool':'figure_forge','priority':1,'backend':'PaperScientist Python vector renderer',
            'upstream_component':'Top-Conf Figure Gallery retrieval and reference metadata',
            'image_generation':'Not invoked for this editable vector figure.',
            'references':refs,'panels':contracts,'source_spec_sha256':digest,
            'status':'rendered; visual and scientific review required','publication_readiness':'not_assessed',
            'reproduce':'python render.py spec.json'}
    return _register_bundle(store, sid, folder, report, layout_binding,
                            'Inspect exported PNG/PDF at final paper size, verify labels, arrows and claims; retain editable SVG/drawio and data/code.')


def _register_bundle(store, sid, folder, report, layout_binding, next_step):
    if layout_binding:
        report['manuscript_layout'] = layout_binding
        report['publication_readiness'] = 'Requires compile_latex PDF layout gate at actual inclusion size'
    (folder/'figure_contract.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    outputs=[]
    for file in sorted(folder.rglob('*')):
        if file.is_file():
            kind='figure' if file.suffix in {'.png','.pdf','.svg','.drawio'} else 'figure_source'
            outputs.append(store.artifact(sid,file,kind,{'tool':'figure_forge','backend':report['backend'],'provenance':'see figure_contract.json'}))
    return {'artifacts':outputs,'directory':folder.relative_to(store.workspace(sid)).as_posix(),
            'contract':report,'next':next_step}
