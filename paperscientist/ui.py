"""A Python-authored desktop-style research workspace."""
from __future__ import annotations

import uuid
from pathlib import Path

import gradio as gr

from .ui_theme import CSS, HEAD, theme
from .timeline import mount as timeline_mount
from .workspace import Workspace
from .workspace_actions import WorkspaceActions
from .sidebar import sidebar_html, SIDEBAR_JS, SIDEBAR_CSS


def mount_ui(app, service):
    from .intro import mount_intro
    mount_intro(app)
    workspace = Workspace(service.store)
    actions = WorkspaceActions(service)

    def panels(sid, pid="default"):
        if not service.store.get_session(sid):
            session = {"id": sid, "user_id": "local", "project_id": pid}
            return workspace.memory_cards(sid, pid), service.store.injected_memory(session), service.store.project(session), [], [], [], []
        session = service.store.get_session(sid)
        # Polling UI panels must not deserialize every full tool result and checkpoint.
        paths = workspace.downloads(sid)
        figures = [p for p in paths if Path(p).suffix.lower() in {".png", ".jpg", ".jpeg"}]
        papers = [[p.get("id"), p.get("title"), p.get("year"), p.get("venue"), p.get("url")] for p in service.store.papers(session)]
        return workspace.memory_cards(sid, session["project_id"]), service.store.injected_memory(session), service.store.project(session), papers, service.store.agents(sid), paths, figures

    with gr.Blocks(title="PaperScientist", analytics_enabled=False, fill_width=True) as ui:
        session_id = gr.State("")
        project_id = gr.State("default")
        revision = gr.State("")
        pending = gr.State([])
        expanded = gr.State([])
        archived = gr.State(False)
        settings_open = gr.State(False)
        view = gr.State({"generation": 0})
        with gr.Row(elem_id="app-shell"):
            with gr.Column(elem_id="sidebar", scale=1):
                gr.Markdown("## ◈ PaperScientist\nPERSONAL RESEARCH", elem_id="brand")
                new = gr.Button("✎   新聊天", elem_id="new-chat")
                search = gr.Textbox(placeholder="搜索对话或项目", show_label=False, container=False, elem_id="chat-search")
                project_create = gr.HTML('<button type="button" class="ps-project-launch">＋ 新建项目</button>',
                    elem_id="project-create", apply_default_css=False,
                    js_on_load="import('/api/ui/projects.js?v=1').then(m => m.mount(element, trigger));")
                with gr.Column(elem_id="sidebar-list"):
                    navigation = gr.HTML("", elem_id="sidebar-nav", js_on_load=SIDEBAR_JS, apply_default_css=False)
                with gr.Row(elem_id="sidebar-bottom"):
                    refresh = gr.Button("↻  刷新", size="sm", min_width=60)
                    gr.Markdown("[重播开场](/welcome)", elem_classes="nav-caption")
            with gr.Column(elem_id="workspace", scale=4):
                heading = gr.HTML('<div class="breadcrumb"><span>▱ 我的研究</span><b>/</b><strong>新对话</strong></div>', elem_id="workspace-heading")
                with gr.Tabs(elem_id="workspace-tabs", key="workspace-tabs", preserved_by_key=["selected"]) as tabs:
                    with gr.Tab("对话", id="chat", elem_id="chat-tab"):
                        chat = gr.HTML(timeline_mount(""), elem_id="workspace-chat", apply_default_css=False,
                                       js_on_load="import('/api/ui/timeline.js?v=3').then(m => m.mount(element));")
                        question_id = gr.State("")
                        with gr.Column(visible=False, elem_id="research-question") as question_panel:
                            question_text = gr.Markdown()
                            question_options = gr.Radio(choices=[], label="建议选项（也可直接填写回答）")
                            question_answer = gr.Textbox(label="你的回答", lines=2)
                            answer_button = gr.Button("提交回答并继续", variant="primary")
                        resume_button = gr.Button("继续未完成的任务", visible=False)
                        with gr.Column(elem_id="composer"):
                            chips = gr.HTML("", elem_id="attachments")
                            clear_files = gr.Button("移除附件", size="sm", elem_id="clear-attachments")
                            query = gr.Textbox(placeholder="提出问题，或继续你的研究…", lines=2, max_lines=6, show_label=False, container=False, elem_id="query")
                            with gr.Row(elem_id="composer-toolbar"):
                                uploads = gr.UploadButton("＋", file_count="multiple", type="filepath", size="sm", scale=0, min_width=34, elem_id="attach", key="upload", preserved_by_key=["value", "interactive"])
                                settings_toggle = gr.Button("⚙", size="sm", scale=0, min_width=34, elem_id="settings-toggle")
                                execution_note = gr.HTML("允许本地执行" if service.settings.allow_execution else "本地执行已关闭", elem_id="execution-note")
                                models = [("DeepSeek Chat", "deepseek:deepseek-chat"), ("DeepSeek Reasoner", "deepseek:deepseek-reasoner"),
                                          ("Gemini 2.5 Flash", "google_genai:gemini-2.5-flash"), ("GPT-4.1", "openai:gpt-4.1"), ("离线演示", "demo")]
                                if service.settings.model not in [v for _, v in models]:
                                    models.insert(0, (service.settings.model, service.settings.model))
                                model = gr.Dropdown(choices=models, value=service.settings.model, allow_custom_value=True,
                                                    show_label=False, container=False, min_width=145, elem_id="model-picker")
                                stop = gr.Button("■", visible=False, size="sm", scale=0, min_width=36, elem_id="stop")
                                send = gr.Button("↑", size="sm", scale=0, min_width=36, elem_id="send", key="send", preserved_by_key=["interactive"])
                        status = gr.Markdown("同一项目共享记忆 · Enter 发送 / Shift + Enter 换行", elem_id="status")
                        with gr.Column(visible=False, elem_id="settings-panel", key="settings-panel", preserved_by_key=["visible"]) as settings_panel:
                            api_key = gr.Textbox(label="临时 API Key（可选）", type="password", placeholder="留空使用服务端配置；不会写入对话")
                            execution = gr.Checkbox(value=service.settings.allow_execution, label="允许运行工作区 Python / LaTeX")
                            continuous = gr.Checkbox(value=True, label="持续执行研究任务，遇到关键决策时暂停提问")
                            gr.Markdown("使用本机 Python 执行研究代码。模型选择对下一轮生效。")
                    with gr.Tab("项目记忆", id="memory"):
                        memory_cards = gr.HTML()
                        with gr.Accordion("画像、来源与记忆版本", open=False):
                            memory = gr.JSON(label="当前注入的记忆")
                        with gr.Accordion("研究计划", open=False):
                            plan = gr.JSON(label="方向、任务与贡献—评估问题")
                    with gr.Tab("论文库"):
                        papers = gr.Dataframe(headers=["引用 ID", "论文", "年份", "来源/会议", "链接"], interactive=False, label="检索证据")
                    with gr.Tab("子代理"):
                        agents = gr.JSON(label="任务、状态与结果")
                    with gr.Tab("产物与图表"):
                        files = gr.File(label="下载论文与产物（论文优先，最近 80 项；完整结果见复现包）", file_count="multiple", interactive=False, height=220)
                        figures = gr.Gallery(label="图表预览", columns=2, rows=2, height=420, object_fit="contain", interactive=False)
                    with gr.Tab("技能库"):
                        mount_skills(service)

        panel_outputs = [memory_cards, memory, plan, papers, agents, files, figures]
        controls = [send, stop, uploads]
        def control_updates(busy=False, readonly=False):
            return (gr.update(visible=not busy, interactive=not (busy or readonly)),
                    gr.update(visible=busy and not readonly, interactive=busy and not readonly),
                    gr.update(interactive=not (busy or readonly), value=None))

        outputs = [query, chat, status, *panel_outputs, revision, heading, pending, chips, clear_files, *controls]
        async def submit(text, sid, pid, selected_model, key, allow_execution, attachments, view_state, durable=False):
            if service.locks.get(sid) and service.locks[sid].locked():
                raise gr.Error("本轮还在进行，请等待完成或先停止")
            try:
                message = workspace.message(text, attachments, sid)
            except ValueError as exc:
                raise gr.Error(str(exc)) from exc
            credentials = dict(service.settings.credentials)
            provider = selected_model.split(":")[0]
            key_name = {"deepseek": "DEEPSEEK_API_KEY", "openai": "OPENAI_API_KEY", "google_genai": "GOOGLE_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(provider)
            if key and key_name:
                credentials[key_name] = key
            settings = service.settings.with_overrides(model=selected_model, credentials=credentials, allow_execution=allow_execution)
            view_state["generation"] += 1
            view_state.update(session_id=sid, stop_requested=False)
            try:
                service.store.session(sid, project_id=pid)
            except ValueError as exc:
                raise gr.Error(str(exc)) from exc
            current = service.runs.db.latest(sid)
            try:
                if current and current["status"] in {"paused", "error", "stopped"}:
                    await service.runs.continue_run(current["id"], message)
                else:
                    await service.runs.start(sid, message, project_id=pid, settings=settings.with_overrides(max_steps=60), continuous=durable)
            except ValueError as exc:
                raise gr.Error(str(exc)) from exc
            service.runs.db.preference(session_id=sid, project_id=pid)
            yield "", gr.skip(), "后台任务已启动 · 刷新或切换聊天不会停止", *panels(sid, pid), uuid.uuid4().hex, workspace.heading(sid, pid), [], "", gr.skip(), *control_updates(True)

        args = [query, session_id, project_id, model, api_key, execution, pending, view, continuous]
        event = send.click(submit, args, outputs, concurrency_limit=8, show_progress="hidden")
        enter_event = query.submit(submit, args, outputs, concurrency_limit=8, show_progress="hidden")
        reset_outputs = [session_id, project_id, chat, status, *panel_outputs, revision, heading, query, pending, chips, clear_files, *controls, tabs]

        def reset(sid, pid, note):
            if service.store.get_session(sid):
                service.runs.db.preference(session_id=sid, project_id=pid)
            is_archived = actions.metadata("session", sid).get("archived") or actions.metadata("project", pid).get("archived")
            run = service.runs.db.latest(sid)
            busy = bool(run and run['status'] in {'queued', 'running', 'recovering', 'waiting_input'})
            buttons = control_updates(busy, is_archived)
            return sid, pid, timeline_mount(sid), note, *panels(sid, pid), uuid.uuid4().hex, workspace.heading(sid, pid), gr.update(value="", interactive=not is_archived), [], "", gr.skip(), *buttons, gr.update(selected="chat")

        async def new_session(pid, previous_sid, view_state):
            view_state["generation"] += 1
            view_state["session_id"] = None
            await service.cancel_turn(previous_sid, wait_stream=True)
            if not any(p["id"] == pid and not p.get("archived") for p in actions.groups()):
                pid = active_project()
            session = service.store.new_chat(project_id=pid)
            sid = session["id"]
            actions.patch("session", sid, unread=False)
            values = list(reset(sid, pid, "已打开空白对话 · 已接入本项目记忆"))
            if sid == previous_sid:
                values[13] = gr.skip()  # Keep the unsent text when already in this blank chat.
            return values

        async def select_session(sid, previous_sid, view_state):
            session = service.store.get_session(sid)
            if not session or session["user_id"] != "local":
                raise gr.Error("未找到该对话")
            view_state["generation"] += 1
            view_state["session_id"] = None
            await service.cancel_turn(previous_sid, wait_stream=True)
            actions.patch("session", sid, unread=False)
            actions.patch("project", session["project_id"], unread=False)
            is_archived = actions.metadata("session", sid).get("archived") or actions.metadata("project", session["project_id"]).get("archived")
            return reset(sid, session["project_id"], "归档对话 · 恢复后可继续追问" if is_archived else "已恢复对话 · 可以继续追问")

        def active_project():
            groups = actions.groups()
            return groups[0]["id"] if groups else service.store.create_project("我的研究")["id"]

        async def sidebar_action(sid, pid, view_state, opened, archive_view, evt: gr.EventData):
            data = evt._data or {}
            action, target, kind = data.get("action"), data.get("id"), data.get("kind")
            values = [gr.skip() for _ in reset_outputs]
            values[11] = uuid.uuid4().hex
            interrupted = False
            try:
                if action in {"view-active", "view-archive"}:
                    return *values, opened, action == "view-archive"
                if action == "expand":
                    return *values, ([x for x in opened if x != target] if target in opened else opened + [target]), archive_view
                if action == "notice":
                    values[3] = "已复制到剪贴板"
                elif action == "new":
                    actions.target("project", target)
                    return *await new_session(target, sid, view_state), opened, False
                elif action in {"select", "open-chat", "open-memory"}:
                    values = list(await select_session(target, sid, view_state))
                    if action == "open-memory":
                        values[-1] = gr.update(selected="memory")
                else:
                    affected = actions.affected(kind, target) if action in {"archive", "delete"} else set()
                    current_affected = sid in affected or (kind == "project" and target == pid)
                    if action in {"archive", "delete"} and current_affected:
                        interrupted = True
                        view_state["generation"] += 1
                        view_state["session_id"] = None
                        await service.cancel_turn(sid, wait_stream=True)
                    result = await actions.execute(kind, target, action, data.get("value", ""), bool(data.get("confirmed")))
                    if result.get("navigate"):
                        values = list(await select_session(result["navigate"], sid, view_state))
                    elif action in {"archive", "delete"} and current_affected:
                        values = list(reset(uuid.uuid4().hex, active_project(), result["note"]))
                    else:
                        values[3] = result["note"]
                        values[12] = workspace.heading(sid, pid)
                        if action == "rename":
                            values[4] = workspace.memory_cards(sid, pid)
                return *values, opened, archive_view
            except (ValueError, OSError) as exc:
                if interrupted and not service.store.get_session(sid):
                    values = list(reset(uuid.uuid4().hex, active_project(), "操作未完成：" + str(exc)))
                else:
                    values[3] = "操作未完成：" + str(exc)
                    if interrupted:
                        values[17:20] = control_updates()
                return *values, opened, archive_view

        navigation.click(sidebar_action, [session_id, project_id, view, expanded, archived], [*reset_outputs, expanded, archived], show_progress="hidden", concurrency_limit=1)
        gr.on(triggers=[revision.change, session_id.change, search.change, expanded.change, archived.change],
              fn=lambda _r, sid, text, opened, archive_view: sidebar_html(actions, sid, text, opened, archive_view),
              inputs=[revision, session_id, search, expanded, archived], outputs=navigation, show_progress="hidden", concurrency_limit=1)

        async def start_chat(pid, previous_sid, view_state):
            return *await new_session(pid, previous_sid, view_state), False
        new.click(start_chat, [project_id, session_id, view], [*reset_outputs, archived], show_progress="hidden")
        chat.clear(start_chat, [project_id, session_id, view], [*reset_outputs, archived], show_progress="hidden")
        async def open_created_project(previous_sid, view_state, evt: gr.EventData):
            try:
                item = actions.target("project", (evt._data or {}).get("id", ""))
            except ValueError as exc:
                raise gr.Error(str(exc)) from exc
            return *await new_session(item["id"], previous_sid, view_state), False
        project_create.click(open_created_project, [session_id, view], [*reset_outputs, archived], show_progress="hidden", concurrency_limit=1)

        async def stop_turn(sid, pid, view_state):
            view_state["generation"] += 1
            view_state["stop_requested"] = True
            service.store.event(sid, "ui_stop_requested", {})
            await service.runs.stop(sid)
            await service.cancel_turn(sid, wait_stream=True)
            return "已停止 · 历史已保存，可以继续", uuid.uuid4().hex, workspace.heading(sid, pid), *control_updates()
        stop.click(stop_turn, [session_id, project_id, view], [status, revision, heading, *controls], queue=False)
        refresh.click(lambda sid, pid: (*panels(sid, pid), uuid.uuid4().hex, workspace.heading(sid, pid)),
                      [session_id, project_id], [*panel_outputs, revision, heading], show_progress="hidden")

        def upload_files(paths, sid, pid, current):
            try:
                saved = current + workspace.attach(paths, sid, pid)
            except ValueError as exc:
                raise gr.Error(str(exc)) from exc
            return saved, workspace.chips(saved), gr.skip(), gr.update(value=None), uuid.uuid4().hex, *panels(sid, pid)
        uploads.upload(upload_files, [uploads, session_id, project_id, pending], [pending, chips, clear_files, uploads, revision, *panel_outputs], show_progress="hidden")
        clear_files.click(lambda: ([], ""), outputs=[pending, chips], queue=False)
        settings_toggle.click(lambda opened: (not opened, gr.update(visible=not opened)), settings_open, [settings_open, settings_panel], queue=False)
        execution.change(lambda enabled: "允许本地执行" if enabled else "本地执行已关闭", execution, execution_note, queue=False)
        def initial_workspace(request: gr.Request):
            requested = request.query_params.get("session") if request else None
            if requested:
                try:
                    s = actions.target("session", requested)
                    actions.patch("session", requested, unread=False)
                    return reset(requested, s["project_id"], "已打开链接中的对话")
                except ValueError:
                    pass
            pid = request.query_params.get("project") if request else None
            previous = service.runs.db.preference()
            candidates = [previous.get("session_id")] + [s["id"] for s in service.store.sessions()]
            for candidate in candidates:
                s = service.store.get_session(candidate) if candidate else None
                if s and (not pid or s["project_id"] == pid) and not actions.metadata("session", s["id"]).get("archived") and not actions.metadata("project", s["project_id"]).get("archived"):
                    return reset(s["id"], s["project_id"], "已恢复上次对话 · 历史与运行状态已保存")
            if not any(p["id"] == pid for p in actions.groups()):
                pid = active_project()
            sid = service.store.new_chat(project_id=pid)["id"]
            return reset(sid, pid, "同一项目共享记忆 · Enter 发送 / Shift + Enter 换行")
        ui.load(initial_workspace, outputs=reset_outputs, show_progress="hidden")

        poll_outputs = [chat, status, *panel_outputs, revision, heading, *controls,
                        question_panel, question_text, question_options, question_answer, question_id, resume_button, execution_note]
        def poll_run(sid, pid, view_state, enabled):
            run = service.runs.db.latest(sid)
            stamp = (sid, run["id"] if run else None, run["updated_at"] if run else None)
            if view_state.get("run_stamp") == stamp:
                return [gr.skip()] * len(poll_outputs)
            view_state["run_stamp"] = stamp
            if not run:
                return *[gr.skip()] * 14, gr.update(visible=False), gr.skip(), gr.skip(), gr.skip(), "", gr.update(visible=False), ("允许本地执行" if enabled else "本地执行已关闭")
            state = run["status"]
            waiting = state == "waiting_input"
            busy = state in {"queued", "running", "recovering", "waiting_input"}
            question = run.get("pending") or {}
            qid = question.get("question_id", "") if waiting else ""
            changed = view_state.get("question_key") != (sid, qid)
            view_state["question_key"] = (sid, qid)
            readonly = actions.metadata("session", sid).get("archived") or actions.metadata("project", pid).get("archived")
            label = {"completed": "已完成", "paused": "已暂停", "error": "运行中断", "stopped": "已停止", "waiting_input": "等待你的回答", "queued": "排队中", "running": "持续执行中", "recovering": "恢复中"}[state]
            detail = " ".join((run.get("error") or run.get("preview") or "检查点已保存").split())
            note = ("已完成 · 产物已保存，可在“产物与图表”下载" if state == "completed"
                    else label + " · " + (detail[:160] + "…" if len(detail) > 160 else detail))
            controls_now = control_updates(busy, readonly)
            return (gr.skip(), note, *panels(sid, pid), uuid.uuid4().hex, workspace.heading(sid, pid), *controls_now,
                    gr.update(visible=waiting and not readonly), question.get("question", "") + "\n\n" + question.get("reason", ""),
                    gr.update(choices=question.get("options", []), value=None) if changed else gr.skip(),
                    gr.update(value="") if changed else gr.skip(), qid,
                    gr.update(visible=state in {"paused", "error", "stopped"} and not readonly),
                    ("本任务允许本地执行" if run["config"]["settings"]["allow_execution"] else "本任务本地执行已关闭") if busy else ("允许本地执行" if enabled else "本地执行已关闭"))

        async def answer_question(sid, qid, selected, answer):
            run = service.runs.db.latest(sid)
            if not run or (run.get("pending") or {}).get("question_id") != qid:
                raise gr.Error("问题已失效，请查看当前对话")
            try:
                await service.runs.answer(run["id"], qid, answer.strip() or selected or "")
            except ValueError as exc:
                raise gr.Error(str(exc)) from exc
            return "回答已保存，正在继续任务", gr.update(visible=False)

        async def resume_run(sid):
            run = service.runs.db.latest(sid)
            if not run:
                raise gr.Error("没有可继续的任务")
            try:
                await service.runs.continue_run(run["id"])
            except ValueError as exc:
                raise gr.Error(str(exc)) from exc
            return "正在从检查点继续"

        answer_button.click(answer_question, [session_id, question_id, question_options, question_answer], [status, question_panel], show_progress="hidden")
        resume_button.click(resume_run, session_id, status, show_progress="hidden")
        ticker = gr.Timer(2)
        gr.on(triggers=[ticker.tick, session_id.change], fn=poll_run, inputs=[session_id, project_id, view, execution], outputs=poll_outputs, show_progress="hidden", concurrency_limit=1)

    ui.queue(default_concurrency_limit=8, max_size=32)
    return gr.mount_gradio_app(app, ui, path="/", allowed_paths=[str(service.settings.data_dir / "workspaces")], show_error=False, css=SIDEBAR_CSS + CSS, theme=theme(), head=HEAD)


def mount_skills(service):
    source_ids = sorted({s.source.get("id", "builtin") for s in service.catalog.skills.values()})
    gr.Markdown(f"### {len(service.catalog.skills)} 个可检索技能\n按研究任务选择技能，查看来源与固定版本。")
    with gr.Row(elem_id="skill-filters"):
        query = gr.Textbox(label="搜索科研能力", placeholder="例如：审稿、框架图、统计、PubMed、实验")
        source = gr.Dropdown(choices=[("全部来源", "")]+[(s, s) for s in source_ids], value="", label="来源", elem_id="skill-source")
    search = gr.Button("检索技能")
    def search_rows(query="", source=""):
        results = service.catalog.search(query, 50, source=source)
        rows = [[s["name"], s["description"][:180], s["source"].get("url", "PaperScientist"),
                 s["source"].get("commit", "")[:12], s["source"].get("license", "project")] for s in results["skills"]]
        return rows, f"匹配 {results['total']} 项；展示前 50 项。"
    rows, count = search_rows()
    results = gr.Dataframe(value=rows, headers=["技能 ID", "用途", "来源", "版本", "许可"], interactive=False, wrap=True)
    summary = gr.Markdown(count)
    for trigger in (search.click, query.submit, source.change):
        trigger(search_rows, [query, source], [results, summary])
    name = gr.Textbox(label="查看完整技能", placeholder="例如 nature:nature-reviewer")
    read = gr.Button("读取技能说明")
    content = gr.Textbox(label="技能内容与适配说明", lines=18, interactive=False)
    def read_skill(name):
        try:
            return service.catalog.load(name.strip())
        except ValueError as exc:
            return str(exc)
    read.click(read_skill, name, content)
