---
name: independent-review
description: Conduct scoped independent manuscript or method reviews with isolated reviewer contexts, source anchors, frozen reports and a separate synthesis. Use when the user requests multiple reviewers or independent critique.
---

# Independent review

Choose the review scope from the user's request. Assemble an immutable packet with the manuscript,
verified evidence, artifact IDs, assessment boundaries and venue criteria. Save its hashes.
Choose reviewer emphases before reading any review, for example method validity, empirical evidence,
and clarity/significance. The count follows scope and available concurrency.

For each substantial review call spawn_agent with role=reviewer, isolated_review=true,
fork_context=false, and artifact_ids containing ONLY the selected immutable source packet.
This mode copies and hashes sources into the child's workspace, suppresses inherited project/memory,
and disables mutable parent reads, memory retrieval, arbitrary execution and external MCP tools.
Supply only the packet's assessment criteria and that reviewer's emphasis in message.
Do not send another reviewer's findings or the parent's suspected problems. Have each reviewer write
a separate report with stable concern IDs, claim locations, exact evidence locations, severity,
uncertainty and a concrete proposed fix. Missing evidence is a limitation, not a fabricated finding.

Wait for and read every report. Freeze its file and hash before comparing reports. Keep independent
agreements and disagreements. Run audit_research and numeric consistency checks as a separate pass.
Synthesize the concerns into a revision matrix: concern ID → evidence → action → changed section →
verification. Do not rewrite the individual reports to make them appear more diverse.

If separate contexts cannot be provided, state that limitation and provide a single review.
Never call sequential role-playing in one context independent review. This is an advisory mock review,
not an editorial decision or an assurance of acceptance.

Further references: nature:nature-reviewer and nature:nature-response, downloaded from
https://github.com/Yuan1z0825/nature-skills/tree/c6ae86c742705fd968b13c79db1a8518a84089d4
Read supporting resources only when needed; do not impose the upstream default reviewer count.
