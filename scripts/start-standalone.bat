@echo off
setlocal enabledelayedexpansion

REM ─── ArtiPivot Dev Starter (Windows) ───

set ROOT_DIR=%~dp0..
set PID_FILE=%ROOT_DIR%\.pids.win

REM Check dependencies
where python >nul 2>&1 || (echo [ERROR] Python not found. Install it first. & exit /b 1)
where node >nul 2>&1 || (echo [ERROR] Node.js not found. Install it first. & exit /b 1)
where npm >nul 2>&1 || (echo [ERROR] npm not found. Install it first. & exit /b 1)

REM Install dependencies if needed
if not exist "%ROOT_DIR%\web\node_modules" (
    echo [INFO] Installing frontend dependencies...
    cd /d "%ROOT_DIR%\web" && npm install
)

REM Clean old PID file
if exist "%PID_FILE%" del "%PID_FILE%"

REM Start backend
echo [INFO] Starting FastAPI backend on :8000...
cd /d "%ROOT_DIR%"
start /b uv run artipivot serve > nul 2>&1
echo !LASTEXITCODE! > "%PID_FILE%"

REM Wait for backend
echo [INFO] Waiting for backend...
:wait_backend
timeout /t 1 /nobreak > nul
curl -s http://127.0.0.1:8000/health > nul 2>&1 && goto backend_ready
goto wait_backend
:backend_ready
echo [INFO] Backend ready

REM Start frontend
echo [INFO] Starting Vite dev server on :5173...
cd /d "%ROOT_DIR%\web"
start /b npx vite --host > nul 2>&1

echo =========================================
echo   ArtiPivot is running!
echo   Frontend:  http://localhost:5173
echo   Backend:   http://localhost:8000
echo   API docs:  http://localhost:8000/docs
echo.
echo   Run stop.bat to stop all services
echo =========================================

endlocal
