import os
import shutil
import threading
import mimetypes
import re
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Any

from database import get_db, init_db
from scanner import scan_folder, get_scan_progress
from matcher import analyze_video, detect_duplicates
from deletion import (
    move_to_trash, restore_from_trash, permanent_delete,
    run_expiry_cleanup, get_trash_list, toggle_protect
)
# ── Models ────────────────────────────────────────────────────────────────────

app = FastAPI(title="ClipCache API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Raise multipart upload limit to 10 GB — prevents silent truncation of large ad videos
try:
    import multipart
    multipart.MultipartParser.max_size = 10 * 1024 * 1024 * 1024  # 10 GB
except Exception:
    pass

UPLOADS_DIR  = os.path.join(os.path.dirname(__file__), '..', 'uploads')
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'frontend')
os.makedirs(UPLOADS_DIR, exist_ok=True)


def _has_column(db, table_name: str, column_name: str) -> bool:
    rows = db.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(r["name"] == column_name for r in rows)


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
def startup():
    init_db()
    # Migrate: add duplicate-detection columns if missing (legacy DB compatibility)
    try:
        db = get_db()
        db.execute("ALTER TABLE media_files ADD COLUMN is_original INTEGER DEFAULT 0")
        db.commit()
        db.close()
        print("✅ Migrated: added is_original column")
    except Exception:
        pass  # Column already exists
    try:
        db = get_db()
        db.execute("ALTER TABLE media_files ADD COLUMN original_id INTEGER")
        db.commit()
        db.close()
        print("✅ Migrated: added original_id column")
    except Exception:
        pass  # Column already exists
    # Migrate: add audio_fp column if missing
    try:
        db = get_db()
        db.execute("ALTER TABLE file_hashes ADD COLUMN audio_fp TEXT")
        db.commit()
        db.close()
        print("✅ Migrated: added audio_fp column")
    except Exception:
        pass  # Column already exists
    # Migrate: add ad_type column if missing
    try:
        db = get_db()
        db.execute("ALTER TABLE final_videos ADD COLUMN ad_type TEXT DEFAULT 'video_with_audio'")
        db.commit()
        db.close()
        print("✅ Migrated: added ad_type column")
    except Exception:
        pass  # Column already exists
    # Migrate: add used_size_bytes, review_size_bytes, review_files columns if missing
    try:
        db = get_db()
        db.execute("ALTER TABLE projects ADD COLUMN used_size_bytes INTEGER DEFAULT 0")
        db.commit()
        db.close()
        print("✅ Migrated: added used_size_bytes column")
    except Exception:
        pass  # Column already exists
    try:
        db = get_db()
        db.execute("ALTER TABLE projects ADD COLUMN review_size_bytes INTEGER DEFAULT 0")
        db.commit()
        db.close()
        print("✅ Migrated: added review_size_bytes column")
    except Exception:
        pass  # Column already exists
    print("🚀 ClipCache API v2.0 started")


# ── Frontend ──────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    p = os.path.join(FRONTEND_DIR, "index.html")
    return FileResponse(p) if os.path.exists(p) else {"status": "API running"}

@app.get("/app")
def serve_app():
    p = os.path.join(FRONTEND_DIR, "index.html")
    return FileResponse(p) if os.path.exists(p) else {"status": "Frontend not found"}

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat(), "version": "2.0.0"}


@app.get("/browse")
def browse_directory(path: str = ""):
    """Browse local filesystem directories for folder picker UI."""
    if not path:
        # Return available drives on Windows, or / on Linux/Mac
        import platform
        if platform.system() == "Windows":
            import string
            drives = [f"{d}:\\" for d in string.ascii_uppercase
                      if os.path.exists(f"{d}:\\")]
            return {"path": "", "drives": drives, "dirs": [], "parent": None}
        else:
            path = "/"

    # Validate path exists
    if not os.path.exists(path):
        raise HTTPException(400, f"Path does not exist: {path}")
    if not os.path.isdir(path):
        raise HTTPException(400, f"Not a directory: {path}")

    try:
        entries = []
        for entry in sorted(os.scandir(path), key=lambda e: e.name.lower()):
            if entry.is_dir() and not entry.name.startswith('.'):
                entries.append({
                    "name": entry.name,
                    "path": entry.path,
                    "type": "dir"
                })

        parent = str(os.path.dirname(path)) if path not in ('/', '') else None
        if parent == path:
            parent = None

        return {
            "path":   path,
            "parent": parent,
            "dirs":   entries
        }
    except PermissionError:
        raise HTTPException(403, "Permission denied")


