@echo off
echo Starting AI Shelf Inventory System...
echo.

echo Starting backend server...
start "Backend" cmd /c "cd /d %~dp0 && python -m backend.main"

timeout /t 3 /nobreak > nul

echo Starting frontend server...
start "Frontend" cmd /c "cd /d %~dp0web && npm run dev -- --host 0.0.0.0 --port 5173"

echo.
echo Servers started!
echo Backend: http://localhost:8000
echo Frontend: http://localhost:5173
echo.
pause