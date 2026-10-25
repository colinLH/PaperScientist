---
name: benchmark-evaluation
description: "Select task-relevant public benchmarks, pin evaluation protocols and collect real, traceable per-case results; use when assessing research methods, models or agent capabilities against external baselines."
---

# Task-relevant benchmark evidence

Use this when a research claim could reasonably be tested against an established benchmark. Do not force a scientific-agent suite onto unrelated research or treat generic unit tests as a benchmark score.

1. Call `discover_benchmarks` with the actual research task, not merely “benchmark”. Search primary sources for domain benchmarks when the curated registry has no match. Compare task, inputs/outputs, evaluation unit and claimed capability. Persist candidates and explain selections or `not_applicable` decisions. Resource limits mean a relevant benchmark is **blocked or deferred**, not scientifically inapplicable.
2. Collect official documentation, dataset metadata and the applicable licenses with `collect_benchmark_source`. Keep code and dataset license conditions separate. Register a manifest with pinned version, split and metric definitions. Never execute downloaded benchmark installers or scripts automatically; use a configured, reviewed local Python adapter and the existing execution setting.
3. Before execution, write the dataset case index and adapter, then call `plan_benchmark`. Freeze exact case IDs, split, methods/baselines, seeds, metrics, evaluator description, budget and limitations. Use official graders where available. Keep test targets out of agent/model inputs and tuning. A sampled subset remains a subset; a full local index is not proof of the full official dataset.
4. Use `run_benchmark`, or run the registered adapter via `run_python` and use `record_benchmark_result` with that run ID. Report errors, timeouts and missing samples. Do not import a hand-written aggregate or call synthetic adapter checks an official benchmark result.
5. Call `audit_benchmarks` before describing completion. Cite protocol, execution run ID, immutable results, coverage, metric and scope. Distinguish successful execution, task success and official comparability. Report repeats/uncertainty, costs, failures and selection bias alongside performance. Audit verifies provenance and arithmetic, not evaluator semantics or novel research claims.

Read [protocol.md](protocol.md) when preparing a manifest, adapter or data/result file. Read [primary-sources.md](primary-sources.md) to decide whether scientific-agent, ML-experimentation or code-repair benchmarks match the claim. Those are examples, not a closed list; register suitable domain benchmarks using the same interface.
