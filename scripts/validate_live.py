"""Opt-in real DeepSeek validation. Reads DEEPSEEK_API_KEY from this process only.

Run: python scripts/validate_live.py
Produces a local report and real execution artifacts; all benchmark data is synthetic.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from langchain_core.messages import AIMessage, HumanMessage
from paperscientist.config import ROOT, Settings, create_model
from paperscientist.context import ContextManager
from paperscientist.runtime import AgentService


async def main():
    key=os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("Set DEEPSEEK_API_KEY in the validation process environment")
    root=ROOT/".test-output"/"deepseek-live"
    cfg=Settings(data_dir=root,model="deepseek:deepseek-chat",credentials={"DEEPSEEK_API_KEY":key},
                 allow_execution=True,extract_memory=True,max_steps=24,output_tokens=4096)
    service=AgentService(cfg)
    sid="live_"+str(time.time_ns())
    report={"model":cfg.model,"session_id":sid,"turns":[],"checks":{}}
    prompts=[
        "这是科研助手的端到端验证。我长期研究机器学习与agent记忆，喜欢用中文交流，请记住这些稳定偏好。"
        "本项目资源仅有CPU，希望探索长对话agent记忆。请先保存这些项目约束，提出两个简短可行方向，并问我一个关键问题；本轮无需联网。",
        "我选择研究‘长对话记忆压缩中的证据保留’，本阶段只验证工程链路，明确所有数据都是合成测试，不作真实科研性能结论。"
        "请确认这个方向，建立一个简短研究计划和贡献-评估问题映射。用Python写一个可重复的小型实验，比较全量保留与仅保留最近消息的证据召回，"
        "生成至少3个seed的原始CSV，然后执行代码、登记合成实验结果，画一张含明确synthetic标注的学术风格图，并画一个简单的记忆工作流框架图。"
        "代码保持轻量，只用标准库、numpy和matplotlib。",
        "请让一个reviewer子代理独立审查刚才的合成实验和评估设计，向它提供产物ID，等它完成后汇总问题。"
        "同时用crossref检索2篇与long context memory compression有关的真实论文并保存；不声称读过全文。"
        "随后将当前工作组装成英文LaTeX研究草稿，包含动机、方法、实验设计、合成链路验证和局限，至少引用1个真实检索到的论文ID。"
        "把已生成的图复制到稿件的figures目录并用相对路径引用，最后使用润色与证据检查skills复核。若本机没有编译器，请准确说明。"
    ]
    try:
        for index,prompt in enumerate(prompts,1):
            print(f"TURN {index} started",flush=True)
            start=time.monotonic()
            tools=[]; done=None; errors=[]
            async for event in service.stream(sid,prompt,project_id="validation"):
                if event["type"]=="tool_call":
                    tools.append(event["data"]["name"])
                    print("  tool: "+event["data"]["name"],flush=True)
                elif event["type"]=="tool_result" and event["data"]["status"]=="error":
                    errors.append(event["data"])
                    print("  tool error: "+event["data"]["name"],flush=True)
                elif event["type"]=="done": done=event["data"]
                elif event["type"]=="error":
                    errors.append(event["data"])
                    print(event["data"]["message"],flush=True)
            report["turns"].append({"index":index,"seconds":round(time.monotonic()-start,1),"tools":tools,"errors":errors,
                                   "stop_reason":done.get("stop_reason") if done else "error", "answer":done["content"] if done else ""})
            print(f"TURN {index} complete ({len(tools)} tool calls)",flush=True)
            (root/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
            if not done:
                break
        session=service.store.get_session(sid)
        all_tools=[name for turn in report["turns"] for name in turn["tools"]]
        artifacts=service.store.artifacts(sid)
        report["checks"].update({
            "three_turns":len(report["turns"])==3 and all(t["answer"] for t in report["turns"]),
            "finished_without_budget_pause": all(t.get("stop_reason") == "completed" for t in report["turns"]),
            "profile_persisted":bool(service.store.memories("user_profile","local")),
            "direction_confirmed":service.store.project(session)["direction_confirmed"],
            "python_executed":"run_python" in all_tools,
            "experiment_registered":any(a["kind"]=="experiment_result" for a in artifacts),
            "figures_created":any(a["kind"]=="figure" for a in artifacts),
            "framework_created":any(a["kind"]=="framework" for a in artifacts),
            "child_completed":any(a["status"]=="completed" for a in service.store.agents(sid)),
            "real_papers":bool(service.store.papers(session)),
            "latex_sources":any(a["kind"]=="latex_source" for a in artifacts),
        })
        # Exercise the actual DeepSeek summary path with an explicit synthetic history fixture.
        print("COMPACTION started",flush=True)
        compact_sid="compact_"+str(time.time_ns())
        compact_session=service.store.session(compact_sid,project_id="validation")
        for i in range(8):
            service.store.append(compact_sid,HumanMessage(content=f"Synthetic validation transcript round {i}. Constraint: CPU only; all numeric results are synthetic, not research findings. "+"Evidence provenance and ablation planning. "*350))
            service.store.append(compact_sid,AIMessage(content="Planned evaluation; no real benchmark run. "+"Preserve uncertainty. "*100))
        service.store.append(compact_sid,HumanMessage(content="What is our compute constraint and can we claim real scientific performance?"))
        ccfg=cfg.with_overrides(context_tokens=8000,output_tokens=1024)
        model=create_model(ccfg)
        messages=await ContextManager(service.store,compact_session,ccfg).build("Summarize the research constraints accurately.",model)
        response=await model.ainvoke(messages)
        report["compaction"]={"checkpoint":bool(service.store.checkpoint(compact_sid)),"answer":response.content,
                              "raw_messages":len(service.store.history(compact_sid)),"context_messages":len(messages)}
        report["checks"]["real_sync_summary"]=report["compaction"]["checkpoint"]
        report["artifacts"]=artifacts
    finally:
        await service.close()
        (root/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"checks":report["checks"],"report":str(root/"report.json")},ensure_ascii=False),flush=True)


if __name__=="__main__":
    asyncio.run(main())
