@echo off
cd /d "%~dp0"

echo.
echo  ============================================
echo   Brownfield IDE -- Starting...
echo  ============================================
echo.

REM Check for Python
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+ and add to PATH.
    pause
    exit /b 1
)

REM Validate existing venv — a venv copied from another machine points at a
REM Python path that no longer exists, so test that it actually runs.
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" --version >nul 2>&1
    if errorlevel 1 (
        echo [WARN] Existing virtual environment is broken. Recreating...
        rmdir /s /q venv
    )
)

REM Create venv if it doesn't exist (or was just removed)
if not exist "venv\Scripts\python.exe" (
    echo [INFO] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [INFO] Virtual environment created.
)

REM Activate venv
call venv\Scripts\activate.bat

REM Install / upgrade requirements
echo [INFO] Installing requirements...
pip install -r requirements.txt --quiet --upgrade
if errorlevel 1 (
    echo [ERROR] Failed to install requirements.
    pause
    exit /b 1
)

echo.
echo  ============================================
echo   Server starting at http://localhost:8000
echo   Press Ctrl+C to stop.
echo  ============================================
echo.

REM Start server
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

pause
