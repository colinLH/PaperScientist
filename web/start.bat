@echo off
cd /d "%~dp0"
echo Starting Agent Chat Web UI on http://localhost:8888
conda run -n llm python -m uvicorn app:app --host 0.0.0.0 --port 8888 --reload
