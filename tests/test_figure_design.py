import numpy as np
import pytest

from paperscientist import figure_render


def test_interval_marks_and_supplied_errors_keep_identity_across_panels():
    import matplotlib.pyplot as plt

    panel = dict(kind='interval', title='Method comparison', question='Which procedure varies?',
                 x='method', y='estimate', group='system', error='half_width', ylabel='Rate (%)')
    rows = [dict(method='Direct', system='A', estimate='16', half_width='2'),
            dict(method='Direct', system='B', estimate='12', half_width='1')]
    fig, axes = plt.subplots(1, 2)
    try:
        styles = {}
        for i, panel_rows in enumerate([rows, list(reversed(rows))]):
            figure_render._panel(axes[i], panel, panel_rows, i, styles, 200, True)
        a1, b1 = axes[0].containers
        b2, a2 = axes[1].containers
        for first, second in [(a1, a2), (b1, b2)]:
            assert first.lines[0].get_color() == second.lines[0].get_color()
            assert first.lines[0].get_marker() == second.lines[0].get_marker()
        assert a1.lines[0].get_marker() != b1.lines[0].get_marker()
        assert list(a1.lines[0].get_xdata()) == [16]
        np.testing.assert_allclose(a1.lines[2][0].get_segments()[0][:, 0], [14, 18])
        np.testing.assert_allclose(b1.lines[2][0].get_segments()[0][:, 0], [11, 13])
        assert axes[0].get_xlabel() == 'Rate (%)'
    finally:
        plt.close(fig)


def test_single_column_uses_full_width_and_wraps_caption(tmp_path, monkeypatch):
    from matplotlib.figure import Figure

    (tmp_path / 'rates.csv').write_text('condition,rate\nA,1\nB,2\n')
    caption = 'Test caption with enough detailed words to require multiple physical lines at this single column width.'
    spec = dict(type='results', size=[3.55, 3.0], columns=2, caption=caption, panels=[
        dict(kind='bar', csv='rates.csv', x='condition', y='rate', question='Recorded values')])
    actual = {}
    def inspect_pdf(fig, filename, **kwargs):
        if filename.suffix == '.pdf':
            fig.canvas.draw()
            ax, = fig.axes
            actual['axes_fraction'] = ax.get_position().width
            text = next(t for t in fig.texts if t.get_text().startswith('Test caption'))
            actual['caption_bounds'] = text.get_window_extent().extents
            actual['figure_bounds'] = fig.bbox.extents
            assert '\n' in text.get_text()
    monkeypatch.setattr(Figure, 'savefig', inspect_pdf)
    figure_render.render_document(spec, tmp_path, tmp_path)
    assert actual['axes_fraction'] > .65
    x0, y0, x1, y1 = actual['caption_bounds']
    fx0, fy0, fx1, fy1 = actual['figure_bounds']
    assert fx0 <= x0 < x1 <= fx1
    assert fy0 <= y0 < y1 <= fy1


def test_interval_does_not_fill_missing_observations(tmp_path):
    (tmp_path / 'data.csv').write_text('x,y,g\nA,1,first\nB,2,second\n')
    spec = {'type': 'results', 'panels': [dict(kind='interval', csv='data.csv',
            x='x', y='y', group='g', question='Compare groups')]}
    with pytest.raises(ValueError, match='Missing category/group cell'):
        figure_render.render_document(spec, tmp_path, tmp_path)
