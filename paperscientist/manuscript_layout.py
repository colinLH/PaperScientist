"""Persisted manuscript contracts and compile-time/PDF layout gates.

Source checks are early diagnostics, never proof of the final layout. A passing
report requires an instrumented compile and inspection of the resulting PDF.
No rule rewrites the document or authorizes a wider/rotated page automatically.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from pathlib import Path
from typing import Callable

PAPER_MM = {"a4": (210.0, 297.0), "letter": (215.9, 279.4)}
CONTRACT_NAME = "layout_contract.json"
_RULES: dict[str, Callable] = {}
_LAYOUT_FIELDS = ("columns", "paper", "orientation", "margins_mm", "column_gap_mm",
                  "allow_wide_figures", "min_figure_font_pt", "rules")


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _contract_path(main):
    """Keep legacy single-entry projects readable; isolate sibling entry points."""
    specific = main.parent / f"layout_contract.{main.name}.json"
    legacy = main.parent / CONTRACT_NAME
    if specific.exists():
        return specific
    if legacy.exists():
        # Invalid JSON must remain an error, not become a fresh inferred contract.
        owner = json.loads(legacy.read_text(encoding="utf-8")).get("main")
        return legacy if owner == main.name else specific
    return legacy if main.name == "main.tex" else specific


def _report_path(main):
    return main.parent / ("layout_report.json" if _contract_path(main).name == CONTRACT_NAME
                          else f"layout_report.{main.name}.json")


def _history_table(db):
    db.execute("""CREATE TABLE IF NOT EXISTS manuscript_layout_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
        main_path TEXT NOT NULL, contract TEXT NOT NULL, created_at REAL NOT NULL)""")


def _recorded_contract(store, sid, main):
    key = main.relative_to(store.workspace(sid)).as_posix()
    with store.connect() as db:
        _history_table(db)
        row = db.execute("SELECT contract FROM manuscript_layout_history WHERE session_id=? AND main_path=? ORDER BY id DESC LIMIT 1",
                         (sid, key)).fetchone()
    return json.loads(row[0]) if row else None


def _persist_contract(store, sid, main, contract):
    """SQLite owns the approved revision; the workspace JSON is its readable mirror."""
    key = main.relative_to(store.workspace(sid)).as_posix()
    with store.connect() as db:
        _history_table(db)
        cursor = db.execute("INSERT INTO manuscript_layout_history(session_id,main_path,contract,created_at) VALUES(?,?,?,?)",
                            (sid, key, "{}", time.time()))
        contract["revision_id"] = cursor.lastrowid
        db.execute("UPDATE manuscript_layout_history SET contract=? WHERE id=?",
                   (json.dumps(contract, ensure_ascii=False), cursor.lastrowid))
        _write(_contract_path(main), contract)


def _user_evidence(store, sid, quote, after_id=0):
    """Resolve an exact user quote, excluding subagent instructions and generated repairs.

    Trust is the application's human-message log, not text an agent puts in a JSON
    file. This is application provenance, not an operating-system security boundary.
    """
    quote = str(quote).strip()
    if not quote:
        raise ValueError("An explicit user layout needs an exact requirement quote from a user message")
    root, seen = sid, set()
    with store.connect() as db:
        while root not in seen:
            seen.add(root)
            row = db.execute("SELECT parent_id FROM sessions WHERE id=?", (root,)).fetchone()
            if not row or not row[0]:
                break
            root = row[0]
        rows = db.execute("SELECT id,payload,created_at FROM messages WHERE session_id=? AND id>? ORDER BY id DESC",
                          (root, int(after_id or 0))).fetchall()
    latest_layout_message = None
    for row in rows:
        payload = json.loads(row["payload"])
        if payload.get("type") != "human":
            continue
        content = payload.get("data", {}).get("content", "")
        if not isinstance(content, str) or content.startswith(("Parent coordination:", "Completion check failed.")):
            continue
        content = content.split("\n\n[Attached files]", 1)[0]
        # Do not quote attached/reference code blocks as direct layout instructions.
        direct = re.sub(r"```.*?```", "", content, flags=re.S)
        direct = "\n".join(line for line in direct.splitlines() if not line.lstrip().startswith(">"))
        if latest_layout_message is None and re.search(r"单栏|双栏|两栏|二栏|single[ -]?column|double[ -]?column|two[ -]?column", direct, re.I):
            latest_layout_message = row["id"]
        if quote in direct:
            if latest_layout_message and latest_layout_message > row["id"]:
                raise ValueError("A later user layout message exists; use the current instruction instead of an older conflicting quote")
            return {"session_id": root, "message_id": row["id"], "message_sha256": hashlib.sha256(content.encode()).hexdigest(),
                    "quote": quote, "created_at": row["created_at"]}, direct
    raise ValueError("Layout changes require an exact quote from a later real user message; assistant text, delegated prompts and contract edits are not user authorization")


def _check_requested_change(contract, changed, evidence, message):
    quote = evidence["quote"]
    if "columns" in changed or re.search(r"单栏|双栏|两栏|二栏|single[ -]?column|double[ -]?column|two[ -]?column", quote, re.I):
        mentions = list(re.finditer(r"单栏|双栏|两栏|二栏|single[ -]?column|double[ -]?column|two[ -]?column", quote, re.I))
        positive = []
        start = message.find(quote)
        for match in mentions:
            # Include the surrounding user clause so quoting 'use double columns'
            # out of 'do not use double columns' cannot invert its meaning.
            prefix = re.split(r"[。！？.!?;；,，\n]", message[:start+match.start()])[-1][-35:]
            if re.search(r"不要|不得|不能|禁止|不使用|非|\b(?:not|avoid|without|from)\b|don't", prefix, re.I):
                continue
            positive.append("single" if re.search(r"单栏|single", match.group(), re.I) else "double")
        direct_short_answer = quote.strip() == message.strip() and len(quote) < 30
        directive = re.search(r"采用|使用|改为|改成|保持|排成|设置|排版|请|可以|\b(?:use|switch|change|keep|set|format|please)\b", quote, re.I)
        if not positive or positive[-1] != contract["columns"] or not (directive or direct_short_answer):
            raise ValueError("The quoted user instruction must explicitly request the selected single/double-column layout")
    keywords = {"paper": r"A4|letter|纸张|paper size", "margins_mm": r"页边距|margin",
                "column_gap_mm": r"栏距|栏间距|column.{0,10}(?:gap|sep)",
                "allow_wide_figures": r"跨栏|通栏|spanning|full[ -]width|wide float",
                "min_figure_font_pt": r"字号|字体|font", "rules": r"页数|page limit|max_pages|溢出|overflow|plugin|规则|rule"}
    for key in changed:
        if key in keywords and not re.search(keywords[key], quote, re.I):
            raise ValueError(f"The user quote does not authorize changing {key}; preserve the existing contract")


def register_layout_rule(name: str, validator: Callable):
    """Trusted application plugins may append diagnostics; never override core gates.

    validator(context) returns a list of {code, message, severity, ...} objects.
    Context contains contract, source_files, pdf, pages and compiled measurements.
    Python code is not loaded from model-written contracts.
    """
    if not re.fullmatch(r"[a-z][a-z0-9_-]{1,63}", name) or not callable(validator):
        raise ValueError("Use a stable rule name and a callable validator")
    _RULES[name] = validator


def configure(store, sid, main_path, columns="single", paper="a4", margin_mm=24.0,
              column_gap_mm=6.0, allow_wide_figures=False, min_figure_font_pt=7.0,
              requirement="", source=None, rules=None):
    """Save an explicit contract next to main.tex. Does not rewrite TeX.

    Without a user requirement the source is explicitly marked inferred/default.
    Margins may be one number or a dict with left/right/top/bottom millimetres.
    Optional declarative rules: max_pages, max_overflow_pt, plugin names.
    """
    main = store.file(sid, main_path)
    if main.suffix != ".tex" or not main.is_file():
        raise ValueError("Expected an existing main .tex file")
    if columns not in {"single", "double"} or paper not in PAPER_MM:
        raise ValueError("columns must be single/double; paper must be a4/letter")
    margins = ({side: float(margin_mm) for side in ("left", "right", "top", "bottom")}
               if isinstance(margin_mm, (float, int)) else {side: float(margin_mm[side])
               for side in ("left", "right", "top", "bottom")})
    if any(not math.isfinite(v) or not 5 <= v <= 60 for v in margins.values()):
        raise ValueError("Margins must be finite millimetres between 5 and 60")
    gap, font = float(column_gap_mm), float(min_figure_font_pt)
    if not math.isfinite(gap) or not 2 <= gap <= 20 or not math.isfinite(font) or not 5 <= font <= 14:
        raise ValueError("Column gap must be 2–20 mm; minimum figure font 5–14 pt")
    rule_config = dict(rules or {})
    if set(rule_config) - {"max_pages", "max_overflow_pt", "plugins"}:
        raise ValueError("Unknown layout rule; register a trusted plugin for custom checks")
    if "max_pages" in rule_config and not 1 <= int(rule_config["max_pages"]) <= 1000:
        raise ValueError("max_pages must be between 1 and 1000")
    if not 0 <= float(rule_config.get("max_overflow_pt", .5)) <= 2:
        raise ValueError("max_overflow_pt must be between 0 and 2")
    if not isinstance(rule_config.get("plugins", []), list):
        raise ValueError("plugins must be a list of registered rule names")
    contract = {"version": 1, "main": main.name, "columns": columns, "paper": paper,
                "orientation": "portrait", "margins_mm": margins, "column_gap_mm": gap,
                "allow_wide_figures": bool(allow_wide_figures), "min_figure_font_pt": font,
                "requirement": str(requirement), "source": source or ("user" if requirement else "inferred_existing"),
                "rules": rule_config, "updated_at": time.time()}
    if contract["source"] not in {"user", "inferred_existing", "default"}:
        raise ValueError("source must be user, inferred_existing or default")
    destination = _contract_path(main)
    previous = _recorded_contract(store, sid, main)
    legacy = load_contract(main) if not previous and destination.is_file() else None
    prior = previous or legacy
    changed = [key for key in _LAYOUT_FIELDS if prior and contract[key] != prior.get(key)]
    if previous and not changed and (previous.get("source") == "user" or not requirement):
        # An idempotent call never downgrades user provenance or invalidates a PDF.
        # Also repairs an accidentally edited/deleted workspace mirror from SQLite.
        _write(destination, previous)
        return {"status": "configured", "contract": previous,
                "path": destination.relative_to(store.workspace(sid)).as_posix(),
                "note": "Existing approved layout retained; no constraint or user provenance changed."}
    explicit_prior = prior and prior.get("source") == "user"
    if explicit_prior or contract["source"] == "user":
        prior_message = prior.get("user_evidence", {}).get("message_id", 0) if prior else 0
        evidence, message = _user_evidence(store, sid, requirement, prior_message if explicit_prior and changed else 0)
        # Initial explicit contracts need a real column instruction. Other fields
        # begin at their declared defaults; later changes need a matching user clause.
        _check_requested_change(contract, changed if explicit_prior else ["columns"], evidence, message)
        contract.update(source="user", user_evidence=evidence)
    if previous:
        contract["previous_revision_id"] = previous["revision_id"]
    _persist_contract(store, sid, main, contract)
    return {"status": "configured", "contract": contract,
            "path": destination.relative_to(store.workspace(sid)).as_posix(),
            "note": "Contract saved; run compile_latex to verify actual PDF layout. No TeX was changed."}


def load_contract(main):
    path = _contract_path(main)
    if not path.is_file():
        return None
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("version") != 1 or contract.get("main") != main.name:
        raise ValueError("Layout contract version or main document does not match")
    if contract.get("columns") not in {"single", "double"} or contract.get("paper") not in PAPER_MM:
        raise ValueError("Invalid layout contract; configure it again")
    if contract.get("orientation") != "portrait":
        raise ValueError("This manuscript contract requires portrait pages")
    return contract


def dimensions(contract):
    pw, ph = PAPER_MM[contract["paper"]]
    m = contract["margins_mm"]
    text = pw - m["left"] - m["right"]
    column = text if contract["columns"] == "single" else (text - contract["column_gap_mm"]) / 2
    return {"page_width_pt": pw * 72 / 25.4, "page_height_pt": ph * 72 / 25.4,
            "text_width_pt": text * 72 / 25.4, "column_width_pt": column * 72 / 25.4,
            "text_height_pt": (ph-m["top"]-m["bottom"]) * 72 / 25.4,
            "column_width_inches": column / 25.4, "text_width_inches": text / 25.4,
            "max_figure_height_inches": (ph-m["top"]-m["bottom"]-24) / 25.4}


def _sources(main, workspace):
    files, errors = {}, []
    def visit(path):
        path = path.resolve()
        if path in files:
            return
        if not path.is_relative_to(workspace.resolve()) or not path.is_file():
            errors.append({"code": "source_missing", "message": f"Missing or out-of-workspace source: {path.name}"})
            return
        if len(files) >= 120 or path.stat().st_size > 2_000_000:
            errors.append({"code": "source_limit", "message": "Source inspection limit exceeded; split the project."})
            return
        content = re.sub(r"(?<!\\)%[^\n]*", "", path.read_text(encoding="utf-8"))
        files[path] = content
        for name in re.findall(r"\\(?:input|include)\s*\{([^}]+)\}", content):
            target = main.parent / name
            visit(target if target.suffix else target.with_suffix(".tex"))
        for command, extension in (("usepackage", ".sty"), ("documentclass", ".cls")):
            for name in re.findall(r"\\"+command+r"(?:\[[^]]*\])?\{([^}]+)\}", content):
                for package in name.split(","):
                    target = main.parent / (package.strip() + extension)
                    if target.is_file():
                        visit(target)
    visit(main)
    return files, errors


def _inputs(main, sources, workspace):
    """Bind validation to TeX, local packages, referenced graphics and bibliographies."""
    result = {str(path.relative_to(main.parent)): _digest(path) for path in sources}
    for text in sources.values():
        for pattern, extensions in ((r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}", (".pdf", ".png", ".jpg", ".jpeg")),
                                    (r"\\(?:bibliography|addbibresource)\{([^}]+)\}", (".bib",))):
            for group in re.findall(pattern, text):
                for name in group.split(","):
                    path = main.parent / name.strip()
                    candidates = [path] if path.suffix else [path.with_suffix(ext) for ext in extensions]
                    for candidate in candidates:
                        if candidate.resolve().is_relative_to(workspace.resolve()) and candidate.is_file():
                            result[str(candidate.relative_to(main.parent))] = _digest(candidate)
                            break
    # Templates may construct input names in macros. Bind the local source tree as
    # well so changing a dynamically included section/class cannot reuse a stale pass.
    local = [p for p in main.parent.rglob('*') if p.is_file() and p.suffix.lower()
             in {'.tex', '.sty', '.cls', '.bib', '.pdf', '.png', '.jpg', '.jpeg'}
             and not p.name.startswith('_ps_layout_') and p != main.with_suffix('.pdf')
             # A sibling entry's output is not an input of this manuscript. An
             # explicitly included PDF was already bound by includegraphics above.
             and not (p.suffix.lower() == '.pdf' and p.with_suffix('.tex').is_file())
             and p.resolve().is_relative_to(workspace.resolve())]
    if len(local) > 1000:
        raise ValueError('More than 1000 manuscript input files; isolate the paper project before compiling')
    for path in local:
        result[str(path.relative_to(main.parent))] = _digest(path)
    return result


def preflight(store, sid, main_path):
    main = store.file(sid, main_path)
    issues = []
    try:
        contract = load_contract(main)
        recorded = _recorded_contract(store, sid, main)
        if recorded and contract != recorded:
            issues.append({"code": "contract_modified", "message": "The workspace layout contract differs from its approved SQLite revision. Restore it with configure_manuscript_layout; explicit user constraints require a later real user instruction to change."})
        elif contract and contract.get("source") == "user" and not recorded:
            issues.append({"code": "user_contract_unverified", "message": "This user-labelled contract has no recorded authorization. Configure it using an exact quote from the user's message before compiling."})
    except (ValueError, KeyError, TypeError) as exc:
        contract = None
        issues.append({"code": "contract_invalid", "message": str(exc)})
    if not contract:
        issues.append({"code": "contract_missing", "message": "Configure manuscript layout before compiling. Preserve the user's requested columns; absent a request, record the existing portrait layout as inferred."})
        return {"status": "blocked", "issues": issues, "contract": None}
    files, source_errors = _sources(main, store.workspace(sid))
    issues.extend(source_errors)
    for path, text in files.items():
        name = path.relative_to(main.parent).as_posix()
        checks = [(r"\\begin\{(?:landscape|sidewaysfigure\*?|sidewaystable\*?)\}", "orientation", "Rotated pages/floats violate the portrait contract. Reflow or split the figure instead."),
                  (r"\\(?:pdfpageattr|pdfpagewidth|pdfpageheight)\b", "page_override", "Direct PDF page overrides require review; use the contracted geometry."),
                  (r"\\(?:twocolumn)\b" if contract["columns"] == "single" else r"\\onecolumn\b", "columns", "Column switch violates the manuscript contract.")]
        if contract["columns"] == "double" and not contract["allow_wide_figures"]:
            checks.append((r"\\begin\{(?:figure|table)\*\}", "wide_float", "Full-width floats were not authorized. Reflow within one column or request an explicit contract change."))
        for pattern, code, message in checks:
            match = re.search(pattern, text)
            if match:
                issues.append({"code": code, "message": message, "file": name, "line": text[:match.start()].count("\n")+1})
        for match in re.finditer(r"\\includegraphics\[([^]]+)\]", text):
            opts = match.group(1)
            if re.search(r"angle\s*=\s*(?!0(?:\D|$))[-\d]", opts):
                issues.append({"code": "rotated_figure", "file": name, "message": "Do not rotate a paper figure to evade the column width. Reflow it."})
            size = re.search(r"width\s*=\s*([0-9.]+)\s*\\(?:line|column|text)width", opts)
            if size and float(size.group(1)) > 1.001:
                issues.append({"code": "figure_width", "file": name, "message": "Figure width exceeds the surrounding text width."})
    return {"status": "blocked" if issues else "ready", "issues": issues, "contract": contract,
            "source_files": [str(p.relative_to(main.parent)) for p in files], "inputs": _inputs(main, files, store.workspace(sid)),
            "dimensions": dimensions(contract)}


def prepare_compile(main):
    """Compile a wrapper so TeX itself reports effective geometry at every shipout."""
    suffix = "" if main.name == "main.tex" else "_" + hashlib.sha256(main.name.encode()).hexdigest()[:12]
    wrapper = main.parent / f"_ps_layout{suffix}_compile.tex"
    wrapper.write_text(r"""\makeatletter
