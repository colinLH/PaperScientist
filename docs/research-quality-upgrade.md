# Intro atmosphere and manuscript quality upgrade

## Visual direction

The first three welcome scenes now use stronger reusable valley-mist sprites, increased distance fog and two softly drifting foreground planes. The envelope follows continuous camera position, fades to zero at the fourth scene, and reverses along the same curve. Hidden/reduced-motion behavior is retained; no extra animation loop or per-frame noise texture is introduced. The 4K nebula, meteor effects, hand tracking and audio transitions retain their existing implementations.

The art direction uses subdued forest colors, layered depth, calmer typography and lighter chrome. References inspected:

- [Anthropic frontend-design](https://github.com/anthropics/skills/tree/main/skills/frontend-design), installed as `frontend:frontend-design` at a pinned commit.
- [Web Design Studio](https://github.com/MustBeSimo/web-design-studio), naturalistic-drift example/theme and film-archetypes reference. Used as inspiration; its component library is not copied wholesale or executed.
- Local `frontend-design` and `animate` guidance for typography, motion continuity and rendering cost.

## Installed sources and tools

`docs/video-skills.lock.json` now pins three additional sources and their hashes/licenses. Restore with `python scripts/install_research_skills.py --source NAME`; verify with `--check`.

| Source ID | Installed content | Use |
|---|---|---|
| `writing-style` | [anti-defensive-writing](https://github.com/Kiterlin/anti-defensive-writing) | `writing-style:anti-defensive-writing`, evidence-preserving prose cleanup |
| `frontend` | Anthropic frontend design skill | Intentional visual design, loaded on demand |
| `figureforge` | [Top-Conf Figure Gallery](https://github.com/qwdwqfwq/topconf-paper-figure-gallery) pinned catalog, licensing and retrieval references | Local reference search; upstream has no SKILL.md, so the builtin `figure-forge` skill is its adapter |

`search_figure_references` performs bounded local BM25 retrieval. `figure_forge` is the first-choice LangChain paper-figure tool. It reads a JSON specification, validates data/graph inputs, and emits PDF/SVG/PNG, editable drawio for diagrams, the final specification, source CSVs, standalone Python and a provenance report. Supported quantitative panels: grouped/stacked bars, lines/error bars, scatter, boxes and annotated heatmaps. Missing cells and implicit duplicate aggregation are rejected. Unverified/synthetic data is labelled; no artificial error bars or significance are added.

The adapter uses the upstream **reference catalog**, plus a local Python renderer. It does **not** run original FigureForge image-model inference. That feature needs a separately configured image provider; a DeepSeek text key is not an image API. Numerical plots always use code and actual data. Paper images retain their authors' rights and are not bundled or copied into new figures.

See `research_skills/figure-forge/specification.md` for the schema. Use `plot_results`, `draw_framework`, or custom Python only for a requirement the preferred tool cannot express, with the reason recorded.

## First-draft improvement trigger

The system prompt now recognizes a complete first manuscript draft regardless of whether it came from `assemble_manuscript` or ordinary file writes. It directs the model to:

1. Save a `review_manuscript(..., phase="baseline")` inventory.
2. Load `manuscript-quality`, `paper-polish`, `writing-style:anti-defensive-writing` and relevant language/LaTeX resources.
3. Review each section and the chain from concrete example to challenge, design, contribution and experiment. Record actual revisions and unresolved evidence gaps.
4. Save the revised review, inspect changed numbers/citations, validate sources, compile and inspect the PDF.

The review tool recursively checks included TeX within the workspace, inventories headings/figures/citations and hashes sources, and detects numeric/citation changes. It is not a scientific acceptance score. This prompt mechanism keeps interactive research flexible; it does not force short answers through a paper pipeline or guarantee model compliance.

`research_skills/manuscript-quality/venue-patterns.md` records representative ICML, NeurIPS, ICLR and USENIX structures with primary links, and NDSS artifact guidance. A venue-specific submission still needs same-topic paper comparison. No general template or cosmetic polishing establishes novelty.

## Validation and example

The existing 228-case recovery experiment was reaggregated after matching its three raw CSV hashes to successful original execution records and comparing outcome counts to the independent audit. The example adds a concrete op-4 crash trace, a grouped recovery architecture and a four-panel results figure. It does not add new experimental measurements or establish LLM competence. The preserved manuscript revision, source lineage and section notes are in the existing research session's `quality_revision/` directory.

Automated tests cover figure reproduction, explicit aggregation/missing-data behavior, path boundaries, graph references, editable exports, unverified-data labelling, skill metadata, signed numeric/citation changes, mist-envelope continuity and existing audio/rendering budgets. DeepSeek live checks cover initial tool routing; they do not certify a full autonomous paper-quality pass. Desktop visual verification was stopped by Computer Use because it could not reliably identify the browser URL; no browser visual/performance pass is claimed for this change.
