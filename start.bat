@echo off
title CONTROLPC Launcher
echo ========================================================
echo          CONTROLPC - LOCAL OS AGENT LAUNCHER
echo ========================================================
echo.

:: 0. Check prerequisite command line tools
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found in your PATH. Please install Python 3.10+ first.
    pause
    exit /b
)

where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js/npm was not found in your PATH. Please install Node.js first.
    pause
    exit /b
)

:: 1. Check and build Frontend
cd /d "%~dp0frontend"
if not exist node_modules (
    echo [SYSTEM] frontend/node_modules not found. Running npm install...
    call npm install
    if errorlevel 1 goto node_error
)
if not exist dist (
    echo [SYSTEM] Building offline production frontend bundle...
    call npm run build
    if errorlevel 1 goto node_error
)
goto check_backend

:node_error
echo [ERROR] Frontend setup failed.
pause
exit /b

:: 2. Check and activate Python Backend
:check_backend
cd /d "%~dp0backend"
if not exist venv (
    echo [SYSTEM] Python virtual environment (venv) not found. Creating venv...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create Python virtual environment.
        pause
        exit /b
    )
    echo [SYSTEM] Virtual environment created successfully. Installing backend dependencies...
    call venv\Scripts\activate
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install requirements from backend/requirements.txt.
        pause
        exit /b
    )
    echo [SYSTEM] Dependencies installed successfully.
) else (
    echo [SYSTEM] Activating existing Python virtual environment...
    call venv\Scripts\activate
)

:: 3. Run application
cd /d "%~dp0"
echo [SYSTEM] Launching native Desktop window...
python desktop.py
if errorlevel 1 (
    echo.
    echo [ERROR] Application exited with error code.
    pause
)
exit /b
