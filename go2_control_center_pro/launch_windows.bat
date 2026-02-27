@echo off
setlocal
cd /d %~dp0
REM Try to run with python in PATH
python go2_control_center_pro.py
if errorlevel 1 (
  echo.
  echo Python not found or app crashed. Try:
  echo   py go2_control_center_pro.py
  pause
)
