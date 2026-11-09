const stages = {exploring: '探索中', supported: '获得支持', rejected: '未获支持', stopped: '已停止'};
const runStates = {queued:'排队中', running:'运行中', recovering:'恢复中', waiting_input:'等待回答',
  completed:'已完成', failed:'失败', stopped:'已停止', paused:'已暂停', cancelled:'已取消'};

function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
function button(text, action, cls) {
  const node = el('button', text, cls); node.type = 'button'; node.onclick = action; return node;
}
function option(value, text) {
  const node = el('option', text); node.value = value; return node;
}
function routeTitle(route) { return route.title || '未命名对话'; }

async function request(url, method = 'GET', body) {
  const response = await fetch(url, {
    method, cache:'no-store',
    ...(body && {headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)})
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const message = typeof data.detail === 'string' ? data.detail : '请求失败 (' + response.status + ')';
    throw new Error(message);
  }
  return response.json();
}

function routeOrder(routes) {
  const children = new Map(), ids = new Set(routes.map(r => r.id));
  for (const r of routes) {
    const parent = r.parent_id && r.parent_id !== r.id && ids.has(r.parent_id) ? r.parent_id : '';
    if (!children.has(parent)) children.set(parent, []);
    children.get(parent).push(r);
  }
  const output = [], seen = new Set();
  function subtree(root) {
    const pending = [[root, 0]];
    while (pending.length) {
      const [r, depth] = pending.pop();
      if (seen.has(r.id)) continue;
      seen.add(r.id); output.push([r, depth]);
      const list = children.get(r.id) || [];
      for (let i = list.length - 1; i >= 0; i--) pending.push([list[i], depth+1]);
    }
  }
  for (const r of children.get('') || []) subtree(r);
  for (const r of routes) if (!seen.has(r.id)) subtree(r);
  return output;
}

function showComparison(target, data) {
  const comp = el('div', undefined, 'ps-route-compare-result');
  const counts = data.files;
  const table = el('table');
  if (data.comparisons.length) {
    const row = table.createTHead().insertRow();
    for (const title of ['评估 / 指标','方法','基线','本路线','差值']) row.append(el('th',title));
    const body = table.createTBody();
    const format = n => Number.isFinite(n) ? Number(n.toPrecision(5)).toString() : '—';
    for (const item of data.comparisons) {
      const tr = body.insertRow();
      for (const value of [item.benchmark_id+' / '+item.metric,item.method,
        format(item.baseline)+' (n='+item.baseline_n+')',format(item.candidate)+' (n='+item.candidate_n+')',
        (item.delta>0?'+':'')+format(item.delta)]) tr.insertCell().textContent=value;
      const scope = {smoke:'冒烟验证', subset:'数据子集', full_split:'完整划分'}[item.scope];
      const provenance = item.provenance === 'local_synthetic' ? '本地合成' : '';
      const qualifiers = [provenance,scope].filter(Boolean);
      if (qualifiers.length) tr.cells[0].append(el('div',qualifiers.join(' · '),'ps-route-note'));
      if (item.baseline_run_id && item.candidate_run_id) {
        const evidence=el('details'); evidence.append(el('summary','来源'));
        evidence.append(el('p', '基线 '+item.baseline_run_id+' · 本路线 '+item.candidate_run_id));
        tr.cells[0].append(evidence);
      }
    }
    const frame=el('div', undefined, 'ps-route-table'); frame.append(table); comp.append(frame);
  }
  if (data.comparison_note) comp.append(el('p',data.comparison_note,'ps-route-note'));
  target.replaceChildren(comp);
  if (!counts) return;
  const files = el('details', undefined,'ps-route-files');
  files.append(el('summary', '已登记产物 · 新增 '+counts.added.length+' · 修改 '+counts.changed.length+
    ' · 移除 '+counts.removed.length+' · 相同 '+counts.unchanged+(counts.unknown?.length?' · 未核实 '+counts.unknown.length:'')));
  for (const [title, paths] of [['新增',counts.added],['修改',counts.changed],['移除',counts.removed],['未核实',counts.unknown || []]]) {
    if (!paths.length) continue;
    files.append(el('strong',title)); const list=el('ul'); for (const p of paths) list.append(el('li',p)); files.append(list);
  }
  comp.append(files);
}

