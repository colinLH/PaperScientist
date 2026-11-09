---
name: experiment-design
description: Map contributions and motivations to evaluation questions, baselines, ablations, controls, metrics, uncertainty and resource-aware experiments.
---

# Experiment design

Build a claim-to-evidence matrix using update_research_plan. Every primary claim must have an evaluation question, a testable prediction, data/split, metrics, baselines, controls and a failure criterion.

Include comparable training budgets, hyperparameter search budgets and compute reporting. Prefer established splits; isolate tuning from held-out tests. Specify seeds, repetitions, aggregation and uncertainty estimates before seeing final results. Do not use standard deviation and standard error interchangeably. Report sample counts and missing/failed runs.

Cover effectiveness, component ablations, robustness/generalization, efficiency and failure analysis only when relevant to the claim. Justify each experiment by the question it answers, rather than collecting decorative plots.

For a comparison, sketch the intended panels **before** collecting data. For instance, a tool-agent security study may compare base and defended policies across attack families and tool environments, measuring both attack success and benign utility. Use the task's own categories and outcomes. Plan matched case IDs, splits and seeds for compared methods, the independent sampling unit, budgets and any uncertainty calculation. With a small budget, prioritize cases that distinguish the competing explanations. Preserve measured costs or failure reasons when they answer a research question.

Freeze categorical annotations in the case index and register relevant `case_facets` and `paired_baselines` through `plan_benchmark`. Check coverage per planned cell and baseline pair during evaluation. If a necessary comparison is missing, record the gap and collect the missing runs under a frozen protocol within budget. Label any extension after seeing results as exploratory. If collection is infeasible, mark the cells unavailable in the figure and narrow the claim.

Load manuscript-quality/venue-patterns.md. The evaluation section should preview its research questions, then give setup/protocol before findings. Include selection criteria, exclusions/failures, version/tuning parity, leakage controls, metric definitions/directions/units, hardware/software and sampling/uncertainty definitions. Use real-data multi-panel figures with figure-forge to expose outcome composition, subgroup/fault differences and cost tradeoffs where supported. A controlled case grid does not justify IID confidence intervals. Clearly separate measured synthetic workloads from deployment-level scientific evidence.

Save the protocol and executable configuration before running. Start with a labelled smoke test for pipeline correctness. A synthetic or toy run cannot establish performance on the research problem. Use record_experiment with the correct provenance and a successful run ID for measured outputs.

For a trusted local Python experiment that should outlive the chat or web process, use `start_experiment_job(name, path, inputs, timeout)` when local execution is enabled. List the script's local data, configurations and helper modules as session-relative input files. The worker snapshots them with hashes and runs in its own directory. Use the same name when retrying the same submission. `inspect_experiment_job` lists this session's jobs or tails a named job's logs. Use `stop_experiment_job` to cancel an unwanted run. For a measured claim, check successful completion and pass the returned run_id and an exact output_files path to `record_experiment`. Registered benchmark protocols keep their existing run_benchmark and benchmark audit workflow.
