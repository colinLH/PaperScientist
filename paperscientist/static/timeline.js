// Durable events are the source of truth; the browser only presents them.
const paths = {
  file:'M6 3h8l4 4v14H6zM14 3v5h5', edit:'m15 4 5 5M4 20l5-1L21 7l-5-5L4 15z',
  globe:'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0M3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18',
  terminal:'M7 8l4 4-4 4M13 16h4M3 3h18v18H3z', chart:'M4 3v17h17M8 15v-4M13 15V7M18 15V4',
  agents:'M8 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6M2 20v-4a6 6 0 0 1 12 0v4M17 4a3 3 0 0 1 0 6M18 13a4 4 0 0 1 4 4v3',
  book:'M3 4h7l2 2 2-2h7v15h-7l-2 2-2-2H3zM12 6v15', tool:'m4 4 4 1 1 4-3 3 7 7 3-3-7-7 4-1 1-4M4 4l16 16',
  spark:'m12 3 3 6 6 3-6 3-3 6-3-6-6-3 6-3z', close:'m6 6 12 12M6 18 18 6', chevron:'m8 5 7 7-7 7',
  undo:'m8 4-5 5 5 5M3 9h11a6 6 0 0 1 0 12', download:'M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4'
};
const statusNames={queued:'排队中',running:'正在进行',recovering:'正在恢复',waiting_input:'等待回答',paused:'已暂停',error:'运行中断',stopped:'已停止',completed:'已完成',historical:'历史记录'};
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}
function icon(name){const e=document.createElementNS('http://www.w3.org/2000/svg','svg');e.setAttribute('viewBox','0 0 24 24');e.setAttribute('aria-hidden','true');e.innerHTML=`<path d="${paths[name]||paths.file}"/>`;return e;}
function button(label,fn,cls=''){const b=el('button',cls,label);b.type='button';b.onclick=fn;return b;}
function fileIcon(path){const e=el('span','ps-file-icon');const ext=path.split('.').pop().toUpperCase();if(['PDF','CSV','XLSX'].includes(ext)){e.textContent=ext;e.dataset.ext=ext;}else e.append(icon('file'));return e;}
async function request(url,options){const r=await fetch(url,options);if(!r.ok){let msg=await r.text();try{msg=JSON.parse(msg).detail||msg;}catch{}throw Error(msg);}return r.json();}

