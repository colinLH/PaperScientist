# Primary benchmark sources

Checked 2026-10-25. Pin revisions at collection time; these links are discovery pointers, not installed dependencies or permission to execute their code.

| Benchmark | What it measures | Applicability and collection constraints |
|---|---|---|
| [ScienceAgentBench](https://github.com/OSU-NLP-Group/ScienceAgentBench), [paper](https://arxiv.org/abs/2410.05080) | Scientific tasks requiring Python programs and task-specific execution evaluation. | Appropriate for data-driven scientific-agent capability. The official README now identifies a verified split and matching verified artifacts. Respect its prohibition on redistributing unpacked benchmark data; use its official rubrics. |
| [MLAgentBench](https://github.com/snap-stanford/MLAgentBench), [paper](https://arxiv.org/abs/2310.03302) | Agents autonomously improving ML models under task goals. | Appropriate for ML experimentation. Preserve task versions, baselines, official evaluation and runtime logs. Some datasets require Kaggle credentials and competition consent. |
| [MLE-bench](https://github.com/openai/mle-bench), [paper](https://arxiv.org/abs/2410.07095) | ML engineering tasks from Kaggle competitions. | Appropriate for competitive ML task performance. Check per-competition data terms, held-out grading, compute budget and evaluator version. Competition-specific raw scores cannot be indiscriminately averaged. |
| [SWE-bench](https://github.com/SWE-bench/SWE-bench), [official evaluation guide](https://www.swebench.com/SWE-bench/guides/evaluation/) | Whether generated repository patches resolve real issues under tests. | Appropriate for software issue-resolution claims. Pin dataset variant and instance IDs; the official containerized grader checks patches. Build errors, execution errors and unresolved issues are different outcomes. |

Local synthetic interruption/recovery cases measure recovery behavior under the chosen fault model. They complement these external suites. They do not establish general scientific discovery, code-repair or ML-engineering benchmark performance. For other domains, search the relevant scientific venue or dataset maintainers and register a new manifest; no code change is needed when the local adapter contract suffices.
