"""Resume the saved DeepSeek validation after fixes; preserve the original report."""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from paperscientist.config import ROOT, Settings
from paperscientist.runtime import AgentService
from paperscientist.artifacts import validate_manuscript


async def main():
    root=ROOT/".test-output"/"deepseek-live"
    original=json.loads((root/"report.json").read_text(encoding="utf-8"))
    cfg=Settings(data_dir=root,model="deepseek:deepseek-chat",credentials={"DEEPSEEK_API_KEY":os.environ["DEEPSEEK_API_KEY"]},
                 allow_execution=True,extract_memory=True,max_steps=40)
    service=AgentService(cfg); sid=original["session_id"]
    report={"model":cfg.model,"session_id":sid,"tools":[],"errors":[]}
    prompt=("继续上轮保存的工程验证，只完成收尾，不新增科研实验。工具已修复：run_python现在自动登记生成的图和数据；"
        "spawn_agent任务名可用小写英文字母数字下划线连字符，角色必须为枚举值。请先load_skill paper-polish和evidence-review。"
        "1. 重跑plot_synthetic_results.py，确认图产物和运行记录。重画一个简单英文框架图，区分full参考与recent-k有限窗口。"
        "2. 找到现有LaTeX稿件，把图复制到该实际目录的figures子目录，使用相对路径引用。把现有子代理审查的关键限制纳入稿件，保持所有数据synthetic。"
        "3. 使用role='reviewer'和task_name='final-review'创建一个短审查：只检查上述源文件与图引用、synthetic声明；给它实际artifact ID，"
        "要求不编辑文件、不联网、最多三条问题。等待并读取结果。4. 使用validate_manuscript检查引用文件完整性并修复，"
        "调用compile_latex准确报告本机可用性；用export_bundle将该稿件目录打包。最后中文简洁汇总确实完成内容和未完成限制，不再开启新工作。")
    start=time.monotonic()
    try:
        async for event in service.stream(sid,prompt,project_id="validation"):
            kind,data=event["type"],event["data"]
            if kind=="tool_call":
                report["tools"].append(data["name"]); print("tool: "+data["name"],flush=True)
            elif kind=="tool_result" and data["status"]=="error":
                report["errors"].append(data); print("tool error: "+data["name"],flush=True)
            elif kind=="error": report["errors"].append(data)
            elif kind=="done":
                report["answer"]=data["content"]; report["stop_reason"]=data.get("stop_reason")
        all_artifacts=service.store.artifacts(sid)
        manuscripts=list(service.store.workspace(sid).rglob("main.tex"))
        integrity=[validate_manuscript(service.store,sid,str(p.relative_to(service.store.workspace(sid)))) for p in manuscripts]
        report["integrity"]=integrity
        agents=service.store.agents(sid)
        report["checks"]={"resumed_to_completion":report.get("stop_reason")=="completed",
            "figures_registered":any(a["kind"]=="figure" for a in all_artifacts),
            "reviewer_completed":any(a["role"]=="reviewer" and a["status"]=="completed" for a in agents),
            "manuscript_integrity":bool(integrity) and all(i["status"]=="passed" for i in integrity),
            "bundle_created":any(a["kind"]=="bundle" for a in all_artifacts),
            "compiler_checked":"compile_latex" in report["tools"]}
        report["seconds"]=round(time.monotonic()-start,1)
    finally:
        await service.close()
        (root/"resume-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report.get("checks",{})),flush=True)


if __name__=="__main__": asyncio.run(main())
