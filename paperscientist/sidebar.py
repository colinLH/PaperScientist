"""Python-rendered navigation and menus, with a small native browser event bridge."""
from __future__ import annotations

from html import escape


def svg_icon(symbol):
    paths = {
        "✎": '<path d="m14 5 5 5M4 20l4-1L20 7a2.8 2.8 0 0 0-4-4L4 15z"/>',
        "♧": '<path d="m16 3 5 5-4 1-4 5 1 3-3 1-5-5 1-3 3 1 5-4zM8 16l-5 5"/>',
        "◉": '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
        "☷": '<path d="M8 5h13M8 12h13M8 19h13M3 5h.1M3 12h.1M3 19h.1"/>',
        "⑂": '<circle cx="6" cy="5" r="2"/><circle cx="18" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><path d="M6 7v10M18 7c0 6-12 2-12 8"/>',
        "↥": '<path d="M12 16V3m-4 4 4-4 4 4M5 12v8h14v-8"/>',
        "⊘": '<circle cx="12" cy="12" r="9"/><path d="m6 18 12-12"/>',
        "▣": '<rect x="8" y="8" width="13" height="13" rx="3"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/>',
        "↗": '<path d="M7 17 19 5M7 5h12v12"/>',
        "▤": '<rect x="3" y="3" width="18" height="4" rx="1"/><path d="M5 7v14h14V7M10 11h4"/>',
        "♜": '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/>',
        "▱": '<path d="M3 7V4h6l3 3h9l-4 13H2L5 9h15"/>',
    }
    return f'<svg aria-hidden="true" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">{paths[symbol]}</svg>' if symbol in paths else escape(symbol)


def item(action, label, icon="", shortcut="", value="", danger=False):
    return (f'<button type="button" role="menuitem" data-action="{action}" data-value="{escape(value, quote=True)}"'
            f' class="ps-menu-item{" danger" if danger else ""}"><span class="ps-icon">{svg_icon(icon)}</span>'
            f'<span>{label}</span><kbd>{shortcut}</kbd></button>')


def submenu(label, icon, content):
    return f'<details class="ps-submenu"><summary role="menuitem"><span class="ps-icon">{svg_icon(icon)}</span>{label}<span class="ps-chevron">›</span></summary><div role="menu">{content}</div></details>'


def menu(data, kind, sections):
    out = item("rename", "重命名", "✎", "Alt+Ctrl+R")
    out += item("pin", "取消置顶" if data.get("pinned") else "置顶", "♧", "Alt+Ctrl+P")
    out += item("unread", "标记为已读" if data.get("unread") else "标记为未读", "◉", "Ctrl+Shift+U")
    section_items = item("section", "默认分区", "", value="")
    section_items += "".join(item("section", escape(s), "✓" if data.get("section") == s else "", value=s) for s in sections)
    section_items += item("custom-section", "新建分区…", "+")
    out += submenu("分区", "☷", section_items) + '<hr>'
    if kind == "session":
        out += submenu("分叉", "⑂", item("fork", "复制完整历史与附件", value="full") + item("fork", "新对话 · 仅共享项目记忆", value="empty"))
        out += '<hr>' + item("share", "分享只读快照…", "↥") + item("unshare", "撤销分享链接", "⊘")
    out += submenu("复制", "▣", item("copy-title", "复制名称") + item("copy-link", "复制链接") + (item("copy-text", "复制对话内容") if kind == "session" else ""))
    out += '<hr>' + item("new-window", "在新窗口中打开", "↗")
    if kind == "session":
        out += submenu("打开方式", "↗", item("open-chat", "在当前窗口打开") + item("open-memory", "查看项目记忆") + item("export-md", "导出 Markdown") + item("export-json", "导出 JSON"))
    else:
        out += item("new", "在此项目新建对话", "+")
    out += '<hr>' + item("archive", "恢复归档" if data.get("archived") else "归档", "▤", "Ctrl+Shift+A")
    out += item("delete", "永久删除…", "♜", danger=True)
    return out


