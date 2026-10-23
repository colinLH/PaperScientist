---
name: evidence-review
description: Audit a research proposal or paper for novelty evidence, reproducibility, unsupported claims, experiment validity and citation accuracy.
---

# Evidence review

Review the artifact the user requested. Build a table of important claims and their evidence. For literature claims verify the paper and relevant passage. For performance claims check raw results, recorded run provenance, dataset splits, baselines, seeds, aggregation, uncertainty and compute fairness.

Identify data leakage, missing controls, cherry-picked subsets, unreported failures, insufficient baselines and conclusions that exceed the measurements. Verify that synthetic pipeline checks are clearly labelled and excluded from scientific claims.

For novelty compare the nearest prior methods, not only broad topic labels. A new combination needs an explicit reason and evidence. Check consistency among manuscript, equations, diagrams, configurations and code interfaces.

Report findings by severity with file/section and a concrete correction. Distinguish established errors, likely issues and questions requiring information. Preserve uncertainty; do not invent an issue just to fill a quota. Recheck corrections before final delivery.

Link an important claim to a source using record_evidence. The exact quote is checked against a
retrieved title/abstract or a registered text artifact; record a page/section locator and keep
interpretation separate. Preserve supporting and contradictory entries. Run audit_research to
find changed sources, unresolved links, missing measured results and missing evaluation coverage.
Report what was checked and what is unassessed; a passing structural audit does not establish validity.
For more guidance search scholar:citation-verification, academic:academic-paper-reviewer and
nature:nature-reviewer. Use independent-review only when multiple independent reviews fit the task.
