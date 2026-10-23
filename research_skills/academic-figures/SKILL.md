---
name: academic-figures
description: Produce publication-style matplotlib figures from measured data with clear uncertainty, consistent typography and reproducible vector exports.
---

# Academic figures

Identify the scientific question the figure answers and inspect the source data and provenance. Choose a line plot for ordered variation, scatter for relationships, or bars for discrete comparisons. Do not invent missing data, confidence intervals or favorable axes.

Use plot_results for standard plots or write a Python script for specialized layouts. Keep units and labels explicit, fonts readable at final paper size, colors accessible, and method ordering consistent. Use direct labels or a concise legend. State what each error bar means, how many repetitions it covers and how it was calculated.

Preserve CSV/JSON inputs, a Python plotting script and PDF/SVG plus 300-DPI PNG. View generated output; check labels, clipped content, legend collisions and whether axis ranges distort comparisons. The caption should state the question, observation and uncertainty without overstating causality.

Keep titles, synthetic annotations and captions in separate layout bands. Framework coordinates may be grid units or pixels; use draw_framework to normalize them and keep labels concise. If the configured model has no image understanding, provide the previews for human review or use an explicitly configured vision tool. Do not claim a visual inspection from filenames or source code alone.

For synthetic tests, include “synthetic / pipeline validation” in the title or caption. Never use those values as measured scientific results in the manuscript.

Use plot_results question/sample_size/n_definition/uncertainty_definition fields to save a figure contract.
Inspect its reporting_gaps. Rendering success, semantic validity and publication readiness are separate.
For specialized plots, search scientific:matplotlib / scientific:statistical-analysis and
sciplot:sciplot-figure-skill. SciPlot's upstream scripts require Python 3.14; our native plotting
tool remains available on the project's Python runtime. Adapt its specification and provenance
principles without claiming that its full QA suite ran.