def sidebar_html(manager, selected, query="", opened=(), archived=False):
    groups = manager.groups(archived, query)
    all_groups = manager.groups(False) + manager.groups(True)
    sections = sorted({x.get("section") for p in all_groups for x in [p, *p["sessions"]] if x.get("section")})
    def row(data, kind="session", recent=False):
        name = data.get("name", data.get("title", ""))
        sid = data["id"]
        title = escape(name, quote=True)
        pid = data.get("project_id", sid)
        classes = "ps-nav-row " + ("ps-project" if kind == "project" else "ps-session")
        classes += " active" if kind == "session" and sid == selected else ""
        classes += " recent" if recent else ""
        badges = ('<span class="ps-unread" title="未读" aria-label="未读"></span>' if data.get("unread") else "") + ('<span class="ps-pin" title="已置顶">'+svg_icon("♧")+'</span>' if data.get("pinned") else "")
        count = len(manager.affected(kind, sid)) if kind == "project" else 1
        return (f'<div class="{classes}" data-kind="{kind}" data-id="{sid}" data-pid="{pid}" data-name="{title}" data-count="{count}" data-archived="{int(bool(data.get("archived")))}">'
                f'<button type="button" class="ps-nav-select" data-action="{"toggle" if kind == "project" else "select"}" title="{title}" {"aria-current=page" if kind == "session" and sid == selected else ""}>'
                f'{"<span class=ps-folder>"+svg_icon("▱")+"</span>" if kind == "project" else ""}<span class="ps-row-name">{escape(name)}</span>{badges}</button>'
                f'<button type="button" class="ps-more" data-action="menu" aria-label="{title}的更多操作">···</button><template class="ps-menu-template">{menu(data, kind, sections)}</template></div>')
    out = '<div class="ps-navigation"><div class="ps-nav-tabs"><button type="button" data-action="view-active" class="' + ("" if archived else "selected") + '">项目</button><button type="button" data-action="view-archive" class="' + ("selected" if archived else "") + '">归档</button></div>'
    pinned = [s for p in groups for s in p["sessions"] if s.get("pinned")]
    if pinned and not archived:
        out += '<p class="ps-caption">置顶</p>' + "".join(row(s, recent=True) for s in pinned)
    section_names = sorted(set(p.get("section", "") for p in groups), key=lambda s: (bool(s), s))
    for section in section_names:
        if section:
            out += '<p class="ps-caption">' + escape(section) + '</p>'
        for p in [p for p in groups if p.get("section", "") == section]:
            out += '<div class="ps-project-group">' + row(p, "project") + '<div class="ps-project-sessions">'
            if not archived:
                out += f'<button type="button" class="ps-new-session" data-action="new" data-kind="project" data-id="{p["id"]}">＋ 新聊天</button>'
            entries = p["sessions"]
            visible = entries if p["id"] in opened or query or archived else entries[:6]
            if selected not in {s["id"] for s in visible}:
                visible += [s for s in entries[6:] if s["id"] == selected]
            for section_name in sorted(set(s.get("section", "") for s in visible), key=lambda s: (bool(s), s)):
                if section_name:
                    out += '<p class="ps-session-section">' + escape(section_name) + '</p>'
                out += "".join(row(s) for s in visible if s.get("section", "") == section_name)
            if len(entries) > 6 and not query and not archived:
                out += f'<button type="button" class="ps-new-session" data-action="expand" data-id="{p["id"]}">{"收起" if p["id"] in opened else "展开全部 · " + str(len(entries))}</button>'
            out += '</div></div>'
    if not groups:
        out += '<p class="ps-caption">' + ("暂无归档项目或对话" if archived else "没有匹配的项目或对话") + '</p>'
    if not archived:
        recent = sorted([s for p in groups for s in p["sessions"] if s["message_count"]], key=lambda s: s["updated_at"], reverse=True)[:6]
        out += '<p class="ps-caption">最近</p>' + "".join(row(s, recent=True) for s in recent)
    return out + '</div>'


