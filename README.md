# ClipCache — Ad Media Manager

> Upload your final ad. ClipCache finds every unused raw photo and video on your hard disk. You approve. Storage is reclaimed.

---

## What It Does

1. **Scan** your raw media folder (photos + videos from the shoot)
2. **Upload** the final compiled ad video
3. **Analyze** — ClipCache extracts up to 24 frames/sec from the final ad and compares every frame against your raw files using perceptual hashing
4. **Review** results: ✅ Used | ❌ Unused | ⚠️ Needs Review
5. **Trash** unused files safely — restore within 30 days if needed

---

## Quick Start

### Prerequisites
- **Python 3.10+** ([download](https://python.org))
- **ffmpeg** ([download](https://ffmpeg.org)) — add to PATH after installation

---

### Windows Setup

**First Time Only — Install Dependencies:**
```batch
cd backend
pip install -r requirements.txt
```

**Start the Application:**

Open two terminal windows:

**Terminal 1 — Backend:**
```batch
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2 — Frontend:**
```batch
cd frontend
python -m http.server 3000
```

Then open your browser to: **http://localhost:3000**

---

### Mac / Linux Setup

**First Time Only — Install Dependencies:**
```bash
cd backend
pip install -r requirements.txt
```

**Start the Application:**

Open two terminal windows or tabs:

**Terminal 1 — Backend:**
```bash
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2 — Frontend:**
```bash
cd frontend
python -m http.server 3000
```

Then open your browser to: **http://localhost:3000**

---

### Troubleshooting

| Issue | Solution |
|---|---|
| `Port 8000 already in use` | Change port: `--port 8001` |
| `Port 3000 already in use` | Change port: `python -m http.server 4000` |
| `ffmpeg not found` | Ensure ffmpeg is in your PATH; restart terminal after installation |
| `ModuleNotFoundError: No module named 'fastapi'` | Run `pip install -r requirements.txt` in `backend/` folder |
| `Permission denied` (Mac/Linux) | Try `python3` instead of `python` |

---

## Requirements

| Software | Version | Download |
|---|---|---|
| Python | 3.10+ | https://python.org |
| ffmpeg | Latest | https://ffmpeg.org (add to PATH) |

> **Windows ffmpeg setup:** Download ffmpeg, extract it, and add the `bin` folder to your System PATH environment variable.

---

## How It Works

### Detection Engine

**Layer 1 — Perceptual Hash (pHash)**
- Generates a 256-bit visual fingerprint for every photo/video keyframe
- Handles: color grading, brightness/contrast changes, LUTs, slow motion
- Accuracy: ~95% for standard edits

**Layer 2 — Scene-Adaptive Frame Extraction**
- Adaptive mode: 5fps base + 24fps burst at every detected scene cut
- Maximum mode: 24fps throughout (catches flash cuts as short as 40ms)
- Configurable per project

### Confidence Scoring

| Score | Classification |
|---|---|
| 85–100% | ✅ USED — high confidence match |
| 55–84% | ⚠️ REVIEW — partial match, check manually |
| 0–54% | ❌ UNUSED — no match found |

### Safe Deletion
- Files are **never permanently deleted directly**
- All deletions go to a `/trash` folder first
- 30-day auto-expiry (configurable)
- Full restore possible at any time before expiry
- CSV report of every deletion logged automatically

---

## Supported File Types

**Photos:** `.jpg` `.jpeg` `.png` `.tiff` `.bmp` `.webp`

**Camera RAW:** `.raw` `.cr2` `.cr3` `.arw` `.nef` `.dng` `.orf` `.rw2`

**Videos:** `.mp4` `.mov` `.avi` `.mkv` `.mxf` `.wmv` `.m4v`

---

## Project Structure

```
framevault/
├── backend/
│   ├── main.py          ← FastAPI server & all API routes
│   ├── database.py      ← SQLite schema & connection
│   ├── scanner.py       ← Hard disk walker & indexer
│   ├── matcher.py       ← Frame extraction & pHash matching
│   ├── deletion.py      ← Safe trash & restore logic
│   └── requirements.txt
├── frontend/
│   └── index.html       ← Complete React dashboard (single file)
├── temp/frames/         ← Temporary frames (auto-cleaned)
├── trash/               ← Safe delete zone
├── reports/             ← CSV deletion reports
├── uploads/             ← Uploaded final ad videos
├── framevault.db        ← SQLite database
├── setup.bat / setup.sh
└── start_server.bat / start_server.sh
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/projects` | Create new project |
| GET | `/projects` | List all projects |
| POST | `/projects/{id}/scan` | Start folder scan |
| GET | `/projects/{id}/scan/progress` | Live scan progress |
| GET | `/projects/{id}/files` | List files (filterable) |
| GET | `/projects/{id}/files/stats` | Used/unused counts |
| POST | `/projects/{id}/analyze` | Upload final video + start analysis |
| GET | `/projects/{id}/analyze/status` | Analysis progress |
| POST | `/projects/{id}/trash` | Move files to trash |
| POST | `/trash/restore` | Restore from trash |
| DELETE | `/trash/delete` | Permanent delete |
| GET | `/projects/{id}/report` | Export CSV report |

---

## Performance

| Library Size | First Index | Re-scan (new files only) | Analysis per Ad |
|---|---|---|---|
| 10,000 files | ~8 min | ~30 sec | ~2 min |
| 50,000 files | ~35 min | ~1 min | ~3 min |
| 100,000 files | ~70 min | ~2 min | ~5 min |

> Indexing runs **once**. All subsequent analyses use the stored database — fast every time.

---

## Tips

- Run the scan **once** after every shoot to keep the index up to date
- Use **Adaptive** FPS mode for most ads — best balance of speed and accuracy
- Use **Maximum (24fps)** for high-energy ads with rapid cuts
- Mark hero shots as **Protected** — they'll never be touched even if unused
- Always review the ⚠️ **Review** pile before trashing — these are uncertain matches
- Export a **CSV report** before deleting for your records
