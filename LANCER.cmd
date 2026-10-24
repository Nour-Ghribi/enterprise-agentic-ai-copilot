@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Environnement Python absent. Suivez les instructions du README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" launch.py
pause
