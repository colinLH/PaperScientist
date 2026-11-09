const stateNames = {queued:'排队中', running:'运行中', completed:'已完成', success:'已完成', failed:'失败',
  timeout:'超时', timed_out:'超时', stopped:'已停止', cancelled:'已取消', interrupted:'已中断'};
const active = status => status === 'queued' || status === 'running';
const stateName = job => job.cancel_requested && active(job.status) ? '正在停止' : stateNames[job.status] || job.status;
const node = (tag, text) => { const item=document.createElement(tag); if (text!==undefined) item.textContent=text; return item; };
const address = (sid,id='') => '/api/sessions/'+encodeURIComponent(sid)+'/experiments'+(id?'/'+encodeURIComponent(id):'');

function styles() {
  if (document.getElementById('ps-experiment-styles')) return;
  const link=node('link'); link.id='ps-experiment-styles'; link.rel='stylesheet'; link.href='/api/ui/experiments.css?v=1';
  document.head.append(link);
}
async function read(url, signal) {
  const res=await fetch(url,{signal,cache:'no-store'}), data=await res.json();
  if (!res.ok) throw Error(typeof data.detail==='string'?data.detail:'实验记录暂时不可用');
  return data;
}
function later(fn, delay, signal) {
  const timer=setTimeout(()=>{signal.removeEventListener('abort',cancel); if(!signal.aborted)fn();},delay);
  function cancel(){clearTimeout(timer);}
  signal.addEventListener('abort',cancel,{once:true});
}
function append(pre,chunk) {
  if (!chunk) return;
  const atEnd=pre.scrollHeight-pre.scrollTop-pre.clientHeight<16;
  const text=(pre.textContent+chunk).slice(-32768);
  pre.textContent=text;
  if (atEnd) pre.scrollTop=pre.scrollHeight;
}

// Read only the selected run. The server resolves it within the current top-level conversation.
export function watchLog(host, sid, runId, signal) {
  styles();
  const status=node('p','读取中…'); status.setAttribute('role','status');
  const meta=node('small','最近日志 · '+runId), outputs=node('details');
  const readers={};
  const shell=node('section'); shell.className='ps-experiment-log'; shell.setAttribute('aria-label','后台实验日志');
  shell.append(meta,status);
  for (const [key,label] of [['stdout','标准输出'],['stderr','标准错误']]) {
    const title=node('h5',label), pre=node('pre'); pre.tabIndex=0; pre.setAttribute('aria-label',label);
    shell.append(title,pre); readers[key]=pre;
  }
  shell.append(outputs); outputs.hidden=true; host.replaceChildren(shell);
  let offsets=new URLSearchParams(), filesKey='';
  async function poll() {
    if (signal.aborted || !host.isConnected) return;
    if (document.hidden) {later(poll,1800,signal);return;}
    try {
      const job=await read(address(sid,runId)+'?'+offsets,signal);
      if (signal.aborted || !host.isConnected) return;
      status.textContent=stateName(job)+(job.exit_code!=null?' · 退出码 '+job.exit_code:'')+(job.error?' · '+job.error:'');
      for (const key of ['stdout','stderr']) {
        append(readers[key],job[key]||'');
        offsets.set(key+'_offset',job[key+'_offset']);
      }
      const files=Array.isArray(job.output_files)?job.output_files:[];
      if (files.length && JSON.stringify(files)!==filesKey) {
        filesKey=JSON.stringify(files); outputs.hidden=false;
        const list=node('ul'); for (const file of files) list.append(node('li',typeof file==='string'?file:(file.path||file.name||'')));
        outputs.replaceChildren(node('summary','输出文件 · '+files.length),list);
      }
      if (active(job.status)) later(poll,1500,signal);
      else if (job.stdout || job.stderr) later(poll,0,signal);
    } catch (err) {
      if (!signal.aborted) {status.textContent=err.message+' · 稍后重试';later(poll,6000,signal);}
    }
  }
  poll();
}

export function mount(element) {
  if(element.dataset.experimentsMounted) return;
  element.dataset.experimentsMounted='true'; styles();
  let sid='', visible=false, shell, list, note, body, reader, session, selected='', rendered='';
  function stop() {session?.abort();reader?.abort();session=null;reader=null;}
  function choose(id) {
    reader?.abort();reader=null;selected=id;
    for(const b of list.children) b.setAttribute('aria-pressed',String(b.dataset.run===id));
    body.replaceChildren(); if (!id || !visible) return;
    reader=new AbortController(); watchLog(body,sid,id,reader.signal);
  }
  function refresh() {
    session?.abort();session=null;
    if (!sid || !shell?.isConnected || !visible) return;
    session=new AbortController();
    const signal=session.signal;
    async function update() {
      if(signal.aborted || !shell?.isConnected) return;
      try {
        if (!document.hidden) {
          const {jobs}=await read(address(sid),signal);
          if(signal.aborted) return;
          note.textContent=jobs.length?'':'本会话尚无后台实验。';
          const signature=JSON.stringify(jobs.map(j=>[j.run_id,j.name,j.status,j.cancel_requested]));
          if(signature!==rendered) {
            rendered=signature;list.replaceChildren();
            for(const job of jobs) {
              const b=node('button'); b.type='button'; b.dataset.run=job.run_id;
              b.append(node('span',job.name),node('small',(job.session_id===sid?'':'子代理 · ')+stateName(job)));
              b.onclick=()=>choose(job.run_id);list.append(b);
            }
            if(!jobs.some(j=>j.run_id===selected)) choose(jobs.find(j=>active(j.status))?.run_id||jobs[0]?.run_id||'');
            else for(const b of list.children)b.setAttribute('aria-pressed',String(b.dataset.run===selected));
          }
          later(update,jobs.some(j=>active(j.status))?2500:10000,signal);return;
        }
      } catch(err){if(signal.aborted)return;note.textContent=err.message;}
      later(update,6000,signal);
    }
    update();
  }
  function context() {
    const marker=element.querySelector('.ps-job-context'), next=marker?.dataset.session||'';
    if(next===sid && (!next || shell?.isConnected)) return;
    stop();shell?.remove();shell=null;sid=next;selected='';rendered='';
    if(!sid) return;
    shell=node('section');shell.className='ps-jobs';shell.setAttribute('aria-label','后台实验');
    const header=node('header'), title=node('h3','后台实验'), reload=node('button','刷新');
    reload.type='button';reload.onclick=refresh;header.append(title,reload);
    list=node('nav');list.setAttribute('aria-label','后台实验列表');note=node('p');note.setAttribute('role','status');
    body=node('div');shell.append(header,note,list,body);marker.after(shell);refresh();
  }
  const observer=new MutationObserver(changes=>{if(changes.some(c=>!c.target.closest?.('.ps-jobs')))context();});
  observer.observe(element,{childList:true,subtree:true,attributes:true,attributeFilter:['data-session']});
  // Observe the tab itself; scrolling through long logs should not tear down the reader.
  const tab=element.closest('[role=tabpanel]')||element;
  const visibility=new IntersectionObserver(entries=>{
    const next=entries.some(e=>e.isIntersecting);
    if(next===visible)return;visible=next;stop();if(visible){refresh();if(selected)choose(selected);}
  });
  visibility.observe(tab);context();
}
