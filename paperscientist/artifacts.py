from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import math
import os
import shutil
import sys
import time
from pathlib import Path

from .store import dumps
from .process_job import ProcessJob


async def run_python(store, sid, path, enabled, timeout=120):
    if not enabled:
        raise PermissionError("Python execution is disabled. Enable it in Web settings or PS_ALLOW_EXECUTION=true for trusted local work.")
    script = store.file(sid, path)
    if script.suffix != ".py" or not script.is_file():
        raise ValueError("Select an existing .py file in the session workspace")
    timeout = max(1, min(timeout, 300))
    script_hash = hashlib.sha256(script.read_bytes()).hexdigest()
    # Explicitly omit all API keys, tokens and database credentials from child env.
    allowed = {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "HOME", "USERPROFILE", "LANG", "CONDA_PREFIX"}
    env = {k: v for k, v in os.environ.items() if k.upper() in allowed}
    env.update(PYTHONIOENCODING="utf-8", MPLBACKEND="Agg")
    out_dir = store.workspace(sid) / "runs"
    out_dir.mkdir(exist_ok=True)
    run_id = f"run_{time.time_ns()}"
    stdout_path, stderr_path = out_dir / f"{run_id}.stdout.txt", out_dir / f"{run_id}.stderr.txt"
    test_evidence = out_dir / f"{run_id}.tests.json"
    started = time.monotonic()
    def result_snapshot():
        root = store.workspace(sid)
        return {str(p.relative_to(root)).replace("\\", "/"): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
                for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {
                    ".csv", ".json", ".png", ".pdf", ".svg", ".jpg", ".jpeg", ".tex", ".bib", ".md", ".txt", ".py"}
                and p.resolve().is_relative_to(root.resolve())
                and not {".git", "__pycache__", ".ui-cache", ".zig-cache", ".pytest_cache", "localappdata", "wheels"}.intersection(p.relative_to(root).parts)
                and p.stat().st_size <= 20_000_000 and not p.is_relative_to(out_dir)}
    before = result_snapshot()
    timed_out = False
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        observer_path = str(Path(__file__).with_name('test_execution.py').resolve())
        runner = f"import runpy,sys;worker=runpy.run_path({observer_path!r});worker['execute'](*sys.argv[1:])"
        proc = await asyncio.create_subprocess_exec(sys.executable, "-I", "-c", runner, str(script), str(store.workspace(sid)), str(test_evidence),
            cwd=store.workspace(sid), env=env, stdout=stdout, stderr=stderr)
        job = None
        try:
            job = ProcessJob(proc.pid)
            await asyncio.wait_for(proc.wait(), timeout)
        except asyncio.TimeoutError:
            timed_out = True
            proc.kill()
            await proc.wait()
        except BaseException:
            proc.kill()
            await proc.wait()
            raise
        finally:
            if job:
                job.close()
    record = {"run_id": run_id, "script": path, "script_sha256": script_hash,
              "exit_code": proc.returncode, "timed_out": timed_out, "duration_seconds": round(time.monotonic() - started, 3),
              "stdout": stdout_path.read_text(encoding="utf-8", errors="replace")[-12000:],
              "stderr": stderr_path.read_text(encoding="utf-8", errors="replace")[-12000:]}
    record['input_source_hashes'] = {name:digest for name,(_,digest) in before.items() if name.endswith('.py')}
    record['unit_tests'] = (json.loads(test_evidence.read_text(encoding='utf-8')) if test_evidence.is_file()
                            else {'observer':'unavailable', 'tests':0, 'successful':False})
    record["output_files"] = {name: digest for name, (mtime, digest) in result_snapshot().items()
                              if before.get(name) != (mtime, digest)}
    log = out_dir / f"{run_id}.json"
    log.write_text(dumps(record), encoding="utf-8")
    record["artifact"] = store.artifact(sid, log, "execution")
    record["generated_artifacts"] = []
    for name in record["output_files"]:
        file = store.file(sid, name)
        kind = "figure" if file.suffix.lower() in {".png", ".svg", ".pdf", ".jpg", ".jpeg"} else "generated_file"
        record["generated_artifacts"].append(store.artifact(sid, file, kind, {
            "run_id": run_id, "script_sha256": script_hash, "exit_code": proc.returncode,
            "data_status": "unverified; register experiment provenance separately"}))
    return record