\newcommand{\PSLayoutMeasurement}{%
\typeout{PSLAYOUT:page=\thepage;columns=\if@twocolumn2\else1\fi;paperwidth=\the\paperwidth;paperheight=\the\paperheight;textwidth=\the\textwidth;columnwidth=\the\columnwidth;textheight=\the\textheight;columnsep=\the\columnsep;left=\the\oddsidemargin;top=\the\topmargin;headheight=\the\headheight;headsep=\the\headsep;END}%
}
\AddToHook{shipout/before}{\PSLayoutMeasurement}
\makeatother
""" + "\\input{" + main.name + "}\n", encoding="utf-8")
    return wrapper


def _measurements(log):
    # TeX wraps log lines at max_print_line; remove those wraps within our marker.
    result = []
    for match in re.findall(r"PSLAYOUT:(.*?);END", log, re.S):
        entry = {}
        for key, value in re.findall(r"(\w+)=([^;]+)", match.replace("\n", "").replace("\r", "")):
            if key in {"page", "columns"}:
                entry[key] = value.strip()
            else:
                number = re.match(r"\s*([-\d.]+)pt", value)
                if number:
                    entry[key] = float(number.group(1)) * 72 / 72.27
        result.append(entry)
    return result


def inspect_pdf(pdf, contract, measurements):
    """Check actual page orientation, text/graphics bounds and effective PDF font size."""
    import pypdfium2 as pdfium
    issues, pages = [], []
    expected, margins = dimensions(contract), contract["margins_mm"]
    doc = pdfium.PdfDocument(str(pdf))
    try:
        if len(measurements) != len(doc):
            issues.append({"code": "measurement_missing", "message": "Every PDF page needs geometry measurements from the instrumented compile."})
        if len(doc) > int(contract.get("rules", {}).get("max_pages", 1000)):
            issues.append({"code": "page_limit", "message": "Compiled page count exceeds the contract."})
        for index in range(len(doc)):
            page = doc[index]
            width, height = page.get_size()
            number = index + 1
            page_issues, min_font, figures = [], None, 0
            def fail(code, message, **extra):
                # One representative of each issue per page avoids thousands of glyph diagnostics.
                if not any(item["code"] == code for item in page_issues):
                    page_issues.append({"code": code, "message": message, "page": number, **extra})
            if page.get_rotation() != 0 or width > height:
                fail("page_orientation", "Page is rotated/landscape; the contract requires portrait.")
            if abs(width-expected["page_width_pt"]) > 1.5 or abs(height-expected["page_height_pt"]) > 1.5:
                fail("paper_size", "Compiled page dimensions do not match the contracted paper size.")
            left = margins["left"] * 72 / 25.4
            right = width - margins["right"] * 72 / 25.4
            bottom, top = margins["bottom"] * 72 / 25.4, height-margins["top"] * 72 / 25.4
            measurement = measurements[index] if index < len(measurements) else {}
            if measurement:
                if measurement.get("columns") != ("1" if contract["columns"] == "single" else "2"):
                    fail("column_count", "TeX's actual column mode differs from the contract.")
                for key, target in (("textwidth", "text_width_pt"), ("columnwidth", "column_width_pt"), ("textheight", "text_height_pt")):
                    if abs(measurement.get(key, -9999)-expected[target]) > 1.5:
                        fail("geometry_"+key, f"Actual {key} is {measurement.get(key)} pt; expected {expected[target]:.2f} pt.")
                actual_left = 72 + measurement.get("left", -9999)
                if abs(actual_left-left) > 1.5:
                    fail("geometry_left", "Actual left margin differs from the contract.")
                actual_top = 72 + sum(measurement.get(key, 0) for key in ("top", "headheight", "headsep"))
                if abs(actual_top-margins["top"]*72/25.4) > 1.5:
                    fail("geometry_top", "Actual top margin differs from the contract.")
            for obj in page.get_objects():
                bounds = obj.get_bounds()
                parent = obj.container
                while parent:
                    bounds = parent.get_matrix().on_rect(*bounds)
                    parent = parent.container
                x0, y0, x1, y1 = bounds
                if not all(math.isfinite(v) for v in bounds):
                    fail("invalid_bounds", "PDF contains a non-finite drawing boundary.")
                    continue
                # Text can extend vertically into running headers/footers but not off the paper.
                if obj.type == 1 and (x0 < -1 or y0 < -1 or x1 > width+1 or y1 > height+1):
                    fail("page_overflow", "PDF text extends beyond the physical page.", bounds=list(bounds))
                if obj.type == 1 and obj.level == 0 and (x0 < left-1.5 or x1 > right+1.5):
                    fail("text_overflow", "Text/table content crosses the contracted horizontal margins.", bounds=list(bounds))
                if obj.type in {3, 5} and obj.level == 0:  # image or imported PDF form
                    figures += 1
                    if x0 < left-1.5 or x1 > right+1.5 or y0 < bottom-2 or y1 > top+2:
                        fail("figure_overflow", "Figure crosses the text area. Split/reflow it; do not shrink labels below the font floor.", bounds=list(bounds))
                    if contract["columns"] == "double" and not contract["allow_wide_figures"] and x1-x0 > expected["column_width_pt"]+2:
                        fail("figure_column_width", "Figure exceeds one column without an authorized spanning float.", width_pt=x1-x0)
                if obj.type == 1 and obj.level > 0:
                    transform = obj.get_matrix()
                    parent = obj.container
                    while parent:
                        transform = transform.multiply(parent.get_matrix())
                        parent = parent.container
                    font = obj.get_font_size() * math.hypot(transform.c, transform.d)
                    if font > 0:
                        min_font = min(min_font, font) if min_font is not None else font
                        if font < float(contract["min_figure_font_pt"])-.15:
                            fail("figure_font", f"Figure text is {font:.2f} pt at publication size, below {contract['min_figure_font_pt']} pt. Redesign at the target width instead of scaling down.")
                # Native table rules expose over-wide tabulars even when text happens to fit.
                if obj.type == 2 and obj.level == 0 and y0 > bottom and y1 < top:
                    if x0 < left-2 or x1 > right+2:
                        fail("drawing_overflow", "A table rule/vector drawing crosses the text margins.", bounds=list(bounds))
                    if contract["columns"] == "double" and not contract["allow_wide_figures"] and x1-x0 > expected["column_width_pt"]+2:
                        fail("drawing_column_width", "A table/vector drawing spans both columns without authorization.")
            pages.append({"page": number, "width_pt": width, "height_pt": height,
                          "rotation": page.get_rotation(), "figures": figures,
                          "minimum_figure_font_pt": round(min_font, 3) if min_font is not None else None})
            if figures and min_font is None:
                page_issues.append({"code": "figure_font_unverified", "severity": "warning", "page": number,
                                    "message": "This figure has no extractable vector text. Inspect raster/outlined labels at publication size; their font floor has not been verified."})
            issues.extend(page_issues)
            page.close()
    finally:
        doc.close()
    return issues, pages


def validate_compiled(store, sid, main_path, pdf, log, before):
    main = store.file(sid, main_path)
    after = preflight(store, sid, main_path)
    issues = list(after["issues"])
    contract = after.get("contract")
    if not contract:
        return after
    if before.get("inputs") != after.get("inputs") or before.get("contract") != contract:
        issues.append({"code": "inputs_changed", "message": "Manuscript inputs or layout contract changed during compilation. Compile again."})
    for amount in re.findall(r"Overfull \\[hv]box \(([\d.]+)pt too (?:wide|high)\)", log):
        if float(amount) > float(contract.get("rules", {}).get("max_overflow_pt", .5)):
            issues.append({"code": "tex_overflow", "message": f"TeX reports an overfull box of {amount} pt. Repair the indicated table, figure or paragraph."})
            break
    measurements = _measurements(log)
    try:
        pdf_issues, pages = inspect_pdf(pdf, contract, measurements)
        issues.extend(pdf_issues)
    except Exception as exc:
        pages = []
        issues.append({"code": "pdf_inspection_failed", "message": f"PDF inspection could not complete: {type(exc).__name__}: {exc}"})
    context = {"contract": contract, "source_files": after.get("source_files", []),
               "pdf": str(pdf), "pages": pages, "measurements": measurements}
    for name in contract.get("rules", {}).get("plugins", []):
        if name not in _RULES:
            issues.append({"code": "plugin_missing", "message": f"Required layout rule {name!r} is not registered."})
            continue
        try:
            issues.extend(_RULES[name](context) or [])
        except Exception as exc:
            issues.append({"code": "plugin_failed", "message": f"Layout rule {name!r} failed: {exc}"})
    report = {"status": "blocked" if any(i.get("severity") != "warning" for i in issues) else "passed",
              "issues": issues, "contract": contract, "pages": pages, "measurements": measurements,
              "inputs": after.get("inputs", {}), "pdf_sha256": _digest(pdf),
              "validated_at": time.time(), "note": "Compiled geometry and PDF bounds checked. Scientific validity and visual overlap review remain separate."}
    _write(_report_path(main), report)
    return report


def validate(store, sid, main_path, require_pdf=True):
    """Reusable role-harness hook: never accepts a stale or source-only PDF claim."""
    main = store.file(sid, main_path)
    check = preflight(store, sid, main_path)
    if check["status"] == "blocked" or not require_pdf:
        return check
    report_path = _report_path(main)
    pdf = main.with_suffix(".pdf")
    if not report_path.is_file() or not pdf.is_file():
        return {**check, "status": "not_compiled", "issues": [{"code": "compile_required", "message": "Run compile_latex with the saved contract; source checks alone cannot verify layout."}]}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("inputs") != check.get("inputs") or report.get("contract") != check.get("contract") or report.get("pdf_sha256") != _digest(pdf):
        return {**check, "status": "blocked", "issues": [{"code": "stale_compile", "message": "Sources, figures, PDF or contract changed since validation. Recompile."}]}
    return report


def harness_check(store, sid, arguments):
    """Adapter for declarative role harnesses, arguments={main_path, require_pdf?}."""
    return validate(store, sid, arguments["main_path"], arguments.get("require_pdf", True))
