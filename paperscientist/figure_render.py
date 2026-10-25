"""Deterministic, standalone figure renderer. No model calls or invented data.

Copied beside each exported specification: python render.py [spec.json]
"""
from __future__ import annotations

import csv
import json
import math
import textwrap
from pathlib import Path
import xml.etree.ElementTree as ET

COLORS = ['#287d8e', '#d38a42', '#75649d', '#519c87', '#c16b72', '#577da5']
FILLS = ['#e8f3f4', '#fbf0df', '#efebf6', '#e9f4eb', '#faecee', '#eaf0f8']
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


def _panel(ax, panel, rows, index):
    import numpy as np
    x, y, group = panel['x'], panel['y'], panel.get('group')
    kind = panel.get('kind', 'bar')
    if kind not in {'bar', 'stacked_bar', 'line', 'scatter', 'box', 'heatmap'}:
        raise ValueError('Unsupported panel kind')
    categories = list(dict.fromkeys(row[x] for row in rows))
    groups = list(dict.fromkeys(row[group] for row in rows)) if group else ['Results']
    if len(groups) > 12 or (kind in {'bar', 'stacked_bar', 'box', 'heatmap'} and len(categories) > 30):
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

    outer_legend = bool(group and kind in {'bar', 'stacked_bar', 'line', 'scatter'})
    ax.set_title(f"({chr(97+index)}) " + panel.get('title', panel['question']), loc='left', pad=42, weight='semibold')
    ax.spines[['top', 'right']].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis='y', color='#dce2e7', linewidth=.6, alpha=.75)
    if kind == 'heatmap':
        matrix = np.array([[cell(g, c)[0] for c in categories] for g in groups])
        art = ax.imshow(matrix, cmap='YlGnBu', aspect='auto')
        ax.set_xticks(range(len(categories)), categories)
        ax.set_yticks(range(len(groups)), groups)
        ax.figure.colorbar(art, ax=ax, fraction=.035, pad=.025, label=panel.get('ylabel', y))
        for r in range(len(groups)):
            for c in range(len(categories)):
                ax.text(c, r, f'{matrix[r,c]:g}', ha='center', va='center', fontsize=8,
                        color='white' if art.norm(matrix[r,c]) > .55 else '#1f3040')
        ax.grid(False)
    elif kind == 'box':
        boxes = ax.boxplot([[_number(r[y]) for r in rows if r[x] == c] for c in categories],
                           patch_artist=True, tick_labels=categories, widths=.55,
                           medianprops={'color': '#243849', 'linewidth': 1.4})
        for i, patch in enumerate(boxes['boxes']):
            patch.set_facecolor(FILLS[i % len(FILLS)])
            patch.set_edgecolor(COLORS[i % len(COLORS)])
        if group:
            raise ValueError('Box panels use raw repetitions per x; split groups into separate panels')
    else:
        bottom = np.zeros(len(categories))
        for i, g in enumerate(groups):
            color = COLORS[i % len(COLORS)]
            if kind in {'bar', 'stacked_bar'}:
                pairs = [cell(g, c) for c in categories]
                yy = np.array([p[0] for p in pairs])
                err = [p[1] for p in pairs] if panel.get('error') else None
                if kind == 'stacked_bar' and (np.any(yy < 0) or err is not None):
                    raise ValueError('Stacked bars require nonnegative values; show uncertainty in a separate panel')
                width = .7 if kind == 'stacked_bar' else .76 / len(groups)
                xx = np.arange(len(categories)) + (0 if kind == 'stacked_bar' else (i-(len(groups)-1)/2)*width)
                bars = ax.bar(xx, yy, width, bottom=bottom if kind == 'stacked_bar' else None,
                              color=FILLS[i % len(FILLS)], edgecolor=color, linewidth=.9,
                              hatch=HATCHES[i % len(HATCHES)], label=g, yerr=err, capsize=3)
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
                                color=color, marker=['o','s','^','D','v','P'][i%6], markersize=4,
                                linestyle=['-','--','-.',':'][i%4], linewidth=1.6, capsize=3, label=g)
                    if len(cats)<=12:ax.set_xticks(xx)
                else:
                    ax.scatter([_number(r[x]) for r in selected], [_number(r[y]) for r in selected],
                               color=color, s=23, alpha=.8, label=g, edgecolors='white', linewidths=.3)
        if group:
            if outer_legend:
                ax.legend(frameon=False, loc='lower left',bbox_to_anchor=(0,1.015),borderaxespad=0,fontsize=8,ncols=min(3,len(groups)))
            else:
                ax.legend(frameon=False, loc='best', fontsize=8, ncols=min(3,len(groups)))
    if panel.get('integer_y') and kind!='heatmap':
        from matplotlib.ticker import MaxNLocator
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_xlabel(panel.get('xlabel', x))
    if kind != 'heatmap':
        ax.set_ylabel(panel.get('ylabel', y))
    if len(categories) > 6 and kind in {'bar','stacked_bar','box','heatmap'}:
        ax.tick_params(axis='x', labelrotation=25)
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
    for i, item in enumerate([*groups, *nodes]):
        is_group = i < len(groups)
        w, h = _number(item.get('width', 23)), _number(item.get('height', 11))
        x, y = _number(item['x']), _number(item['y'])
        if min(w,h) <= 0 or len(item.get('label','')) > 300:
            raise ValueError('Invalid box geometry or excessively long label')
        bounds += [(x,y),(x+w,y+h)]
        color_idx = int(item.get('palette',i)) % len(COLORS)
        fill = '#f8fafb' if is_group else FILLS[color_idx]
        color = '#aebbc5' if is_group else COLORS[color_idx]
        label = str(item.get('label',''))
        label = ('★ ' if item.get('contribution') else '') + label
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0,rounding_size=.7',
                                   linewidth=.8 if is_group else 1.1,edgecolor=color,facecolor=fill,
                                   linestyle='--' if is_group else '-',zorder=0 if is_group else 3))
        fontsize = 10.5 if is_group else 10
        wrapped = '\n'.join(textwrap.fill(line,width=max(12,int(w*1.25))) for line in label.splitlines())
        ax.text(x+1.3 if is_group else x+w/2,y+2 if is_group else y+h/2,wrapped,
                fontsize=fontsize,weight='semibold' if is_group or item.get('contribution') else 'normal',
                ha='left' if is_group else 'center',va='top' if is_group else 'center',color='#233c4a',zorder=4)
        ident = ('g' if is_group else 'n')+str(item['id'])
        cell = ET.SubElement(root,'mxCell',id=ident,parent='1',vertex='1',value=label,
                             style=f'rounded=1;whiteSpace=wrap;html=0;fillColor={fill};strokeColor={color};fontSize=13;'+('dashed=1;verticalAlign=top;align=left;' if is_group else ''))
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
    ET.ElementTree(doc).write(target/'figure.drawio',encoding='utf-8',xml_declaration=True)