def figure_fonts():
    """Use a locally installed CJK font when available; retain a portable Latin fallback."""
    from matplotlib import font_manager
    available = {f.name for f in font_manager.fontManager.ttflist}
    candidates = ("Microsoft YaHei", "Noto Sans CJK SC", "Source Han Sans SC", "SimHei", "PingFang SC")
    return [next((name for name in candidates if name in available), "DejaVu Sans"), "DejaVu Sans"]


def plot_results(store, sid, csv_path, x, y, group=None, error=None, title="", ylabel=None, kind="line"):
    """Generate a self-contained plotting script and vector/raster outputs from real CSV rows."""
    if kind not in {"line", "bar", "scatter"}:
        raise ValueError("kind must be line, bar or scatter")
    source = store.file(sid, csv_path)
    with source.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows or any(c and c not in rows[0] for c in (x, y, group, error)):
        raise ValueError("CSV is empty or requested columns do not exist")
    if len(rows) > 100000:
        raise ValueError("Plot at most 100000 rows")
    for row in rows:
        if not math.isfinite(float(row[y])):
            raise ValueError("Figure values must be finite; handle missing values explicitly")
        if error:
            if not math.isfinite(float(row[error])) or float(row[error]) < 0:
                raise ValueError("Error bars must be finite and nonnegative")
    folder = store.workspace(sid) / "figures" / f"plot_{time.time_ns()}"
    folder.mkdir(parents=True)
    options = {"csv_path": os.path.relpath(source, folder), "x": x, "y": y, "group": group,
               "error": error, "title": title, "ylabel": ylabel or y, "kind": kind, "fonts": figure_fonts()}
    code = '''import csv, json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
OPTIONS = json.loads(OPTIONS_JSON)
with (HERE / OPTIONS["csv_path"]).open(encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))
plt.rcParams.update({"font.family":OPTIONS["fonts"], "font.size":10, "axes.spines.top":False,
    "axes.spines.right":False, "pdf.fonttype":42, "ps.fonttype":42, "savefig.bbox":"tight"})
fig, ax = plt.subplots(figsize=(6.2, 3.8), layout="constrained")
groups = list(dict.fromkeys(r[OPTIONS["group"]] if OPTIONS["group"] else "Results" for r in rows))
categories = list(dict.fromkeys(r[OPTIONS["x"]] for r in rows))
for idx, label in enumerate(groups):
    subset = [r for r in rows if not OPTIONS["group"] or r[OPTIONS["group"]] == label]
    labels = [r[OPTIONS["x"]] for r in subset]
    try:
        xx = [float(v) for v in labels]
    except ValueError:
        xx = [categories.index(v) for v in labels]
        ax.set_xticks(range(len(categories)), categories)
    yy = [float(r[OPTIONS["y"]]) for r in subset]
    err = [float(r[OPTIONS["error"]]) for r in subset] if OPTIONS["error"] else None
    if OPTIONS["kind"] == "bar":
        width = .8 / len(groups)
        xx = [categories.index(v) + (idx - (len(groups)-1)/2)*width for v in labels]
        ax.bar(xx, yy, width=width, yerr=err, capsize=3, label=label)
        ax.set_xticks(range(len(categories)), categories)
    elif OPTIONS["kind"] == "scatter":
        ax.scatter(xx, yy, label=label)
        if err: ax.errorbar(xx, yy, yerr=err, fmt="none", capsize=3)
    else:
        ordered = sorted(zip(xx, yy, err if err else [0]*len(yy)))
        xx, yy, ee = zip(*ordered)
        ax.errorbar(xx, yy, yerr=ee if err else None, marker="o", capsize=3, label=label)
ax.set(xlabel=OPTIONS["x"], ylabel=OPTIONS["ylabel"], title=OPTIONS["title"])
ax.grid(axis="y", alpha=.2)
if OPTIONS["group"]: ax.legend(frameon=False)
for ext in ("png", "pdf", "svg"):
    fig.savefig(HERE / ("figure."+ext), dpi=300)
plt.close(fig)
'''.replace("OPTIONS_JSON", repr(dumps(options)))
    script = folder / "plot.py"
    script.write_text(code, encoding="utf-8")
    return script, source


