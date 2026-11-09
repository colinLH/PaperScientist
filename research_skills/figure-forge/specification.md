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

### Faceted profiles

For repeated measurements on a **common scale and direction**, one `radar_grid` panel can fill the page with paired profiles. Pick it when the shape across several metrics matters. For precise interval estimates, use the interval chart. Supply the planned axes in scientific order, a common positive scale maximum measured from zero, and the unit. One CSV row is one measured estimate for one row facet, column facet, series and axis. For example, columns could be `detector,split,working_point,metric,rate`.

```json
{
  "type":"results", "size":[6.4,7.2],
  "panels":[{
    "kind":"radar_grid", "csv":"results/profiles.csv",
    "question":"How does the working point change detection and benign acceptance?",
    "facet_row":"detector", "facet_column":"split", "group":"working_point",
    "x":"metric", "y":"rate", "dimensions":["Attack","Benign","Tier 1","Tier 2","Tier 3"],
    "scale_max":100, "unit":"%", "column_order":["Seed 13","Seed 42","Seed 2025"],
    "series_order":["Fixed","Calibrated"]
  }]
}
```

Report the actual sample size, case unit and per-axis denominators in the specification and caption. Keep paired cases together across working points. Optional `row_order`, `column_order` and `series_order` can retain planned levels with no observations. Absent cells and blank numeric values remain unmeasured. Incomplete profiles show only recorded points; zero is an observed value. Duplicate estimates, out-of-scale values, error bars and implicit aggregation are rejected. Keep labels short. Use 3–12 spokes, at most 4 overlaid series, and up to 5 rows by 4 columns, reducing the grid when the publication width requires it.

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

## Modular method figures with GPT Image

Use `type: "framework_plate"` to storyboard 2–6 neighboring panels. Each panel uses either its own standalone `prompt` (one MicuAPI generation) or an existing session-workspace raster `asset` (offline). Give it a unique ID and a short title. Include a local paper/section locator in `source` to keep the scientific basis alongside the spec. Only the panel prompt is transmitted. Plan any editable labels and their empty space together. Coordinates for labels and for the optional zoom window are normalized to the source image, measured from the top left. The tool draws a dashed crop boundary and puts the actual enlarged region in a separate strip. Two neighbors in `links` get a vector arrow in the gutter; independent panels can omit links.

```json
{
  "type": "framework_plate", "size": [7.1, 2.8], "columns": 3,
  "panels": [
    {"id":"mail","title":"Tool return","prompt":"Wide close-up of an open ivory envelope. A rust-red address sticker covers a blue address strip on the enclosed page. No lettering.","source":"Methods, attack example"},
    {"id":"parse","title":"Typed extraction","asset":"art/parser.png","zoom":[0.60,0.25,0.92,0.60],"source":"Methods, parser"},
    {"id":"gate","title":"Policy check","prompt":"An envelope carrying an amber provenance tag stops at a red mechanical gate immediately before an empty teal outbox. Thin ink outlines on white. Leave lower left clear.","labels":[{"text":"Held","x":0.22,"y":0.82}]}
  ],
  "links":[["mail","parse"],["parse","gate"]]
}
```

Reuse a consistent palette and ink treatment in all prompts. Render only qualitative objects. Put exact labels, topology, or measured quantities in editable elements or CSV-backed results. A bundle includes normalized `parts/*.png`, editable text and connector paths in SVG/PDF, a PNG, the spec, model/asset provenance and an offline `python render.py` replay. When a subsequent panel fails, surface the error. Valid completed generations in this session can be reused when retrying the same prompt and aspect.
