import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from paperscientist import figure_forge, figure_render, manuscript_review
from paperscientist.store import Store


@pytest.fixture
def workspace(tmp_path):
    store = Store(tmp_path / 'store')
    store.session('figures')
    return store, 'figures', store.workspace('figures')


def result_spec():
    return {'type':'results','size':[8,4], 'panels':[
        {'kind':'stacked_bar','csv':'data.csv','x':'method','y':'count','group':'outcome',
         'question':'How do completion outcomes differ?', 'sample_size':3,'n_definition':'Designed cases per method'}]}


def test_real_bundle_is_editable_and_reproducible(workspace, tmp_path, monkeypatch):
    store,sid,base=workspace
    data=base/'data.csv';data.write_text('method,outcome,count\nA,success,2\nA,blocked,1\nB,success,3\nB,blocked,0\n')
    store.artifact(sid,data,'experiment_result',{'sha256':hashlib.sha256(data.read_bytes()).hexdigest(),'provenance':'user_supplied'})
    (base/'spec.json').write_text(json.dumps(result_spec()))
    monkeypatch.setattr(figure_forge,'search_references',lambda brief:{'available':True,'references':[]})
    result=figure_forge.create_figure(store,sid,'spec.json','fault outcomes')
    folder=base/result['directory']
    assert result['contract']['panels'][0]['provenance']=='user_supplied'
    assert not result['contract']['panels'][0]['reporting_gaps']
    assert all((folder/f'figure.{ext}').stat().st_size>100 for ext in ('png','pdf','svg'))
    assert '<text' in (folder/'figure.svg').read_text(encoding='utf-8')
    subprocess.run([sys.executable,str(folder/'render.py'),str(folder/'spec.json')],check=True,timeout=60,cwd=tmp_path)


def test_unverified_data_is_visibly_labelled(workspace,monkeypatch):
    store,sid,base=workspace
    (base/'data.csv').write_text('method,outcome,count\nA,success,2\n')
    (base/'spec.json').write_text(json.dumps(result_spec()))
    monkeypatch.setattr(figure_forge,'search_references',lambda brief:{'available':True,'references':[]})
    result=figure_forge.create_figure(store,sid,'spec.json','fault outcomes')
    spec=json.loads((base/result['directory']/'spec.json').read_text())
    assert 'pipeline validation only' in spec['caption']


@pytest.mark.parametrize('data,match',[
    ('method,outcome,count\nA,s,1\nB,f,2\n','Missing category'),
    ('method,outcome,count\nA,s,1\nA,s,2\n','Duplicate cells'),
    ('method,outcome,count\nA,s,nan\n','finite'),
])
def test_does_not_silently_fabricate_cells(tmp_path,data,match):
    (tmp_path/'data.csv').write_text(data)
    with pytest.raises(ValueError,match=match):
        figure_render.render_document(result_spec(),tmp_path,tmp_path/'out')


def test_refuses_path_escape(tmp_path):
    child=tmp_path/'bundle';child.mkdir()
    (tmp_path/'data.csv').write_text('x,y\n1,2\n')
    with pytest.raises(ValueError,match='inside'):
        figure_render._rows(child,{'csv':'../data.csv','x':'x','y':'y'})


def test_framework_has_native_nodes_and_rejects_dangling_edges(tmp_path):
    spec={'type':'framework','size':[8,3],'nodes':[
        {'id':'a','label':'Plan','x':0,'y':0}, {'id':'b','label':'Audit','x':34,'y':0}],
        'edges':[{'source':'a','target':'b','label':'evidence'}]}
    figure_render.render_document(spec,tmp_path,tmp_path)
    assert 'source="na" target="nb"' in (tmp_path/'figure.drawio').read_text()
    spec['edges'][0]['target']='missing'
    with pytest.raises(ValueError,match='dangling'):
        figure_render.render_document(spec,tmp_path,tmp_path)


def test_review_detects_changed_claims_across_included_files(workspace):
    store,sid,base=workspace
    (base/'main.tex').write_text(r'\section{Introduction}\input{results}')
    (base/'results.tex').write_text(r'\section{Evaluation} 48 cases \cite{actual}')
    baseline=manuscript_review.review(store,sid,'main.tex')
    assert len(baseline['source_hashes'])==2
    (base/'results.tex').write_text(r'\section{Evaluation} 49 cases \cite{new}')
    revised=manuscript_review.review(store,sid,'main.tex','revised')
    changes=revised['changes_requiring_verification']
    assert changes['numeric_tokens_changed']
    assert changes['citation_keys_removed']==['actual']
    assert changes['citation_keys_added']==['new']
    assert revised['status']=='requires_semantic_review'


def test_review_rejects_escape(workspace):
    store,sid,base=workspace
    (base/'main.tex').write_text(r'\input{../escape}')
    (base.parent/'escape.tex').write_text('private')
    with pytest.raises(ValueError,match='escaping'):
        manuscript_review.review(store,sid,'main.tex')


def test_review_detects_signed_values_and_optional_citation_arguments(workspace):
    store,sid,base=workspace
    (base/'main.tex').write_text(r'-3.0\\% and 1e-4 \citep[see][p.2]{real}')
    before=manuscript_review.review(store,sid,'main.tex')
    assert before['citation_keys']==['real']
    (base/'main.tex').write_text(r'+3.0\\% and 1e-4 \citep[see][p.2]{real}')
    assert manuscript_review.review(store,sid,'main.tex','revised')['changes_requiring_verification']['numeric_tokens_changed']


def test_builtin_skills_are_parseable_and_priority_entry_is_discoverable():
    from paperscientist.skills import SkillCatalog
    root=Path(__file__).resolve().parents[1]/'research_skills'
    catalog=SkillCatalog([root])
    assert not catalog.errors
    assert 'manuscript-quality' in catalog.skills
    assert catalog.search('论文画图',limit=1)['skills'][0]['name']=='figure-forge'
