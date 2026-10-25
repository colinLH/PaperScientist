const folderIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M3 7V5a2 2 0 0 1 2-2h4l3 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/><path d="M3 8h18"/></svg>';

export function mount(element, trigger) {
  if (element.dataset.projectsMounted) return;
  element.dataset.projectsMounted = 'true';
  if (!document.getElementById('ps-project-styles')) {
    const link = document.createElement('link');
    link.id = 'ps-project-styles'; link.rel = 'stylesheet'; link.href = '/api/ui/projects.css?v=1';
    document.head.append(link);
  }
  let dialog;
  element.querySelector('button').addEventListener('click', () => {
    if (dialog?.open) return;
    dialog = document.createElement('dialog');
    dialog.className = 'ps-project-dialog';
    dialog.setAttribute('aria-labelledby', 'ps-project-title');
    dialog.innerHTML = `<form class="ps-project-form">
      <header><h2 id="ps-project-title">创建项目</h2><button type="button" class="ps-dialog-close" aria-label="关闭创建项目">×</button></header>
      <label for="ps-project-name">项目名称</label>
      <div class="ps-name-field">${folderIcon}<input id="ps-project-name" name="name" autocomplete="off" maxlength="80" placeholder="例如：长时程 Agent 记忆" required autofocus></div>
      <div class="ps-source-label">源文件夹 <span>可选</span></div>
      <section class="ps-folder-card" aria-label="项目源文件夹">
        <p class="ps-folder-caption">在此电脑上添加文件夹</p>
        <div class="ps-selected-folder" hidden>${folderIcon}<span></span><button type="button" class="ps-folder-remove" aria-label="移除文件夹绑定">×</button></div>
        <button type="button" class="ps-folder-add">${folderIcon}<span>添加</span></button>
      </section>
      <section class="ps-folder-browser" aria-label="选择本地文件夹" hidden>
        <div class="ps-browser-header"><strong>选择本地文件夹</strong><button type="button" class="ps-browser-close" aria-label="关闭文件夹选择">×</button></div>
        <div class="ps-folder-roots"></div>
        <label class="ps-path-label" for="ps-folder-path">文件夹路径</label>
        <div class="ps-path-row"><input id="ps-folder-path" placeholder="输入完整路径" autocomplete="off"><button type="button" class="ps-folder-go">前往</button></div>
        <button type="button" class="ps-folder-up">↑ 上一级</button>
        <div class="ps-folder-list" aria-label="子文件夹"></div>
        <p class="ps-folder-error" role="status"></p>
        <button type="button" class="ps-folder-use">使用此文件夹</button>
      </section>
      <aside class="ps-project-hint"><span aria-hidden="true">✧</span><p>将聊天、文件夹和项目记忆集中整理，持续推进同一项研究。也可以不绑定文件夹，直接开始研究。</p></aside>
      <p class="ps-project-error" role="alert"></p>
      <div class="ps-project-footer"><span class="ps-memory-label" title="项目内的聊天共享项目记忆">默认记忆 <span>· 项目内共享</span></span><button type="submit" class="ps-project-submit" disabled>创建项目</button></div>
    </form>`;
    document.body.append(dialog);
    const $ = s => dialog.querySelector(s);
    const form = $('form'), name = $('#ps-project-name'), submit = $('.ps-project-submit');
    const browser = $('.ps-folder-browser'), pathInput = $('#ps-folder-path'), folderList = $('.ps-folder-list');
    const error = $('.ps-project-error'), folderError = $('.ps-folder-error');
    let folderPath = null, location = null, saving = false, browseVersion = 0, folderLoading = false;
    const close = () => { if (!saving) dialog.close(); };
    $('.ps-dialog-close').onclick = close;
    dialog.addEventListener('cancel', e => { if (saving) e.preventDefault(); });
    dialog.addEventListener('click', e => {
      const r = dialog.getBoundingClientRect();
      if (e.target === dialog && (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom)) close();
    });
    dialog.addEventListener('close', () => {
      browseVersion++; dialog.remove(); element.querySelector('button')?.focus();
    }, {once: true});
    name.oninput = () => { submit.disabled = saving || !name.value.trim(); error.textContent = ''; };
    const chooseFolder = path => {
      folderPath = path;
      $('.ps-selected-folder').hidden = !path;
      $('.ps-selected-folder span').textContent = path || '';
      $('.ps-selected-folder span').title = path || '';
      $('.ps-folder-caption').hidden = !!path;
      $('.ps-folder-add span').textContent = path ? '更换文件夹' : '添加';
      browser.hidden = true; browseVersion++;
      $('.ps-folder-add').focus();
    };
    $('.ps-folder-remove').onclick = () => chooseFolder(null);
    const closeBrowser = () => { browser.hidden = true; browseVersion++; $('.ps-folder-add').focus(); };
    $('.ps-browser-close').onclick = closeBrowser;
    function folderButton(label, path, parent) {
      const button = document.createElement('button');
      button.type = 'button'; button.textContent = label; button.title = path;
      button.onclick = () => loadFolder(path);
      parent.append(button);
    }
    async function loadFolder(path = '', offset = 0) {
      const version = ++browseVersion;
      folderError.textContent = '正在读取文件夹…'; folderLoading = true;
      $('.ps-folder-use').disabled = true;
      try {
        const response = await fetch('/api/local-folders?' + new URLSearchParams({path, offset}));
        const data = await response.json();
        if (!response.ok) throw Error(data.detail || '无法读取文件夹');
        if (version !== browseVersion || !dialog.open) return null;
        location = data; pathInput.value = data.path;
        if (!offset) folderList.replaceChildren();
        else folderList.querySelector('.ps-folder-more')?.remove();
        for (const item of data.folders) folderButton(item.name, item.path, folderList);
        if (!folderList.children.length) folderList.textContent = '没有子文件夹，可以直接选择当前文件夹。';
        if (data.next_offset !== null) {
          const more = document.createElement('button'); more.type = 'button'; more.className = 'ps-folder-more'; more.textContent = '显示更多文件夹';
          more.onclick = () => loadFolder(data.path, data.next_offset); folderList.append(more);
        }
        const roots = $('.ps-folder-roots'); roots.replaceChildren();
        for (const root of data.roots) folderButton(root, root, roots);
        $('.ps-folder-up').disabled = !data.parent;
        folderError.textContent = '';
        return data.path;
      } catch (err) {
        if (version === browseVersion) { folderError.textContent = err.message; location = null; }
        return null;
      } finally {
        if (version === browseVersion) { folderLoading = false; $('.ps-folder-use').disabled = !location; }
      }
    }
    $('.ps-folder-add').onclick = () => { browser.hidden = false; loadFolder(folderPath || ''); pathInput.focus(); };
    $('.ps-folder-go').onclick = () => loadFolder(pathInput.value.trim());
    pathInput.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); loadFolder(pathInput.value.trim()); } };
    $('.ps-folder-up').onclick = () => { if (location?.parent) loadFolder(location.parent); };
    $('.ps-folder-use').onclick = async () => {
      if (folderLoading) return;
      const path = await loadFolder(pathInput.value.trim());
      if (path) chooseFolder(path);
    };
    form.addEventListener('submit', async e => {
      e.preventDefault();
      if (saving || !name.value.trim()) return;
      if (!browser.hidden) { folderError.textContent = '请先选择文件夹，或关闭文件夹选择后创建。'; return; }
      saving = true; submit.disabled = true; submit.textContent = '正在创建…'; error.textContent = '';
      try {
        const response = await fetch('/api/projects', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:name.value.trim(), folder_path:folderPath})});
        const project = await response.json();
        if (!response.ok) throw Error(typeof project.detail === 'string' ? project.detail : '创建失败，请检查项目名称与文件夹');
        trigger('click', {id:project.id});
        saving = false; dialog.close();
      } catch (err) { error.textContent = err.message; }
      finally { saving = false; submit.disabled = !name.value.trim(); submit.textContent = '创建项目'; }
    });
    dialog.showModal();
    name.focus();
  });
}
