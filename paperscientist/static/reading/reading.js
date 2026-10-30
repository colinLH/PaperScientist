const $ = s => document.querySelector(s);
const statuses = {queued:'排队中',running:'精读中',recovering:'恢复中',waiting_input:'等待回答',paused:'已暂停',error:'执行遇到问题',completed:'已完成',stopped:'已停止'};
const tools = {search_papers:'检索论文',web_search:'查找来源',fetch_url:'核实原文来源',check_reading_archive:'检查重复论文',read_source_pdf:'阅读原文 PDF',capture_paper_figure:'保存论文原图',save_paper_review:'保存单篇精读稿',publish_reading_report:'核验并归档报告',finish_research:'整理交付结果'};
const active = new Set(['queued','running','recovering','waiting_input']);
let state = null, busy = false, timer = null, loading = false;
function el(tag, text, cls) { const node = document.createElement(tag); if(text != null) node.textContent = text; if(cls) node.className = cls; return node; }
function notice(text='', error=false) { $('#notice').textContent=text; $('#notice').dataset.error=String(error); }
async function api(path, data) {
  const response = await fetch('/api/reading'+path, data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const body = await response.json();
  if(!response.ok) throw Error(typeof body.detail === 'string' ? body.detail : '请求未能完成，请检查输入后重试');
  return body;
}
function updateSubmit() { $('#submit').disabled=busy || !state?.ready || state.jobs.some(j=>active.has(j.run?.status)); }
function humanPreview(text) {
  let result = text || '';
  for(const [name,label] of Object.entries(tools)) result=result.replaceAll(name,label);
  return result;
}
function renderJobs() {
  const host=$('#jobs'), focused=document.activeElement, editing=focused?.closest('.question');
  // Polling must never erase a partially typed answer.
  if(editing && host.contains(editing)) return;
  host.replaceChildren();
  if(!state.jobs.length) { host.append(el('p','输入一个主题，开始第一份精读报告。','empty')); return; }
  for(const job of state.jobs) {
    const card=el('div',null,'job'), top=el('div',null,'job-top'), run=job.run;
    top.append(el('h3',job.keywords));
    const badge=el('span',statuses[run?.status]||'尚未开始','badge'); badge.dataset.status=run?.status||''; top.append(badge); card.append(top);
    card.append(el('p',humanPreview(run?.error || run?.preview || '任务已创建，正在准备阅读材料。')));
    card.append(el('small',`${job.created_at.slice(0,10)} · ${job.paper_count} 篇`));
    const actions=el('div',null,'job-actions');
    function action(label, fn) { const b=el('button',label); b.type='button'; b.onclick=async()=>{b.disabled=true;try{await fn();notice('');await refresh();}catch(e){notice(e.message,true);}finally{b.disabled=false;}}; actions.append(b); }
    if(job.archive?.report_file) action('阅读报告',()=>openReport(job.archive.report_file,job.keywords));
    if(run && active.has(run.status)) action('停止',()=>api(`/jobs/${run.id}/stop`,{}));
    if(run && ['paused','error','stopped'].includes(run.status)) action('继续处理',()=>api(`/jobs/${run.id}/continue`,{}));
    card.append(actions);
    if(run?.status==='waiting_input' && run.pending) {
      const q=el('form',null,'question'), label=el('label',run.pending.question), input=el('textarea'), send=el('button','提交回答','primary');
      input.required=true; input.maxLength=10000; input.setAttribute('aria-label',run.pending.question); label.append(input); q.append(label,send);
      q.onsubmit=async e=>{e.preventDefault();send.disabled=true;try{await api(`/jobs/${run.id}/answer`,{question_id:run.pending.question_id,answer:input.value});input.blur();await refresh();}catch(err){notice(err.message,true);}finally{send.disabled=false;}};
      card.append(q);
    }
    host.append(card);
  }
}
function renderReports() {
  const host=$('#reports'), query=$('#filter').value.trim().toLocaleLowerCase(); host.replaceChildren();
  const reports=state.reports.filter(r=>r.title.toLocaleLowerCase().includes(query));
  $('#report-count').textContent=String(state.reports.length);
  if(!reports.length) {host.append(el('p',query?'没有匹配的报告。':'完成精读后，报告会出现在这里。','empty'));return;}
  for(const report of reports) {
    const row=el('div',null,'report-row'), date=el('time',report.date), button=el('button',report.title.replace(/^\d{4}-\d{2}-\d{2}[｜|：:]\s*/,''));
    date.dateTime=report.date; button.onclick=()=>openReport(report.path,report.title).catch(e=>notice(e.message,true));
    if(report.complete === false) button.prepend(el('span','草稿','draft'));
    const obsidian=el('a','↗'); obsidian.href=report.obsidian_url; obsidian.setAttribute('aria-label','在 Obsidian 打开 '+report.title);
    row.append(date,button,obsidian); host.append(row);
  }
}
async function openReport(path,title) {
  const data=await api('/report?path='+encodeURIComponent(path));
  $('#report-title').textContent=title;
  // Server parses Markdown with raw HTML disabled and resolves local URLs within the archive.
  $('#report-body').innerHTML=data.html;
  $('#report-obsidian').href=data.obsidian_url;
  $('#report-download').href='/api/reading/file?path='+encodeURIComponent(path); $('#report-download').download=path.split('/').pop();
  $('#report-dialog').showModal(); $('#report-dialog').scrollTop=0;
}
async function refresh() {
  if(loading) return; loading=true;
  try {
    state=await api('/status'); renderJobs(); renderReports();
    $('#paper-total').textContent=String(state.paper_count); $('#vault').textContent=state.vault;
    $('#open-vault').href=state.obsidian_url; $('#open-vault').hidden=false;
    if(state.warnings.length) notice(state.warnings.join('\n'),true);
    else if(!state.ready) notice('当前为演示模式。配置 PaperScientist 的模型后即可开始精读。',true);
    updateSubmit();
  }catch(e){notice('连接失败：'+e.message,true);$('#submit').disabled=true;}
  finally{loading=false;clearTimeout(timer);if(!document.hidden)timer=setTimeout(refresh,state?.jobs.some(j=>active.has(j.run?.status))?3000:15000);}
}
$('#reading-form').onsubmit=async e=>{
  e.preventDefault(); if(busy || $('#submit').disabled) return;
  busy=true;updateSubmit();notice('正在创建精读任务…');
  try { await api('/jobs',{keywords:$('#keywords').value.trim(),count:Number($('#paper-count').value)});notice('任务已开始。可以离开页面，稍后回来查看进度和报告。');await refresh(); }
  catch(err){notice(err.message,true);}finally{busy=false;updateSubmit();}
};
document.querySelectorAll('[data-keywords]').forEach(b=>b.onclick=()=>{$('#keywords').value=b.dataset.keywords;$('#keywords').focus();});
$('#filter').oninput=()=>state&&renderReports(); $('#refresh').onclick=()=>refresh();
$('#close-report').onclick=()=>$('#report-dialog').close();
document.addEventListener('visibilitychange',()=>{clearTimeout(timer);if(!document.hidden)refresh();});
refresh();