# Browser-only affordances: pointer menus, keyboard focus, clipboard, and local dialogs.
# All workspace mutations and validation remain in Python.
SIDEBAR_JS = r"""
window.__psSidebarAbort?.abort();
const abort = new AbortController(); window.__psSidebarAbort = abort;
const listen = (el, event, fn) => el.addEventListener(event, fn, {signal:abort.signal});
document.querySelectorAll('.ps-context-menu,.ps-dialog').forEach(x => x.remove());
let popup = null, dialog = null, lastRow = null, opener = null;
const closeMenu = () => { popup?.remove(); popup = null; };
const closeDialog = () => { dialog?.close(); dialog?.remove(); dialog = null; opener?.focus(); };
const emit = (data) => { closeMenu(); closeDialog(); trigger('click', data); };
function showDialog(title, description, initial, onConfirm, danger=false, readonly=false) {
  closeMenu(); closeDialog();
  dialog = document.createElement('dialog'); dialog.className = 'ps-dialog';
  dialog.setAttribute('aria-label', title);
  dialog.innerHTML = '<form><h2></h2><p></p><input aria-label="名称或链接" maxlength="80"><div class="ps-dialog-actions"><button type="button" class="ps-cancel">取消</button><button type="submit" class="ps-confirm"></button></div></form>';
  dialog.querySelector('h2').textContent = title; dialog.querySelector('p').textContent = description;
  const input = dialog.querySelector('input'); input.value = initial ?? ''; input.hidden = initial === null; input.readOnly = readonly;
  if(readonly) input.removeAttribute('maxlength');
  const confirm = dialog.querySelector('.ps-confirm'); confirm.textContent = danger ? '永久删除' : readonly ? '复制链接' : '确定';
  confirm.classList.toggle('danger', danger); dialog.querySelector('.ps-cancel').textContent = readonly ? '关闭' : '取消';
  listen(dialog.querySelector('.ps-cancel'), 'click', closeDialog);
  listen(dialog, 'cancel', (e) => {e.preventDefault(); closeDialog();});
  listen(dialog.querySelector('form'), 'submit', async(e) => { e.preventDefault(); if(initial !== null && !readonly && !input.value.trim()) {input.focus(); return;}
    try { await onConfirm(input.value); closeDialog(); } catch(err) { dialog.querySelector('p').textContent = err.message; }
  });
  document.body.append(dialog); dialog.showModal(); (input.hidden ? dialog.querySelector('.ps-cancel') : input).focus(); input.select();
}
function showMenu(row, x, y) {
  closeMenu(); lastRow = row; opener = row.querySelector('.ps-more');
  popup = document.createElement('div'); popup.className = 'ps-context-menu'; popup.setAttribute('role','menu'); popup.setAttribute('aria-label',row.dataset.name+'的操作');
  popup.innerHTML = row.querySelector('template').innerHTML;
  document.body.append(popup);
  popup.style.left = Math.max(8, Math.min(x, innerWidth-popup.offsetWidth-8))+'px';
  popup.style.top = Math.max(8, Math.min(y, innerHeight-popup.offsetHeight-8))+'px';
  listen(popup, 'click', e => { const b=e.target.closest('[data-action]'); if(b) {e.stopPropagation(); act(b.dataset.action,row,b.dataset.value || '');} });
  popup.querySelector('button').focus();
}
const urlFor = row => {const u=new URL(location.href); u.search=''; u.searchParams.set(row.dataset.kind==='project'?'project':'session',row.dataset.id); return u.href;};
async function copy(text) { try { await navigator.clipboard.writeText(text); } catch {const ta=document.createElement('textarea'); ta.value=text; document.body.append(ta); ta.select(); const ok=document.execCommand('copy'); ta.remove(); if(!ok) throw new Error('浏览器未允许复制，请手动复制内容');} }
async function act(action, row, value='') {
  const data={action,kind:row?.dataset.kind,id:row?.dataset.id,value};
  opener=row?.querySelector('.ps-more'); lastRow=row;
  try {
    if(action==='menu') {const r=row.getBoundingClientRect(); showMenu(row,r.right-12,r.top+12); return;}
    if(action==='toggle') {row.parentElement.classList.toggle('collapsed'); return;}
    if(action==='rename' || action==='custom-section') {
      showDialog(action==='rename'?'重命名':'新建分区',action==='rename'?'输入便于识别的名称。':'分区只改变侧边栏组织方式，项目记忆范围保持不变。',action==='rename'?row.dataset.name:'',v=>emit({...data,action:action==='rename'?'rename':'section',value:v})); return;
    }
    if(action==='delete') {
      const scope=row.dataset.kind==='project'?`此项目内的 ${row.dataset.count} 个对话（含子代理）、附件、项目记忆和论文库`:'此对话及其子代理、附件和由这些对话提炼的记忆';
      showDialog('永久删除“'+row.dataset.name+'”？',scope+'将被永久删除，相关分享链接失效。此操作无法撤销。',null,()=>emit({...data,confirmed:true}),true); return;
    }
    if(action==='copy-title' || action==='copy-link' || action==='copy-text') {
      let text=action==='copy-title'?row.dataset.name:urlFor(row);
      if(action==='copy-text') {const r=await fetch('/api/sessions/'+data.id+'/transcript'); if(!r.ok) throw Error('无法读取对话'); text=(await r.json()).markdown;}
      await copy(text); closeMenu(); trigger('click',{action:'notice',value:'已复制到剪贴板'}); return;
    }
    if(action==='share') {
      closeMenu();
      const r=await fetch('/api/workspace/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...data,target:data.id})});
      const result=await r.json(); if(!r.ok) throw Error(result.detail || '分享失败');
      showDialog('分享只读快照',result.note+'。仅包含可见对话，不包含项目记忆、工具日志或附件原文件。',new URL(result.url,location.origin).href,copy,false,true); return;
    }
    if(action==='new-window') {window.open(urlFor(row),'_blank','noopener,noreferrer'); closeMenu(); return;}
    if(action==='export-md' || action==='export-json') {const a=document.createElement('a'); a.href='/api/sessions/'+data.id+(action==='export-md'?'/markdown':'/export'); a.download=''; document.body.append(a); a.click(); a.remove(); closeMenu(); return;}
    emit(data);
  } catch(err) {showDialog('操作未完成',err.message,null,()=>{});}
}
listen(element,'contextmenu',e=>{const row=e.target.closest('.ps-nav-row'); if(row){e.preventDefault(); showMenu(row,e.clientX,e.clientY);}});
listen(element,'click',e=>{const b=e.target.closest('[data-action]'); if(!b) return; const row=b.closest('.ps-nav-row') || b; act(b.dataset.action,row,b.dataset.value || '');});
listen(document,'pointerdown',e=>{if(popup && !popup.contains(e.target) && !e.target.closest('.ps-more')) closeMenu();});
listen(document,'keydown',e=>{
  if(e.key==='Escape'){closeMenu(); opener?.focus(); return;}
  if(dialog) return;
  if(popup && ['ArrowDown','ArrowUp','Home','End'].includes(e.key)) {
    e.preventDefault(); const items=[...popup.querySelectorAll('button,summary')].filter(x=>x.getClientRects().length); let i=items.indexOf(document.activeElement);
    i=e.key==='Home'?0:e.key==='End'?items.length-1:(i+(e.key==='ArrowDown'?1:-1)+items.length)%items.length; items[i]?.focus(); return;
  }
  const focused=document.activeElement?.closest('.ps-nav-row');
  if((e.key==='ContextMenu' || (e.shiftKey && e.key==='F10')) && focused){e.preventDefault(); act('menu',focused); return;}
  if(e.target.closest('input,textarea,[contenteditable="true"]')) return;
  const row=focused || (popup ? lastRow : element.querySelector('.ps-nav-row.active'));
  if(!row) return;
  const key=e.key.toLowerCase(); const action=e.ctrlKey&&e.altKey&&key==='r'?'rename':e.ctrlKey&&e.altKey&&key==='p'?'pin':e.ctrlKey&&e.shiftKey&&key==='u'?'unread':e.ctrlKey&&e.shiftKey&&key==='a'?'archive':null;
  if(action){e.preventDefault(); act(action,row);}
});
"""

