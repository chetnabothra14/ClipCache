# FrameVault Quick Start

## Installation

1. Install backend dependencies:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

2. Start backend:
   ```bash
   cd backend
   python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

3. Start frontend (new terminal):
   ```bash
   cd frontend
   python -m http.server 3000
   ```

4. Open the app:
   - http://localhost:3000
   - The dashboard opens directly.

## Basic Usage

1. Click New Project.
2. Enter project name and raw media folder path.
3. Open project and run Scan.
4. Upload a final ad video from Analyze.
5. Review Used, Review, and Unused files.
6. Move unused files to trash when ready.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Backend not reachable | Confirm backend is running on port 8000 |
| Frontend not loading | Confirm frontend server is running on port 3000 |
| Database errors | Stop backend, remove framevault.db, then restart |
| ffmpeg issues | Install ffmpeg and ensure it is available in PATH |

## Notes

- FrameVault uses local SQLite storage.
- Existing auth-related tables in an old database file are harmless leftovers and no longer used.