def draw_framework(store, sid, nodes, edges, title="Research framework"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch
    if not nodes or len(nodes) > 24 or len(edges) > 60:
        raise ValueError("Use 1–24 nodes and at most 60 edges")
    ids = {n["id"] for n in nodes}
    if len(ids) != len(nodes) or any(e["source"] not in ids or e["target"] not in ids for e in edges):
        raise ValueError("Node IDs must be unique and edges must reference existing nodes")
    fonts = figure_fonts()
    raw = {n["id"]: (float(n.get("x", i*2.4)), float(n.get("y", 0))) for i, n in enumerate(nodes)}
    xs, ys = zip(*raw.values())
    if any(not __import__("math").isfinite(v) for v in (*xs, *ys)):
        raise ValueError("Node coordinates must be finite")
    # Accept grid units or pixel-like coordinates without shrinking boxes to dots.
    xspan = max(1, len(set(xs))-1)*3.3 if max(xs) != min(xs) else 0
    yspan = max(1, len(set(ys))-1)*1.7 if max(ys) != min(ys) else 0
    positions = {key: ((x-min(xs))/(max(xs)-min(xs))*xspan if xspan else 0,
                       (y-min(ys))/(max(ys)-min(ys))*yspan if yspan else 0)
                 for key, (x, y) in raw.items()}
    fig, ax = plt.subplots(figsize=(min(20,max(7,xspan+3)),min(16,max(4.5,yspan+2.5))))
    fig.subplots_adjust(top=.87, bottom=.04, left=.02, right=.98)
    import textwrap
    boxes = {}
    for n in nodes:
        x, y = positions[n["id"]]
        width = 12 if any(ord(c) > 0x2e80 for c in n["label"]) else 26
        lines = [line for paragraph in n["label"].splitlines() for line in textwrap.wrap(paragraph, width)]
        height = max(.72,len(lines)*.19+.24)
        box = FancyBboxPatch((x-1.25,y-height/2),2.5,height,boxstyle="round,pad=.06",
                            facecolor="#edf3ff", edgecolor="#45669b",zorder=3)
        ax.add_patch(box)
        boxes[n["id"]] = box
        ax.text(x, y, "\n".join(lines), ha="center", va="center", fontsize=9, fontfamily=fonts,zorder=4)
    for e in edges:
        start, end = positions[e["source"]], positions[e["target"]]
        ax.annotate("", xy=end, xytext=start, zorder=2, arrowprops={"arrowstyle":"->", "color":"#56657a",
                    "patchA":boxes[e["source"]],"patchB":boxes[e["target"]],"shrinkA":6,"shrinkB":6,"lw":1.2})
    xx, yy = zip(*positions.values())
    ax.set(xlim=(min(xx)-1.5,max(xx)+1.5), ylim=(min(yy)-1.2,max(yy)+1.2))
    fig.suptitle("\n".join(textwrap.wrap(title,100)), fontfamily=fonts,fontsize=13,y=.98)
    ax.axis("off")
    folder = store.workspace(sid) / "figures" / f"framework_{time.time_ns()}"
    folder.mkdir(parents=True)
    paths = []
    for ext in ("png", "pdf", "svg"):
        path = folder / f"framework.{ext}"
        fig.savefig(path, dpi=300, bbox_inches="tight")
        paths.append(path)
    plt.close(fig)
    spec = folder / "framework.json"
    spec.write_text(dumps({"nodes":nodes,"edges":edges,"title":title}), encoding="utf-8")
    editable = folder / "framework.drawio"
    write_drawio(editable, nodes, edges, positions, title)
    return paths + [spec, editable]


def write_drawio(path, nodes, edges, positions, title):
    """Native editable mxGraph XML; labels escaped as text, no HTML or network assets."""
    import xml.etree.ElementTree as ET
    document = ET.Element("mxfile", host="PaperScientist")
    diagram = ET.SubElement(document, "diagram", name=title, id="research-framework")
    model = ET.SubElement(diagram, "mxGraphModel", grid="1", gridSize="10", page="1",
                          pageWidth="1600", pageHeight="1000")
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", id="0")
    ET.SubElement(root, "mxCell", id="1", parent="0")
    # Remap source IDs to avoid collisions with mxGraph's reserved 0/1 and edge IDs.
    ids = {n["id"]: f"node_{i}" for i, n in enumerate(nodes)}
    ymax = max(y for x, y in positions.values())
    for n in nodes:
        x, y = positions[n["id"]]
        cell = ET.SubElement(root, "mxCell", id=ids[n["id"]], value=n["label"], vertex="1", parent="1",
            style="rounded=1;whiteSpace=wrap;html=0;fillColor=#edf3ff;strokeColor=#45669b;fontSize=14;")
        height = max(80, 24 * (1 + len(n["label"]) // 24))
        ET.SubElement(cell, "mxGeometry", x=str(40+x*100), y=str(60+(ymax-y)*100),
                      width="250", height=str(height), attrib={"as": "geometry"})
    for i, edge in enumerate(edges):
        cell = ET.SubElement(root, "mxCell", id=f"edge_{i}", edge="1", parent="1",
                            source=ids[edge["source"]], target=ids[edge["target"]],
                            style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=0;endArrow=block;")
        ET.SubElement(cell, "mxGeometry", relative="1", attrib={"as": "geometry"})
    ET.ElementTree(document).write(path, encoding="utf-8", xml_declaration=True)


def tex_escape(text):
    replacements = {"\\":r"\textbackslash{}", "&":r"\&", "%":r"\%", "$":r"\$", "#":r"\#", "_":r"\_", "{":r"\{", "}":r"\}", "~":r"\textasciitilde{}", "^":r"\textasciicircum{}"}
    return "".join(replacements.get(c,c) for c in text)


def assemble_manuscript(store, session, title, abstract, sections, paper_ids,
                        columns="single", paper="a4", margin_mm=24.0, column_gap_mm=6.0,
                        allow_wide_figures=False, min_figure_font_pt=7.0,
                        requirement="", layout_rules=None):
    import re
    papers = {p["id"]:p for p in store.papers(session)}
    if any(pid not in papers for pid in paper_ids):
        raise ValueError("Citations must use retrieved paper IDs from this project")
    cited = set()
    for body in [abstract, *sections.values()]:
        for match in re.findall(r"\\cite\w*\{([^}]+)\}", body):
            cited.update(s.strip() for s in match.split(","))
    if cited - set(paper_ids):
        raise ValueError(f"Unverified citation keys: {sorted(cited-set(paper_ids))}")
    folder = store.workspace(session["id"]) / "manuscripts" / f"draft_{time.time_ns()}"
    (folder / "sections").mkdir(parents=True)
    if columns not in {"single", "double"} or paper not in {"a4", "letter"}:
        raise ValueError("columns must be single/double and paper a4/letter")
    margins = ({side: float(margin_mm) for side in ("left", "right", "top", "bottom")}
               if isinstance(margin_mm, (int, float)) else margin_mm)
    geometry = ",".join(f"{side}={float(margins[side])}mm" for side in ("left", "right", "top", "bottom"))
    options = f"11pt,{paper}paper" + (",twocolumn" if columns == "double" else "")
    lines = [r"\documentclass["+options+"]{article}", r"\usepackage["+geometry+"]{geometry}",
             r"\setlength{\columnsep}{"+str(float(column_gap_mm))+"mm}",
             r"\usepackage{amsmath,amssymb,graphicx,booktabs,hyperref}",
             r"\title{"+tex_escape(title)+"}", r"\author{Author information pending}", r"\date{}",
             r"\begin{document}", r"\maketitle", r"\begin{abstract}", abstract, r"\end{abstract}"]
    for i, (heading, body) in enumerate(sections.items(),1):
        name = f"section_{i:02d}.tex"
        (folder/"sections"/name).write_text(body, encoding="utf-8")
        lines.extend([r"\section{"+tex_escape(heading)+"}",r"\input{sections/"+name+"}"])
    lines.extend([r"\bibliographystyle{plain}",r"\bibliography{references}",r"\end{document}"])
    (folder/"main.tex").write_text("\n".join(lines), encoding="utf-8")
    entries = []
    for pid in dict.fromkeys(paper_ids):
        p = papers[pid]
        fields = {"title": p["title"], "author": " and ".join(p.get("authors", [])),
                  "year":p.get("year", ""), "doi":p.get("doi", ""), "url":p.get("url", ""),
                  "note": "Metadata retrieved from "+p.get("provider", "source")}
        entries.append("@misc{"+pid+",\n"+",\n".join(f"  {k} = {{{tex_escape(str(v))}}}" for k,v in fields.items() if v)+"\n}")
    (folder/"references.bib").write_text("\n\n".join(entries), encoding="utf-8")
    (folder/"README.txt").write_text("Research draft. Verify all claims, author details, citations and measured results before submission.\nCompile: pdflatex main; bibtex main; pdflatex main; pdflatex main.\nFor Chinese content use a ctex/XeLaTeX preamble.\n",encoding="utf-8")
    from .manuscript_layout import configure
    configure(store, session["id"], (folder/"main.tex").relative_to(store.workspace(session["id"])).as_posix(),
              columns, paper, margin_mm, column_gap_mm, allow_wide_figures, min_figure_font_pt,
              requirement, source="user" if requirement else "default", rules=layout_rules)
    return folder


async def compile_latex(store, sid, main_path):
    path = store.file(sid, main_path)
    if path.suffix != ".tex" or not path.is_file():
        raise ValueError("Expected a saved .tex file")
    from .manuscript_layout import preflight, prepare_compile, validate_compiled
    before = preflight(store, sid, main_path)
    if before["status"] == "blocked":
        return {"status": "layout_blocked", "layout": before,
                "message": "Repair the manuscript or explicitly configure its layout contract before compilation."}
    # LaTeX is a code execution capability too: caller gates this tool.
    bundled = Path(__file__).resolve().parents[1] / ".tools" / "tectonic" / ("tectonic.exe" if os.name == "nt" else "tectonic")
    compiler = shutil.which("tectonic") or (str(bundled) if bundled.is_file() else None) or shutil.which("pdflatex")
    if not compiler:
        return {"status":"unavailable", "message":"Install tectonic or TeX Live/MiKTeX. Sources are saved.", "path":main_path}
    # Optional operator-selected bundle, kept outside source and manuscript inputs.
    bundle_hint = bundled.parent / "bundle.url"
    bundle = os.environ.get("PS_TECTONIC_BUNDLE") or (bundle_hint.read_text(encoding="utf-8").strip() if bundle_hint.is_file() else "")
    wrapper = prepare_compile(path)
    commands = [[compiler,"--untrusted", "--keep-logs", *(["--bundle", bundle] if bundle else []), wrapper.name]] if "tectonic" in Path(compiler).name else [
        [compiler,"-no-shell-escape","-interaction=nonstopmode","-halt-on-error",wrapper.name]]
    if "pdflatex" in Path(compiler).name and (path.parent/"references.bib").exists() and shutil.which("bibtex"):
        commands += [[shutil.which("bibtex"),wrapper.stem],commands[0],commands[0]]
    logs = []
    for command in commands:
        process = await asyncio.create_subprocess_exec(*command, cwd=path.parent, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            env={**{k:v for k,v in os.environ.items() if k.upper() in {"SYSTEMROOT","WINDIR","PATH","TEMP","TMP","HOME","USERPROFILE","LOCALAPPDATA","APPDATA","HTTP_PROXY","HTTPS_PROXY","NO_PROXY"}},
                 "openin_any":"p","openout_any":"p"})
        try:
            output, _ = await asyncio.wait_for(process.communicate(),300)
        except BaseException:
            process.kill()
            await process.wait()
            raise
        logs.append(output.decode(errors="replace")[-10000:])
        if process.returncode:
            return {"status":"error","log":"\n".join(logs)}
    candidate = wrapper.with_suffix(".pdf")
    full_log = wrapper.with_suffix(".log").read_text(encoding="utf-8", errors="replace") if wrapper.with_suffix(".log").is_file() else "\n".join(logs)
    layout = validate_compiled(store, sid, main_path, candidate, full_log, before)
    if layout["status"] != "passed":
        return {"status": "layout_blocked", "layout": layout, "log": "\n".join(logs),
                "message": "Compilation succeeded but layout validation failed. The previous delivered PDF was preserved."}
    pdf = path.with_suffix(".pdf")
    shutil.copyfile(candidate, pdf)
    return {"status":"success", "artifact":store.artifact(sid,pdf,"manuscript_pdf", {"layout_validated": True}),
            "layout": layout, "log":"\n".join(logs)}


def validate_manuscript(store, sid, main_path):
    """Static source integrity checks; this is not a TeX compiler or scientific review."""
    import re
    main = store.file(sid, main_path)
    root = main.parent
    if not main.is_file() or main.suffix != ".tex":
        raise ValueError("Expected a saved main .tex file")
    errors, texts, visited = [], [], set()

    def read(path):
        path = path.resolve()
        if not path.is_relative_to(store.workspace(sid).resolve()):
            errors.append("Source escapes the workspace: " + path.name)
            return
        if path in visited:
            return
        visited.add(path)
        if not path.is_file():
            errors.append("Missing source: " + str(path.relative_to(root)))
            return
        text = re.sub(r"(?<!\\)%[^\n]*", "", path.read_text(encoding="utf-8"))
        texts.append(text)
        for name in re.findall(r"\\(?:input|include)\{([^}]+)\}", text):
            target = root / name
            read(target if target.suffix else target.with_suffix(".tex"))
        for name in re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}", text):
            target = root / name
            candidates = [target] if target.suffix else [target.with_suffix(ext) for ext in (".pdf", ".png", ".jpg", ".jpeg")]
            if not any(p.resolve().is_relative_to(store.workspace(sid).resolve()) and p.is_file() for p in candidates):
                errors.append("Missing figure: " + name)

    read(main)
    joined = "\n".join(texts)
    bib_keys = set()
    for names in re.findall(r"\\bibliography\{([^}]+)\}", joined):
        for name in names.split(","):
            path = root / name.strip()
            path = path if path.suffix else path.with_suffix(".bib")
            if path.resolve().is_relative_to(store.workspace(sid).resolve()) and path.is_file():
                bib_keys.update(re.findall(r"@\w+\s*\{\s*([^,]+),", path.read_text(encoding="utf-8")))
            else:
                errors.append("Missing bibliography: " + name)
    citations = {k.strip() for group in re.findall(r"\\cite\w*(?:\[[^]]*\])*\{([^}]+)\}", joined) for k in group.split(",")}
    errors.extend("Undefined citation: " + k for k in sorted(citations - bib_keys))
    labels = set(re.findall(r"\\label\{([^}]+)\}", joined))
    refs = {k.strip() for group in re.findall(r"\\(?:ref|eqref|autoref|cref|Cref)\{([^}]+)\}", joined) for k in group.split(",")}
    errors.extend("Undefined reference: " + k for k in sorted(refs - labels))
    return {"status": "error" if errors else "passed", "errors": errors, "source_files": len(visited),
            "citations": sorted(citations), "note": "Static integrity only; compilation and scientific review are separate checks."}
