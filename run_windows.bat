@echo off
title Job Role Finder
where py >nul 2>nul
if %errorlevel%==0 (
  set PYTHON_CMD=py
) else (
  set PYTHON_CMD=python
)
start "" http://127.0.0.1:5000
%PYTHON_CMD% app.py
pause
