@echo off
setlocal enabledelayedexpansion

title CONTROLPC Launcher
echo ========================================================
echo          CONTROLPC - LOCAL OS AGENT LAUNCHER
echo ========================================================
echo.

:: Set absolute root directory (hardcoded, no spaces issue)
set "ROOT=C:\1 CODE\CONTROLPC"
set "FRONTEND=%ROOT%\frontend"
set "BACKEND=%ROOT%\backend"

:: 0. Check prerequisite command line tools
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python was not found in your PATH. Please install Python 3.10+.
    pause
    exit /b 1
)

where npm >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Node.js/npm was not found. Please install Node.js first.
    pause
    exit /b 1
)

:: 1. Check and build Frontend
cd /d "%FRONTEND%"
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Cannot access frontend directory: %FRONTEND%
    pause
    exit /b 1
)

if not exist "%FRONTEND%\node_modules" (
    echo [SYSTEM] node_modules not found. Running npm install...
    call npm install
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] npm install failed.
        pause
        exit /b 1
    )
)

if not exist "%FRONTEND%\dist" (
    echo [SYSTEM] Building frontend production bundle...
    call npm run build
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] npm run build failed.
        pause
        exit /b 1
    )
)

echo [OK] Frontend ready.

:: 2. Check and activate Python Backend venv
cd /d "%BACKEND%"
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Cannot access backend directory: %BACKEND%
    pause
    exit /b 1
)

if not exist "%BACKEND%\venv" (
    echo [SYSTEM] Creating Python virtual environment...
    python -m venv venv
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to create venv.
        pause
        exit /b 1
    )
    echo [SYSTEM] Installing backend dependencies...
    call "%BACKEND%\venv\Scripts\activate.bat"
    python -m pip install --upgrade pip --quiet
    pip install -r "%BACKEND%\requirements.txt"
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] pip install failed.
        pause
        exit /b 1
    )
    echo [OK] Dependencies installed.
) else (
    echo [SYSTEM] Activating existing venv...
    call "%BACKEND%\venv\Scripts\activate.bat"
)

echo [OK] Backend venv active.

:: 3. Launch Desktop app
cd /d "%ROOT%"
echo [SYSTEM] Launching CONTROLPC Desktop...
python "%ROOT%\desktop.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Application exited with an error. Check logs above.
    pause
)

endlocal
exit /b
