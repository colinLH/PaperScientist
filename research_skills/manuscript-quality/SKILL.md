---
name: manuscript-quality
description: "Section-level scientific manuscript improvement after a first draft: concrete motivation examples, challenge-design-innovation mapping, venue-informed evaluation protocol, figures and evidence-preserving revisions."
---

# Full-draft quality pass

## Binding layout contract

Before writing or assembling the paper, save the requested single/double columns, portrait paper size, margins, column gap, figure scope and minimum published figure font with `configure_manuscript_layout`. Use the exact user requirement when available. Otherwise preserve existing layout and mark it as inferred, never as an explicit user choice. For a new unspecified manuscript record the portrait single-column default.

The contract constrains all included sections, tables and imported graphics. Do not switch column count, rotate pages or introduce spanning floats to make a large diagram fit. Reflow or split it with readable labels at the actual column width. Use `compile_latex` for a staged compilation and `validate_manuscript_layout` before delivery. A blocked layout must be repaired; the last delivered PDF remains intact. Recompile after changing any source, figure or contract. Check rendered pages as well: geometry validation cannot prove absence of overlaps or scientific correctness.

Trigger when a complete first manuscript draft exists, even if it was written with write_file instead of assemble_manuscript. Local edits/short notes do not require the whole procedure. This is a review contract, not a fixed research workflow: decide which missing evidence to collect, discuss or mark as a limitation.

1. Call `review_manuscript(main_path, phase="baseline")`. Read source, claim ledger, experiment manifests and figures. Its report is an inventory, not proof that claims or prose are good.
2. Load `paper-polish`, `writing-style:anti-defensive-writing`, and relevant installed language/LaTeX skills using `list_skills`/`load_skill`. Apply these references within the user request, preserving accurate uncertainty and scientific scope.
3. Save section-specific findings and a matrix: motivating example → observed failure → challenge C_i → insight/contribution → module/equation/code → RQ → experiment/figure → supported conclusion. Separate new mechanisms from engineering support. Missing evidence is a gap, not an invitation to fabricate.
4. Revise structure before language, then call the revised review. Check changed numeric tokens and citations against source evidence; these checks can produce benign differences (section numbers etc.). Run `validate_manuscript`, compile, inspect the PDF and fix visual issues. Report unresolved scientific gaps.

## Section contracts

- **Introduction:** concrete problem and stakes, what closest work cannot handle under stated assumptions, central insight, then bounded contributions with evidence pointers. Avoid unsupported "first" or "state of the art".
- **Background:** prerequisites, notation, task/system/threat model and scope needed to understand the method; no unrelated tutorial. Clarify which assumptions are assessed experimentally.
- **Motivation/challenges:** one representative concrete input and baseline failure trace. Show the before/after or state transition in an example figure. Derive challenges from the trace rather than adjectives such as "complex" or "dynamic". Name what a successful design must preserve.
- **Overview:** grouped architecture with genuine processing/state boundaries, inputs/outputs and feedback. Reuse exact module names throughout. Invoke figure-forge first. Explain the path through the diagram in prose.
- **Design detail:** start each subsection with the challenge and mechanism/novelty; specify I/O, algorithm/equations, assumptions, example trace, implementation and the ablation that could falsify necessity. Explain why plausible alternatives fail or trade off, without inventing baseline results.
- **Experiments:** preview research questions; then setup/protocol before results. Report selection/splits/leakage control, versions/tuning parity, metrics and units/directions, hardware/software, seeds/repetitions, timeouts/failures, sample unit and uncertainty definition. Organize results by RQ: overall effects, justified controls/ablations, robustness/sensitivity, cost, failures/cases. Each panel should answer a different question using actual data. See `venue-patterns.md`.
- **Discussion/limits:** explain supported scope, alternative explanations, selection/measurement bias, deployment cost and failure boundary. Distinguish simulated fault injection, controlled prototypes and real-world deployment.

## Prose pass

Remove repetitive disclaimers, generic transitions, ornate claims, mechanical parallel lists and paragraphs that merely repeat a heading. Replace them with precise subject/action/evidence and varied natural phrasing. Do not remove material caveats, inflate novelty, promise evasion of AI detectors, disguise authorship or silently alter measured values. Preserve LaTeX labels, equations, citations, figures and result provenance.
