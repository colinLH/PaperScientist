---
name: figure-forge
description: Highest-priority paper figure tool. Retrieve Top-Conf Figure Gallery layouts and produce traceable multi-panel experiment charts and editable complex framework diagrams with FigureForge's Python adapter.
---

# Paper figure production — first choice

For paper figures, first use `search_figure_references` (English topic + layout terms work best) and `figure_forge`. The installed upstream is https://github.com/qwdwqfwq/topconf-paper-figure-gallery, pinned in docs/video-skills.lock.json. The adapter uses its local reference metadata and a Python vector renderer. It does NOT run upstream image-model inference; that browser feature requires a separately configured image provider. Never imply DeepSeek Chat generates images or send paper drafts to an unconfigured provider.

Retrieve a few relevant references, compare information hierarchy and layout, then design around the actual scientific question. Do not copy paper images, numbers, method content or contribution claims. Save the reference provenance. If retrieval has no relevant hits, say so; use a justified local layout. Use `plot_results`, `draw_framework`, or a custom script only when the preferred adapter cannot express the figure, recording why.

Write a JSON specification with `write_file`, then call `figure_forge(spec_path, brief)`. Read `specification.md` for the exact schema. Outputs include PDF, SVG, 300-DPI PNG, source spec, reproducible standalone Python, source CSVs, provenance and citations; framework outputs also include editable `.drawio`.

Before quantitative rendering, inspect actual CSV rows. Every panel must answer a distinct question. Use two to six panels only when they add information: overall effectiveness; component effects; fault/type/subgroup distribution; robustness; measured resource costs; failures. A simple study may need fewer panels. Use a common ordering and palette across plots. Hatches supplement color. Never invent data, variation, significance or error bars to make a chart look richer.

Declare sample size and its unit (cases, devices, independent seeds, etc.). Controlled fault-grid cases are not IID repetitions. Aggregation is explicit; missing cells are not implicitly zero. Preserve unsuccessful cases. A measured result requires registered experimental provenance; unregistered/synthetic sources are visibly labelled and cannot substantiate a scientific claim.

For frameworks, specify genuine groups, I/O, module internals, persistence boundaries and feedback paths. Mark only supported contributions. Match section/code names. Aim for 8–20 concise nodes when the method actually has that structure; complexity is a consequence of the method, not an aesthetic goal. Pair the overview with a small example diagram showing the baseline's failure and the proposed mechanism's action.

Inspect final PDF/PNG at the intended one/two-column size. Check arrow routing, overlaps, clipping, readable labels, color-blind/grayscale interpretation and captions. Iterate the spec and rerender. Rendering is not a scientific quality pass. If the active model cannot see images, hand the preview to a configured vision reviewer or the user and report that visual review remains pending.

Before rendering for a manuscript, persist its layout with `configure_manuscript_layout`. Copy the user's single/double-column choice exactly; when no choice exists, record the existing portrait layout as inferred. Add `"manuscript": "manuscripts/draft/main.tex"` and `"figure_scope": "column"` to the figure spec. The renderer binds the target width to that contract. `page` scope is allowed in a double-column document only when spanning figures were explicitly authorized. Design at the final physical width; split/reflow dense panels instead of drawing wide and shrinking. Never introduce landscape pages, sideways figures or full-width floats to avoid a layout failure.

After inclusion call `compile_latex`, then `validate_manuscript_layout`. Only an instrumented compile plus actual PDF geometry, object bounds and effective vector-font checks can pass. Source regex checks, a compiler exit code, or an attractive standalone wide figure are insufficient. Fix every blocking diagnostic and inspect the final rendered pages for overlaps; the automated gate does not claim scientific or complete visual review.
