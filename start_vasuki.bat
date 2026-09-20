@echo off
title Vasuki AI Assistant — Startup
color 0A
echo.
echo  ██╗   ██╗ █████╗ ███████╗██╗   ██╗██╗  ██╗██╗
echo  ██║   ██║██╔══██╗██╔════╝██║   ██║██║ ██╔╝██║
echo  ██║   ██║███████║███████╗██║   ██║█████╔╝ ██║
echo  ╚██╗ ██╔╝██╔══██║╚════██║██║   ██║██╔═██╗ ██║
echo   ╚████╔╝ ██║  ██║███████║╚██████╔╝██║  ██╗██║
echo    ╚═══╝  ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝
echo.
echo  Privacy-Sovereign AI Voice Assistant
echo  =======================================
echo.

:: Store project directory
set PROJECT_DIR=%~dp0

echo [1/3] Starting Ollama (local AI engine)...
start "Vasuki - Ollama" cmd /k "ollama serve"
timeout /t 3 /nobreak >nul

echo [2/3] Starting Vasuki API server...
start "Vasuki - API" cmd /k "cd /d "%PROJECT_DIR%" && uvicorn app.main:app"
timeout /t 2 /nobreak >nul

echo [3/3] Starting Vasuki voice listener...
start "Vasuki - Listener" cmd /k "cd /d "%PROJECT_DIR%" && python console_listener.py"

echo.
echo  All systems started. Vasuki is waking up...
echo  Say "Vasuki" to activate.
echo.
echo  To stop: close all three Vasuki windows.
echo.
pause