export function mount(element){
  window.__psTimelineCleanup?.();
  let host,scroll,list,rail,tip,live,jump,connection,sid='',generation=0,source,cursor=0,frame=0;
  let turns=[],views=new Map(),follow=true,hoverTimer,dialog,dialogRequest=0,closed=false;
  let dirty=new Set(),activeId=null,scrollFrame=0,renderTimer=0,sessionAbort,dialogAbort;
  let previewShell,previewSplitter,previewController,previewOpener,previewShare=50;
  const controller=new AbortController();
  const url=(route,query={})=>`/api/sessions/${encodeURIComponent(sid)}/${route}?${new URLSearchParams(query)}`;
  const setConnection=(text,bad=false)=>{if(connection){connection.textContent=text;connection.classList.toggle('ps-warning',bad);}};
  function cleanup(){closed=true;generation++;source?.close();observer.disconnect();controller.abort();sessionAbort?.abort();closeDialog();cancelAnimationFrame(frame);cancelAnimationFrame(scrollFrame);clearTimeout(renderTimer);clearTimeout(hoverTimer);host?.remove();views.clear();dirty.clear();turns=[];}
  window.__psTimelineCleanup=cleanup;
  // Gradio replaces the marker when switching sessions. Our own streaming DOM
  // mutations are not a reason to scan the entire conversation for that marker.
  const observer=new MutationObserver(records=>{if(!closed&&records.some(r=>!r.target.closest?.('.ps-timeline')))boot();});
  observer.observe(element,{childList:true,subtree:true,attributes:true,attributeFilter:['data-session']});
  function scheduleRender(){
    if(closed||document.hidden||renderTimer||frame)return;
    renderTimer=setTimeout(()=>{renderTimer=0;frame=requestAnimationFrame(()=>{frame=0;if(!closed&&!document.hidden)render();});},50);
  }
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&dirty.size)scheduleRender();},{signal:controller.signal});

  async function boot(){
    const marker=element.querySelector('.ps-session-marker');
    if(!marker || (marker.dataset.session===sid && host?.isConnected))return;
    source?.close();sessionAbort?.abort();sessionAbort=new AbortController();closeDialog();host?.remove();generation++;const gen=generation;
    cancelAnimationFrame(frame);cancelAnimationFrame(scrollFrame);clearTimeout(renderTimer);clearTimeout(hoverTimer);frame=scrollFrame=renderTimer=0;
    sid=marker.dataset.session;views=new Map();turns=[];dirty=new Set();activeId=null;follow=true;cursor=0;
    host=el('div','ps-timeline');scroll=el('div','ps-scroll');scroll.tabIndex=0;scroll.setAttribute('aria-label','会话记录');
    list=el('div','ps-turns');scroll.append(list);rail=el('nav','ps-turn-rail');rail.setAttribute('aria-label','对话轮次导航');
    tip=el('div','ps-turn-tip');tip.hidden=true;connection=el('div','ps-connection','正在恢复会话…');
    live=el('div','ps-sr-only');live.setAttribute('role','status');live.setAttribute('aria-live','polite');
    jump=button('↓ 回到最新',()=>{follow=true;scroll.scrollTo({top:scroll.scrollHeight,behavior:'instant'});jump.hidden=true;},'ps-jump');jump.hidden=true;
    host.append(scroll,rail,tip,connection,jump,live);element.append(host);
    scroll.addEventListener('scroll',()=>{
      if(scrollFrame)return;
      scrollFrame=requestAnimationFrame(()=>{scrollFrame=0;follow=scroll.scrollHeight-scroll.scrollTop-scroll.clientHeight<90;if(jump.hidden!==follow)jump.hidden=follow;activeTurn();tip.hidden=true;clearTimeout(hoverTimer);});
    },{passive:true});
    host.addEventListener('click',e=>{const a=e.target.closest('[data-file]');if(a){e.preventDefault();const turn=turns.find(t=>t.id===a.closest('[data-turn]')?.dataset.turn);openFile(turn,a.dataset.file);}});
    if(!sid){empty();setConnection('');return;}
    try{
      const snapshot=await request(url('timeline'),{signal:sessionAbort.signal});
      if(gen!==generation)return;
      turns=snapshot.turns;dirty=new Set(turns.map(t=>t.id));cursor=snapshot.cursor;render();scroll.scrollTop=scroll.scrollHeight;
      source=new EventSource(url('events',{after:cursor}));
      source.onopen=()=>{if(gen===generation)setConnection('实时连接 · 记录已保存');};
      source.onerror=()=>{if(gen===generation)setConnection('连接中断，正在重连…',true);};
      source.addEventListener('removed',()=>{source.close();setConnection('对话已删除',true);});
      source.addEventListener('timeline',event=>{
        if(gen!==generation)return;
        const row=JSON.parse(event.data);if(row.id<=cursor)return;cursor=row.id;apply(row);
        scheduleRender();
      });
    }catch(error){if(gen===generation){setConnection(error.message,true);list.append(button('重新连接',()=>{sid='';boot();},'ps-retry'));}}
  }
  function empty(){list.replaceChildren(el('div','ps-empty'));const box=list.firstChild;box.append(el('h2','','从一个好问题开始。'),el('p','','聊聊你的研究兴趣，或添加一篇论文、一份数据。'));}
  function apply(row){
    const d=row.data;let t=turns.find(t=>t.id===row.turn_id);
    if(row.kind==='turn'){if(!t){turns.push({...d,items:[],files:[],changes:[]});dirty.add(d.id);}return;}
    if(!t)return;
    dirty.add(t.id);
    let item=t.items.find(i=>i.id===d.id);
    if(row.kind==='assistant_start'){
      if(!item){item={id:d.id,type:'assistant'};t.items.push(item);}Object.assign(item,{text:'',html:'',state:'streaming'});
    }else if(row.kind==='assistant_delta'){
      if(!item){item={id:d.id,type:'assistant',text:'',state:'streaming'};t.items.push(item);}item.text+=d.text;
    }else if(['assistant_commit','assistant_discard'].includes(row.kind)){
      if(!item){item={id:d.id,type:'assistant'};t.items.push(item);}Object.assign(item,d,{state:row.kind==='assistant_commit'?'complete':'discarded'});
      if(row.kind==='assistant_discard')t.items.push({id:'retry-'+row.id,type:'note',text:d.reason});
    }else if(row.kind==='tool_start'){
      if(!item)t.items.push({...d,type:'tool',status:'running'});else Object.assign(item,d,{status:'running'});
    }else if(row.kind==='tool_end'){if(item)Object.assign(item,d);}
    else if(row.kind==='status'){Object.assign(t,d);live.textContent=statusNames[d.status]||d.status;}
    else if(row.kind==='files'){Object.assign(t,d);}
    else if(row.kind==='note'){t.items.push({...d,id:'event-'+row.id,type:'note'});}
  }
  function render(){
    if(!turns.length){empty();return;}
    list.querySelector('.ps-empty')?.remove();
    const previousBottom=follow;
    for(const turn of turns){
      let v=views.get(turn.id);
      if(v&&!dirty.has(turn.id))continue;
      if(!v){
        const section=el('section','ps-turn');section.dataset.turn=turn.id;section.id='turn-'+turn.id;
        const question=el('div','ps-question');question.textContent=turn.question;
        const meta=el('div','ps-turn-meta'),flow=el('div','ps-flow'),ending=el('div','ps-ending');
        section.append(question,flow,ending,meta);list.append(section);
        const tick=button('',()=>{follow=false;scroll.scrollTo({top:section.offsetTop-scroll.offsetTop-20,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});},'ps-turn-tick');
        tick.append(el('span'));tick.setAttribute('aria-label',turn.title||turn.question.slice(0,60));
        tick.addEventListener('pointerenter',()=>{clearTimeout(hoverTimer);hoverTimer=setTimeout(()=>showTip(turn,tick),180);});
        tick.addEventListener('pointerleave',()=>{clearTimeout(hoverTimer);tip.hidden=true;});
        tick.addEventListener('focus',()=>showTip(turn,tick));tick.addEventListener('blur',()=>{tip.hidden=true;});rail.append(tick);
        v={section,flow,ending,meta,tick,nodes:new Map(),endingKey:''};views.set(turn.id,v);
      }
      const units=[];
      for(const item of turn.items){
        if(item.type==='assistant'&&!item.text)continue;
        const last=units.at(-1);
        if(item.type==='tool'&&last?.type==='group'&&last.category===item.category)last.items.push(item);
        else units.push(item.type==='tool'?{id:'group-'+item.id,type:'group',category:item.category,items:[item]}:item);
      }
      const keep=new Set();
      units.forEach((item,index)=>{
        keep.add(item.id);let node=v.nodes.get(item.id);
        if(!node){node=item.type==='group'?el('details','ps-tool-group'):el('div',item.type==='assistant'?'ps-assistant ps-markdown':'ps-note');v.nodes.set(item.id,node);}
        if(v.flow.children[index]!==node)v.flow.insertBefore(node,v.flow.children[index]||null);
        if(item.type==='group')renderGroup(node,item,turn);
        else if(item.type==='assistant'){
          if(node._text!==item.text||node._state!==item.state){
            if(item.state==='complete'&&item.html)node.innerHTML=item.html;
            else if(item.state==='streaming'&&node._state==='streaming'&&node.firstChild?.nodeType===3&&item.text.startsWith(node._text||''))node.firstChild.appendData(item.text.slice((node._text||'').length));
            else node.textContent=item.text;
            node._text=item.text;node._state=item.state;
          }
          node.classList.toggle('ps-streaming',item.state==='streaming'&&['running','queued','recovering'].includes(turn.status));
          node.classList.toggle('ps-interrupted',item.state!=='complete'&&['stopped','error','paused'].includes(turn.status));
        }else if(node.textContent!==item.text)node.textContent=item.text;
      });
      for(const [key,node]of v.nodes)if(!keep.has(key)){node.remove();v.nodes.delete(key);}
      const key=JSON.stringify([turn.files,turn.changes,turn.status,turn.skipped_files]);
      if(v.endingKey!==key){v.endingKey=key;renderEnding(v.ending,turn);}
      const date=new Date(turn.created_at);const time=Number.isNaN(+date)?'':date.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
      const status=statusNames[turn.status]||turn.status;
      const extra=turn.status!=='completed'&&turn.status!=='historical'?(turn.error||turn.pending?.question||turn.preview||''):'';
      const text=`${status} · ${time}${extra?' · '+extra:''}`;if(v.meta.textContent!==text)v.meta.textContent=text;
      v.meta.classList.toggle('ps-warning',turn.status==='error');
    }
    dirty.clear();
    if(previousBottom)scroll.scrollTop=scroll.scrollHeight;
    activeTurn();
  }
  function activeTurn(){
    // Ordered sections allow O(log n) geometry reads and only two DOM writes.
    const target=scroll.scrollTop+scroll.clientHeight*.45;let low=0,high=turns.length-1,index=0;
    while(low<=high){const mid=(low+high)>>1;if(views.get(turns[mid].id)?.section.offsetTop<target){index=mid;low=mid+1;}else high=mid-1;}
    const next=turns[index]?.id;if(next===activeId)return;
    const previous=views.get(activeId)?.tick,current=views.get(next)?.tick;
    previous?.classList.remove('ps-active');previous?.removeAttribute('aria-current');
    current?.classList.add('ps-active');current?.setAttribute('aria-current','true');activeId=next;
  }
  function showTip(turn,tick){
    tip.replaceChildren(el('strong','',turn.title||turn.question.slice(0,60)),el('div','',statusNames[turn.status]||turn.status));
    const answer=turn.items.filter(i=>i.type==='assistant'&&i.text).at(-1)?.text||turn.preview||'尚无回复';
    tip.append(el('p','',answer.slice(0,190)),el('small','',(turn.files||[]).slice(0,3).map(f=>f.name).join(' · ')));
    const r=tick.getBoundingClientRect();tip.style.right=(innerWidth-r.left+10)+'px';tip.style.top=Math.max(12,Math.min(r.top-60,innerHeight-230))+'px';tip.hidden=false;
  }
  function renderGroup(node,group,turn){
    if(!node._body){const summary=el('summary');summary.append(icon(group.items[0].icon),el('span'),icon('chevron'));node._summary=summary.children[1];node._body=el('div','ps-tool-rows');node.append(summary,node._body);node._rows=new Map();
      node.addEventListener('toggle',()=>{if(node.open)renderToolRows(node);else{node._body.replaceChildren();node._rows.clear();}});
    }
    node._group=group;
    const running=group.items.some(i=>i.status==='running'),errors=group.items.filter(i=>i.status==='error').length;
    const label=(group.items[0].label||'工具调用')+` · ${group.items.length} 次`+(running?' · 进行中':'')+(errors?` · ${errors} 项失败`:'');
    if(node._summary.textContent!==label)node._summary.textContent=label;
    if(node.open)renderToolRows(node);
  }
  function renderToolRows(node){
    for(const item of node._group.items){
      let row=node._rows.get(item.id);
      if(!row){row=button('',()=>openTool(item), 'ps-tool-row');row.append(icon(item.icon),el('span'),el('small'));node._body.append(row);node._rows.set(item.id,row);}
      const text=item.name+(item.args?' · '+(typeof item.args==='string'?item.args:JSON.stringify(item.args)):'');
      if(row._text!==text){row._text=text;row.children[1].textContent=text;row.title=text;}
      if(row._status!==item.status){row._status=item.status;row.children[2].textContent={success:'完成',error:'失败',running:'运行中',interrupted:'已中断'}[item.status]||item.status;row.classList.toggle('ps-warning',item.status==='error');}
    }
  }
  function fileButton(turn,file,primary=false){
    const b=button('',()=>openFile(turn,file.path),primary?'ps-primary-file':'ps-file-chip');b.append(fileIcon(file.path));
    if(primary){const text=el('span');text.append(el('strong','',file.name),el('small','',file.path.split('.').pop().toUpperCase()+' · 本轮产物'));b.append(text,el('span','ps-open-label','预览 ↗'));}
    else b.append(el('span','',file.name));b.title=file.path;return b;
  }
  function renderEnding(box,turn){
    const wasExpanded=box.querySelector('.ps-more-files')?.open;
    box.replaceChildren();const files=turn.files||[],changes=turn.changes||[];
    if(files.length){const chips=el('div','ps-file-chips');for(const file of files.slice(1))chips.append(fileButton(turn,file));if(chips.children.length)box.append(chips);box.append(fileButton(turn,turn.primary||files[0],true));}
    if(changes.length){
      const card=el('div','ps-changes'),header=el('div','ps-changes-header'),description=el('div');
      description.append(el('strong','',`已更改 ${changes.length} 个文件`));const counts=el('div','ps-counts');counts.append(el('span','ps-added','+'+changes.reduce((n,c)=>n+c.added,0)),el('span','ps-removed','−'+changes.reduce((n,c)=>n+c.removed,0)));description.append(counts);
      header.append(icon('edit'),description);const undo=button('撤销 ↶',()=>undoFiles(turn),'ps-small');undo.disabled=changes.every(c=>c.undone)||['running','queued','recovering','waiting_input'].includes(turn.status);
      header.append(undo,button('查看变更',()=>openDiff(turn,changes[0].path),'ps-small'));card.append(header);
      const changeRow=c=>{const row=button('',()=>openDiff(turn,c.path),'ps-change-row');row.append(el('span','',c.path),el('small',c.undone?'':'ps-added',c.undone?'已撤销':c.binary?'二进制':'+'+c.added),el('small','ps-removed',c.undone||c.binary?'':'−'+c.removed));return row;};
      for(const c of changes.slice(0,3))card.append(changeRow(c));
      if(changes.length>3){const more=el('details','ps-more-files');more.open=!!wasExpanded;more.append(el('summary','',`再显示 ${changes.length-3} 个文件`));for(const c of changes.slice(3))more.append(changeRow(c));card.append(more);}box.append(card);
    }
    if(turn.skipped_files)box.append(el('small','ps-note',`${turn.skipped_files} 个大文件或特殊路径未保存撤销快照（单文件上限 20 MB）`));
  }
  function readingPosition(){
    if(!scroll||!list)return ()=>{};
    if(follow)return ()=>{scroll.scrollTop=scroll.scrollHeight;};
    const top=scroll.getBoundingClientRect().top,anchor=[...list.children].find(n=>n.getBoundingClientRect().bottom>top);
    const offset=anchor?.getBoundingClientRect().top;
    return ()=>{if(anchor?.isConnected)scroll.scrollTop+=anchor.getBoundingClientRect().top-offset;};
  }
  function closeDialog(restoreFocus=false){
    dialogRequest++;dialogAbort?.abort();dialogAbort=null;previewController?.abort();
    if(dialog){
      const restore=readingPosition();dialog.remove();dialog=null;previewSplitter?.remove();
      previewShell?.classList.remove('ps-has-preview','ps-resizing');
      previewShell?.style.removeProperty('--ps-chat-fr');previewShell?.style.removeProperty('--ps-preview-fr');
      restore();if(restoreFocus&&previewOpener?.isConnected)previewOpener.focus({preventScroll:true});
      previewOpener=null;document.dispatchEvent(new CustomEvent('ps:overlay',{detail:false}));
    }
  }
  function resizePreview(share){
    const restore=readingPosition();previewShare=Math.min(70,Math.max(30,share));
    previewShell.style.setProperty('--ps-chat-fr',`${100-previewShare}fr`);
    previewShell.style.setProperty('--ps-preview-fr',`${previewShare}fr`);
    previewSplitter.setAttribute('aria-valuenow',String(Math.round(previewShare)));restore();
  }
  function openDialog(title){
    dialogRequest++;dialogAbort?.abort();dialogAbort=new AbortController();
    if(!dialog){
      const restore=readingPosition();previewOpener=document.activeElement;previewShell=element.closest('#app-shell');
      previewController=new AbortController();const signal=previewController.signal;
      dialog=el('aside','ps-preview');dialog.id='ps-file-preview';dialog.setAttribute('aria-label','文件与工具预览');dialog.setAttribute('role','region');
      previewSplitter=el('div','ps-preview-splitter');previewSplitter.tabIndex=0;
      for(const [key,value] of Object.entries({role:'separator','aria-label':'调整预览宽度','aria-orientation':'vertical','aria-controls':dialog.id,'aria-valuemin':'30','aria-valuemax':'70','aria-valuenow':String(previewShare)}))previewSplitter.setAttribute(key,value);
      previewSplitter.title='拖动调整宽度；双击恢复均分';
      previewShell.classList.add('ps-has-preview');previewShell.append(previewSplitter,dialog);resizePreview(previewShare);restore();
      let drag=null,resizeFrame=0;
      const endDrag=()=>{drag=null;cancelAnimationFrame(resizeFrame);resizeFrame=0;previewShell.classList.remove('ps-resizing');};
      previewSplitter.addEventListener('pointerdown',e=>{
        if(e.button!==0)return;e.preventDefault();previewSplitter.focus({preventScroll:true});
        const work=previewShell.querySelector('#workspace').getBoundingClientRect(),pane=dialog.getBoundingClientRect();
        drag={left:work.left,right:pane.right,width:pane.right-work.left-previewSplitter.offsetWidth};previewSplitter.setPointerCapture(e.pointerId);previewShell.classList.add('ps-resizing');
      },{signal});
      previewSplitter.addEventListener('pointermove',e=>{if(!drag)return;const share=100*(drag.right-e.clientX)/drag.width;cancelAnimationFrame(resizeFrame);resizeFrame=requestAnimationFrame(()=>{resizeFrame=0;if(drag)resizePreview(share);});},{signal});
      previewSplitter.addEventListener('pointerup',endDrag,{signal});previewSplitter.addEventListener('lostpointercapture',endDrag,{signal});
      signal.addEventListener('abort',endDrag,{once:true});
      previewSplitter.addEventListener('dblclick',()=>resizePreview(50),{signal});
      previewSplitter.addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight','Home'].includes(e.key)){e.preventDefault();resizePreview(e.key==='Home'?50:previewShare+(e.key==='ArrowLeft'?5:-5));}},{signal});
      document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!e.defaultPrevented&&!document.querySelector('dialog[open]')&&!e.target.closest('input,textarea,select,[contenteditable="true"]')){e.preventDefault();closeDialog(true);}},{signal});
      document.dispatchEvent(new CustomEvent('ps:overlay',{detail:true}));
    }
    const head=el('header'),name=el('strong','',title),close=button('',()=>closeDialog(true),'ps-close');name.title=title;close.append(icon('close'));close.setAttribute('aria-label','关闭预览');
    head.append(name,close);const toolbar=el('div','ps-preview-toolbar'),body=el('div','ps-preview-body','正在载入…');body.tabIndex=0;body.setAttribute('aria-label','预览内容');dialog.replaceChildren(head,toolbar,body);
    close.focus({preventScroll:true});
    body.addEventListener('click',e=>{const a=e.target.closest('[data-file]');if(a){e.preventDefault();openFile(null,a.dataset.file);}});
    return {body,toolbar,token:dialogRequest,signal:dialogAbort.signal};
  }
  async function openFile(turn,path){
    const {body,toolbar,token,signal}=openDialog(path),query={path,turn:turn?.id||''};
    try{const result=await request(url('file-preview',query),{signal});if(token!==dialogRequest)return;
      const download=el('a','ps-small','下载原文件');download.href=url('file-content',query);download.download=path.split('/').pop();toolbar.append(el('span','',result.version),download);body.replaceChildren();
      if(result.note)body.append(el('p','ps-note',result.note));
      if(result.kind==='markdown'){const content=el('div','ps-markdown');content.innerHTML=result.html;body.append(content);}
      else if(result.kind==='text')body.append(el('pre','',result.text));
      else if(result.kind==='table'){const table=el('table','ps-data-table');for(const [i,row] of result.rows.entries()){const tr=el('tr');for(const value of row)tr.append(el(i===0?'th':'td','',String(value)));table.append(tr);}body.append(table);}
      else if(result.kind==='image'){const image=el('img','ps-preview-image');image.alt=path;image.src=url('file-content',query);body.append(image);}
      else if(result.kind==='pdf'){
        let page=0;const image=el('img','ps-pdf-page'),label=el('span'),prev=button('上一页',()=>{page--;show();},'ps-small'),next=button('下一页',()=>{page++;show();},'ps-small');
        function show(){label.textContent=`${page+1} / ${result.pages}`;prev.disabled=page===0;next.disabled=page>=result.pages-1;image.alt=`PDF 第 ${page+1} 页`;image.src=url('file-content',{...query,page});body.scrollTop=0;}
        image.onerror=()=>{label.textContent='此页加载失败，请重试或下载原文件';};toolbar.append(prev,label,next);body.append(image);show();
      }
    }catch(e){if(token===dialogRequest)body.textContent=e.message;}
  }
  async function openTool(item){
    const {body,token,signal}=openDialog(item.name);
    if(!item.detail_event_id&&!item.detail_message_id){body.textContent=item.status==='running'?'工具正在运行，完成后可查看返回结果。':'这条历史工具记录没有可用的结果。';return;}
    try{const r=await request(url('tool-detail',{event_id:item.detail_event_id||0,message_id:item.detail_message_id||0}),{signal});if(token!==dialogRequest)return;body.replaceChildren(el('pre','',r.text));if(r.truncated)body.prepend(el('p','ps-note','预览已截取前 200,000 个字符'));}catch(e){if(token===dialogRequest)body.textContent=e.message;}
  }
  async function openDiff(turn,path){
    const {body,toolbar,token,signal}=openDialog('文件变更');
    const select=el('select');select.setAttribute('aria-label','选择变更文件');for(const c of turn.changes){const option=el('option','',c.path);option.value=c.path;select.append(option);}select.value=path;select.onchange=()=>openDiff(turn,select.value);toolbar.append(select);
    try{const d=await request(url('file-diff',{turn:turn.id,path}),{signal});if(token!==dialogRequest)return;body.replaceChildren();
      if(d.undone)toolbar.append(el('span','','已撤销'));
      else{const undo=button('撤销此文件',()=>undoFiles(turn,[path]),'ps-small');undo.disabled=['running','queued','recovering','waiting_input'].includes(turn.status);toolbar.append(undo);}
      if(d.binary)body.append(el('p','','二进制文件或较大文本：可预览文件内容，逐行差异不可用。'),button('预览文件',()=>openFile(turn,path),'ps-small'));
      else{const pre=el('pre','ps-diff');for(const line of d.diff.split('\n'))pre.append(el('span',line.startsWith('+')?'ps-diff-add':line.startsWith('-')?'ps-diff-remove':'',line+'\n'));body.append(pre);}
      if(d.truncated)body.prepend(el('p','ps-note','差异预览已截取前 12,000 行'));
    }catch(e){if(token===dialogRequest)body.textContent=e.message;}
  }
  function undoFiles(turn,paths){
    const {body,toolbar,token}=openDialog('撤销文件更改');body.textContent=paths?'将恢复此文件的编辑前版本。':'将恢复本轮文件的编辑前版本；本轮新增的文件将从工作区移除。';
    body.append(el('p','ps-note','后续已修改的文件会阻止撤销，当前内容会被保留。对话记录不会删除。'));
    const confirm=button('确认撤销',async()=>{confirm.disabled=true;try{const result=await request(url('undo'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({turn_id:turn.id,paths:paths||null})});turn.changes=result.changes;dirty.add(turn.id);if(token===dialogRequest){body.textContent='已撤销 '+result.restored.length+' 个文件的更改。';toolbar.replaceChildren(button('关闭',()=>closeDialog(true),'ps-small'));}render();}catch(e){if(token===dialogRequest){body.append(el('p','ps-warning',e.message));confirm.disabled=false;}}},'ps-small');
    toolbar.append(confirm,button('取消',()=>closeDialog(true),'ps-small'));
  }
  boot();
}