function baselineLibrary(route, endpoint) {
  const section = el('details', undefined, 'ps-route-library');
  section.append(el('summary', '跨项目基线'));
  const body = el('div'), notice = el('p', '', 'ps-route-note'), result = el('div');
  notice.setAttribute('role', 'status');
  section.append(body, notice, result);
  function selector(label, rows, describe) {
    const select = el('select');
    select.setAttribute('aria-label', label);
    for (const [index, row] of rows.entries()) select.append(option(String(index), describe(row)));
    return select;
  }
  function controls(input, title, action) {
    const line = el('div', undefined, 'ps-route-controls');
    const submit = button(title, async () => {
      submit.disabled = true; notice.textContent = ''; result.replaceChildren();
      try { await action(); }
      catch (error) { notice.textContent = error.message; }
      finally { submit.disabled = false; }
    }, 'ps-route-secondary');
    line.append(input, submit); body.append(line);
  }
  async function load() {
    const data = await request(endpoint);
    body.replaceChildren();
    if (!route.archived) {
      if (data.runs.length) {
        const runs = selector('已核验的运行', data.runs, r => r.run_id+' · '+r.scope);
        controls(runs, '生成基线引用', async () => {
          const {plan_id, run_id} = data.runs[Number(runs.value)];
          const snapshot = await request(endpoint+'/export', 'POST', {plan_id, run_id});
          const ref = el('input'); ref.type = 'text'; ref.readOnly = true;
          ref.setAttribute('aria-label', '可复制的基线引用');
          ref.value = snapshot.source_session_id+'/'+snapshot.artifact_id;
          result.append(ref); ref.focus(); ref.select();
          notice.textContent = '复制引用后，可以在其他会话中使用。';
        });
      }
      const input = el('input'); input.placeholder = '粘贴源会话的基线引用';
      input.setAttribute('aria-label', '基线引用');
      controls(input, '引用基线', async () => {
        const parts = input.value.trim().split('/');
        if (parts.length !== 2 || parts.some(p => !p)) throw new Error('请粘贴源会话生成的完整基线引用。');
        await request(endpoint+'/attach', 'POST', {source_session_id:parts[0], artifact_id:parts[1]});
        await load(); notice.textContent = '已核验并引用基线。';
      });
    }
    const attached = data.attached.filter(r => r.valid);
    if (attached.length) {
      const refs = selector('已引用的基线', attached, r => r.benchmark_id+' · '+r.run_id);
      controls(refs, '对照已引用基线', async () => {
        const id = attached[Number(refs.value)].artifact_id;
        showComparison(result, await request(endpoint+'/'+encodeURIComponent(id)+'/compare'));
      });
    }
    if (attached.length < data.attached.length) body.append(el('p','部分基线的内容校验失败。','ps-route-note'));
    if (route.archived && !data.attached.length) body.append(el('p','此路线没有已引用的基线。','ps-route-note'));
  }
  section.ontoggle = async () => {
    if (!section.open || body.childElementCount) return;
    try { await load(); } catch (error) { notice.textContent = error.message; }
  };
  return section;
}

