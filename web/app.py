"""Run: python -m uvicorn web.app:app --host 127.0.0.1 --port 8888"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paperscientist.server_runtime import configure_server_runtime
configure_server_runtime()
from paperscientist.api import create_app
app = create_app()
