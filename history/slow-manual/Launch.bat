@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto error
)
if not exist ".venv\.deps-ready" (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto error
    type nul > ".venv\.deps-ready"
)
".venv\Scripts\python.exe" coloring_pixels_assistant.py
if errorlevel 1 goto error
exit /b 0
:error
pause
exit /b 1
