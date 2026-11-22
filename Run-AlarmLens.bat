@echo off
title AlarmLens
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run: setting up AlarmLens...
  py -3 -m venv .venv || (echo Python not found. Install it from python.org first. & pause & exit /b)
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
)
if "%~1"=="" (
  echo No file given - running on the sample data.
  ".venv\Scripts\python.exe" -m alarmlens sample\alarm_log_sample.csv --sample --open -o sample\sample_report.html
) else (
  ".venv\Scripts\python.exe" -m alarmlens "%~1" --open -o "%~dpn1_report.html"
)
pause
