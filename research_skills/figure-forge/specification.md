# Figure specification

All paths are workspace relative. A bundle copies inputs so `python render.py spec.json` reproduces the vector figure without PaperScientist. Requires matplotlib/numpy; no model call.

## Results

```json
{
  "type": "results", "size": [12, 7], "columns": 2,
  "title": "Evaluation", "caption": "State scope, sample unit and uncertainty here.",
  "panels": [{
    "kind": "stacked_bar", "csv": "results/outcomes.csv",
    "x": "strategy", "y": "count", "group": "outcome",
    "question": "Which strategies avoid false completion?",
    "title": "Completion outcomes", "xlabel": "Strategy", "ylabel": "Cases",
    "sample_size": 57, "n_definition": "Designed fault cases per strategy, not IID repetitions"
  }]
}
```

CSV above has columns strategy,count,outcome; provide one explicit numeric value per category/group cell. Complete all cells; do not replace unmeasured cells with zero. Supported kinds: `bar`, `stacked_bar`, `line`, `scatter`, `box`, `heatmap`. Line/scatter x values are numeric. Box uses raw repetitions by x category, without group. Heatmap uses x columns, group rows, y cell values. Error bars use `error` (existing CSV column) and `uncertainty_definition`; stacking does not support error bars. Duplicate bar/line/heatmap cells require explicit `aggregate: "sum"` or `"mean"`; compute uncertainty beforehand. Optional `annotate: false` hides bar labels. Max 6 panels, 12 groups, 30 categorical x values. Use meaningful final-size labels.

## Framework / motivating example

```json
{
  "type": "framework", "size": [12, 5], "title": "Execution and evidence",
  "caption": "Solid arrows: execution. Dashed arrows: recovery.",
  "groups": [{"id":"runtime", "label":"Runtime", "x":0,"y":0,"width":110,"height":32}],
  "nodes": [
    {"id":"plan","label":"Plan\ninputs and constraints","x":4,"y":12,"width":25,"height":12,"palette":0},
    {"id":"receipt","label":"Reconcile receipts\nintent + observed state","x":42,"y":12,"width":27,"height":12,"palette":1,"contribution":true},
    {"id":"audit","label":"Completion audit\nverify artifacts","x":80,"y":12,"width":26,"height":12,"palette":2}
  ],
  "edges": [{"source":"plan","target":"receipt"},{"source":"receipt","target":"audit"}]
}
```

Coordinates are consistent abstract units, y increases downward. Node IDs are unique. Width/height defaults 23/11; groups should enclose their nodes with room for group headings. `palette` indexes six coordinated colors; `contribution` marks a supported contribution. Edges support `label`, `feedback: true`, `curve: 0.2` (optional curvature), `source_side`/`target_side` (`west`, `east`, `north`, `south`), `waypoints: [[x,y], ...]` for routing around groups, and `label_at: [x,y]` to avoid collisions. Use concise labels. Max 60 nodes/150 edges/12 groups. Native drawio output is editable; arrange groups/edges manually if necessary and preserve the source spec. Results panels can set `integer_y: true` for count axes.
