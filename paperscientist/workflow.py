"""Session-scoped paper milestones. Project plans are shared between chats and cannot identify a chat's progress."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Literal

Stage = Literal["idea", "literature", "design", "evaluation", "writing", "review", "delivery"]
STAGES = {
    "idea": "研究选题", "literature": "文献调研", "design": "方法设计", "evaluation": "实验分析",
    "writing": "论文撰写", "review": "审阅修订", "delivery": "论文交付",
}
TOOL_STAGES = {
    "set_research_direction": "idea", "search_papers": "literature", "read_paper": "literature",
    "download_paper": "literature", "record_evidence": "literature", "plan_benchmark": "design",
    "run_benchmark": "evaluation", "record_benchmark_result": "evaluation",
    "record_experiment": "evaluation", "plot_results": "evaluation",
    "assemble_manuscript": "writing", "configure_manuscript_layout": "writing",
    "review_manuscript": "review", "validate_manuscript": "review",
    "validate_manuscript_layout": "review", "compile_latex": "writing",
}
ROLE_STAGES = {"ideation": "idea", "literature": "literature", "design": "design",
               "evaluation": "evaluation", "writing": "writing", "reviewer": "review"}
ARTIFACT_STAGES = {
    "benchmark_protocol": "design", "benchmark_result": "evaluation", "experiment_result": "evaluation",
    "source_pdf": "literature", "latex_source": "writing", "manuscript_pdf": "writing",
    "manuscript_review": "review",
}
RUN_LABEL = {"queued": "排队中", "recovering": "恢复中", "waiting_input": "等待回答",
             "paused": "已暂停", "stopped": "已停止", "error": "运行中断"}
PLAN_STAGES = {**{k: k for k in STAGES}, **{v: k for k, v in STAGES.items()},
               "exploration": "idea", "ideation": "idea", "experiment": "evaluation",
               "experiments": "evaluation", "drafting": "writing", "revision": "review"}


def session_workflow(store, sid, run):
    """Rebuild a small display from durable records, including sessions predating stage reports."""
    observed = []
    completed = {}
    reported = None
    live = bool(run and run["status"] == "running")
    with store.connect() as db:
        # Restrict by session and tool name using the partial index. Full results can be megabytes.
        names = [*TOOL_STAGES, "update_research_plan"]
        placeholders = ",".join("?" for _ in names)
        records = db.execute(f"""SELECT created_at, json_extract(data,'$.name') AS tool,
            json_extract(data,'$.status') AS status, json_extract(data,'$.result.stage') AS stage,
            json_extract(data,'$.result.direction_confirmed') AS confirmed
            FROM events WHERE session_id=? AND kind='tool_result'
            AND json_extract(data,'$.name') IN ({placeholders}) ORDER BY id""", (sid, *names))
        for date, tool, status, plan_stage, confirmed in records:
            stage = TOOL_STAGES.get(tool) or PLAN_STAGES.get(str(plan_stage).strip().lower())
            if stage:
                observed.append((date, stage))
                if tool == "set_research_direction" and status == "success" and confirmed:
                    completed[stage] = "已记录用户确认的研究方向"
        for kind, date in db.execute("SELECT kind,max(created_at) FROM artifacts WHERE session_id=? GROUP BY kind", (sid,)):
            if kind in ARTIFACT_STAGES:
                observed.append((date, ARTIFACT_STAGES[kind]))
        # An explicit stage change is committed in the same receipt as its visible progress message.
        for date, tid, data in db.execute("""SELECT created_at,turn_id,data FROM ui_events
                WHERE session_id=? AND kind='workflow' ORDER BY id""", (sid,)):
            entry = json.loads(data)
            for stage in entry.get("completed", []):
                if stage in STAGES and stage != "delivery":
                    completed[stage] = "研究助手已报告此阶段完成"
            stage = entry.get("stage")
            if stage in STAGES:
                observed.append((date, stage))
                if run and tid == run["id"]:
                    reported = stage
        for role, date in db.execute("""SELECT json_extract(data,'$.role'), json_extract(data,'$.updated_at')
                FROM agents WHERE parent_id=?""", (sid,)):
            if role in ROLE_STAGES and date:
                observed.append((date, ROLE_STAGES[role]))
        # Only a completed turn that actually delivered a registered manuscript PDF closes delivery.
        # A completed literature question, a PDF source paper or a failed compile never does.
        root = store.root / "workspaces" / sid
        pdfs = {Path(row[0]).resolve() for row in db.execute(
            "SELECT DISTINCT path FROM artifacts WHERE session_id=? AND kind='manuscript_pdf'", (sid,))}
        if pdfs:
            for date, outcome in db.execute("""SELECT updated_at,outcome FROM research_runs
                    WHERE session_id=? AND status='completed' AND outcome IS NOT NULL ORDER BY updated_at DESC""", (sid,)):
                if any((root / path).resolve() in pdfs and (root / path).is_file()
                       for path in json.loads(outcome).get("artifacts", [])):
                    completed["delivery"] = "已交付本会话登记的论文 PDF"
                    completed.setdefault("writing", "已生成并交付论文稿件")
                    observed.append((date, "delivery"))
                    break

    last_date, last = max(observed, key=lambda item: item[0], default=("", None))
    state = run["status"] if run else None
    in_this_run = bool(run and last_date >= run["created_at"])
    current = reported if reported and state != "completed" else last
    active = live and in_this_run
    if live and not reported:
        tool = (run.get("preview") or "").removeprefix("正在调用 ")
        if tool in TOOL_STAGES:
            current, active = TOOL_STAGES[tool], True
    delivered = current == "delivery" and "delivery" in completed and state == "completed"
    # Earlier stages may be skipped or revisited. Order alone is never completion evidence.
    steps = []
    touched = {stage for _, stage in observed}
    for key, label in STAGES.items():
        if key == current and not delivered and (active or key not in completed):
            status = "active" if active else "current"
        elif key in completed:
            status = "done"
        else:
            status = "visited" if key in touched else "pending"
        steps.append({"id": key, "label": label, "status": status, "evidence": completed.get(key, "")})
    if delivered:
        caption = "已交付论文"
    elif state in RUN_LABEL:
        caption = (STAGES[current] + " · " if current else "") + RUN_LABEL[state]
    elif current:
        caption = ("进行中 · " if active else "最近阶段 · ") + STAGES[current]
    else:
        caption = "等待阶段记录" if run else "尚未开始"
    return {"session_id": sid, "summary": caption, "steps": steps}


def workflow_html(progress):
    labels = {"active": "进行中", "current": "当前阶段", "done": "已完成", "visited": "有活动记录", "pending": "待开展"}
    items = []
    for step in progress["steps"]:
        status, label = step["status"], step["label"]
        current = ' aria-current="step"' if status in {"active", "current"} else ""
        title = step["evidence"] if status == "done" else labels[status]
        items.append(f'<li data-status="{status}" data-stage="{step["id"]}"{current} title="{title}">'
                     f'<i aria-hidden="true">{"✓" if status == "done" else ""}</i>'
                     f'<span>{label}</span><span class="ps-sr-only">，{labels[status]}</span></li>')
    return (f'<section class="ps-workflow" data-session="{html.escape(progress["session_id"],quote=True)}" aria-label="论文进度">'
            f'<div class="ps-workflow-title"><strong>论文进度</strong><span role="status">{html.escape(progress["summary"])}</span></div>'
            f'<ol>{"".join(items)}</ol></section>')
