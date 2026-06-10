@echo off
REM Odysseus launcher with ChromaDB dependency
REM Run this from the odysseus project root

cd /d "%~dp0"

echo ==========================================
echo Starting Odysseus stack...
echo ==========================================

REM Check if virtual environment exists
if not exist "venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found at .\venv
    echo Run setup.py first or create venv manually
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

REM Check if ChromaDB is already running on port 8100
curl -s http://127.0.0.1:8100/api/v2/heartbeat >nul 2>&1
if %errorlevel% equ 0 (
    echo [ok] ChromaDB already running on port 8100
) else (
    echo [start] Launching ChromaDB on port 8100...
    start "ChromaDB" /b cmd /c "chroma run --host 127.0.0.1 --port 8100 --path .\data\chroma"
    
    REM Wait for ChromaDB to be healthy
    echo [wait] Waiting for ChromaDB to be ready...
    for /l %%i in (1,1,30) do (
        curl -s http://127.0.0.1:8100/api/v2/heartbeat >nul 2>&1
        if %errorlevel% equ 0 (
            echo [ok] ChromaDB is ready
            goto :chromadb_ready
        )
        timeout /t 1 >nul
    )
    echo [warn] ChromaDB startup timed out, continuing anyway...
    :chromadb_ready
)

REM Start Odysseus
echo [start] Launching Odysseus on http://127.0.0.1:7000
echo ==========================================
python -m uvicorn app:app --host 127.0.0.1 --port 7000