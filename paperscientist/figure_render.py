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
    columns = [panel.get(k) for k in ('x', 'y', 'group', 'error') if panel.get(k)]
    if not rows or len(rows) > 100000 or any(c not in rows[0] for c in columns):
        raise ValueError('Empty/oversized CSV or missing columns')
    for row in rows:
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


def _framework(fig, spec, target):
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
    nodes, groups, edges = spec['nodes'], spec.get('groups', []), spec.get('edges', [])
    if not 1 <= len(nodes) <= 60 or len(edges) > 150 or len(groups) > 12:
        raise ValueError('Framework limit: 60 nodes, 150 edges, 12 groups')
    ids = {str(n['id']): n for n in nodes}
    if len({str(g['id']) for g in groups}) != len(groups) or len(ids) != len(nodes) or any(str(e[k]) not in ids for e in edges for k in ('source','target')):
        raise ValueError('Duplicate node IDs or dangling framework edge')
    ax = fig.add_subplot(111)
    ax.set_aspect('equal'); ax.axis('off')
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
            fill, color = '#fafbfc', '#bcc7ce'
        elif item.get('contribution') or 'palette' in item:
            fill, color = FILLS[color_idx], COLORS[color_idx]
        label = str(item.get('label',''))
        weight = 'bold' if is_group or item.get('contribution') else 'normal'
        line_width = 1.8 if item.get('contribution') else .8
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0,rounding_size=.7',
                                   linewidth=line_width,edgecolor=color,facecolor=fill,
                                   linestyle='--' if is_group else '-',zorder=0 if is_group else 3))
        labels.append((x,y,w,h,label,is_group,weight))
        ident = ('g' if is_group else 'n')+str(item['id'])
        cell = ET.SubElement(root,'mxCell',id=ident,parent='1',vertex='1',value=label,
                             style=f'rounded=1;whiteSpace=wrap;html=0;fillColor={fill};strokeColor={color};strokeWidth={line_width};fontSize=13;fontStyle={int(weight=="bold")};'+('dashed=1;verticalAlign=top;align=left;' if is_group else ''))
        ET.SubElement(cell,'mxGeometry',x=str(x*10),y=str(y*10),width=str(w*10),height=str(h*10),attrib={'as':'geometry'})
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
            ax.text(lx,ly,str(e['label']),fontsize=7,
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
            for x,y in waypoints:ET.SubElement(points,'mxPoint',x=str(x*10),y=str(y*10))
    ax.set_xlim(min(x for x,y in bounds)-2,max(x for x,y in bounds)+2)
    ax.set_ylim(max(y for x,y in bounds)+2,min(y for x,y in bounds)-2)
    fig.canvas.draw()
    for x,y,w,h,label,is_group,weight in labels:
        left, right = ax.transData.transform([(x,y),(x+w,y)])
        width_pt = max(1, (right[0] - left[0]) * 72 / fig.dpi - 7)
        fontsize = 9 if is_group else 8.5
        wrapped = _wrap_label(fig, label, width_pt, fontsize, weight)
        ax.text(x+1.3 if is_group else x+w/2,y+1.2 if is_group else y+h/2,wrapped,
                fontsize=fontsize,weight=weight,ha='left' if is_group else 'center',
                va='top' if is_group else 'center',color=INK,zorder=4)
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
    default_width = 3.55 if spec['type']=='results' and len(panels)==1 else 7.1
    width = _number(spec['size'][0]) if 'size' in spec else default_width
    cols = min(len(panels) or 1, 3, max(1, int(spec.get('columns', 2 if width >= 6 else 1))))
    default_height = 2.4 * math.ceil(len(panels) / cols) + .75 if panels else 3.8
    width,height=map(_number,spec.get('size',[default_width,default_height]))
    if not 3<=width<=20 or not 2<=height<=16:
        raise ValueError('Figure size must fit 3–20 × 2–16 inches')
    target.mkdir(parents=True,exist_ok=True)
    style={'font.family':fonts,'font.size':9,'axes.titlesize':10,'text.color':INK,
           'axes.labelsize':9,'axes.labelcolor':INK,'axes.edgecolor':'#80919d','axes.linewidth':.7,
           'xtick.color':INK,'ytick.color':INK,'xtick.labelsize':8,
           'ytick.labelsize':8,'svg.fonttype':'none','pdf.fonttype':42,'text.usetex':False,'savefig.facecolor':'white'}
    with plt.rc_context(style):
        fig=plt.figure(figsize=(width,height),layout='constrained')
        try:
            text_width = width * 72 - 16
            if spec.get('title'):
                fig.suptitle(_wrap_label(fig,spec['title'],text_width,11,'bold'),
                             x=.02,ha='left',fontsize=11,weight='bold')
            if spec.get('caption'):
                fig.supxlabel(_wrap_label(fig,spec['caption'],text_width,8),
                              x=.02,ha='left',fontsize=8,color='#495963')
            if spec['type']=='framework':
                _framework(fig,spec,target)
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