@app.get("/browse-dialog")
def browse_dialog():
    """Open native OS folder-picker dialog and return the selected path.
    This blocks the request thread until the user picks a folder or cancels."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()                    # hide the blank Tk window
        root.attributes('-topmost', True)  # bring dialog to front on Windows
        folder = filedialog.askdirectory(title="Select Raw Media Folder")
        root.destroy()

        if not folder:
            raise HTTPException(400, "No folder selected")

        # Normalise to OS-native separators
        folder = os.path.normpath(folder)
        return {"folder": folder}

    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(500, "tkinter not available on this system")
    except Exception as e:
        raise HTTPException(500, f"Could not open folder dialog: {e}")



class ProjectCreate(BaseModel):
    name:       str
    raw_folder: str

@app.post("/projects")
def create_project(data: ProjectCreate):
    if not os.path.exists(data.raw_folder):
        raise HTTPException(400, f"Folder not found: {data.raw_folder}")
    db  = get_db()
    pid = db.execute(
        "INSERT INTO projects (name, raw_folder) VALUES (?, ?)",
        (data.name, data.raw_folder)
    ).lastrowid
    db.commit()
    row = db.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    db.close()
    return dict(row)

@app.get("/projects")
def list_projects():
    db   = get_db()
    rows = db.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    db.close()
    return [dict(r) for r in rows]

@app.get("/projects/{project_id}")
def get_project(project_id: int):
    db  = get_db()
    row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(404, "Project not found")
    return dict(row)

# ── Scanning ──────────────────────────────────────────────────────────────────

@app.post("/projects/{project_id}/scan")
def start_scan(project_id: int):
    db  = get_db()
    row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(404, "Project not found")
    threading.Thread(target=scan_folder, args=(project_id, row['raw_folder']), daemon=True).start()
    return {"message": "Scan started", "project_id": project_id}

@app.get("/projects/{project_id}/scan/progress")
def scan_progress(project_id: int):
    return get_scan_progress(project_id)


# ── Files ─────────────────────────────────────────────────────────────────────

@app.get("/projects/{project_id}/files")
def list_files(
    project_id: int,
    status:    Optional[str] = None,
    file_type: Optional[str] = None,
    page:      int = 1,
    per_page:  int = 50
):
    db     = get_db()
    query  = "SELECT * FROM media_files WHERE project_id=?"
    params: List[Any] = [project_id]
    
    if status == 'duplicates':
        if _has_column(db, "media_files", "original_id"):
            query += " AND original_id IS NOT NULL"
        else:
            query += " AND 1=0"
    elif status:
        query += " AND status=?"; params.append(status)
    
    if file_type:
        query += " AND file_type=?"; params.append(file_type)
    total  = db.execute(f"SELECT COUNT(*) as c FROM ({query})", params).fetchone()['c']
    query += " ORDER BY filename ASC LIMIT ? OFFSET ?"
    params += [per_page, (page-1)*per_page]
    rows   = db.execute(query, params).fetchall()
    db.close()
    return {"total": total, "page": page, "per_page": per_page, "files": [dict(r) for r in rows]}

@app.get("/projects/{project_id}/files/stats")
def file_stats(project_id: int):
    db    = get_db()
    has_original_id = _has_column(db, "media_files", "original_id")
    duplicates_expr = (
        "SUM(CASE WHEN original_id IS NOT NULL THEN 1 ELSE 0 END)"
        if has_original_id
        else "0"
    )
    stats = db.execute(f"""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status='used'       THEN 1 ELSE 0 END) as used,
            SUM(CASE WHEN status='unused'     THEN 1 ELSE 0 END) as unused,
            SUM(CASE WHEN status='review'     THEN 1 ELSE 0 END) as review,
            SUM(CASE WHEN status='unanalyzed' THEN 1 ELSE 0 END) as unanalyzed,
            SUM(CASE WHEN status='trashed'    THEN 1 ELSE 0 END) as trashed,
            {duplicates_expr} as duplicates,
            SUM(size_bytes) as total_size,
            SUM(CASE WHEN status='unused' THEN size_bytes ELSE 0 END) as unused_size,
            SUM(CASE WHEN status='used'   THEN size_bytes ELSE 0 END) as used_size,
            SUM(CASE WHEN status='review' THEN size_bytes ELSE 0 END) as review_size,
            SUM(CASE WHEN status='unanalyzed' THEN size_bytes ELSE 0 END) as unanalyzed_size
        FROM media_files WHERE project_id=?
    """, (project_id,)).fetchone()
    db.close()
    return dict(stats) if stats else {}

@app.patch("/files/{file_id}/protect")
def protect_file(file_id: int, protected: bool = True):
    return toggle_protect(file_id, protected)

@app.get("/files/{file_id}/preview")
def preview_file(file_id: int, thumb: bool = False):
    db  = get_db()
    row = db.execute("SELECT * FROM media_files WHERE id=?", (file_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(404, "File not found")
    path = row['filepath']
    if not os.path.exists(path):
        raise HTTPException(404, "File not found on disk")
        
    # If it's a video and asked for a thumbnail, extract a frame
    if thumb and row['file_type'] == 'video':
        import cv2, io, subprocess
        from PIL import Image
        
        cap = cv2.VideoCapture(path)
        ret, frame = cap.read()
        if not ret:
            # Keep trying linearly for up to 30 frames (ignores empty P-frames)
            for _ in range(30):
                ret, frame = cap.read()
                if ret: break
        cap.release()
        
        # 1. Try OpenCV
        if ret:
            try:
                img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                img.thumbnail((400, 400)) # Resize for faster grid loading
                buf = io.BytesIO()
                img.save(buf, format='JPEG', quality=85)
                buf.seek(0)
                return StreamingResponse(buf, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})
            except Exception as e:
                print(f"Error converting frame: {e}")
                
        # 2. If modern iPhone HEVC / 10-bit format, OpenCV may fail entirely. Fallback to FFmpeg.
        try:
            cmd = [
                "ffmpeg", "-y", "-ss", "00:00:00.500", "-i", path, 
                "-vframes", "1", "-f", "image2pipe", "-vcodec", "mjpeg", "-"
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            if result.returncode == 0 and result.stdout:
                img = Image.open(io.BytesIO(result.stdout)).convert("RGB")
                img.thumbnail((400, 400))
                buf = io.BytesIO()
                img.save(buf, format='JPEG', quality=85)
                buf.seek(0)
                return StreamingResponse(buf, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})
        except Exception as e:
            print(f"ffmpeg thumb fallback failed: {e}")
                
        raise HTTPException(404, "Could not extract video thumbnail via OpenCV or FFmpeg")

    # Otherwise return the actual media file
    mime, _ = mimetypes.guess_type(path)
    return FileResponse(path, media_type=mime or "application/octet-stream", headers={"Cache-Control": "max-age=86400"})

@app.get("/files/{file_id}/stream")
def stream_file(file_id: int, request: Request):
    """Serve video files with support for Range requests for the video player."""
    db  = get_db()
    row = db.execute("SELECT * FROM media_files WHERE id=?", (file_id,)).fetchone()
    db.close()
    if not row or not os.path.exists(row['filepath']):
        raise HTTPException(404, "Video not found")
        
    path = row['filepath']
    file_size = os.path.getsize(path)
    mime, _ = mimetypes.guess_type(path)
    content_type = mime or "video/mp4"

    # Support HTTP 206 Partial Content (Range requests) which is required by Safari and some Chrome features
    range_header = request.headers.get("Range")
    if range_header:
        byte1, byte2 = 0, None
        match = re.search(r'bytes=(\d+)-(\d*)', range_header)
        if match:
            byte1 = int(match.group(1))
            if match.group(2):
                byte2 = int(match.group(2))
        
        byte2 = byte2 if byte2 is not None else file_size - 1
        length = byte2 - byte1 + 1

        def file_iterator(file_path, start, end):
            with open(file_path, "rb") as video:
                video.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk_size = min(1024 * 1024, remaining)
                    data = video.read(chunk_size)
                    if not data:
                        break
                    yield data
                    remaining -= len(data)

        headers = {
            "Content-Range": f"bytes {byte1}-{byte2}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
        }
        return StreamingResponse(file_iterator(path, byte1, byte2), status_code=206, headers=headers, media_type=content_type)
        
    return FileResponse(path, media_type=content_type)

@app.get("/files/{file_id}/match-frame")
def match_frame(file_id: int):
    """Return the matched frame from the final ad."""
    db    = get_db()
    match = db.execute("""
        SELECT fv.filepath as video_path, m.matched_at_second
        FROM matches m JOIN final_videos fv ON fv.id=m.video_id
        WHERE m.file_id=? ORDER BY m.confidence DESC LIMIT 1
    """, (file_id,)).fetchone()
    db.close()
    if not match:
        raise HTTPException(404, "No match found")

    import cv2, io
    cap = cv2.VideoCapture(match['video_path'])
    cap.set(cv2.CAP_PROP_POS_MSEC, (match['matched_at_second'] or 0) * 1000)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        raise HTTPException(500, "Could not extract frame")

    from PIL import Image
    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=90)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/jpeg")


# ── Video Analysis ────────────────────────────────────────────────────────────

# Track active analysis per project to avoid duplicates
_active_analysis = set()

@app.post("/projects/{project_id}/analyze/chunk")
async def upload_analyze_chunk(
    project_id: int,
    file_id: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    chunk: UploadFile = File(...)
):
    safe_name = f"upload_{project_id}_{file_id}"
    video_path = os.path.join(UPLOADS_DIR, safe_name)
    
    mode = "ab" if chunk_index > 0 else "wb"
    with open(video_path, mode) as f:
        data = await chunk.read()
        if data:
            f.write(data)
    
    return {"status": "ok", "chunk_index": chunk_index}

@app.post("/projects/{project_id}/analyze/complete")
async def analyze_complete(
    project_id: int,
    file_id: str = Form(...),
    filename: str = Form(...),
    fps_mode: str = Form('adaptive'),
    ad_type: str = Form('video_with_audio')
):
    db = get_db()
    try:
        row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Project not found")

        # Validate ad_type
        valid_ad_types = {'video_with_audio', 'acted_ads', 'product_photoshoot'}
        if ad_type not in valid_ad_types:
            raise HTTPException(400, f"Invalid ad_type. Must be one of: {', '.join(valid_ad_types)}")

        # Validate fps_mode
        valid_fps_modes = {'quick', 'standard', 'high', 'maximum', 'adaptive'}
        if fps_mode not in valid_fps_modes:
            raise HTTPException(400, f"Invalid fps_mode. Must be one of: {', '.join(valid_fps_modes)}")

        count = db.execute(
            "SELECT COUNT(*) as c FROM media_files WHERE project_id=? AND status != 'trashed'",
            (project_id,)
        ).fetchone()['c']
        if count == 0:
            raise HTTPException(400, "No indexed files. Run scan first.")

        if filename:
            ext = os.path.splitext(filename)[1].lower()
            ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".mxf", ".wmv",
                                  ".m4v", ".ts", ".webm", ".mpg", ".mpeg"}
            if ext not in ALLOWED_VIDEO_EXTS:
                raise HTTPException(400, f"Unsupported file type: {ext}")

        safe_name = f"upload_{project_id}_{file_id}"
        temp_path = os.path.join(UPLOADS_DIR, safe_name)
        
        if not os.path.exists(temp_path):
            raise HTTPException(400, "Uploaded file missing")
            
        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_name  = f"project_{project_id}_{timestamp}_{filename}"
        video_path = os.path.join(UPLOADS_DIR, final_name)
        os.rename(temp_path, video_path)
        
        total_bytes = os.path.getsize(video_path)
        if total_bytes == 0:
            os.remove(video_path)
            raise HTTPException(400, "Uploaded file is empty")

        print(f"📁 Video saved: {video_path} ({total_bytes/1024/1024:.1f} MB)")

        db.execute(
            "UPDATE media_files SET status='unanalyzed', confidence=0 WHERE project_id=? AND status != 'trashed'",
            (project_id,)
        )

        vid_id = db.execute("""
            INSERT INTO final_videos (project_id, filename, filepath, fps_mode, analysis_status, ad_type)
            VALUES (?, ?, ?, ?, 'pending', ?)
        """, (project_id, filename, video_path, fps_mode, ad_type)).lastrowid

        db.execute("UPDATE projects SET status='analyzing' WHERE id=?", (project_id,))
        db.commit()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Unexpected error during finalizing: {e}")
    finally:
        db.close()
    
    if not vid_id:
        raise HTTPException(500, "Failed to create video record")
        
    def run():
        _active_analysis.add(project_id)
        try:
            analyze_video(project_id, vid_id, video_path, fps_mode, ad_type)
        finally:
            _active_analysis.discard(project_id)

    threading.Thread(target=run, daemon=True).start()

    return {
        "message":    "Analysis started",
        "video_id":   vid_id,
        "fps_mode":   fps_mode,
        "filename":   filename,
        "ad_type":    ad_type,
        "size_mb":    round(total_bytes / 1024 / 1024, 2)
    }

@app.get("/projects/{project_id}/analyze/status")
def analysis_status(project_id: int):
    db  = get_db()
    vid = db.execute(
        "SELECT * FROM final_videos WHERE project_id=? ORDER BY id DESC LIMIT 1",
        (project_id,)
    ).fetchone()
    
    result: dict = dict(vid) if vid else {"analysis_status": "no_video"}
    result["is_active"] = project_id in _active_analysis
    
    from matcher import get_analysis_progress
    prog = get_analysis_progress(project_id)
    
    # If analysis is not actively running but DB shows stuck status, reset it
    if not result["is_active"] and vid and vid["analysis_status"] not in ("complete", "error", "no_video"):
        db.execute("UPDATE final_videos SET analysis_status=? WHERE id=?", ("error", vid["id"]))
        db.commit()
        result["analysis_status"] = "error"
    
    # Update with progress data if analysis is actively running
    if prog["status"] != "idle":
        result.update(prog)
        
    db.close()
    return result

@app.post("/projects/{project_id}/analyze/cancel")
def cancel_analysis_endpoint(project_id: int):
    """Cancel current analysis."""
    from matcher import cancel_analysis
    cancel_analysis(project_id)
    return {"message": "Analysis cancellation requested"}

@app.delete("/projects/{project_id}/analyze")
def clear_analysis(project_id: int):
    """Clear current analysis so a new video can be uploaded."""
    from matcher import cancel_analysis
    cancel_analysis(project_id)
    
    db = get_db()
    db.execute(
        "UPDATE media_files SET status='unanalyzed', confidence=0 WHERE project_id=?",
        (project_id,)
    )
    db.execute("UPDATE projects SET status='scanned' WHERE id=?", (project_id,))
    db.commit()
    db.close()
    return {"message": "Analysis cancelled and cleared. Ready for new video upload."}

@app.post("/projects/{project_id}/detect-duplicates")
def detect_duplicates_endpoint(project_id: int):
    """Run duplicate detection on all files in project."""
    try:
        count = detect_duplicates(project_id)
        return {"message": "Duplicate detection completed", "duplicates_found": count}
    except Exception as e:
        raise HTTPException(500, f"Duplicate detection failed: {str(e)}")


# ── Project Deletion ─────────────────────────────────────────────────────────

@app.delete("/projects/{project_id}")
def delete_project(project_id: int, delete_files: bool = False):
    """Permanently delete a project and all its associated data.
    If delete_files=true, also permanently removes raw media files from disk."""
    from matcher import cancel_analysis
    cancel_analysis(project_id)

    db = get_db()
    try:
        row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Project not found")

        # Get all media files for this project
        media_rows = db.execute(
            "SELECT id, filepath FROM media_files WHERE project_id=?", (project_id,)
        ).fetchall()
        file_ids = [r['id'] for r in media_rows]

        # If user wants to delete raw files from disk
        deleted_count = 0
        if delete_files:
            for mf in media_rows:
                try:
                    if mf['filepath'] and os.path.exists(mf['filepath']):
                        os.remove(mf['filepath'])
                        deleted_count += 1
                except Exception as e:
                    print(f"  ⚠️  Could not delete {mf['filepath']}: {e}")

        # Remove associated DB data
        if file_ids:
            placeholders = ','.join('?' * len(file_ids))
            db.execute(f"DELETE FROM file_hashes WHERE file_id IN ({placeholders})", file_ids)
            # Also clean trash records
            db.execute(f"DELETE FROM trash WHERE file_id IN ({placeholders})", file_ids)

        db.execute("DELETE FROM media_files WHERE project_id=?", (project_id,))
        db.execute("DELETE FROM scan_progress WHERE project_id=?", (project_id,))

        # Remove final videos if table exists
        try:
            db.execute("DELETE FROM final_videos WHERE project_id=?", (project_id,))
        except Exception:
            pass

        db.execute("DELETE FROM projects WHERE id=?", (project_id,))
        db.commit()

        # Clean up uploaded ad videos for this project
        for f in os.listdir(UPLOADS_DIR):
            if f.startswith(f"project_{project_id}_"):
                try:
                    os.remove(os.path.join(UPLOADS_DIR, f))
                except Exception:
                    pass

        # Clean trash folder for this project
        trash_project_dir = os.path.join(os.path.dirname(__file__), '..', 'trash', f'project_{project_id}')
        if os.path.exists(trash_project_dir):
            shutil.rmtree(trash_project_dir, ignore_errors=True)

        msg = f"Project '{row['name']}' deleted"
        if delete_files:
            msg += f" — {deleted_count} files permanently removed from disk"
        print(f"🗑️ {msg}")
        return {"message": msg}
    finally:
        db.close()


# ── Deletion ──────────────────────────────────────────────────────────────────

class FileIdList(BaseModel):
    file_ids:    List[int]
    expiry_days: Optional[int] = 30

@app.post("/projects/{project_id}/trash")
def trash_files(project_id: int, data: FileIdList):
    return move_to_trash(data.file_ids, data.expiry_days or 30)

@app.post("/trash/restore")
def restore_files(data: FileIdList):
    return restore_from_trash(data.file_ids)

@app.delete("/trash/delete")
def delete_permanently(data: FileIdList):
    return permanent_delete(data.file_ids)

@app.post("/trash/cleanup")
def cleanup_expired():
    return run_expiry_cleanup()

@app.get("/projects/{project_id}/trash")
def project_trash(project_id: int):
    return get_trash_list(project_id)


# ── Reports ───────────────────────────────────────────────────────────────────

@app.get("/projects/{project_id}/report")
def export_report(project_id: int):
    db    = get_db()
    proj  = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    files = db.execute(
        "SELECT filename, file_type, status, confidence, size_bytes, filepath FROM media_files WHERE project_id=?",
        (project_id,)
    ).fetchall()
    db.close()

    lines     = ["filename,type,status,confidence,size_bytes,filepath\n"]
    lines    += [f"{r['filename']},{r['file_type']},{r['status']},{r['confidence']},{r['size_bytes']},{r['filepath']}\n"
                 for r in files]
    proj_name = proj['name'] if proj else f"project_{project_id}"
    return StreamingResponse(iter(lines), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{proj_name}_report.csv"'})


# ── Static files (keep last) ──────────────────────────────────────────────────
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
