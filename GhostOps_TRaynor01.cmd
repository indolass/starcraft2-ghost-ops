@echo off
rem Double click: choose a Ghost Ops variant of Liberation Day and start it.
rem ASCII only on purpose (cmd); the menu text itself is printed by Python in UTF-8.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found in PATH. Install Python 3 or run tools\ghostops_menu.py by hand.
  pause
  exit /b 1
)
python -I tools\ghostops_menu.py
