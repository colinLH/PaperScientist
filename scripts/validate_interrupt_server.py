"""Isolated browser fixture using the configured real model, never the main workspace."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from paperscientist.api import create_app
from paperscientist.config import Settings, ROOT

if __name__ == "__main__":
    uvicorn.run(create_app(Settings.load(data_dir=ROOT / ".test-output/interrupt-live", extract_memory=False, skill_roots=())), host="127.0.0.1", port=8889)
