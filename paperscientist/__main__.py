"""Terminal client for the running PaperScientist workbench."""

import argparse
import json
from pathlib import Path
import sys
import time
from urllib.parse import quote

import httpx


def parser():
    cli = argparse.ArgumentParser(prog="python -m paperscientist")
    cli.add_argument(
        "--url",
        default="http://127.0.0.1:8888",
        help="Workbench URL (or local SSH tunnel)",
    )
    commands = cli.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "doctor",
        help="Check server, configured model, skill count and execution setting",
    )
    commands.add_parser("projects", help="List projects with their workbench IDs")
    routes = commands.add_parser("routes", help="List a project's research routes")
    routes.add_argument("project", nargs="?")
    start = commands.add_parser(
        "start", help="Start a durable research task on the workbench"
    )
    start.add_argument("objective")
    target = start.add_mutually_exclusive_group()
    target.add_argument("--project", help="Create a conversation in this project")
    target.add_argument("--session", help="Use an existing conversation")
    start.add_argument("--repo", default="", help="Public GitHub repository URL")
    start.add_argument("--revision", default="", help="Git branch, tag or commit")
    start.add_argument(
        "--source-path",
        action="append",
        default=[],
        help="Copy a file from the pinned repository (repeatable)",
    )
    paper_input = start.add_mutually_exclusive_group()
    paper_input.add_argument(
        "--paper-file", type=Path, help="Upload a local PDF to this session"
    )
    paper_input.add_argument(
        "--paper", default="", help="arXiv URL or PDF already in this session"
    )
    start.add_argument(
        "--artifact",
        action="append",
        default=[],
        help="Existing session artifact ID (repeatable)",
    )
    start.add_argument(
        "--allow-execution",
        action="store_true",
        default=None,
        help="Enable local code for this run",
    )
    status = commands.add_parser(
        "status", help="Show a durable task's current checkpoint"
    )
    status.add_argument("run")
    status.add_argument(
        "--watch",
        action="store_true",
        help="Wait until the task finishes or needs input",
    )
    resume = commands.add_parser("continue", help="Continue a paused run")
    resume.add_argument("run")
    resume.add_argument("message", nargs="?", default="")
    answer = commands.add_parser("answer", help="Answer an outstanding question")
    answer.add_argument("run")
    answer.add_argument("question_id")
    answer.add_argument("answer")
    watcher = commands.add_parser(
        "feishu-watch",
        help="Subscribe one run to your locally configured Feishu webhook",
    )
    watcher.add_argument("run")
    switches = watcher.add_mutually_exclusive_group()
    switches.add_argument("--once", action="store_true")
    switches.add_argument("--disable", action="store_true")
    stop = commands.add_parser("stop", help="Stop a durable research run")
    stop.add_argument("run")
    return cli


def request(client, method, path, **kwargs):
    r = client.request(method, path, **kwargs)
    if r.is_error:
        try:
            detail = r.json().get("detail", r.reason_phrase)
        except ValueError:
            detail = r.reason_phrase
        raise ValueError(f"HTTP {r.status_code}: {detail}")
    return r.json()


def run_summary(run):
    fields = (
        "id",
        "session_id",
        "status",
        "updated_at",
        "preview",
        "pending",
        "outcome",
        "error",
    )
    return {k: run[k] for k in fields if run.get(k)}


def dispatch(client, args):
    if args.command == "feishu-watch":
        from .feishu_watch import watch

        return watch(client, args.run, once=args.once, disable=args.disable)
    if args.command == "doctor":
        return request(client, "GET", "/api/health")
    if args.command in {"projects", "routes"}:
        if args.command == "routes" and args.project:
            return request(
                client,
                "GET",
                "/api/projects/" + quote(args.project, safe="") + "/routes",
            )
        projects = request(client, "GET", "/api/projects")
        if args.command == "projects":
            return [{"id": p["id"], "name": p["name"]} for p in projects]
        routes = []
        for project in projects:
            pid = project["id"]
            result = request(
                client, "GET", "/api/projects/" + quote(pid, safe="") + "/routes"
            )
            routes.extend(dict(route, project_id=pid) for route in result["routes"])
        return {"routes": routes}
    if args.command == "start":
        if (args.revision or args.source_path) and not args.repo:
            raise ValueError("Provide --repo for a revision or a source path")
        if not args.objective.strip():
            raise ValueError("Provide a research objective")
        if args.paper_file and (
            not args.paper_file.is_file()
            or args.paper_file.suffix.lower() != ".pdf"
            or args.paper_file.stat().st_size > 20_000_000
        ):
            raise ValueError("--paper-file must be an existing PDF of at most 20 MB")
        project = args.project or "default"
        if args.session:
            sid = args.session
            sessions = request(client, "GET", "/api/sessions")
            project = next(
                (
                    s["project_id"]
                    for s in sessions
                    if s["id"] == sid and not s.get("parent_id")
                ),
                None,
            )
            if not project:
                raise ValueError("Existing root conversation was not found")
        else:
            sid = request(
                client,
                "POST",
                "/api/sessions",
                params={"project_id": project, "dedicated": "true"},
            )["id"]
        session_path = "/api/sessions/" + quote(sid, safe="")
        objective = args.objective
        try:
            paper = args.paper
            if args.paper_file:
                with args.paper_file.open("rb") as stream:
                    paper = request(
                        client,
                        "POST",
                        session_path + "/upload",
                        files={
                            "file": (args.paper_file.name, stream, "application/pdf")
                        },
                    )["path"]
            if args.repo or paper or args.artifact:
                packet = request(
                    client,
                    "POST",
                    session_path + "/intake",
                    json={
                        "objective": objective,
                        "repository": args.repo,
                        "revision": args.revision,
                        "paper": paper,
                        "source_paths": args.source_path,
                        "artifact_ids": args.artifact,
                    },
                )
                objective += (
                    "\nResearch intake packet in this workspace: "
                    + packet["artifact"]["path"]
                )
            run = request(
                client,
                "POST",
                session_path + "/runs",
                json={
                    "message": objective,
                    "project_id": project,
                    "allow_execution": args.allow_execution,
                },
            )
        except (ValueError, httpx.HTTPError) as exc:
            raise ValueError(f"Session {sid}: {exc}") from exc
        return {
            **run_summary(run),
            "workbench": str(client.base_url).rstrip("/")
            + "/?session="
            + quote(sid, safe=""),
        }
    base = "/api/runs/" + quote(args.run, safe="")
    if args.command == "status":
        previous = None
        while True:
            summary = run_summary(request(client, "GET", base))
            if not args.watch or summary["status"] not in {
                "queued",
                "running",
                "recovering",
            }:
                return summary
            if previous != summary:
                print(json.dumps(summary, ensure_ascii=False), flush=True)
                previous = summary
            time.sleep(2)
    if args.command == "answer":
        return run_summary(
            request(
                client,
                "POST",
                base + "/answer",
                json={"question_id": args.question_id, "answer": args.answer},
            )
        )
    if args.command == "continue":
        return run_summary(
            request(client, "POST", base + "/continue", json={"message": args.message})
        )
    return run_summary(request(client, "POST", base + "/stop"))


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        timeout = 1200 if args.command == "start" else 95
        with httpx.Client(
            base_url=args.url, timeout=timeout, trust_env=False
        ) as client:
            print(json.dumps(dispatch(client, args), ensure_ascii=False, indent=2))
    except (httpx.HTTPError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
