@echo off
title India Job Openings Excel Collector
where py >nul 2>nul
if %errorlevel%==0 (
  set PYTHON_CMD=py
) else (
  set PYTHON_CMD=python
)
%PYTHON_CMD% collect_jobs.py
echo.
echo The Excel file is inside the output folder.
pause
