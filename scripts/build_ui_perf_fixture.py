"""Build a local, offline UI performance replay from a saved session snapshot.

Run before and after a change with the same snapshot and viewport. This measures
browser rendering, not model latency or the desktop app's total GPU allocation.
Serve output/ui-performance on 127.0.0.1 and use its visible benchmark buttons.
"""
import argparse
import json
from pathlib import Path
import shutil
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('label')
    parser.add_argument('--session', default='be1fb2c1f22d411da4d81252088fc627')
    args = parser.parse_args()
    if not args.label.replace('-', '').isalnum():
        parser.error('Use a simple label')
    target = ROOT / 'output' / 'ui-performance' / args.label
    target.mkdir(parents=True, exist_ok=True)
    snapshot_path = target.parent / 'snapshot.json'
    if not snapshot_path.exists():
        with urllib.request.urlopen(f'http://127.0.0.1:8888/api/sessions/{args.session}/timeline') as response:
            snapshot_path.write_bytes(response.read())
    for name in ('timeline.js', 'timeline.css', 'effects.css', 'effects.js'):
        shutil.copy2(ROOT / 'paperscientist/static' / name, target / name)
    html = '''<!doctype html><html lang="zh"><meta charset="utf-8">
<title>PaperScientist UI rendering replay</title>
<link rel="stylesheet" href="timeline.css"><link rel="stylesheet" href="effects.css">
<style>@property --ps-angle {syntax:'<angle>';initial-value:0deg;inherits:false;}
*{box-sizing:border-box}#app-shell{display:flex}#workspace{flex:1}#sidebar{display:flex;flex-direction:column}
#composer-toolbar{display:flex}#query textarea{width:100%;color:#ddd}button{cursor:pointer;color:inherit}
#probe{position:fixed;right:20px;top:8px;z-index:20000;background:#141421;padding:6px 12px;border:1px solid #7463b8;border-radius:8px;font:12px sans-serif}
#probe pre{max-height:210px;overflow:auto;margin:5px 0}#probe button{background:#28233e;border:1px solid #7463b8;border-radius:4px;margin:2px;padding:4px}
</style>
<div id="probe"><b>LABEL · 本地历史回放</b> <button id="bench">滚动测量 8 秒</button><button id="stream">流式回放</button><pre id="result">等待操作</pre></div>
<div class="gradio-container"><div id="app-shell"><aside id="sidebar"><div id="brand"><h2>◈ PaperScientist</h2><p>PERSONAL RESEARCH</p></div><button id="new-chat">✎ 新聊天</button><p>科研 Agent · 历史会话</p></aside>
<main id="workspace"><div id="workspace-heading">性能验收：相同历史、相同视口、相同滚动轨迹</div><div id="workspace-chat"><span class="ps-session-marker" data-session="replay" hidden></span></div>
<div id="composer"><div id="query"><textarea placeholder="提出问题，或继续你的研究…"></textarea></div><div id="composer-toolbar"><button id="attach">＋</button><span style="flex:1">DeepSeek Chat</span><button id="send">↑</button></div></div></main></div></div>
<script>
let draws=0;const clear=CanvasRenderingContext2D.prototype.clearRect;
CanvasRenderingContext2D.prototype.clearRect=function(...args){if(this.canvas.id==='ps-fx')draws++;return clear.apply(this,args)};
</script><script src="effects.js"></script><script type="module">
import {mount} from './timeline.js';
const snapshot=await (await fetch('../snapshot.json')).json();
const originalFetch=window.fetch;window.fetch=(url,options)=>String(url).includes('/timeline?')?Promise.resolve(new Response(JSON.stringify(snapshot))):originalFetch(url,options);
let streamSource;window.EventSource=class {constructor(){this.listeners={};streamSource=this;}addEventListener(name,fn){this.listeners[name]=fn}close(){}emit(row){this.listeners.timeline?.({data:JSON.stringify(row)})}};
mount(document.querySelector('#workspace-chat'));
const output=document.querySelector('#result');
const percentile=(a,p)=>a.slice().sort((x,y)=>x-y)[Math.min(a.length-1,Math.floor(a.length*p))]||0;
let busy=false;
document.querySelector('#bench').onclick=()=>{
 if(busy)return;busy=true;const scroller=document.querySelector('.ps-scroll');scroller.scrollTop=0;
 const started=performance.now(),gaps=[],tasks=[];let previous=started,firstDraw=draws,mutations=0;
 const observer=new MutationObserver(rows=>mutations+=rows.length);observer.observe(document.querySelector('.ps-turns'),{childList:true,subtree:true,attributes:true,characterData:true});
 const long=new PerformanceObserver(list=>tasks.push(...list.getEntries().map(e=>e.duration)));long.observe({type:'longtask'});
 output.textContent='测量中…';
 function step(now){gaps.push(now-previous);previous=now;const elapsed=now-started;
  scroller.scrollTop=(Math.sin(elapsed/1800-Math.PI/2)+1)/2*(scroller.scrollHeight-scroller.clientHeight);
  if(elapsed<8000)requestAnimationFrame(step);else{
   observer.disconnect();long.disconnect();busy=false;
   const canvas=document.querySelector('#ps-fx');
   output.textContent=JSON.stringify({label:'LABEL',duration_ms:Math.round(elapsed),frames:gaps.length,frame_p95_ms:+percentile(gaps,.95).toFixed(1),frame_max_ms:+Math.max(...gaps).toFixed(1),long_tasks:tasks.length,canvas_draws:draws-firstDraw,canvas_pixels:canvas.width*canvas.height,dom_mutations:mutations,dom_nodes:document.querySelectorAll('*').length,heap_mb:performance.memory?+(performance.memory.usedJSHeapSize/1048576).toFixed(1):null},null,2);
  }
 }requestAnimationFrame(step);
};
document.querySelector('#stream').onclick=()=>{
 if(busy)return;busy=true;let cursor=snapshot.cursor,n=0,oldMutations=0;
 const turn=snapshot.turns.at(-1),first=document.querySelector('.ps-turn');
 const observer=new MutationObserver(rows=>oldMutations+=rows.length);observer.observe(first,{subtree:true,childList:true,attributes:true,characterData:true});
 const emit=(kind,data)=>streamSource.emit({id:++cursor,turn_id:turn.id,kind,data});
 emit('status',{status:'running'});emit('assistant_start',{id:'perf-stream'});
 const timer=setInterval(()=>{emit('assistant_delta',{id:'perf-stream',text:'流式验证 '+(++n)+'。'});
  if(n===100){clearInterval(timer);emit('assistant_commit',{id:'perf-stream',text:'100 段流式内容已完整到达。',html:'<p>100 段流式内容已完整到达。</p>'});emit('status',{status:'completed'});
   setTimeout(()=>{observer.disconnect();busy=false;output.textContent=JSON.stringify({label:'LABEL',chunks:n,unchanged_turn_mutations:oldMutations,complete:document.querySelector('.ps-turn:last-child').textContent.includes('100 段流式内容已完整到达。')},null,2)},150);
  }
 },30);
};
</script></html>'''
    (target / 'index.html').write_text(html.replace('LABEL', args.label), encoding='utf-8')
    print(json.dumps({'fixture': str(target), 'snapshot': str(snapshot_path)}))


if __name__ == '__main__':
    main()
