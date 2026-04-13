@echo off
echo Starting Backend...
start cmd /k "cd backend & python run.py"

echo Starting Frontend...
start cmd /k "cd frontend & npm run dev"

echo System Started.
echo Backend: http://127.0.0.1:5000
echo Frontend Local: http://localhost:5888
echo Frontend Network: http://<your-ip>:5888 (Check terminal output for IP)
pause
