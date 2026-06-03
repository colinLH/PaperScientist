@echo off
chcp 65001 >nul
echo ============================================
echo  PaperScientist - Setup ^& Run
echo ============================================

:: ── 1. Check .env ──────────────────────────────────────────────────────────
if not exist ".env" (
    echo [ERROR] .env file not found. Please create it based on the README.
    pause
    exit /b 1
)

:: ── 2. Install dependencies ────────────────────────────────────────────────
echo.
echo [1/2] Installing Python dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install failed. Make sure your conda/Python env is activated.
    pause
    exit /b 1
)

:: ── 3. Start server ────────────────────────────────────────────────────────
echo.
echo [2/2] Starting PaperScientist server...
echo.
echo  Access the web UI at: http://localhost:8888
echo  Press Ctrl+C to stop the server.
echo.
cd web
python -m uvicorn app:app --host 0.0.0.0 --port 8888 --reload
