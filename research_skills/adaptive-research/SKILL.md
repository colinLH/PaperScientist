---
name: adaptive-research
description: Manage a sustained research task using bounded hypothesis-test iterations and evidence-based synthesis checkpoints. Use for multi-experiment work or revising a research plan after unexpected results.
---

# Adaptive research

Read the current user scope, project claims, plan, constraints and recorded artifacts. Pick the
smallest experiment that distinguishes the competing explanations. Save the hypothesis, prediction,
evaluation question, budget, baseline and stopping condition before running it.

After execution, check logs and captured hashes, register results with record_experiment, and record
what was observed separately from why it might have happened. Failure and negative results remain
part of the evidence. Keep a concise decision log in the workspace.

When results surprise you, an assumption fails, or another run is unlikely to change the conclusion,
pause iteration to synthesize. Use audit_research, compare alternatives, and update_research_plan
with the next experiment, a literature question, a proposed pivot or a justified stopping point.
Only the user's explicit selection confirms a new direction. Work may move directly to writing,
review or another task; no stage order, experiment quota or unattended scheduling is imposed.

For method-specific engineering, search the orchestra skill source and load only relevant packages.
This bounded iteration/synthesis pattern is inspired by Orchestra Research's autoresearch:
https://github.com/Orchestra-Research/AI-Research-SKILLs/tree/773a52944ba4747a18bd4ae9ade53fff041adcbc/0-autoresearch-skill
The upstream continuity hooks and host-specific control commands are not part of this adapter.