SIDEBAR_CSS = """
#sidebar-list {display:block; overflow-x:hidden;}
#sidebar-nav {background:transparent; border:0; padding:0;}
.ps-nav-tabs {display:flex; gap:4px; margin:12px 6px;}
.ps-nav-tabs button {background:transparent; border:0; border-radius:6px; padding:5px 10px; color:#888; font:12px inherit; cursor:pointer; transition:background .25s, color .25s, box-shadow .25s;}
.ps-nav-tabs button:hover {color:#e6e3ff;}
.ps-nav-tabs button.selected {background:linear-gradient(135deg, rgba(124,92,255,.30), rgba(34,211,238,.12)); color:#fff; box-shadow:inset 0 0 0 1px rgba(124,92,255,.35), 0 4px 16px rgba(124,92,255,.2);}
.ps-nav-row {display:flex; position:relative; align-items:center; min-height:37px; border-radius:8px; margin:2px 0; transition:background .25s, box-shadow .25s;}
.ps-nav-row:hover {background:rgba(255,255,255,.05); box-shadow:inset 0 0 0 1px rgba(255,255,255,.04);}
.ps-nav-row.active {background:linear-gradient(90deg, rgba(124,92,255,.26), rgba(34,211,238,.06)); box-shadow:inset 2px 0 0 #a78bfa, inset 0 0 0 1px rgba(124,92,255,.22), 0 6px 20px rgba(124,92,255,.14);}
.ps-nav-row.active .ps-row-name {color:#fff; text-shadow:0 0 10px rgba(196,181,253,.5);}
.ps-nav-select {display:flex; align-items:center; gap:7px; min-width:0; width:100%; border:0; background:transparent; color:#d5d5d5; cursor:pointer; text-align:left; padding:9px 10px 9px 27px; font:13px/20px 'Microsoft YaHei',sans-serif;}
.ps-project .ps-nav-select {padding-left:9px; font-size:14px;} .ps-nav-row.recent .ps-nav-select {padding-left:11px;}
.ps-row-name {overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1;}
.ps-folder {font-size:20px; line-height:16px; color:#bbb;}
.ps-more {border:0; background:transparent; color:#aaa; border-radius:5px; cursor:pointer; font-size:18px; padding:2px 6px; position:absolute; right:3px; opacity:0;}
.ps-nav-row:hover .ps-more,.ps-nav-row:focus-within .ps-more {opacity:1; background:rgba(124,92,255,.22);}
.ps-nav-row:hover .ps-nav-select,.ps-nav-row:focus-within .ps-nav-select {padding-right:29px;}
.ps-more:focus-visible,.ps-nav-select:focus-visible {outline:1px solid #8d9caf; outline-offset:-2px;}
.ps-caption {font-size:12px; color:#888; padding:17px 10px 5px; margin:0;}
.ps-new-session {display:block; border:0; background:transparent; color:#777; padding:6px 27px; font-size:12px; cursor:pointer;}
.ps-new-session:hover {color:#e9e5ff; text-shadow:0 0 10px rgba(124,92,255,.7);} .ps-project-group.collapsed .ps-project-sessions {display:none;}
.ps-session-section {color:#888; font-size:11px; margin:12px 0 5px 27px;}
.ps-unread {width:6px; height:6px; border-radius:50%; background:#67e8f9; flex-shrink:0; box-shadow:0 0 8px #22d3ee, 0 0 14px rgba(34,211,238,.6);}
.ps-pin {font-size:13px; color:#aaa;} .ps-nav-row:has(.ps-unread) .ps-row-name {color:#f1f1f1; font-weight:600;}
.ps-context-menu {position:fixed; z-index:10000; width:270px; max-width:calc(100vw - 16px); max-height:calc(100vh - 16px); overflow-y:auto; padding:6px; color:#e4e4e4; background:rgba(22,22,36,.82); backdrop-filter:blur(18px) saturate(150%); -webkit-backdrop-filter:blur(18px) saturate(150%); border:1px solid rgba(124,92,255,.28); border-radius:12px; box-shadow:0 18px 50px #0009, 0 0 30px rgba(124,92,255,.18), inset 0 1px 0 rgba(255,255,255,.06); font:13px/1.5 'Microsoft YaHei',sans-serif;}
.ps-menu-item,.ps-submenu summary {width:100%; display:flex; align-items:center; gap:10px; border:0; border-radius:6px; background:transparent; padding:8px 10px; text-align:left; color:inherit; font:inherit; cursor:pointer; box-sizing:border-box;}
.ps-menu-item:hover,.ps-menu-item:focus-visible,.ps-submenu summary:hover,.ps-submenu summary:focus-visible {background:linear-gradient(90deg, rgba(124,92,255,.28), rgba(34,211,238,.08)); outline:none;}
.ps-menu-item kbd {margin-left:auto; color:#999; font:10px/1.5 inherit; white-space:nowrap;}
.ps-menu-item.danger {color:#f49b99;}
.ps-icon {width:17px; text-align:center; font-size:16px; font-weight:400; flex-shrink:0;}
.ps-context-menu hr {border:0; border-top:1px solid rgba(255,255,255,.08); margin:5px -6px;}
.ps-chevron {margin-left:auto; color:#aaa;} .ps-submenu[open] .ps-chevron {transform:rotate(90deg);}
.ps-submenu summary {list-style:none;} .ps-submenu summary::-webkit-details-marker {display:none;}
.ps-submenu > div {padding:3px 0 3px 14px; background:rgba(255,255,255,.03); border-radius:6px;}
.ps-submenu .ps-menu-item {font-size:12px; padding:7px;}
.ps-dialog {background:rgba(22,22,36,.88); backdrop-filter:blur(20px) saturate(150%); -webkit-backdrop-filter:blur(20px) saturate(150%); color:#eee; border:1px solid rgba(124,92,255,.3); border-radius:16px; padding:25px; width:440px; max-width:calc(100vw - 40px); box-shadow:0 24px 80px #000a, 0 0 50px rgba(124,92,255,.22), inset 0 1px 0 rgba(255,255,255,.06); font:14px/1.7 'Microsoft YaHei',sans-serif;}
.ps-dialog::backdrop {background:rgba(5,5,12,.6); backdrop-filter:blur(6px);} .ps-dialog h2 {font-size:18px; font-weight:500; margin:0 0 12px; overflow-wrap:anywhere;}
.ps-dialog p {font-size:13px; color:#aaa; margin:0 0 18px;}
.ps-dialog input {box-sizing:border-box; width:100%; background:rgba(255,255,255,.05); color:#eee; border:1px solid rgba(255,255,255,.12); border-radius:8px; padding:10px; outline:none; transition:border-color .25s, box-shadow .25s;}
.ps-dialog input:focus {border-color:rgba(124,92,255,.7); box-shadow:0 0 0 3px rgba(124,92,255,.18);} .ps-dialog input[hidden] {display:none;}
.ps-dialog-actions {display:flex; justify-content:flex-end; gap:9px; margin-top:22px;}
.ps-dialog button {background:rgba(255,255,255,.08); color:#eee; border:0; border-radius:8px; padding:8px 16px; cursor:pointer; font:inherit; transition:filter .25s, box-shadow .25s;}
.ps-dialog .ps-confirm {background:linear-gradient(135deg, #a78bfa, #22d3ee); color:#0b0b18; box-shadow:0 6px 20px rgba(124,92,255,.4);} .ps-dialog .ps-confirm.danger {background:linear-gradient(135deg, #e11d48, #b94242); color:white; box-shadow:0 6px 20px rgba(225,29,72,.4);}
.ps-dialog button:hover {filter:brightness(1.12);}
@media (hover:none) {.ps-more {opacity:1;} .ps-nav-select {padding-right:30px;}}
"""