def render_document(spec, base, target):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    base,target = Path(base),Path(target)
    available={f.name for f in font_manager.fontManager.ttflist}
    fonts=[n for n in ['Microsoft YaHei','Noto Sans CJK SC','DejaVu Sans'] if n in available]
    width,height=map(_number,spec.get('size',[12,6]))
    if not 3<=width<=20 or not 2<=height<=16:
        raise ValueError('Figure size must fit 3–20 × 2–16 inches')
    panels=spec.get('panels',[])
    if spec['type']=='results' and not 1<=len(panels)<=6:
        raise ValueError('Use 1–6 panels answering distinct questions')
    target.mkdir(parents=True,exist_ok=True)
    style={'font.family':'sans-serif','font.sans-serif':fonts,'font.size':9,'axes.titlesize':10,
           'axes.labelsize':9,'axes.edgecolor':'#8796a2','axes.linewidth':.7,'xtick.labelsize':8,
           'ytick.labelsize':8,'svg.fonttype':'none','pdf.fonttype':42,'text.usetex':False,'savefig.facecolor':'white'}
    with plt.rc_context(style):
        fig=plt.figure(figsize=(width,height),layout='constrained')
        try:
            if spec['type']=='framework':
                _framework(fig,spec,target)
            elif spec['type']=='results':
                cols=min(3,max(1,int(spec.get('columns',2))))
                axes=fig.subplots(math.ceil(len(panels)/cols),cols,squeeze=False).flat
                for i,ax in enumerate(axes):
                    if i>=len(panels):ax.remove();continue
                    if not panels[i].get('question'):raise ValueError('Every panel needs a scientific question')
                    _panel(ax,panels[i],_rows(base,panels[i]),i)
            else:
                raise ValueError('type must be framework or results')
            if spec.get('title'):fig.suptitle(spec['title'],fontsize=12,weight='semibold')
            if spec.get('caption'):fig.supxlabel(textwrap.fill(spec['caption'],160),fontsize=8,color='#435460')
            for ext in ('png','pdf','svg'):fig.savefig(target/f'figure.{ext}',dpi=300)
        finally:
            plt.close(fig)


if __name__=='__main__':
    import sys
    path=Path(sys.argv[1] if len(sys.argv)>1 else Path(__file__).with_name('spec.json')).resolve()
    render_document(json.loads(path.read_text(encoding='utf-8')),path.parent,path.parent)
