@echo off
cd /d "%~dp0"
if exist ".runtime\python\python.exe" (
    set PYTHONUTF8=1
    ".runtime\python\python.exe" bootstrap_local.py
    if errorlevel 1 pause
    exit /b
)
powershell.exe -NoProfile -File "%~dp0start-windows.ps1"
