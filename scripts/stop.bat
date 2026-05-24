@echo off
setlocal enabledelayedexpansion

REM ─── ArtiPivot Dev Stopper (Windows) ───

set ROOT_DIR=%~dp0..
set PID_FILE=%ROOT_DIR%\.pids.win

if not exist "%PID_FILE%" (
    echo No .pids.win file found. Is ArtiPivot running?
    exit /b 0
)

echo [INFO] Stopping ArtiPivot...

REM Find and kill node and python processes related to artipivot
for /f "tokens=2" %%a in ('tasklist /fi "imagename eq node.exe" /nh 2^>nul ^| findstr /i "node"') do (
    taskkill /pid %%a /f >nul 2>&1
    echo   Stopped node PID %%a
)

for /f "tokens=2" %%a in ('tasklist /fi "imagename eq python.exe" /nh 2^>nul ^| findstr /i "python"') do (
    wmic process where "processid=%%a and commandline like '%%artipivot%%'" get processid 2>nul | findstr %%a >nul && (
        taskkill /pid %%a /f >nul 2>&1
        echo   Stopped python PID %%a
    )
)

del "%PID_FILE%" 2>nul
echo [INFO] All services stopped.

endlocal
