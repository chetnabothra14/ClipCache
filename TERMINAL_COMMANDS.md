# FrameVault - Essential Terminal Commands

## Installation Commands

### Install Python Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### Upgrade existing dependencies
```bash
cd backend
pip install -r requirements.txt --upgrade
```

### Install with specific Python version (if multiple versions installed)
```bash
# Windows
python -m pip install -r requirements.txt

# Linux/Mac
python3 -m pip install -r requirements.txt
```

---

## Run FrameVault

### Start Backend (Main Command)
```bash
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Start Frontend (New Terminal Tab)
```bash
cd frontend
python -m http.server 3000
```

### Both Together (Windows - using start command)
```bash
cd backend && start cmd /k "python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload" && cd ../frontend && python -m http.server 3000
```

### Both Together (Linux/Mac - using background processes)
```bash
cd backend && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
cd frontend && python -m http.server 3000
```

---

## Database Commands

### Check if database exists
```bash
cd backend
ls framevault.db    # Linux/Mac
dir framevault.db   # Windows
```

### Reset database (deletes all data)
```bash
# Windows
cd backend && del framevault.db

# Linux/Mac
cd backend && rm framevault.db
```

### Access database with SQLite3
```bash
cd backend
sqlite3 framevault.db
```

---

## Testing Commands

### Test Backend Connection
```bash
curl http://localhost:8000/health
```

---

## Debug Commands

### Check Python version
```bash
python --version
python3 --version
```

### Check if pip packages installed
```bash
pip list | grep -i fastapi
```

### View backend logs (real-time)
```bash
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
# Logs appear in terminal as requests come in
```

### Check if ports are available
```bash
# Windows
netstat -ano | findstr :8000
netstat -ano | findstr :3000

# Linux/Mac
lsof -i :8000
lsof -i :3000
```

### Kill process on port (if needed)
```bash
# Windows
taskkill /PID <PID> /F
taskkill /F /IM python.exe

# Linux/Mac
kill -9 $(lsof -t -i :8000)
kill -9 $(lsof -t -i :3000)
```

---

## Development Commands

### Install new package
```bash
pip install package_name
pip install package_name==1.2.3
```

### Freeze current dependencies
```bash
pip freeze > requirements.txt
```

### Create virtual environment (recommended)
```bash
# Windows
python -m venv venv
venv\Scripts\activate
pip install -r backend/requirements.txt

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
```

### Deactivate virtual environment
```bash
deactivate
```

---

## File Operations

### View database file size
```bash
ls -lh backend/framevault.db   # Linux/Mac
dir backend\framevault.db      # Windows
```

### Backup database
```bash
# Windows
copy backend\framevault.db backend\framevault.db.backup

# Linux/Mac
cp backend/framevault.db backend/framevault.db.backup
```

### List all files in project
```bash
tree                         # Linux/Mac (if installed)
dir /s                       # Windows
find . -type f              # Linux/Mac
```

---

## Browser Commands

### Open application in Windows
```bash
start http://localhost:3000
```

### Open application in Mac
```bash
open http://localhost:3000
```

### Open application in Linux
```bash
xdg-open http://localhost:3000
```

---

## Useful Shortcuts

### Run backend with auto-reload disabled
```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### Run backend on different port
```bash
python -m uvicorn main:app --host 0.0.0.0 --port 5000
```

### Run frontend on different port
```bash
python -m http.server 8888
```

### Clear terminal screen
```bash
clear          # Linux/Mac
cls            # Windows
```

### Go back to previous directory
```bash
cd ..
```

### List files in current directory
```bash
ls                # Linux/Mac
dir               # Windows
```

---

## Quick Workflow

```bash
# 1. Terminal 1 - Install & Start Backend
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 2. Terminal 2 - Start Frontend
cd frontend
python -m http.server 3000

# 3. Terminal 3 - Optional: Access database
cd backend
sqlite3 framevault.db

# 4. Browser - Open application
http://localhost:3000

# 5. When done - Stop all (Ctrl+C in each terminal)
```

---

## Troubleshooting Commands

### Test if backend responds
```bash
curl http://localhost:8000/health -v
```

### Check what's in requirements.txt
```bash
cat backend/requirements.txt              # Linux/Mac
type backend\requirements.txt             # Windows
```

### Find Python installation
```bash
which python                    # Linux/Mac
where python                    # Windows
```

### Check if ffmpeg installed
```bash
ffmpeg -version
```

### Verify SQLite installed
```bash
sqlite3 --version
```

---

## Save These Commands

**Copy this script to `run.bat` (Windows):**
```batch
@echo off
echo Starting FrameVault...
start cmd /k "cd backend && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
timeout /t 2
start cmd /k "cd frontend && python -m http.server 3000"
timeout /t 2
start http://localhost:3000
echo FrameVault started! Backend: http://localhost:8000, Frontend: http://localhost:3000
```

**Save to `run.sh` (Linux/Mac):**
```bash
#!/bin/bash
echo "Starting FrameVault..."
cd backend && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
sleep 2
cd ../frontend && python -m http.server 3000 &
sleep 2
open http://localhost:3000
echo "FrameVault started!"
```

Then just run: `./run.bat` or `./run.sh`
