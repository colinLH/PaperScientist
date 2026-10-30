import json
from pathlib import Path

import pytest

from paperscientist.obsidian_vaults import discover_vaults
from paperscientist.reading_archive import ReadingArchive, atomic_json, identities


@pytest.mark.parametrize('registry', ['Library/Application Support/obsidian/obsidian.json',
    'AppData/Roaming/obsidian/obsidian.json', '.config/obsidian/obsidian.json',
    '.var/app/md.obsidian.Obsidian/config/obsidian/obsidian.json'])
def test_discover_current_users_registered_vaults(tmp_path, registry):
    vault = tmp_path / '我的 Notes'
    vault.mkdir()
    atomic_json(tmp_path / registry, {'vaults': {'a': {'path': str(vault)}, 'b': {'path': str(vault)},
                'stale': {'path': str(tmp_path / 'missing')}, 'invalid': None}})
    assert discover_vaults(tmp_path, {}) == [{'name': vault.name, 'path': str(vault)}]


def test_discovery_custom_environment_and_malformed_registry(tmp_path):
    vault = tmp_path / 'vault'
    vault.mkdir()
    registry = tmp_path / 'config/obsidian/obsidian.json'
    atomic_json(registry, {'vaults': {'id': {'path': str(vault)}}})
    assert discover_vaults(tmp_path, {'XDG_CONFIG_HOME': str(tmp_path / 'config')})[0]['path'] == str(vault)
    registry.write_text('{broken')
    assert discover_vaults(tmp_path, {'XDG_CONFIG_HOME': str(tmp_path / 'config')}) == []


def test_local_metadata_dedup_does_not_rewrite_index_or_notes(tmp_path):
    archive = ReadingArchive(tmp_path, '.', True)
    atomic_json(archive.index_path, {'records': [{'title': 'Already indexed', 'arxiv_id': '2601.12345'}], 'custom': 'keep'})
    (tmp_path / 'first.md').write_text('---\ntitle: Alternate paper title\narxiv_id: 2601.12345v2\n---\n')
    (tmp_path / 'second.md').write_text('---\npaper_title: Another local paper\ndoi: https://doi.org/10.1234/ABC\n---\n')
    (tmp_path / 'ordinary.md').write_text('# Notes\nCitation: https://arxiv.org/abs/2601.99999')
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    records = archive.index()['records']
    assert len(records) == 2
    assert identities({'doi': '10.1234/abc'}) & identities(records[1])
    assert len(archive.reports()) == 3
    assert archive.stored_index()['custom'] == 'keep'
    assert {p: p.read_bytes() for p in before} == before
    with pytest.raises(ValueError, match='已归档'):
        archive.publish('a' * 32, 'test', [{'title': 'different title', 'doi': '10.1234/abc'}], {}, {})


def test_note_preview_wikilinks_and_scope_boundaries(tmp_path):
    root = tmp_path / 'papers'
    root.mkdir()
    archive = ReadingArchive(tmp_path, 'papers', True)
    (root / 'figure.png').write_bytes(b'image')
    (root / 'other.md').write_text('Other note')
    note = root / 'paper.md'
    note.write_text('# Paper\n![[figure.png]]\n[[other|Related]]\n<script>alert(1)</script>\n![secret](../secret.png)')
    (tmp_path / 'secret.png').write_bytes(b'private')
    (root / 'escaped.md').symlink_to(tmp_path / 'secret.png')
    atomic_json(root / '.obsidian/private.json', {})
    html = archive.preview('papers/paper.md')
    assert 'src="/api/reading/file?path=papers%2Ffigure.png"' in html
    assert '>Related</a>' in html
    assert '<script>' not in html
    assert 'src="../secret.png"' not in html
    assert len(archive.reports()) == 2
    with pytest.raises(ValueError):
        archive.public_file('papers/escaped.md')
    with pytest.raises(ValueError):
        archive.public_file('papers/.obsidian/private.json')


def test_import_preserves_missing_index_gate(tmp_path):
    (tmp_path / '01-报告').mkdir()
    (tmp_path / '01-报告/old.md').write_text('Existing report')
    with pytest.raises(ValueError, match='缺少累计索引'):
        ReadingArchive(tmp_path, '.', True).index()
