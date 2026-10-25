---
name: method-design
description: Design a paper's scientific method, module interfaces, equations, overall workflow and editable framework diagram.
---

# Method design

Derive the architecture from the scientific claim. Specify inputs, outputs, information available at training/inference, assumptions, objective functions and complexity. State how each module addresses a specific motivation or challenge. Identify possible data leakage.

For every module record: responsibility, tensor/data shapes, public interface, algorithm or pseudocode, parameters, dependencies and verification criterion. Keep naming consistent across code, diagram and manuscript. Distinguish a new mechanism from engineering support.

Load figure-forge and use its preferred tool with explicit coordinates, short labels, readable groups and directional edges. Include real module internals, persistence/training boundaries and feedback paths when relevant. Save editable JSON/drawio and PDF/SVG alongside PNG. Use draw_framework or specialized Python only for unsupported needs. Review overlaps and labels at final print size.

Introduce a concrete motivating example and a small example figure before the overview. Trace baseline behavior, identify C1/C2 challenges, then map each challenge to a contribution, design subsection, implementation symbol and falsifiable evaluation question. Start design subsections with this mapping; distinguish novel mechanisms from support plumbing. Detailed diagrams should clarify the actual design, not manufacture complexity.

Prepare an ablation for each claimed necessary component. If two modules make the same causal claim, design a control that distinguishes them. Use a methodologist/reviewer child for independent criticism when the design is substantial.

draw_framework also saves a native .drawio file with editable nodes and edges. Use the same node IDs
and module names in equations, implementation and the manuscript. For complex methods build a
mapping table: concept → equation/assumptions → Python symbol → test → ablation. Search
research:atomic-decomposition and drawio:drawio-skill for further guidance; external tool names
in those references do not create new execution capabilities.
