---
name: experiment-design
description: Map contributions and motivations to evaluation questions, baselines, ablations, controls, metrics, uncertainty and resource-aware experiments.
---

# Experiment design

Build a claim-to-evidence matrix using update_research_plan. Every primary claim must have an evaluation question, a testable prediction, data/split, metrics, baselines, controls and a failure criterion.

Include comparable training budgets, hyperparameter search budgets and compute reporting. Prefer established splits; isolate tuning from held-out tests. Specify seeds, repetitions, aggregation and uncertainty estimates before seeing final results. Do not use standard deviation and standard error interchangeably. Report sample counts and missing/failed runs.

Cover effectiveness, component ablations, robustness/generalization, efficiency and failure analysis only when relevant to the claim. Justify each experiment by the question it answers, rather than collecting decorative plots.

Load manuscript-quality/venue-patterns.md. The evaluation section should preview its research questions, then give setup/protocol before findings. Include selection criteria, exclusions/failures, version/tuning parity, leakage controls, metric definitions/directions/units, hardware/software and sampling/uncertainty definitions. Use real-data multi-panel figures with figure-forge to expose outcome composition, subgroup/fault differences and cost tradeoffs where supported. A controlled case grid does not justify IID confidence intervals. Clearly separate measured synthetic workloads from deployment-level scientific evidence.

Save the protocol and executable configuration before running. Start with a labelled smoke test for pipeline correctness. A synthetic or toy run cannot establish performance on the research problem. Use record_experiment with the correct provenance and a successful run ID for measured outputs.
