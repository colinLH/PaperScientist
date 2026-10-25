# Manuscript layout contract and verification

`assemble_manuscript` saves `layout_contract.json` alongside the new main file. For
an existing document, call `configure_manuscript_layout` first. Preserve an explicit
user choice of single/double columns. If there was no choice, record the existing
portrait layout as `inferred_existing`; newly assembled defaults are `default`.
The contract is not permission to silently change the user's requested format.

The approved revision is also saved in the application's SQLite
`manuscript_layout_history` table. `layout_contract.json` is a readable mirror, not
the authority for changing an approved layout. Editing that file makes preflight
fail with `contract_modified`, even if the edited TeX would compile under its new
values. Calling configure with the original constraints restores the mirror.

An explicit user contract requires `requirement` to quote an actual human message
in the root session (or a parent root session for delegated work). Assistant text,
subagent prompts, attached-file text and reference/code quotations do not establish
authorization. The selected column count must be explicitly requested in that
quote. Its message ID, hash and quote are saved with the contract. A changed user
contract requires a later human message; unrelated requests such as “continue” do
not authorize a single-to-double-column change. Identical configure calls preserve
the approved revision and its user provenance. They never downgrade it to inferred
or default. Each genuine change records the prior revision ID; history is retained.

This is application-level provenance and accidental-change protection. It is not
an OS sandbox or a guarantee against direct modification of the application database.
The API signature is unchanged. Existing unrecorded user-labelled contracts must
be configured with a real user quote before compiling; existing inferred contracts
remain usable. Keep requirement wording direct, e.g. `请改为双栏排版` or
`Use a single-column layout`, rather than paraphrasing user intent.

The persisted contract specifies columns, A4/Letter portrait paper, four margins,
column gap, whether spanning floats are authorized, and the minimum effective font
size in imported vector figures. Configuration does not rewrite TeX. Defaults are
single-column A4, 24 mm margins, 6 mm column gap, no spanning floats, and a 7 pt
figure-font floor. A double-column manuscript should normally use `\columnwidth`
or `\linewidth`, not `\textwidth`, for its figures.

## Compile and verify

1. Source preflight follows `\input`, `\include` and local packages. It blocks
   orientation/column switches and unapproved wide floats, reporting source lines.
2. Compilation uses a generated `_ps_layout_compile.tex` wrapper in the manuscript
   folder. TeX reports the actual column mode and geometry at every page shipout.
   The wrapper's job name differs from the main source; templates that depend on
   `\jobname` for input filenames should use explicit project filenames.
3. The complete engine log is checked for overfull boxes. PDFium inspects the actual
   PDF page size/rotation, text bounds, imported image/form bounds, native drawing
   bounds, and vector figure font sizes after all enclosing transforms. Full-width
   title text on the first page does not count as a forbidden spanning figure.
4. Only a passing PDF is copied to `main.pdf` and registered as `manuscript_pdf`.
   A blocked compilation preserves the prior delivered PDF. The new candidate and
   `layout_report.json` provide diagnostics; a TeX exit code alone is not success.
5. `validate_manuscript_layout` checks hashes of source, included files, referenced
   figures, bibliography, contract and final PDF. A changed input requires a new
   compile. It never calls source-only checks a verified PDF.

This is a mechanical layout gate, not a scientific or full visual-review claim.
Rasterized label legibility and overlaps require rendered-page review. Inspect the
final pages at publication size. Fix wide material by reflowing or splitting it;
neither rotating pages nor shrinking labels below the floor is an accepted repair.

## FigureForge binding

Add these fields to a figure spec:

```json
{
  "manuscript": "manuscripts/draft/main.tex",
  "figure_scope": "column",
  "type": "results",
  "size": [3.1, 4.8],
  "columns": 1,
  "panels": []
}
```

Use real panels/data. The adapter derives the allowed physical width/height from
the contract, rejects oversized specs, and retains the contract hash as provenance.
`page` scope for a double-column paper requires `allow_wide_figures=true`.
The final compile gate checks the inclusion size even if a figure was created by
another tool or if TeX macros conceal an oversized inclusion.

## Role-specific and custom rules

Python integration (trusted application code only):

```python
from paperscientist.manuscript_layout import register_layout_rule, harness_check

def venue_rule(context):
    return ([{"code": "venue_page_limit", "message": "Body must fit 9 pages"}]
            if len(context["pages"]) > 9 else [])

register_layout_rule("venue-review", venue_rule)
# Contract rules={"plugins": ["venue-review"], "max_pages": 12,
#                 "max_overflow_pt": 0.5}
result = harness_check(store, session_id, {"main_path": "paper/main.tex"})
```

Plugins append diagnostics; they cannot replace the core gates. Missing required
plugins and plugin exceptions block delivery. A diagnostic may explicitly be a
`severity: warning`; all other diagnostics block. Contracts cannot load arbitrary
Python or relax orientation/column checks. The role registry can call
`harness_check` as a before-delivery hook and retain the structured result.

The regression suite compiles genuine single/double-column multi-file papers,
checks class-level column overrides and macro-hidden rotations, catches oversized
tables/figures and tiny figure fonts, verifies stale-input detection and confirms
that failed revisions preserve the prior PDF.
