"""Deterministic, standalone figure renderer. No model calls or invented data.

Copied beside each exported specification: python render.py [spec.json]
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

COLORS = ['#176390', '#af591d', '#176c5a', '#80568b', '#526077', '#937000']
FILLS = ['#c4dced', '#f5ceae', '#b8dbce', '#e0cce6', '#cdd3df', '#f0dda4']
MARKERS = ['o', 's', '^', 'D', 'v', 'P', 'X', '<', '>', '*', 'p', 'h']
INK = '#243340'
HATCHES = ['', '//', '..', 'xx', '\\\\', '++']


def _number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('Figure values must be finite')
    return result


def _rows(base, panel):
    path = (base / panel['csv']).resolve()
    if not path.is_relative_to(base.resolve()) or path.stat().st_size > 20_000_000:
        raise ValueError('CSV must be a bounded file inside the figure bundle')
    with path.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    columns = [panel.get(k) for k in ('x', 'y', 'group', 'error', 'facet_row', 'facet_column') if panel.get(k)]
    if not rows or len(rows) > 100000 or any(c not in rows[0] for c in columns):
        raise ValueError('Empty/oversized CSV or missing columns')
    for row in rows:
        if panel.get('kind') == 'radar_grid' and not row[panel['y']].strip():
            continue
        _number(row[panel['y']])
        if panel.get('error') and _number(row[panel['error']]) < 0:
            raise ValueError('Error bars must be nonnegative')
    return rows


def _wrap_label(fig, text, width_pt, fontsize, weight='normal'):
    """Wrap to a physical width using the selected typeface, including CJK text."""
    from matplotlib.font_manager import FontProperties
    renderer = fig.canvas.get_renderer()
    font = FontProperties(size=fontsize, weight=weight)
    limit = renderer.points_to_pixels(width_pt)
    def fits(line):
        return renderer.get_text_width_height_descent(line, font, ismath=False)[0] <= limit
    lines = []
    for line in str(text).split('\n'):
        while len(line) > 1 and not fits(line):
            lo, hi = 1, len(line)
            while hi - lo > 1:
                mid = (lo + hi) // 2
                if fits(line[:mid]):
                    lo = mid
                else:
                    hi = mid
            split = line.rfind(' ', 0, lo + 1)
            cut = split if split > 0 else lo
            lines.append(line[:cut].rstrip())
            line = line[cut:].lstrip()
        lines.append(line)
    return '\n'.join(lines)


def _panel(ax, panel, rows, index, series_styles, panel_width_pt, multiple):
    import numpy as np
    x, y, group = panel['x'], panel['y'], panel.get('group')
    kind = panel.get('kind', 'bar')
    if kind not in {'bar', 'stacked_bar', 'line', 'scatter', 'box', 'heatmap', 'interval'}:
        raise ValueError('Unsupported panel kind')
    categories = list(dict.fromkeys(row[x] for row in rows))
    groups = list(dict.fromkeys(row[group] for row in rows)) if group else ['Results']
    if len(groups) > 12 or (kind in {'bar', 'stacked_bar', 'box', 'heatmap', 'interval'} and len(categories) > 30):
        raise ValueError('Too many categories for a readable panel; split the figure')
    values = {}
    for row in rows:
        key = (row[group] if group else groups[0], row[x])
        values.setdefault(key, []).append(row)

    def cell(g, c):
        items = values.get((g, c), [])
        if not items:
            raise ValueError('Missing category/group cell; provide an explicit zero or use another chart')
        numbers = [_number(r[y]) for r in items]
        if len(items) > 1:
            agg = panel.get('aggregate')
            if panel.get('error') or agg not in {'mean', 'sum'}:
                raise ValueError('Duplicate cells require explicit mean/sum aggregation; precompute uncertainty separately')
            return sum(numbers) / (len(numbers) if agg == 'mean' else 1), None
        return numbers[0], _number(items[0][panel['error']]) if panel.get('error') else None

    outer_legend = bool(group and kind in {'bar', 'stacked_bar', 'line', 'scatter', 'interval'})
    heading = (f'{chr(97+index)}   ' if multiple else '') + panel.get('title', panel['question'])
    heading = _wrap_label(ax.figure, heading, panel_width_pt, 10, 'bold')
    title_pad = 6
    ax.spines[['top', 'right']].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis='x' if kind == 'interval' else 'y', color='#e2e6e8', linewidth=.5)
    if kind == 'heatmap':
        matrix = np.array([[cell(g, c)[0] for c in categories] for g in groups])
        art = ax.imshow(matrix, cmap='cividis', aspect='auto')
        ax.set_xticks(range(len(categories)), categories)
        ax.set_yticks(range(len(groups)), groups)
        ax.figure.colorbar(art, ax=ax, fraction=.035, pad=.025, label=panel.get('ylabel', y))
        for r in range(len(groups)):
            for c in range(len(categories)):
                rgb = np.array(art.cmap(art.norm(matrix[r,c]))[:3])
                linear = np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
                luminance = linear @ [.2126, .7152, .0722]
                ax.text(c, r, f'{matrix[r,c]:g}', ha='center', va='center', fontsize=8,
                        color='white' if luminance < .179 else 'black')
        ax.grid(False)
    elif kind == 'box':
        boxes = ax.boxplot([[_number(r[y]) for r in rows if r[x] == c] for c in categories],
                           patch_artist=True, tick_labels=categories, widths=.55,
                           medianprops={'color': '#243849', 'linewidth': 1.4})
        for patch in boxes['boxes']:
            patch.set_facecolor(FILLS[0])
            patch.set_edgecolor(COLORS[0])
        if group:
            raise ValueError('Box panels use raw repetitions per x; split groups into separate panels')
    else:
        bottom = np.zeros(len(categories))
        for i, g in enumerate(groups):
            styles = series_styles.setdefault(group, {})
            style = styles.setdefault(g, len(styles))
            color = COLORS[style % len(COLORS)]
            marker = MARKERS[style % len(MARKERS)]
            if kind == 'interval':
                pairs = [cell(g, c) for c in categories]
                offset = (i - (len(groups) - 1) / 2) * min(.24, .7 / len(groups))
                ax.errorbar([v for v, err in pairs], np.arange(len(categories)) + offset,
                            xerr=[err for v, err in pairs] if panel.get('error') else None,
                            fmt=marker, color=color, markersize=5, elinewidth=1.2, capsize=2, label=g)
                labels = [_wrap_label(ax.figure, c, panel_width_pt * .38, 8) for c in categories]
                ax.set_yticks(range(len(categories)), labels)
                ax.set_ylim(len(categories) - .5, -.5)
            elif kind in {'bar', 'stacked_bar'}:
                pairs = [cell(g, c) for c in categories]
                yy = np.array([p[0] for p in pairs])
                err = [p[1] for p in pairs] if panel.get('error') else None
                if kind == 'stacked_bar' and (np.any(yy < 0) or err is not None):
                    raise ValueError('Stacked bars require nonnegative values; show uncertainty in a separate panel')
                width = .7 if kind == 'stacked_bar' else .76 / len(groups)
                xx = np.arange(len(categories)) + (0 if kind == 'stacked_bar' else (i-(len(groups)-1)/2)*width)
                bars = ax.bar(xx, yy, width, bottom=bottom if kind == 'stacked_bar' else None,
                              color=FILLS[style % len(FILLS)], edgecolor=color, linewidth=.9,
                              hatch=HATCHES[style % len(HATCHES)], label=g, yerr=err, capsize=3)
                if panel.get('annotate', True):
                    ax.bar_label(bars, labels=[f'{v:g}' if v or kind!='stacked_bar' else '' for v in yy], label_type='center' if kind == 'stacked_bar' else 'edge',
                                 padding=0 if kind == 'stacked_bar' else 3, fontsize=8, color='#253744')
                bottom += yy
                ax.set_xticks(range(len(categories)), categories)
                ax.margins(y=.18)
            else:
                selected = [r for r in rows if not group or r[group] == g]
                if kind == 'line':
                    cats = sorted({r[x] for r in selected}, key=_number)
                    pairs = [cell(g, c) for c in cats]
                    xx, yy = [_number(c) for c in cats], [v[0] for v in pairs]
                    ax.errorbar(xx, yy, yerr=[v[1] for v in pairs] if panel.get('error') else None,
                                color=color, marker=marker, markersize=4,
                                linestyle=['-','--','-.',':'][style%4], linewidth=1.6, capsize=3, label=g)
                else:
                    xx = [_number(r[x]) for r in selected]
                    yy = [_number(r[y]) for r in selected]
                    if panel.get('error'):
                        ax.errorbar(xx, yy, yerr=[_number(r[panel['error']]) for r in selected],
                                    fmt='none', color=color, elinewidth=.8, capsize=2)
                    ax.scatter(xx, yy, color=color, marker=marker, s=23, alpha=.85, label=g,
                               edgecolors='white', linewidths=.3)
        if kind == 'line':
            ticks = sorted({_number(c) for c in categories})
            if len(ticks) <= 8:
                ax.set_xticks(ticks)
        if outer_legend:
            renderer = ax.figure.canvas.get_renderer()
            for cols in range(min(3,len(groups)), 0, -1):
                legend = ax.legend(frameon=False, loc='lower left', bbox_to_anchor=(0,1),
                                   borderaxespad=0, fontsize=8, ncols=cols,
                                   handlelength=1.5, handletextpad=.45, columnspacing=.9)
                bounds = legend.get_window_extent(renderer)
                if bounds.width <= renderer.points_to_pixels(panel_width_pt):
                    break
            title_pad += bounds.height / renderer.points_to_pixels(1)
    ax.set_title(heading, loc='left', pad=title_pad, weight='bold', color=INK)
    if panel.get('integer_y') and kind!='heatmap':
        from matplotlib.ticker import MaxNLocator
        (ax.xaxis if kind == 'interval' else ax.yaxis).set_major_locator(MaxNLocator(integer=True))
    if kind == 'interval':
        ax.set_xlabel(panel.get('ylabel', y))
        ax.set_ylabel(panel.get('xlabel', ''))
        ax.spines['left'].set_visible(False)
        ax.tick_params(axis='y', length=0)
    else:
        ax.set_xlabel(panel.get('xlabel', x))
    if kind not in {'heatmap', 'interval'}:
        ax.set_ylabel(panel.get('ylabel', y))
    if kind in {'bar','stacked_bar','box','heatmap'}:
        slot = panel_width_pt / len(categories)
        if slot >= 24:
            wrapped = [_wrap_label(ax.figure, c, slot * .90, 8) for c in categories]
            ax.set_xticks(ax.get_xticks(), wrapped)
        else:
            ax.tick_params(axis='x', labelrotation=40)
            for tick in ax.get_xticklabels():
                tick.set_horizontalalignment('right')
    # No autosynthetic error bars, significance stars, favorable limits or hidden runs.


def _profile_grid(fig, panel, rows):
    """Compare paired profiles on identical spokes, scales and facets without imputing cells."""
    import numpy as np
    from matplotlib.lines import Line2D

    fields = ('facet_row', 'facet_column', 'group', 'x', 'y')
    if any(not panel.get(field) for field in fields):
        raise ValueError('radar_grid needs facet_row, facet_column, group, x and y columns')
    if panel.get('aggregate') or panel.get('error'):
        raise ValueError('Use one precomputed estimate per spoke; put uncertainty in a separate panel')
    row_key, column_key, group_key, dimension_key, value_key = (panel[field] for field in fields)
    dimensions = panel.get('dimensions', [])
    if not (isinstance(dimensions, list) and 3 <= len(dimensions) <= 12
            and all(isinstance(item, str) and item.strip() for item in dimensions)
            and len(set(dimensions)) == len(dimensions)):
        raise ValueError('Declare 3–12 unique ordered dimension labels for a radar grid')
    maximum = _number(panel.get('scale_max', 0))
    if maximum <= 0 or not str(panel.get('unit', '')).strip():
        raise ValueError('Declare a common positive scale_max and unit for all spokes')
    def levels(key, order):
        observed = list(dict.fromkeys(record[key] for record in rows))
        declared = panel.get(order, observed)
        if (not isinstance(declared, list)
                or any(not isinstance(name, str) or not name.strip() for name in declared)
                or len(set(declared)) != len(declared) or not set(observed).issubset(declared)):
            raise ValueError(f'{order} must contain each observed label with no duplicates')
        return declared

    row_labels = levels(row_key, 'row_order')
    column_labels = levels(column_key, 'column_order')
    series = levels(group_key, 'series_order')
    if len(row_labels) > 5 or len(column_labels) > 4 or len(series) > 4:
        raise ValueError('Split radar grids larger than 5 rows, 4 columns or 4 series')
    values = {}
    for record in rows:
        key = tuple(record[field] for field in (row_key, column_key, group_key, dimension_key))
        if key in values or key[-1] not in dimensions:
            raise ValueError('Duplicate profile cell or undeclared radar dimension')
        raw = record[value_key].strip()
        value = _number(raw) if raw else None
        if value is not None and not 0 <= value <= maximum:
            raise ValueError('Profile estimate outside declared 0–scale_max range')
        values[key] = value
    missing = (len(values) != len(row_labels)*len(column_labels)*len(series)*len(dimensions)
               or None in values.values())
    colors = ['#536475', '#bf4e29', '#00837a', '#7653a2']
    lines = ['--', '-', '-.', ':']
    markers = ['o', 'D', '^', 's']
    ticks = np.linspace(maximum / 4, maximum, 4)
    angles = np.arange(len(dimensions)) * 2 * np.pi / len(dimensions)
    grid = fig.add_gridspec(len(row_labels)+2, len(column_labels)+1,
                            width_ratios=[.10]+[1]*len(column_labels),
                            height_ratios=[.23, .16]+[1]*len(row_labels))
    legend_ax = fig.add_subplot(grid[0, :])
    legend_ax.set_axis_off()
    handles = [Line2D([], [], color=colors[k], linestyle=lines[k], marker=markers[k], lw=1.4,
                      markerfacecolor='white' if k == 0 else colors[k], markersize=4, label=name)
               for k, name in enumerate(series)]
    legend_ax.legend(handles=handles, ncol=len(series), frameon=False, loc='center left',
                     bbox_to_anchor=(0, .75), fontsize=8, borderaxespad=0)
    scale_label = f"Scale  0–{maximum:g} {panel['unit']}   ·   Rings  " + ' / '.join(f'{t:g}' for t in ticks)
    if missing:
        scale_label += '   ·   Incomplete profiles show observed points only'
    legend_ax.text(0, .05, _wrap_label(fig, scale_label, fig.get_figwidth()*72-18, 8),
                   color=INK, va='center', fontsize=8)
    for col, label in enumerate(column_labels):
        header = fig.add_subplot(grid[1, col+1])
        header.set_facecolor('#e8edf0')
        header.set_xticks([])
        header.set_yticks([])
        header.spines[:].set_visible(False)
        header.text(.5, .5, label, ha='center', va='center', weight='bold', fontsize=9)
    for i, label in enumerate(row_labels):
        side = fig.add_subplot(grid[i+2, 0])
        side.set_facecolor('#e8edf0')
        side.set_xticks([])
        side.set_yticks([])
        side.spines[:].set_visible(False)
        side.text(.5, .5, label, rotation=90, ha='center', va='center', weight='bold', fontsize=8)
        for j, column in enumerate(column_labels):
            ax = fig.add_subplot(grid[i+2, j+1], projection='polar')
            ax.set_theta_zero_location('N')
            ax.set_theta_direction(-1)
            ax.set_xticks(angles, dimensions, fontsize=8)
            ax.tick_params(axis='x', pad=1)
            ax.set_ylim(0, maximum)
            ax.set_yticks(ticks, ['']*len(ticks))
            ax.spines['polar'].set_edgecolor('#a2b1b9')
            ax.grid(color='#c7cfd4', lw=.55)
            ax.set_facecolor('#fbfcfc')
            if all(values.get((label, column, name, d)) is None for name in series for d in dimensions):
                ax.text(.5, .5, 'No observations', transform=ax.transAxes, ha='center', va='center',
                        fontsize=8, bbox={'facecolor': 'white', 'edgecolor': 'none', 'pad': 2})
            for k, name in enumerate(series):
                points = [values.get((label, column, name, d)) for d in dimensions]
                style = dict(color=colors[k], marker=markers[k], markersize=4 if k == 0 else 2.7,
                             markerfacecolor='white' if k == 0 else colors[k], linewidth=1.25,
                             clip_on=False)
                if None in points:
                    ax.plot(angles, [float('nan') if v is None else v for v in points],
                            linestyle='none', **style)
                else:
                    loop = np.r_[angles, angles[0]]
                    radial = [*points, points[0]]
                    ax.fill(loop, radial, color=colors[k], alpha=.11)
                    ax.plot(loop, radial, linestyle=lines[k], **style)


def _cell_grid(node):
    """One header plus rectangular data cells. Accent coordinates use zero-based row, column."""
    rows = node.get('cells', [])
    if not isinstance(rows, list) or len(rows) > 12:
        raise ValueError('cells must be a rectangular table of at most 12 rows')
    if rows and (not isinstance(rows[0], list) or not 1 <= len(rows[0]) <= 10):
        raise ValueError('A table requires 1–10 columns')
    if any(not isinstance(row, list) or len(row) != len(rows[0])
           or any(not isinstance(v, str) or '\n' in v for v in row) for row in rows):
        raise ValueError('Each row in cells must contain the same number of single-line strings')
    accents = node.get('accent_cells', [])
    if not isinstance(accents, list):
        raise ValueError('accent_cells must be a list of cell coordinates')
    for pair in accents:
        if (not isinstance(pair, list) or len(pair) != 2 or any(type(n) is not int for n in pair)
                or not 0 <= pair[0] < len(rows) or not 0 <= pair[1] < len(rows[0])):
            raise ValueError('accent_cells coordinate outside table')
    return rows, {tuple(pair) for pair in accents}


def _mechanism_layout(fig, nodes, groups, font):
    """Position ordered stages and same-row branches at a scale close to physical points."""
    if not groups:
        raise ValueError('mechanism layout requires at least one stage in groups')
    by_group = {g['id']: {} for g in groups}
    for node in nodes:
        if node.get('group') not in by_group:
            raise ValueError('Every mechanism node must refer to an existing group')
        rows = by_group[node['group']]
        index = node.get('row', max(rows, default=-1) + 1)
        if type(index) is not int or index < 0:
            raise ValueError('row must be a nonnegative integer')
        rows.setdefault(index, []).append(node)
    col_gap, branch_gap, inset = 12, 9, 5
    total_width = fig.get_figwidth() * 72 - 14
    col_width = (total_width - (len(groups)-1) * col_gap) / len(groups)
    row_height = font * 1.70
    stages, placed = [], []
    for i, g in enumerate(groups):
        x = i * (col_width + col_gap)
        y = font * 2.4
        rows = by_group[g['id']]
        if not rows:
            raise ValueError('Every mechanism group needs a node')
        for _, peers in sorted(rows.items()):
            width = (col_width - 2 * inset - (len(peers)-1)*branch_gap)/len(peers)
            if width <= font * 3:
                raise ValueError('Too many nodes in one branch row at this figure width')
            heights = []
            for j, node in enumerate(peers):
                cells, _ = _cell_grid(node)
                lines = _wrap_label(fig, node.get('label',''), width - 8, font, 'bold').count('\n') + 1
                if cells and lines > 1:
                    raise ValueError(f"Shorten table title in node {node['id']}")
                height = (len(cells) + lines) * row_height + (0 if cells else 3)
                placed.append({**node, 'x':x+inset+j*(width+branch_gap), 'y':y,
                               'width':width,'height':height,'palette':node.get('palette',g.get('palette',i))})
                heights.append(height)
            y += max(heights) + branch_gap
        stages.append({**g,'x':x,'y':0,'width':col_width,'height':y-branch_gap+inset,
                       'palette':g.get('palette',i)})
    return placed, stages


def _framework_table(fig, ax, item, ident, root, scale, font):
    from matplotlib.patches import Rectangle

    rows, accents = _cell_grid(item)
    x, y, w, h = (item[k] for k in ('x','y','width','height'))
    rh = h/(len(rows)+1)
    palette = int(item.get('palette',0)) % len(COLORS)
    for row_no, values in enumerate([[item.get('label','')], *rows]):
        cw = w/len(values)
        for col, value in enumerate(values):
            left, top = x+cw*col, y+rh*row_no
            header = row_no == 0
            accent = (row_no-1,col) in accents
            fill = FILLS[palette] if header or accent else 'white'
            border = COLORS[palette] if accent else '#a6b4bd'
            weight = 'bold' if header or accent else 'normal'
            ax.add_patch(Rectangle((left,top),cw,rh,facecolor=fill,edgecolor=border,linewidth=.65,zorder=3))
            text = ax.text(left+cw/2,top+rh/2,value,va='center',ha='center',fontsize=font,weight=weight,
                           parse_math=False, zorder=4,color=INK)
            p0, p1 = ax.transData.transform([(left,top),(left+cw,top+rh)])
            box = text.get_window_extent(fig.canvas.get_renderer())
            if box.width+2 > abs(p1[0]-p0[0]) or box.height+1 > abs(p1[1]-p0[1]):
                raise ValueError(f"Cell text does not fit node {item['id']} at final size: {value!r}")
            drawio_font = font * cw * scale / ((p1[0]-p0[0])*72/fig.dpi)
            cell = ET.SubElement(root,'mxCell',id=f'cell:{ident}:{row_no}:{col}',parent=ident,vertex='1',value=value,
                    style=f'html=0;whiteSpace=wrap;fillColor={fill};strokeColor={border};fontSize={drawio_font:.2f};fontStyle={int(weight=="bold")};')
            ET.SubElement(cell,'mxGeometry',x=str(cw*col*scale),y=str(rh*row_no*scale),
                          width=str(cw*scale),height=str(rh*scale),attrib={'as':'geometry'})


def _framework(fig, spec, target):
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
    nodes, groups, edges = spec['nodes'], spec.get('groups', []), spec.get('edges', [])
    if not 1 <= len(nodes) <= 60 or len(edges) > 150 or len(groups) > 12:
        raise ValueError('Framework limit: 60 nodes, 150 edges, 12 groups')
    ids = {str(n['id']): n for n in nodes}
    if len({str(g['id']) for g in groups}) != len(groups) or len(ids) != len(nodes) or any(str(e[k]) not in ids for e in edges for k in ('source','target')):
        raise ValueError('Duplicate node IDs or dangling framework edge')
    compact = spec.get('layout') == 'mechanism'
    structured = compact or any('cells' in node for node in nodes)
    font = max(7.5, _number(spec.get('minimum_font_pt', 7))) if structured else 7.5
    if compact:
        nodes, groups = _mechanism_layout(fig, nodes, groups, font)
        ids = {str(n['id']): n for n in nodes}
        if 'size' not in spec or spec.get('fit_height'):
            label_height = sum(t.get_window_extent().height*72/fig.dpi + 2 for t in fig.texts)
            natural = (max(g['height'] for g in groups) + 14 + label_height)/72
            # A contract-provided size bounds the drawing, even when its height is implicit.
            height_limit = fig.get_figheight() if 'size' in spec else 16
            fig.set_figheight(max(.75, min(height_limit, natural)))
    scale = 4/3 if compact else 10
    tables = []
    ax = fig.add_subplot(111)
    ax.set_aspect('equal', anchor='N' if compact else 'C'); ax.axis('off')
    doc = ET.Element('mxfile', host='PaperScientist')
    root = ET.SubElement(ET.SubElement(ET.SubElement(doc, 'diagram', name=spec.get('title','Framework')),'mxGraphModel'),'root')
    ET.SubElement(root,'mxCell',id='0');ET.SubElement(root,'mxCell',id='1',parent='0')
    bounds = []
    labels = []
    for i, item in enumerate([*groups, *nodes]):
        is_group = i < len(groups)
        w, h = _number(item.get('width', 23)), _number(item.get('height', 11))
        x, y = _number(item['x']), _number(item['y'])
        if min(w,h) <= 0 or len(item.get('label','')) > 300:
            raise ValueError('Invalid box geometry or excessively long label')
        bounds += [(x,y),(x+w,y+h)]
        color_idx = int(item.get('palette',0)) % len(COLORS)
        fill, color = '#f0f3f5', '#80919d'
        if is_group:
            fill, color = '#fafbfc', COLORS[color_idx] if compact else '#bcc7ce'
        elif item.get('contribution') or 'palette' in item:
            fill, color = FILLS[color_idx], COLORS[color_idx]
        label = str(item.get('label',''))
        weight = 'bold' if is_group or item.get('contribution') else 'normal'
        line_width = 1.8 if item.get('contribution') else .8
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0,rounding_size=.7',
                                   linewidth=line_width,edgecolor=color,facecolor=fill,
                                   linestyle='--' if is_group else '-',zorder=0 if is_group else 3))
        ident = ('g' if is_group else 'n')+str(item['id'])
        grid = [] if is_group else _cell_grid(item)[0]
        if grid:
            tables.append(({**item, 'x':x,'y':y,'width':w,'height':h},ident))
        else:
            labels.append((x,y,w,h,label,is_group,weight))
        cell = ET.SubElement(root,'mxCell',id=ident,parent='1',vertex='1',value='' if grid else label,
                             style=f'rounded=1;whiteSpace=wrap;html=0;fillColor={fill};strokeColor={color};strokeWidth={line_width};fontSize={font*4/3 if compact else 13:g};fontStyle={int(weight=="bold")};'+('dashed=1;verticalAlign=top;align=left;' if is_group else ''))
        ET.SubElement(cell,'mxGeometry',x=str(x*scale),y=str(y*scale),width=str(w*scale),height=str(h*scale),attrib={'as':'geometry'})
    for i,e in enumerate(edges):
        a,b = ids[str(e['source'])],ids[str(e['target'])]
        ax0,ay0,bx,by = (float(a['x']),float(a['y']),float(b['x']),float(b['y']))
        aw,ah,bw,bh = (float(a.get('width',23)),float(a.get('height',11)),float(b.get('width',23)),float(b.get('height',11)))
        if abs((bx+bw/2)-(ax0+aw/2)) > abs((by+bh/2)-(ay0+ah/2)):
            start=(ax0+aw if bx>ax0 else ax0,ay0+ah/2);end=(bx if bx>ax0 else bx+bw,by+bh/2)
        else:
            start=(ax0+aw/2,ay0+ah if by>ay0 else ay0);end=(bx+bw/2,by if by>ay0 else by+bh)
        def port(box, side, default):
            x,y,w,h=box
            return {'west':(x,y+h/2),'east':(x+w,y+h/2),'north':(x+w/2,y),'south':(x+w/2,y+h)}.get(side,default)
        start=port((ax0,ay0,aw,ah),e.get('source_side'),start)
        end=port((bx,by,bw,bh),e.get('target_side'),end)
        waypoints=[tuple(map(_number,p)) for p in e.get('waypoints',[])]
        if len(waypoints)>20 or any(len(p)!=2 for p in waypoints):raise ValueError('Invalid edge waypoints')
        path=None
        if waypoints:
            from matplotlib.path import Path as MplPath
            path=MplPath([start,*waypoints,end]);bounds.extend(waypoints)
        arrow_style=dict(arrowstyle='-|>',mutation_scale=11,linewidth=1.1,color='#496777',
                         linestyle='--' if e.get('feedback') else '-',zorder=2)
        arrow=(FancyArrowPatch(start,end,connectionstyle='arc3,rad='+str(_number(e.get('curve',0))),**arrow_style)
               if path is None else FancyArrowPatch(path=path,**arrow_style))
        ax.add_patch(arrow)
        if e.get('label'):
            lx,ly=map(_number,e.get('label_at',[(start[0]+end[0])/2,(start[1]+end[1])/2-1]))
            ax.text(lx,ly,str(e['label']),fontsize=font if structured else 7,
                    ha='center',color='#38596b',bbox={'facecolor':'white','edgecolor':'none','pad':1},zorder=5)
        ports={'west':(0,.5),'east':(1,.5),'north':(.5,0),'south':(.5,1)}
        style='edgeStyle=orthogonalEdgeStyle;endArrow=block;html=0;'+('dashed=1;' if e.get('feedback') else '')
        for key,prefix in [('source_side','exit'),('target_side','entry')]:
            if e.get(key) in ports:
                x,y=ports[e[key]];style+=f'{prefix}X={x};{prefix}Y={y};'
        cell=ET.SubElement(root,'mxCell',id=f'e{i}',parent='1',edge='1',source='n'+str(e['source']),target='n'+str(e['target']),value=str(e.get('label','')),style=style)
        geom=ET.SubElement(cell,'mxGeometry',relative='1',attrib={'as':'geometry'})
        if waypoints:
            points=ET.SubElement(geom,'Array',attrib={'as':'points'})
            for x,y in waypoints:ET.SubElement(points,'mxPoint',x=str(x*scale),y=str(y*scale))
    ax.set_xlim(min(x for x,y in bounds)-2,max(x for x,y in bounds)+2)
    ax.set_ylim(max(y for x,y in bounds)+2,min(y for x,y in bounds)-2)
    fig.canvas.draw()
    for x,y,w,h,label,is_group,weight in labels:
        left, right = ax.transData.transform([(x,y),(x+w,y)])
        width_pt = max(1, (right[0] - left[0]) * 72 / fig.dpi - 7)
        fontsize = (max(font,8) if is_group else font) if compact else max(font if structured else 0, 9 if is_group else 8.5)
        wrapped = _wrap_label(fig, label, width_pt, fontsize, weight)
        artist = ax.text(x+1.3 if is_group else x+w/2,y+1.2 if is_group else y+h/2,wrapped,
                fontsize=fontsize,weight=weight,ha='left' if is_group else 'center',
                va='top' if is_group else 'center',color=INK,zorder=4)
        if compact:
            box = artist.get_window_extent(fig.canvas.get_renderer())
            height = h if not is_group else font*2.2
            p0, p1 = ax.transData.transform([(x,y),(x+w,y+height)])
            if box.width+1 > abs(p1[0]-p0[0]) or box.height+1 > abs(p1[1]-p0[1]):
                raise ValueError(f'Shorten framework label at final size: {label!r}')
    for item, ident in tables:
        _framework_table(fig, ax, item, ident, root, scale, font)
    ET.ElementTree(doc).write(target/'figure.drawio',encoding='utf-8',xml_declaration=True)


def render_document(spec, base, target):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    base,target = Path(base),Path(target)
    available={f.name for f in font_manager.fontManager.ttflist}
    fonts=[n for n in ['DejaVu Sans','Noto Sans CJK SC','Microsoft YaHei','PingFang SC','Heiti SC','Arial Unicode MS'] if n in available]
    panels=spec.get('panels',[])
    if spec['type']=='results' and not 1<=len(panels)<=6:
        raise ValueError('Use 1–6 panels answering distinct questions')
    profile_panels = [p for p in panels if p.get('kind') == 'radar_grid']
    if profile_panels and (len(panels) != 1 or not spec.get('size')):
        raise ValueError('A radar grid occupies the whole figure; use a single panel and specify its final size')
    default_width = 3.55 if spec['type']=='results' and len(panels)==1 else 7.1
    width = _number(spec['size'][0]) if 'size' in spec else default_width
    cols = min(len(panels) or 1, 3, max(1, int(spec.get('columns', 2 if width >= 6 else 1))))
    default_height = 2.4 * math.ceil(len(panels) / cols) + .75 if panels else 3.8
    width,height=map(_number,spec.get('size',[default_width,default_height]))
    min_height = .75 if spec['type']=='framework' and spec.get('layout')=='mechanism' else 2
    if not 3<=width<=20 or not min_height<=height<=16:
        raise ValueError(f'Figure size must fit 3–20 × {min_height:g}–16 inches')
    target.mkdir(parents=True,exist_ok=True)
    style={'font.family':fonts,'font.size':9,'axes.titlesize':10,'text.color':INK,
           'axes.labelsize':9,'axes.labelcolor':INK,'axes.edgecolor':'#80919d','axes.linewidth':.7,
           'xtick.color':INK,'ytick.color':INK,'xtick.labelsize':8,
           'ytick.labelsize':8,'svg.fonttype':'none','pdf.fonttype':42,'text.usetex':False,'savefig.facecolor':'white'}
    with plt.rc_context(style):
        fig=plt.figure(figsize=(width,height),layout='constrained')
        try:
            text_width = width * 72 - 16
            min_font = _number(spec.get('minimum_font_pt', 7)) if spec['type']=='framework' else 7
            title_font, caption_font = max(11,min_font), max(8,min_font)
            if spec.get('title'):
                fig.suptitle(_wrap_label(fig,spec['title'],text_width,title_font,'bold'),
                             x=.02,ha='left',fontsize=title_font,weight='bold')
            if spec.get('caption'):
                fig.supxlabel(_wrap_label(fig,spec['caption'],text_width,caption_font),
                              x=.02,ha='left',fontsize=caption_font,color='#495963')
            if spec['type']=='framework':
                _framework(fig,spec,target)
            elif spec['type']=='results' and profile_panels:
                panel = profile_panels[0]
                if not panel.get('question'):
                    raise ValueError('Every panel needs a scientific question')
                _profile_grid(fig, panel, _rows(base, panel))
            elif spec['type']=='results':
                axes=fig.subplots(math.ceil(len(panels)/cols),cols,squeeze=False).flat
                series_styles = {}
                panel_width = width * 72 / cols - 40
                for i,ax in enumerate(axes):
                    if i>=len(panels):ax.remove();continue
                    if not panels[i].get('question'):raise ValueError('Every panel needs a scientific question')
                    _panel(ax,panels[i],_rows(base,panels[i]),i,series_styles,panel_width,len(panels)>1)
            else:
                raise ValueError('type must be framework or results')
            for ext in ('png','pdf','svg'):fig.savefig(target/f'figure.{ext}',dpi=300)
        finally:
            plt.close(fig)


if __name__=='__main__':
    import sys
    path=Path(sys.argv[1] if len(sys.argv)>1 else Path(__file__).with_name('spec.json')).resolve()
    render_document(json.loads(path.read_text(encoding='utf-8')),path.parent,path.parent)
