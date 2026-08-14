@echo off
REM Daily commit script for FlowSight (Windows)
REM Run via Task Scheduler daily at 2 AM

set REPO_DIR=C:\Users\shahi\flowsight
set LOG_FILE=%REPO_DIR%\logs\daily_commit.log

REM Create log directory
if not exist "%REPO_DIR%\logs" mkdir "%REPO_DIR%\logs"

REM Log start
echo [%date% %time%] Starting daily commit >> "%LOG_FILE%"

REM Change to repo directory
cd /d "%REPO_DIR%"

REM Run the daily commit script
python scripts/daily_commit.py >> "%LOG_FILE%" 2>&1

REM Log completion
echo [%date% %time%] Daily commit completed >> "%LOG_FILE%"