export function mount(element) {
  if (element.dataset.routesMounted) return;
  element.dataset.routesMounted = 'true';
  if (!document.getElementById('ps-route-styles')) {
    const link=el('link'); link.id='ps-route-styles'; link.rel='stylesheet'; link.href='/api/ui/routes.css?v=1';
    document.head.append(link);
  }
  let project='', current='', selected='', shell, visible=false, requested=false, generation=0, listRequest=0, comparison=0;
  let routes=[], byId=new Map();
  const url = () => '/api/projects/'+encodeURIComponent(project)+'/routes';
  const resource = id => url()+'/'+encodeURIComponent(id);
  const chatLink = id => '/?session='+encodeURIComponent(id);
  function notice(text, alert=false) {
    const status=shell.querySelector('.ps-route-status');
    status.textContent=text; status.setAttribute('role', alert?'alert':'status');
  }
  function context() {
    const marker=element.querySelector('.ps-route-context');
    const pid=marker?.dataset.project || '', sid=marker?.dataset.session || '';
    if (pid===project && sid===current && (!pid || shell?.isConnected)) return;
    ++generation; ++listRequest; ++comparison;
    shell?.remove(); shell=null; requested=false; project=pid; current=sid; selected=sid; routes=[]; byId=new Map();
    if (!pid || !marker) return;
    shell = el('section',undefined,'ps-routes'); shell.setAttribute('aria-label','项目研究路线');
    shell.innerHTML = '<header class="ps-routes-heading"><h2>项目研究路线</h2></header><p class="ps-route-status" role="status"></p><div class="ps-route-layout"><nav aria-label="路线列表"></nav><article aria-label="路线详情"></article></div>';
    shell.querySelector('header').append(button('刷新',()=>load(),'ps-route-quiet'));
    marker.after(shell);
    if (visible) load();
  }
  async function load() {
    const version=++listRequest; requested=true;
    notice('正在读取路线…');
    try {
      const data=await request(url());
      if (version!==listRequest) return;
      routes=data.routes; byId=new Map(routes.map(r=>[r.id,r]));
      if (!byId.has(selected)) selected = byId.has(current) ? current : routes[0]?.id;
      notice(routes.length?'':'项目里还没有可查看的研究对话。');
      draw();
    } catch (error) { if (version===listRequest) notice(error.message,true); }
  }
  function draw() {
    ++comparison;
    const nav=shell.querySelector('nav'), article=shell.querySelector('article');
    nav.replaceChildren(); article.replaceChildren();
    for (const [r, depth] of routeOrder(routes)) {
      const pick=button('',()=>{ selected=r.id; notice(''); draw(); },'ps-route-node');
      pick.style.setProperty('--indent',Math.min(depth,5));
      const branch = el('span',undefined,'ps-route-branch');
      branch.setAttribute('aria-hidden','true');
      if (depth) branch.classList.add('is-fork');
      pick.append(branch);
      if (r.id===selected) pick.setAttribute('aria-current','true');
      const name=el('span',undefined,'ps-route-name'); name.append(el('span',routeTitle(r)));
      if (r.reason) {
        const reason=el('small',r.reason,'ps-route-question'); reason.title=r.reason; name.append(reason);
      }
      pick.append(name);
      const state=el('small',r.archived?'已归档':(stages[r.status] || ''),'ps-route-state');
      state.dataset.stage=r.archived?'archived':r.status; pick.append(state);
      nav.append(pick);
    }
    if (!byId.has(selected)) return;
    const route=byId.get(selected);
    const heading=el('header',undefined,'ps-route-title'), title=el('h3',routeTitle(route));
    heading.append(title);
    const jump=el('a',route.archived?'查看对话':'打开对话','ps-route-open'); jump.href=chatLink(selected); heading.append(jump); article.append(heading);
    const source=el('p',undefined,'ps-route-note');
    if (byId.has(route.parent_id)) {
      source.append('分叉自 ', button(routeTitle(byId.get(route.parent_id)),()=>{selected=route.parent_id;draw();},'ps-route-link'));
    } else source.textContent='项目对话';
    if (route.id===current) source.append(' · 当前会话');
    if (route.run_status) source.append(' · 任务'+(runStates[route.run_status] || route.run_status));
    article.append(source);
    const fields=el('dl',undefined,'ps-route-fields');
    for (const [name,value] of [['研究理由',route.reason],['路线结论',route.outcome],['下一步',route.next_step]]) {
      if (!value) continue;
      fields.append(el('dt',name),el('dd',value));
    }
    if (fields.children.length) article.append(fields);
    if (!route.archived) {
      const actions=el('div',undefined,'ps-route-actions'), editor=el('div');
      actions.append(button('编辑记录',()=>form(editor,route,false),'ps-route-secondary'),
                     button('从此分叉',()=>form(editor,route,true),'ps-route-secondary'));
      article.append(actions,editor);
    }
    article.append(baselineLibrary(route,resource(route.id)+'/baselines'));
    if (routes.length<2) return;
    const panel=el('section',undefined,'ps-route-compare');
    panel.append(el('h4','与基线比较'));
    const line=el('div',undefined,'ps-route-controls');
    const base=el('select'); base.setAttribute('aria-label','基线会话');
    base.append(option('','选择基线会话'));
    for (const r of routes) if (r.id!==route.id) base.append(option(r.id, r.reason ? routeTitle(r)+' · '+r.reason.slice(0,60) : routeTitle(r)));
    if (route.parent_id && byId.has(route.parent_id)) base.value=route.parent_id;
    const target=el('div'); target.setAttribute('aria-live','polite');
    const compare=button('比较',async()=>{
      const id=++comparison; compare.disabled=true; target.textContent='正在核对证据…';
      try {
        const data=await request(url()+'/compare?'+new URLSearchParams({baseline:base.value,candidate:route.id}));
        if (id===comparison) showComparison(target,data);
      } catch (error) { if (id===comparison) target.textContent=error.message; }
      finally { if (id===comparison) compare.disabled=!base.value; }
    },'ps-route-secondary');
    compare.disabled=!base.value;
    base.onchange=()=>{ ++comparison; compare.disabled=!base.value; target.replaceChildren(); };
    line.append(base,compare); panel.append(line,target); article.append(panel);
  }
  function form(target, route, fork) {
    const formGeneration=generation;
    const f=el('form',undefined,'ps-route-editor'); target.replaceChildren(f);
    const inputs={};
    function field(name,title,value,required=false) {
      const label=el('label',title); const input=name==='status'?el('select'):el('textarea');
      if (name==='status') for (const [k,v] of Object.entries(stages)) input.append(option(k,v));
      else { input.rows=2; input.maxLength=1000; }
      input.value=value || ''; input.required=required; label.append(input); f.append(label); inputs[name]=input;
    }
    if (fork) field('reason','新路线要验证什么？','',true);
    else {
      field('reason','研究理由',route.reason);
      field('status','路线状态',route.status);
      field('outcome','结论或停止原因',route.outcome);
      field('next_step','下一步',route.next_step);
    }
    const controls=el('div',undefined,'ps-route-actions');
    const save=el('button',fork?'创建分叉':'保存记录','ps-route-save'); save.type='submit';
    const close=button('取消',()=>target.replaceChildren(),'ps-route-quiet');
    const error=el('p',undefined,'ps-route-error'); error.setAttribute('role','alert');
    controls.append(save,close); f.append(controls,error); f.querySelector('textarea').focus();
    f.onsubmit=async event=>{
      event.preventDefault(); if (save.disabled) return;
      const values=Object.fromEntries(Object.entries(inputs).map(([key,input])=>[key,input.value.trim()]));
      if (fork && !values.reason) { error.textContent='请填写分叉理由。'; return; }
      save.disabled=true; close.disabled=true; error.textContent='';
      try {
        if (fork) {
          const child=await request(resource(route.id)+'/fork','POST',values);
          if (generation!==formGeneration || !f.isConnected) return;
          selected=child.session_id;
        } else {
          await request(resource(route.id),'PUT',{...values,revision:route.revision});
          if (generation!==formGeneration || !f.isConnected) return;
        }
        await load();
      } catch (err) { if (generation===formGeneration && f.isConnected) error.textContent=err.message; }
      finally { save.disabled=false; close.disabled=false; }
    };
  }
  const observer=new MutationObserver(changes=>{
    if (changes.some(change=>!change.target.closest?.('.ps-routes'))) context();
  });
  observer.observe(element,{childList:true,subtree:true,attributes:true,attributeFilter:['data-session','data-project']});
  const visibility=new IntersectionObserver(entries=>{
    visible=entries.some(entry=>entry.isIntersecting);
    if (visible && shell && !requested) load();
  });
  visibility.observe(element);
  context();
}
