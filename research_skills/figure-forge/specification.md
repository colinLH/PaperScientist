# Figure specification

All paths are workspace relative. For results and frameworks the bundle copies inputs so `python render.py spec.json` reproduces the vector figure with Matplotlib/NumPy. Generated illustrations retain the exported image and generation settings.

## Results

```json
{
  "type": "results", "size": [3.55, 3.25],
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

CSV above has columns strategy,count,outcome; provide one explicit numeric value per category/group cell. Complete all cells; do not replace unmeasured cells with zero. Supported kinds: `bar`, `stacked_bar`, `line`, `scatter`, `box`, `heatmap` and `interval`. Line/scatter x values are numeric. Box uses raw repetitions by x category, without group. Heatmap uses x columns, group rows, y cell values. Error bars use `error` (existing CSV column) and `uncertainty_definition`; stacking does not support error bars. Duplicate bar/line/heatmap cells require explicit `aggregate: "sum"` or `"mean"`; compute uncertainty beforehand. Optional `annotate: false` hides bar labels. Max 6 panels, 12 groups, 30 categorical x values. Use meaningful final-size labels.

For horizontal dot-and-interval comparisons, use `{"kind":"interval", "x":"condition", "y":"estimate", "group":"method", "error":"half_width", "ylabel":"Detection rate (%)", "uncertainty_definition":"Half-width of the stated interval from the source CSV"}` inside a panel with its question, CSV and sample fields. Each CSV row supplies the center and optionally a nonnegative, symmetric half-width. Categories are on the vertical axis; `ylabel` labels the horizontal value axis. Omit `error` for a point-only display. Give asymmetric bounds or raw distributions their own plotting specification or script.

Set `size` in inches at the intended publication width. A single panel uses the whole available grid. At a narrow width, multiple panels stack by default; use explicit `columns` only if the labels and data still fit.

## Framework / motivating example

```json
{
  "type": "framework", "size": [7.1, 3], "title": "Execution and evidence",
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


## Conceptual illustration

```json
{
  "type": "illustration",
  "size": [3.55, 2.6],
  "prompt": "Explain the approval boundary in a tool-using assistant. Read left to right. A neutral document submits a tool request to a blue outlined checkpoint. Beyond it, a tool receives an approved request. The only arrows are document to checkpoint and checkpoint to tool. Use these three exact labels: Request, Approval, Tool. White background with generous space between objects."
}
```

The `prompt` is sent to the configured MicuAPI service. Omit private session material and credentials. Add `manuscript` and `figure_scope` for a layout-bound export. The output contains `figure.png` and a `figure.pdf` with the specified physical page size, plus the spec and generation record. Keep the PNG for exact reuse. Compare labels, count, arrow direction and the depicted mechanism against the source method before inclusion. Use a results spec and source CSV for plots with measured axes, counts or uncertainty.
