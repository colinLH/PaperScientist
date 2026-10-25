"""Evidence-preserving draft/revision packets, not an automated acceptance score."""
import hashlib
import json
from pathlib import Path
import re
import time

RUBRIC = {
    'introduction': 'Problem and stakes → concrete prior-work gap → central insight → bounded contributions, each supported by later evidence.',
    'background': 'Define only prerequisites needed by this method; fix notation, assumptions, system/threat model and task boundary before the design.',
    'motivation_challenges': 'Walk one concrete input through a baseline failure. Add an example figure. Map each observed failure to C1/C2 challenges, design choices and a falsifiable question.',
    'framework': 'One readable overview with input/output, grouped stages, training/inference or data/control separation where real, key state, feedback edges, legend and contribution callouts. Match code and section names.',
    'design_details': 'For each module: addressed challenge, new mechanism versus support plumbing, I/O, equations/pseudocode, assumptions, one traced example, implementation pointer and ablation.',
    'evaluation': 'Start with research questions, setup and protocol; then effectiveness, necessary ablations, sensitivity/robustness, cost and failure/case analysis. Include only experiments relevant to actual claims.',
    'evaluation_setup': 'Datasets/targets and selection, units/counts, split/leakage control, baselines/version/tuning parity, metrics/directions, hardware/software, seeds/repetitions, failures and uncertainty definitions.',
    'figures': 'Distinct question per panel; traceable raw data and sample unit, comparable scales, readable final-size labels, accessible colors+hatches, meaningful annotations and uncertainty where justified.',
    'prose': 'Load paper-polish and writing-style:anti-defensive-writing plus the relevant installed language/LaTeX skill. Remove repetitive hedges and generic phrasing while preserving true scope, uncertainty, citations and measured values.',
}


def review(store, sid, main_path, phase='baseline'):
    if phase not in {'baseline','revised'}:
        raise ValueError('phase must be baseline or revised')
    main=store.file(sid,main_path)
    if main.suffix!='.tex':raise ValueError('Expected a saved LaTeX main file')
    root=store.workspace(sid).resolve(); pending=[main];files={};texts=[]
    while pending:
        path=pending.pop().resolve()
        if path in files:continue
        if not path.is_relative_to(root) or not path.is_file():raise ValueError('Missing/escaping manuscript input')
        if len(files)>=80 or path.stat().st_size>1_000_000:raise ValueError('Manuscript read limit exceeded')
        raw=path.read_text(encoding='utf-8')
        files[path]=hashlib.sha256(path.read_bytes()).hexdigest();texts.append(raw)
        for child in re.findall(r'\\(?:input|include)\s*\{([^}]+)\}',raw):
            item=Path(child);item=item if item.suffix else item.with_suffix('.tex')
            target=main.parent/item
            if not target.is_file():target=path.parent/item
            pending.append(target)
    full='\n'.join(texts)
    sections=re.findall(r'\\(?:sub)*section\*?(?:\[[^]]*\])?\{([^}]+)\}',full)
    checks={
        'introduction':r'introduction|引言|绪论', 'background':r'background|preliminar|背景|预备',
        'motivation_challenges':r'motivat|challeng|动机|挑战', 'evaluation':r'evaluat|experiment|实验|评估',
        'evaluation_setup':r'experimental setup|evaluation setup|implementation details|实验设置|实验环境',
    }
    notices=[{'area':k,'finding':'Expected heading/phrase not detected; inspect the actual structure, do not insert boilerplate.'} for k,v in checks.items() if not re.search(v,full,re.I)]
    images=re.findall(r'\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}',full)
    if not images:notices.append({'area':'figures','finding':'No figure inclusion detected. Check overview, motivating example and experimental figures.'})
    todos=re.findall(r'\b(?:TODO|TBD|FIXME)\b|待补充|待验证',full,re.I)
    if todos:notices.append({'area':'incomplete','finding':f'{len(todos)} unresolved draft markers; inspect their scientific impact.'})
    citations=sorted(set(k.strip() for group in re.findall(r'\\cite\w*\*?(?:\[[^]]*\]){0,2}\{([^}]+)\}',full) for k in group.split(',')))
    numbers=sorted(re.findall(r'(?<![\w.])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?(?:\\?%)?',full))
    result={'phase':phase,'main':main_path,'source_hashes':{p.relative_to(root).as_posix():h for p,h in files.items()},
            'sections':sections,'figures':images,'citation_keys':citations,'numeric_tokens':numbers,'notices':notices,
            'rubric':RUBRIC,'status':'requires_semantic_review','meaning':'Structural inventory and change detection only; not a scientific or language-quality pass.',
            'required_next_actions':['Load paper-polish and writing-style:anti-defensive-writing (or report installation gap).',
              'Review every rubric area against manuscript/code/data; record section-specific findings, edits and unresolved evidence gaps.',
              'Apply revisions, run revised review, inspect numeric/citation changes, validate_manuscript, compile, and visually inspect the PDF.']}
    previous=[p for p in sorted(main.parent.glob('review_baseline_*.json'))
              if json.loads(p.read_text(encoding='utf-8')).get('main')==main_path]
    if phase=='revised' and previous:
        before=json.loads(previous[-1].read_text(encoding='utf-8'))
        result['changes_requiring_verification']={
            'numeric_tokens_changed':before['numeric_tokens']!=numbers,
            'citation_keys_added':sorted(set(citations)-set(before['citation_keys'])),
            'citation_keys_removed':sorted(set(before['citation_keys'])-set(citations)),
            'baseline':previous[-1].relative_to(root).as_posix()}
    elif phase=='revised':
        result['notices'].append({'area':'baseline','finding':'No saved baseline; cannot verify preservation across revisions.'})
    path=main.parent/f'review_{phase}_{time.time_ns()}.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    result['artifact']=store.artifact(sid,path,'manuscript_review')
    return result
