@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo PaperScientist - Personal Research Agent
python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
echo Open http://127.0.0.1:8888
python -m uvicorn web.app:app --host 127.0.0.1 --port 8888
