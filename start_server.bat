@echo off
echo Starting ClipCache Backend Server...
echo.
echo Backend API: http://localhost:8000
echo Dashboard:   Open frontend/index.html in your browser
echo.
echo Press Ctrl+C to stop the server
echo.
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
