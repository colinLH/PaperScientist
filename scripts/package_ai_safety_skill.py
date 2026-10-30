#!/usr/bin/env python3
"""Compatibility command; builds the renamed research-obsidian package."""
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).with_name("package_research_obsidian_skill.py")), run_name="__main__")
