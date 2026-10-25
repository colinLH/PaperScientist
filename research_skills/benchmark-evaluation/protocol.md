# Local benchmark adapter contract

The `paperscientist.benchmarks` module stores append-only source/manifest/protocol/result artifacts in the session workspace. Registered artifacts include SHA-256 digests. A later output overwrite does not erase the immutable result snapshot. Audits after restart re-read the execution receipts, frozen inputs and snapshots.

## Manifest

`register_benchmark(manifest)` accepts an object:

```json
{
  "id": "my-domain-benchmark",
  "title": "Name of published benchmark",
  "version": "immutable-dataset-revision-and-grader-version",
  "source_url": "https://official.example/benchmark",
  "license": "Exact applicable data/code license names",
  "license_url": "https://official.example/terms",
  "license_notes": "Access, consent, attribution and redistribution conditions",
  "task": "Task and expected output measured by the benchmark",
  "provenance": "external",
  "splits": ["test"],
  "metrics": {"pass_rate": "Passed tasks / all planned task executions"}
}
```

`local_synthetic` provenance is reserved for adapter tests and requires `smoke` scope. `latest`, `main`, `master` and unknown versions are rejected. Supported arithmetic: `accuracy`, `exact_match`, `pass_rate`, `mae`, `rmse`, `mean_score`. The latter means a finite per-case score already produced by the reviewed official evaluator; it is not a universal substitute for that evaluator. A new benchmark can supply a different local adapter without adding it to the built-in candidate catalog.

## Dataset index and protocol

Store a UTF-8 JSON array with unique case IDs and splits. For prediction metrics, include frozen `target` values. Keep confidential labels in the evaluator's area; never include them in agent prompts or use them to tune the tested method. The local runner does not itself provide a hidden-label isolation boundary.

```json
[{"case_id": "case-001", "split": "test", "target": "expected label"}]
```

Before execution call `plan_benchmark(benchmark_id, protocol)`:

```json
{
  "decision": "selected",
  "rationale": "Why this suite is relevant to the target claim",
  "claim": "Bounded scientific claim being assessed",
  "task_match": "Input, output, task and evaluation unit alignment",
  "scope": "subset",
  "split": "test",
  "case_ids": ["case-001"],
  "methods": ["proposed", "baseline"],
  "seeds": [0, 1, 2],
  "metrics": ["pass_rate"],
  "adapter": "local_python",
  "script_path": "evaluation/official_adapter.py",
  "dataset_path": "evaluation/cases.json",
  "result_path": "evaluation/results.json",
  "evaluator_description": "Reviewed wrapper around pinned official grader; describe commands and mapping",
  "limitations": "Subset selection, task exclusions and comparability limits",
  "budget": {"timeout_seconds": 300, "max_evaluations": 6, "hardware": "CPU model; RAM; GPU if used"}
}
```

Optional `manifest_path` selects a specific registered manifest version. A `not_applicable` decision requires only `rationale`, `claim`, and `task_match` besides its decision and benchmark selection; do not use it to conceal insufficient budget. Scopes: `smoke`, `subset`, `full_split`. `full_split` means every entry in the supplied frozen split index, not automatically every task in the official benchmark. The indexed methods × seeds × cases must fit the declared maximum evaluations. The local runner enforces a process-tree wall timeout of up to 300 seconds per run; hardware is recorded, not imposed as a memory/GPU quota. Longer official evaluations must be split into pre-registered subsets that fit this adapter, or require a separately configured durable runner. Do not silently increase budgets or call partial work complete.

Use optional `input_paths` to include local raw data, collected source manifests, prediction files and evaluator dependencies beyond the case index. Their hashes are frozen and rechecked before execution and during audit. All paths are inside the session workspace; large files are hashed incrementally. The operator must pin installed grader/environment versions in the manifest because the generic harness cannot freeze libraries outside the workspace.

## Run and results

The local script uses the session workspace as its current directory. It must write the configured results file. Dependencies and any official grader must already be installed and reviewed; source collection never installs or runs downloaded code. The existing Python runner omits model/API credentials from child processes. It is intended for local evaluation of already-produced agent outputs, not an implicit paid inference loop.

```json
[
  {"case_id": "case-001", "method": "proposed", "seed": 0, "status": "ok", "passed": true},
  {"case_id": "case-001", "method": "baseline", "seed": 0, "status": "timeout"}
]
```

Each `(case_id, method, seed)` occurs once. `status` is `ok`, `error` or `timeout`. Prediction metrics use `prediction` versus the frozen index target; pass rate needs a boolean `passed` from the evaluator; `mean_score` needs finite numeric `score`. A wrong answer is `status=ok, passed=false`, because the grader ran successfully. A crashed grader is `error` and prevents protocol completion.

`run_benchmark(plan_id)` executes and records. Alternatively execute the exact frozen script through `run_python`, then call `record_benchmark_result(plan_id, result_path, run_id)`. The protocol must predate the successful execution. The script hash, run ID and output hash must match. Missing cases and errors remain in the planned denominator for success metrics; numeric error metrics report their scored coverage and remain incomplete if rows are missing or failed.

`audit_benchmarks()` independently recomputes coverage and summary metrics. `protocol_complete` means every planned evaluation has a valid row and no evaluator errors; a zero success rate can still be a complete evaluation. `official_benchmark_complete` stays false because this generic harness cannot certify the semantic validity of a grader, official inventory, leakage controls or leaderboard compliance. Report the actual protocol scope and link evidence rather than promising an official score certification.

## Reproducible adapter smoke

Run `python research_skills/benchmark-evaluation/scripts/smoke.py` from the repository root. This performs 24 actual local evaluations over six synthetic parity cases, two trivial methods and two seeds, then reopens the store and audits persisted receipts. It writes `.test-output/benchmark-harness/smoke-report.json`. Optional `--collect-primary-source` also collects the official ScienceAgentBench README with its source hash; it does not run ScienceAgentBench or download restricted data. No model/API call is involved and no official benchmark performance is claimed.
