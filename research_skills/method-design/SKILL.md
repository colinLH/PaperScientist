---
name: method-design
description: Design a paper's scientific method, module interfaces, equations, overall workflow and editable framework diagram.
---

# Method design

Derive the architecture from the scientific claim. Specify inputs, outputs, information available at training/inference, assumptions, objective functions and complexity. State how each module addresses a specific motivation or challenge. Identify possible data leakage.

For every module record: responsibility, tensor/data shapes, public interface, algorithm or pseudocode, parameters, dependencies and verification criterion. Keep naming consistent across code, diagram and manuscript. Distinguish a new mechanism from engineering support.

Use draw_framework with explicit coordinates, short labels, readable grouping and directional edges. Save the editable JSON and PDF/SVG alongside PNG. For a more complex diagram write a reproducible Python script with matplotlib rather than flattening the design into an uneditable screenshot. Review overlaps and labels.

Prepare an ablation for each claimed necessary component. If two modules make the same causal claim, design a control that distinguishes them. Use a methodologist/reviewer child for independent criticism when the design is substantial.

draw_framework also saves a native .drawio file with editable nodes and edges. Use the same node IDs
and module names in equations, implementation and the manuscript. For complex methods build a
mapping table: concept → equation/assumptions → Python symbol → test → ablation. Search
research:atomic-decomposition and drawio:drawio-skill for further guidance; external tool names
in those references do not create new execution capabilities.
