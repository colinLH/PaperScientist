---
name: latex-writing
description: Assemble a complete academic LaTeX manuscript with consistent sections, verified citations, figures, methods and evidence-backed results.
---

# LaTeX writing

Read the current plan, paper library, source code and registered experiment results. Decide which sections the user requested now; do not require an artificial phase order. Maintain a claim ledger linking manuscript statements to references or measured artifacts.

For a complete draft use a clear problem-to-method-to-evidence narrative: abstract, introduction, related work, problem formulation, method, experimental setup, results, limitations and conclusion. Match venue constraints only from a provided or verified template. Do not claim compliance from a generic article class.

Use assemble_manuscript with LaTeX section bodies and project paper IDs as citation keys. Escape ordinary text, keep equations valid, and ensure symbols match code. Save figures under the manuscript directory and use relative paths. Missing experiments, author information and unsupported conclusions must be explicit TODOs; avoid fabricated placeholders that resemble real results.

For Chinese text adapt the preamble to ctex and XeLaTeX/LuaLaTeX with available fonts. For English the built-in article template is a starting point. Compile with compile_latex when enabled and available; fix diagnostics and check references. Compilation success is distinct from scientific validation.

Load paper-polish and evidence-review before calling a draft ready for submission. Package all supporting sources, bibliography and figures together.
