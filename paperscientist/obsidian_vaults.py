"""Discover this installation's Obsidian vaults without scanning personal folders."""
import json
import os
from pathlib import Path


def discover_vaults(home=None, environ=None):
    home, env = Path(home or Path.home()), os.environ if environ is None else environ
    registries = [home / 'Library/Application Support/obsidian/obsidian.json',
                  Path(env.get('APPDATA', home / 'AppData/Roaming')) / 'obsidian/obsidian.json',
                  Path(env.get('XDG_CONFIG_HOME', home / '.config')) / 'obsidian/obsidian.json',
                  home / '.var/app/md.obsidian.Obsidian/config/obsidian/obsidian.json']
    found = {}
    for registry in registries:
        try:
            data = json.loads(registry.read_text(encoding='utf-8'))
            for item in data.get('vaults', {}).values():
                if not isinstance(item, dict) or not isinstance(item.get('path'), str):
                    continue
                path = Path(item['path']).expanduser()
                if path.is_absolute() and path.is_dir():
                    path = path.resolve()
                    found[str(path)] = {'name': path.name, 'path': str(path)}
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return sorted(found.values(), key=lambda item: item['name'].casefold())
