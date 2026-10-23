"""Structural evidence checks. These never claim to prove scientific correctness."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path

from .store import dumps


def source_record(store, session, source_type, source_id):
    if source_type == "paper":
        item = next((p for p in store.papers(session) if p["id"] == source_id), None)
        if not item:
            raise ValueError("Paper ID must exist in this project")
        text = item.get("title", "") + "\n" + (item.get("abstract") or "")
        return text, hashlib.sha256(text.encode()).hexdigest(), {
            "reading_level": "metadata/abstract", "url": item.get("url", ""), "provenance": "literature"}
    if source_type != "artifact":
        raise ValueError("source_type must be paper or artifact")
    item = next((a for a in store.artifacts(session["id"]) if a["id"] == source_id), None)
    if not item:
        raise ValueError("Artifact ID must exist in this session")
    path = Path(item["path"])
    if not path.resolve().is_relative_to(store.workspace(session["id"]).resolve()):
        raise ValueError("Artifact outside session")
    if not path.is_file() or path.stat().st_size > 5_000_000:
        raise ValueError("Evidence requires an existing text artifact up to 5MB")
    text = path.read_text(encoding="utf-8-sig")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != item["metadata"].get("sha256"):
        raise ValueError("Artifact changed after registration; register the new version first")
    return text, digest, {"reading_level": "local text artifact", "path": str(path),
                         "kind": item["kind"], "provenance": item["metadata"].get("provenance", "unverified")}


def record_evidence(store, session, claim_id, source_type, source_id, quote, interpretation, relation, locator):
    project = store.project(session)
    if claim_id not in {c["id"] for c in project.get("claims", [])}:
        raise ValueError("Define this claim with update_research_plan first")
    if relation not in {"supports", "contradicts", "context"}:
        raise ValueError("Invalid evidence relation")
    text, digest, details = source_record(store, session, source_type, source_id)
    if len(quote.strip()) < 8 or quote not in text:
        raise ValueError("Evidence quote must be an exact source substring of at least 8 characters")
    evidence_id = "ev_" + uuid.uuid4().hex[:12]
    record = {"id": evidence_id, "claim_id": claim_id, "source_type": source_type, "source_id": source_id,
              "source_sha256": digest, "quote": quote, "locator": locator, "interpretation": interpretation,
              "relation": relation, "details": details, "scope": "quote verified; interpretation requires scientific review"}
    path = store.file(session["id"], f"evidence/{evidence_id}.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(dumps(record), encoding="utf-8")
    artifact = store.artifact(session["id"], path, "evidence_record", {"evidence_id": evidence_id, "claim_id": claim_id})
    claims = project["claims"]
    for claim in claims:
        if claim["id"] == claim_id:
            claim["evidence_ids"] = list(dict.fromkeys(claim.get("evidence_ids", []) + [evidence_id]))
    store.update_project(session, {"claims": claims})
    return {**record, "artifact": artifact}


def audit_research(store, session):
    artifacts = store.artifacts(session["id"])
    evidence = {}
    issues = []
    for artifact in artifacts:
        if artifact["kind"] != "evidence_record":
            continue
        path = Path(artifact["path"])
        try:
            if hashlib.sha256(path.read_bytes()).hexdigest() != artifact["metadata"]["sha256"]:
                raise ValueError("Evidence record modified after registration")
            record = json.loads(path.read_text(encoding="utf-8"))
            _, digest, _ = source_record(store, session, record["source_type"], record["source_id"])
            if digest != record["source_sha256"]:
                raise ValueError("Evidence source has changed")
            evidence[record["id"]] = record
        except (ValueError, OSError, KeyError) as exc:
            issues.append({"type": "stale_evidence", "artifact_id": artifact["id"], "detail": str(exc)})
    claims = store.project(session).get("claims", [])
    rows = []
    for claim in claims:
        refs = claim.get("evidence_ids", [])
        verified = [evidence[r] for r in refs if r in evidence]
        unknown = [r for r in refs if r not in evidence]
        if unknown:
            issues.append({"claim_id": claim["id"], "type": "unresolved_evidence", "ids": unknown})
        measured = [a for a in artifacts if a["kind"] == "experiment_result" and a["metadata"].get("claim_id") == claim["id"]]
        statuses = []
        for a in measured:
            intact = Path(a["path"]).is_file() and hashlib.sha256(Path(a["path"]).read_bytes()).hexdigest() == a["metadata"]["sha256"]
            statuses.append({"artifact_id": a["id"], "provenance": a["metadata"]["provenance"], "hash_matches": intact})
            if not intact:
                issues.append({"claim_id": claim["id"], "type": "changed_result", "artifact_id": a["id"]})
        gaps = []
        if not claim.get("evaluation_question"):
            gaps.append("No falsifiable evaluation question")
        if not verified:
            gaps.append("No quote-verified evidence links")
        if not any(s["provenance"] == "measured" and s["hash_matches"] for s in statuses):
            gaps.append("No recorded measured result; empirical conclusion remains unverified")
        rows.append({"claim_id": claim["id"], "evidence": verified, "results": statuses, "gaps": gaps,
                     "contradictions": [r["id"] for r in verified if r["relation"] == "contradicts"]})
    report = {"status": "needs_review" if issues or not rows or any(r["gaps"] for r in rows) else "structural_checks_passed",
              "coverage": "Current session evidence/results and project claims only; semantic support and statistical validity require review.",
              "issues": issues, "claims": rows, "scientific_validity": "not established by this audit"}
    path = store.file(session["id"], f"audits/research_{time.time_ns()}.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(dumps(report), encoding="utf-8")
    return {**report, "artifact": store.artifact(session["id"], path, "research_audit")}


def figure_report(store, sid, source, *, question="", error=None, uncertainty_definition="",
                  sample_size=None, n_definition=""):
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    records = [a for a in store.artifacts(sid) if a["kind"] == "experiment_result"
               and a["metadata"].get("sha256") == digest]
    provenance = records[-1]["metadata"]["provenance"] if records else "unverified"
    gaps = []
    if not question:
        gaps.append("Scientific question not stated")
    if error and not uncertainty_definition:
        gaps.append("Error bars need a definition (SD / SEM / CI and confidence level)")
    if sample_size is None or not n_definition:
        gaps.append("Sample size and independent sampling unit not stated")
    if provenance in {"synthetic", "unverified"}:
        gaps.append("Source data cannot establish a real empirical result")
    return {"source_sha256": digest, "question": question, "provenance": provenance,
            "sample_size": sample_size, "n_definition": n_definition, "error_column": error,
            "uncertainty_definition": uncertainty_definition, "reporting_gaps": gaps,
            "render_status": "completed", "publication_readiness": "requires scientific and visual review",
            "scope": "Checks declarations and file provenance; does not recompute statistics or inspect visual overlap"}
