---
name: scientific-python
description: Implement research modules and reproducible Python experiments with explicit configurations, meaningful tests and result provenance.
---

# Scientific Python

Inspect existing workspace files before changes. Create small modules with clear input/output contracts. Keep model logic, datasets, training, evaluation, configuration and plotting separate when complexity warrants it. Use configuration files, deterministic seeds where feasible, and explicit dependency versions.

Write checks for meaningful properties: output dimensions, loss behavior, dataset leakage, metric correctness, numerical stability and baseline equivalence. A test that merely repeats the implementation is not useful. Run a small pipeline test before a costly experiment.

Save raw per-seed observations to CSV/JSON with dataset, split, method, seed, metric, units and configuration identifiers. Record failed runs explicitly. Use run_python to capture logs, exit code, duration, script hash and result hashes. Inspect outputs before declaring success.

Execution is opt-in for trusted local code and is not a hostile-code sandbox. Do not attempt to bypass its gate. If disabled, finish writing code/configuration and state the exact next execution command. For multi-agent work give each child a separate module/output ownership and import reviewed artifacts explicitly.
