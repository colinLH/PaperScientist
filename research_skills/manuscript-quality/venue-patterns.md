# Evaluation structures from representative papers

These are task-dependent patterns, not mandatory headings or claims that one layout guarantees acceptance. Do not import their reported numbers into another study.

| Source | Useful pattern | Application |
|---|---|---|
| [MLAgentBench, ICML 2024](https://proceedings.mlr.press/v235/huang24y.html), §4 | Explicit models/baselines, run/action/time budgets, task-level outcomes, then research-process analysis | State unequal budgets openly; evaluate final success and process failures separately; an average can hide task differences. |
| [SWE-agent, NeurIPS 2024](https://papers.nips.cc/paper_files/paper/2024/hash/5a7c947568c1b1328ccc5230172e1e7c-Abstract-Conference.html), §§4–5 | Setup defines benchmarks, baselines, resolution and cost metrics; results lead to interface ablations and behavior cases | Separate configuration search from final testing; pair effectiveness with cost; connect each mechanism to a control and concrete trace. |
| [Self-RAG, ICLR 2024](https://proceedings.iclr.cc/paper_files/paper/2024/file/25f7be9694d7b32d5cc670927b8091e1-Paper-Conference.pdf), §4 / Fig. 3 | Main task results plus component ablations and inference/retrieval tradeoffs | Put mechanism removal, customization and parameter sensitivity in separate panels; name their datasets/protocol differences. |
| [WebRR, USENIX Security 2024](https://www.usenix.org/system/files/usenixsecurity24-allen.pdf), §5 | Questions precede experimental setup and metrics; later subsections address record/replay, comparisons and resource overhead | Use RQs as the organizing spine; specify the target environment, correctness oracle and cost before presenting results. |
| [NDSS 2025 artifact guidance](https://www.ndss-symposium.org/ndss2025/submissions/call-for-artifacts/) | Reusable code, data and executable reproduction instructions | Ship exact inputs/configuration, environment, scripts and outputs; document partial results and limitations. This is artifact guidance, not a paper template. |

For a particular CCS, NDSS, S&P or other venue submission, retrieve two recent papers in the SAME task family and inspect their actual setup/protocol before adapting this outline. Do not claim that every venue shares a fixed template or that all cited structures were empirically compared.

Suggested adaptable outline:
1. RQs and tested claims (cross-reference design components).
2. Setup: subjects/data, selection and split, baselines and fairness, implementations, environment, metrics, budgets, repetitions and failure handling.
3. Overall effectiveness and per-category outcomes.
4. Mechanism ablations and controlled comparisons.
5. Relevant robustness/sensitivity/scaling and resource costs.
6. Representative successes/failures with traces and explanatory figures.
7. Scope and threats: what the experiment does NOT measure; what evidence would test those gaps.

Only include sections justified by the claims and available evidence. Schedule missing essential experiments or narrow claims. Never pad the paper with fabricated measurements, duplicate panels or decorative statistical tests.
