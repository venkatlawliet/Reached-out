@echo off
cd /d "%~dp0"

:: Kill any previous instance running on port 5000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5000 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1

pip install -r requirements.txt >nul 2>&1
start /b python app.py
timeout /t 2 /noq >nul
start http://localhost:5000
