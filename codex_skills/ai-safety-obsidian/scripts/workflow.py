#!/usr/bin/env python3
"""Compatibility entry point for commands saved before the skill rename."""
from pathlib import Path
import runpy
import sys

scripts = Path(__file__).resolve().parents[2] / "research-obsidian/scripts"
if not (scripts / "workflow.py").is_file():
    raise SystemExit("Install the research-obsidian skill next to this legacy alias first")
sys.path.insert(0, str(scripts))
runpy.run_path(str(scripts / "workflow.py"), run_name="__main__")
