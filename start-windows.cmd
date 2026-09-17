@echo off
cd /d "%~dp0"
py -3 -c "import requests" >nul 2>nul
if errorlevel 1 (
    echo Please install Python 3.8+ and run: py -3 -m pip install -r requirements.txt
    pause
    exit /b 1
)
py -3 main.py
pause
