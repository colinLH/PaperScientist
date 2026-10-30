#!/usr/bin/env python3
"""Portable entry point. Research/extraction and scheduling are performed by Codex."""
import argparse
import importlib.metadata
import html
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from runtime_support import (file_lock, load_config, validate_config, config_environment,
                             default_prefix, storage_names, bind_instance)

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def initialize(args):
    config_path = Path(args.config).expanduser().resolve()
    config = validate_config({
        "schema": 2,
        "domain": {"name": args.domain, "keywords": args.keyword,
                   "exclude_keywords": args.exclude_keyword, "sources": args.source, "categories": {}},
        "vault_root": str(Path(args.vault).expanduser().resolve()),
        "workspace": str(Path(args.workspace).expanduser().resolve()),
        "prefix": args.prefix or default_prefix(args.domain),
        "timezone": args.timezone,
        "papers_per_day": args.papers_per_day,
        "collect_at": args.collect_at,
        "sync_at": args.sync_at,
        "site": {"enabled": False},
    })
    root = Path(config["vault_root"]) / config["prefix"]
    if config_path.exists():
        old = load_config(config_path)
        if any(old[k] != v for k, v in config.items() if k != "site"):
            raise ValueError("Configuration already exists and differs; edit it deliberately instead of reinitializing")
        config = old
    elif root.exists() and any(root.iterdir()):
        raise ValueError("Knowledge directory is not empty; use its existing config or choose an unused prefix")
    bind_instance(config)
    names = storage_names(config)
    domain = config["domain"]["name"]
    for folder in ("01-报告", "02-论文", "03-领域", "04-知识", "05-图谱", "06-关系证据",
                   "附件/PDF", "附件/图表", "系统"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    work = Path(config["workspace"])
    for folder in ("work/sync", "work/site/dist", "work/site/data", "outputs/" + names["stem"]):
        (work / folder).mkdir(parents=True, exist_ok=True)
    index = root / "系统/collection-index.json"
    if not index.exists():
        write_json(index, {"schema": "research-obsidian/2", "records": []})
    guide = root / "使用说明.md"
    if not guide.exists():
        guide.write_text(
            f"# {domain}知识库\n\n在 01-报告 中编辑正文；source_id 保持不变。\n"
            "完整正文和本地附件核验后才设置 complete: true。\n"
            "系统生成内容放在 RESEARCH 标记之间；个人笔记写在标记之外。\n"
            "图谱、证据卡和 Canvas 是来源报告的派生视图。缺失文件不会删除既有关系。\n"
            "运行配置：" + str(config_path) + "\n", encoding="utf-8")
    readme = work / "outputs" / names["stem"] / "README.md"
    if not readme.exists():
        readme.write_text((SKILL / "assets/EXPORT_README.md").read_text(encoding="utf-8").replace("{{DOMAIN}}", domain).replace("{{DATABASE}}", names["database"]), encoding="utf-8")
    index_html = work / "work/site/dist/index.html"
    if not index_html.exists():
        index_html.write_text(
            f'<!doctype html><meta charset="utf-8"><title>{html.escape(domain)}知识图谱</title>'
            f'<h1>{html.escape(domain)}知识图谱</h1><p><a href="graphify.html">打开交互图谱</a></p>'
            '<p><a href="downloads/' + names['stem'] + '.zip">下载图谱与出处</a></p>', encoding="utf-8")
    write_json(config_path, config)
    return {"initialized": True, "config": str(config_path), "vault": str(root),
            "schedules_created": False, "next": "Run doctor, then ask Codex to create or update the schedules"}


def doctor(config):
    problems = []
    versions = {}
    if not (3, 12) <= sys.version_info[:2] < (3, 15):
        problems.append("Use Python 3.12–3.14 for the pinned runtime")
    for row in (HERE / "requirements.txt").read_text(encoding="utf-8").splitlines():
        name, wanted = row.split("==")
        try:
            actual = importlib.metadata.version(name)
            versions[name] = actual
            if actual != wanted:
                problems.append(f"{name}: expected {wanted}, got {actual}")
        except importlib.metadata.PackageNotFoundError:
            problems.append(f"Missing dependency: {name}=={wanted}")
    root = Path(config["vault_root"]) / config["prefix"]
    for path in (root / "01-报告", root / "系统/collection-index.json",
                 Path(config["workspace"]) / "work/sync"):
        if not path.exists():
            problems.append("Missing initialized path: " + str(path))
    if not problems:
        import graph_sync as graph
        from obsidian_sync import Vault
        vault = Vault(config)
        _, errors = vault.report_descriptors()
        report_issues = errors + vault.managed_conflicts()
        state = graph.load(graph.paths(config["workspace"], config=config))
        sources = len(state["sources"])
    else:
        sources = None
        report_issues = []
    return {"ok": not problems, "python": sys.executable, "versions": versions,
            "domain": config["domain"], "sources": sources, "problems": problems, "report_issues": report_issues,
            "agent_requirements": ["web search and original PDF reading/rendering", "Codex automation tool for scheduling"],
            "site_enabled": bool(config.get("site", {}).get("enabled"))}


def prompts(config, path):
    result = {}
    for mode in ("collect", "sync", "daily"):
        result[mode] = (
            f"使用 $research-obsidian 执行 {mode}。配置文件：{path}。研究领域：{config['domain']['name']}。"
            "先读取 skill 和该配置，按配置中的领域、关键词、排除词及来源偏好筛选，按配置时区确定日期，运行 doctor。"
            "这是定时执行轮次，只执行工作，不创建或修改定时任务。"
            "恢复未完成步骤，保护个人笔记，禁止重复收录；如实报告失败和实际完成范围。"
            "没有实际变化或需要处理的问题时安静结束。")
    return {"timezone": config["timezone"], "collect_at": config["collect_at"],
            "sync_at": config["sync_at"], "prompts": result, "schedules_created": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=config_environment(), required=not config_environment())
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--vault", required=True)
    init.add_argument("--workspace", required=True)
    init.add_argument("--domain", required=True)
    init.add_argument("--keyword", action="append", default=[])
    init.add_argument("--exclude-keyword", action="append", default=[])
    init.add_argument("--source", action="append", default=[])
    init.add_argument("--prefix")
    init.add_argument("--timezone", default="Asia/Shanghai")
    init.add_argument("--papers-per-day", type=int, default=2)
    init.add_argument("--collect-at", default="09:00")
    init.add_argument("--sync-at", default="13:00")
    commands.add_parser("doctor")
    commands.add_parser("prompts")
    for name in ("obsidian", "graph"):
        commands.add_parser(name).add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command == "init":
        # The same workspace lock is used by both archive and graph writers.
        with file_lock(Path(args.workspace).expanduser().resolve() / "work/sync/pipeline.lock"):
            result = initialize(args)
    else:
        config_path = Path(args.config).expanduser().resolve()
        config = load_config(config_path)
        if args.command == "doctor":
            result = doctor(config)
        elif args.command == "prompts":
            result = prompts(config, config_path)
        else:
            env = {**os.environ, "RESEARCH_OBSIDIAN_CONFIG": str(config_path), "PYTHONUTF8": "1"}
            command = [sys.executable, str(HERE / (args.command + "_sync.py"))]
            if args.command == "graph":
                command += ["--workspace", config["workspace"]]
            command += args.arguments
            with file_lock(Path(config["workspace"]) / "work/sync/pipeline.lock"):
                completed = subprocess.run(command, cwd=config["workspace"], env=env, check=False)
            return completed.returncode
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("ok") is False else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
