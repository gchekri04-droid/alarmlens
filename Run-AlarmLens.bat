@echo off
title AlarmLens
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run: setting up AlarmLens...
  py -3 -m venv .venv || (echo Python not found. Install it from python.org first. & pause & exit /b)
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
  ".venv\Scripts\python.exe" -m pip install -q tkinterdnd2 || echo Drag-and-drop add-on not installed - use the Choose button instead.
)
if "%~1"=="" (
  start "" ".venv\Scripts\pythonw.exe" -m alarmlens.gui
  exit /b
)
".venv\Scripts\python.exe" -m alarmlens "%~1" --open -o "%~dpn1_report.html"
pause
