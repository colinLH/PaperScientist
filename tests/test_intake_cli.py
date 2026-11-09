import asyncio
import hashlib
import io
import json
from pathlib import Path

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from paperscientist import intake
from paperscientist.__main__ import dispatch, parser
from paperscientist.api import create_app
from paperscientist.config import Settings
from paperscientist.runtime import AgentService
from paperscientist.tools import ToolSet


def pdf_bytes():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=300)
    writer.add_metadata({"/Title": "Study"})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_pinned_inputs_and_receipts_via_web_and_native_tool(tmp_path, monkeypatch):
    service = AgentService(
        Settings(data_dir=tmp_path, model="demo", extract_memory=False)
    )
    store = service.store
    session = store.session("s")
    source = b"print(123)\n"
    blob = hashlib.sha1(
        b"blob " + str(len(source)).encode() + b"\x00" + source
    ).hexdigest()
    monkeypatch.setattr(
        intake,
        "inspect_git_tree",
        lambda url, ref, paths: (
            "a" * 40,
            ["README.md", "analysis.py"],
            {"analysis.py": blob},
        ),
    )

    async def fetched(url, limit):
        assert url.endswith("/" + "a" * 40 + "/analysis.py")
        return source

    monkeypatch.setattr(intake, "public_bytes", fetched)
    pdf = store.file("s", "paper.pdf")
    pdf.write_bytes(pdf_bytes())
    receipt = store.artifact("s", pdf, "upload")
    req = {
        "objective": "Check starting evidence",
        "repository": "https://github.com/example/lab",
        "source_paths": ["analysis.py"],
        "paper": "paper.pdf",
        "artifact_ids": [receipt["id"]],
    }
    with TestClient(create_app(service=service, with_ui=False)) as api:
        packet = api.post("/api/sessions/s/intake", json=req)
        assert packet.status_code == 200, packet.text
        packet = packet.json()
        assert packet["paper"]["pages"] == 1
        assert store.file("s", packet["paper"]["path"]).read_bytes() == pdf.read_bytes()
        assert (
            store.file(
                "s", packet["repository"]["files"][0]["workspace_path"]
            ).read_bytes()
            == source
        )
        assert packet["prior_artifacts"][0]["status"] == "unchanged"
        pdf.write_bytes(b"changed")
        tools = {
            t.name: t
            for t in ToolSet(
                service, session, service.settings, service.scheduler
            ).tools
        }
        result = asyncio.run(
            tools["prepare_research_intake"].ainvoke(
                {"objective": "Audit", "artifact_ids": [receipt["id"]]}
            )
        )
        assert result["prior_artifacts"][0]["status"] == "changed"
        store.session("other")
        assert (
            api.post(
                "/api/sessions/other/intake",
                json={"objective": "reuse", "artifact_ids": [receipt["id"]]},
            ).status_code
            == 400
        )
        assert (
            api.post(
                "/api/sessions/s/intake", json={**req, "source_paths": ["../escape"]}
            ).status_code
            == 400
        )
        store.session("review", parent_id="s")
        assert api.post("/api/sessions/review/intake", json=req).status_code == 404


def test_cli_starts_with_local_paper_in_dedicated_or_existing_project(tmp_path):
    pdf = tmp_path / "reference.pdf"
    pdf.write_bytes(pdf_bytes())
    service = AgentService(
        Settings(data_dir=tmp_path / "store", model="demo", extract_memory=False)
    )
    with TestClient(create_app(service=service, with_ui=False)) as api:
        project = api.post("/api/projects", json={"name": "Signals"}).json()["id"]
        empty = api.post("/api/sessions", params={"project_id": project}).json()["id"]
        args = parser().parse_args(
            ["start", "复现实验", "--project", project, "--paper-file", str(pdf)]
        )
        run = dispatch(api, args)
        assert run["session_id"] != empty and run["id"]
        status = dispatch(api, parser().parse_args(["status", run["id"]]))
        assert status["session_id"] == run["session_id"]
        packet = next(
            a
            for a in service.store.artifacts(run["session_id"])
            if a["kind"] == "research_intake"
        )
        assert json.loads(Path(packet["path"]).read_text())["paper"]["title"] == "Study"
        again = dispatch(
            api, parser().parse_args(["start", "检查已有材料", "--session", empty])
        )
        assert again["session_id"] == empty
        assert project in {
            p["id"] for p in dispatch(api, parser().parse_args(["projects"]))
        }
        assert empty in {
            r["id"] for r in dispatch(api, parser().parse_args(["routes"]))["routes"]
        }
