"""Opt-in live validation against the running local PaperScientist server.

The server must be configured for DeepSeek. No API key is saved by this script.
All example data and claims are explicitly synthetic.
"""
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    base = "http://127.0.0.1:8888"
    out = ROOT / ".test-output/video-skills"
    out.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=360) as client:
        health = client.get(base+"/api/health").raise_for_status().json()
        if not health["model"].startswith("deepseek:"):
            raise RuntimeError("Live validation requires the configured DeepSeek model")
        sid = client.post(base+"/api/sessions", params={"project_id":"video-skills-validation"}).raise_for_status().json()["id"]
        prompts = [
            "这是新增科研skills的集成验证，请实际调用工具。先检索适合绘制可编辑框架图的外部skill并加载一个。"
            "然后使用系统原生工具生成一个三节点框架图：文献证据→实验评估→论文表达，节点坐标0、1、2，输出PNG/PDF/SVG和.drawio。"
            "再检索Nature审稿技能，读取其说明和一个相关reference，简述它如何和我们的隔离reviewer机制配合。"
            "本轮只做技能检索、图和机制说明，不启动子代理、不安装外部软件。",
            "继续做证据链与统计图验证。所有内容仅为synthetic工程测试，不代表真实科研结论。"
            "保存计划，建立C1假设‘演示方案B的分数较高’，评估问题‘相同合成设置下B是否高于A？’。"
            "写入结果CSV：method,score,sd三列，A,0.60,0.03与B,0.70,0.04。登记为C1的synthetic结果。"
            "用该登记产物ID记录准确CSV原文证据，interpretation明确仅合成演示。"
            "生成带误差棒的bar图，问题为‘合成测试的两种配置对比’，sample_size=3，n_definition='synthetic seeds'，"
            "uncertainty_definition='synthetic standard deviation'，图标题明确synthetic。"
            "最后运行audit_research，指出为何仍不能声称真实实验证明C1。无需联网检索或执行任意脚本。"
        ]
        report = {"model":health["model"], "session_id":sid, "installed_skills":health["skills"], "turns":[]}
        for i, prompt in enumerate(prompts, 1):
            print(f"TURN {i} started", flush=True)
            events = []
            with client.stream("POST",base+f"/api/chat/{sid}",json={"message":prompt,"project_id":"video-skills-validation"}) as response:
                response.raise_for_status()
                event_type = ""
                for line in response.iter_lines():
                    if line.startswith("event: "):
                        event_type = line[7:]
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                        event = {"type": event_type, "data": data}
                        events.append(event)
                        if event["type"] == "tool_call":
                            print("  "+event["data"]["name"], flush=True)
                        elif event["type"] == "error":
                            print("  ERROR "+event["data"]["message"], flush=True)
            done = next((e["data"] for e in reversed(events) if e["type"] == "done"), {})
            report["turns"].append({"tools":[e["data"]["name"] for e in events if e["type"]=="tool_call"],
                "stop_reason":done.get("stop_reason"), "answer":done.get("content"),
                "errors":[e["data"] for e in events if e["type"]=="error"]})
            (out/"live-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
            print(f"TURN {i} {done.get('stop_reason')}",flush=True)
        snapshot = client.get(base+f"/api/sessions/{sid}").raise_for_status().json()
        names = [a["path"] for a in snapshot["artifacts"]]
        calls = [t for turn in report["turns"] for t in turn["tools"]]
        report["checks"] = {
            "completed":all(t["stop_reason"]=="completed" for t in report["turns"]),
            "skill_search":"list_skills" in calls, "skill_load":"load_skill" in calls,
            "editable_drawio":any(p.endswith(".drawio") for p in names),
            "figure_contract":any(a["kind"]=="figure_contract" for a in snapshot["artifacts"]),
            "evidence_record":any(a["kind"]=="evidence_record" for a in snapshot["artifacts"]),
            "research_audit":any(a["kind"]=="research_audit" for a in snapshot["artifacts"]),
            "no_arbitrary_execution":"run_python" not in calls,
        }
        report["artifacts"] = snapshot["artifacts"]
        (out/"live-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(report["checks"],ensure_ascii=False),flush=True)
        if not all(report["checks"].values()):
            raise SystemExit("One or more live integration checks failed; inspect live-report.json")


if __name__ == "__main__":
    main()
