@echo off
rem Runs Battery Inventory on this computer, without Home Assistant.
rem Needs Python 3.10 or newer. Keep this window open while you use the app.
chcp 65001 >nul
title Battery Inventory
cd /d "%~dp0.."
set PYTHONUTF8=1
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 battery_inventory\server.py --ouvrir
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    python battery_inventory\server.py --ouvrir
  ) else (
    echo Python is not installed on this computer.
  )
)
echo.
echo The server is stopped.
pause
