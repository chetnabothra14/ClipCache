import os
import wave
import subprocess
import tempfile
from datetime import datetime
from PIL import Image
import imagehash
import cv2
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed
from database import get_db

# ── Supported formats ─────────────────────────────────────────────────────────
SUPPORTED_PHOTOS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"}
SUPPORTED_RAW    = {".raw", ".cr2", ".cr3", ".arw", ".nef", ".dng", ".orf", ".rw2"}
SUPPORTED_VIDEOS = {
    ".mp4", ".mov", ".avi", ".mkv", ".mxf", ".wmv", ".flv",
    ".m4v", ".ts", ".webm", ".3gp", ".mpg", ".mpeg"
}
ALL_SUPPORTED = SUPPORTED_PHOTOS | SUPPORTED_RAW | SUPPORTED_VIDEOS


# ── Keyframe density for raw video clips ──────────────────────────────────────
# Dense sampling because editor might use only 1 second from a 30 second clip
def _get_interval(duration_sec: float) -> float:
    if duration_sec <= 5:
        return 0.25      # every 250ms — catches very short clips
    elif duration_sec <= 15:
        return 0.5       # every 500ms
    elif duration_sec <= 60:
        return 1.0       # every 1s
    elif duration_sec <= 300:
        return 2.0       # every 2s
    else:
        return 3.0       # every 3s for long footage


def _fingerprint_file_for_scan(filepath: str) -> tuple:
    """
    Helper for multiprocessing: fingerprint a single file.
    Returns (filepath, file_type, phash_str, audio_fp, duration, frame_count)
    """
    ext = os.path.splitext(filepath)[1].lower()
    file_type = "video" if ext in SUPPORTED_VIDEOS else "photo"
    
    try:
        if file_type == "video":
            result = fingerprint_video(filepath)
            if result is None:
                return (filepath, file_type, None, None, 0, 0)
            phash_str, audio_fp, duration, frame_count = result
            return (filepath, file_type, phash_str, audio_fp, duration, frame_count)
        else:
            phash_str = fingerprint_photo(filepath)
            if phash_str is None:
                return (filepath, file_type, None, None, 0, 0)
            return (filepath, file_type, phash_str, None, 0, 0)
    except Exception as e:
        print(f"  ❌ Fingerprint error: {filepath}: {e}")
        return (filepath, file_type, None, None, 0, 0)


def scan_folder(project_id: int, folder_path: str):
    """
    Walk folder, index ALL files — photos and videos.
    Videos get dense visual + audio fingerprints.
    Photos get aspect-aware pHash.
    OPTIMIZED: Uses multiprocessing (4 workers) for fingerprinting.
    """
    db = get_db()

    progress_id = db.execute(
        "INSERT INTO scan_progress (project_id, status) VALUES (?, 'running')",
        (project_id,)
    ).lastrowid
    db.commit()

    try:
        print(f"\n📁 SCANNER — Walking: {folder_path}")
        all_files = []
        for root, dirs, files in os.walk(folder_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "Trash"]
            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                if ext in ALL_SUPPORTED:
                    all_files.append(os.path.join(root, filename))

        total = len(all_files)
        print(f"   Found {total} supported files")

        db.execute("UPDATE scan_progress SET total_found=? WHERE id=?", (total, progress_id))
        db.commit()

        processed = skipped = failed = 0
        
        # Pre-compute which files need fingerprinting (skip already-indexed)
        to_fingerprint = []
        for filepath in all_files:
            stat = os.stat(filepath)
            size_bytes = stat.st_size
            mtime = stat.st_mtime
            
            existing = db.execute(
                "SELECT id, modified_at, size_bytes FROM media_files WHERE filepath=? AND project_id=?",
                (filepath, project_id)
            ).fetchone()
            
            if existing and existing["modified_at"] == mtime and existing["size_bytes"] == size_bytes:
                skipped += 1
            else:
                if existing:
                    db.execute("DELETE FROM file_hashes WHERE file_id=?", (existing["id"],))
                    db.execute("DELETE FROM media_files WHERE id=?", (existing["id"],))
                    db.commit()
                to_fingerprint.append((filepath, size_bytes, mtime))
        
        # Fingerprint in parallel (4 workers)
        fingerprint_results = {}
        with ProcessPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(_fingerprint_file_for_scan, fp): fp for fp, _, _ in to_fingerprint}
            
            for future in as_completed(futures):
                filepath = futures[future]
                try:
                    result = future.result()
                    fingerprint_results[filepath] = result
                except Exception as e:
                    print(f"  ❌ Parallel fingerprint error: {filepath}: {e}")
                    fingerprint_results[filepath] = None
        
        # Store results in database (single-threaded for safety)
        for filepath, size_bytes, mtime in to_fingerprint:
            try:
                db.execute("""
                    UPDATE scan_progress
                    SET processed=?, skipped=?, failed=?, current_file=?
                    WHERE id=?
                """, (processed, skipped, failed, os.path.basename(filepath), progress_id))
                db.commit()
                
                result = fingerprint_results.get(filepath)
                if result is None or result[2] is None:  # result[2] is phash_str
                    failed += 1
                    continue
                
                _, file_type, phash_str, audio_fp, _, _ = result
                ext = os.path.splitext(filepath)[1].lower()
                
                print(f"  {'🎬' if file_type == 'video' else '🖼️ '} {os.path.basename(filepath)}")
                
                file_id = db.execute("""
                    INSERT INTO media_files
                    (project_id, filepath, filename, extension, size_bytes,
                     file_type, status, indexed_at, modified_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'unanalyzed', ?, ?)
                """, (
                    project_id, filepath, os.path.basename(filepath),
                    ext, size_bytes, file_type,
                    datetime.now().isoformat(), mtime
                )).lastrowid

                db.execute(
                    "INSERT INTO file_hashes (file_id, phash, audio_fp) VALUES (?, ?, ?)",
                    (file_id, phash_str, audio_fp)
                )
                db.commit()
                processed += 1

            except Exception as e:
                print(f"  ❌ DB Error: {filepath}: {e}")
                failed += 1
                continue

        # Final stats
        total_size  = db.execute("SELECT SUM(size_bytes) as s FROM media_files WHERE project_id=?", (project_id,)).fetchone()["s"] or 0
        total_count = db.execute("SELECT COUNT(*) as c FROM media_files WHERE project_id=?", (project_id,)).fetchone()["c"]

        db.execute("""
            UPDATE projects SET total_files=?, total_size_bytes=?, status='scanned' WHERE id=?
        """, (total_count, total_size, project_id))

        db.execute("""
            UPDATE scan_progress SET status='complete', processed=?, skipped=?, failed=? WHERE id=?
        """, (processed, skipped, failed, progress_id))
        db.commit()

        _backup_database()

        print(f"\n✅ SCAN COMPLETE: {processed} indexed, {skipped} skipped, {failed} failed")
        return {"processed": processed, "skipped": skipped, "failed": failed, "total": total}

    except Exception as e:
        db.execute("UPDATE scan_progress SET status='error' WHERE id=?", (progress_id,))
        db.commit()
        print(f"❌ Scan failed: {e}")
        raise
    finally:
        db.close()


# ── Photo fingerprinting ──────────────────────────────────────────────────────

def fingerprint_photo(filepath: str) -> str | None:
    """
    Generate aspect-aware pHash for a photo.
    Stores full + center crop hash so horizontal→vertical edits are caught.
    """
    try:
        img   = Image.open(filepath).convert("RGB")
        w, h  = img.size
        ratio = w / h
        hashes = []

        # Always include full squished hash
        full = img.resize((512, 512), Image.LANCZOS)
        hashes.append(str(imagehash.phash(full, hash_size=16)))

        # For landscape photos — also store center portrait crop
        # Editor commonly crops horizontal photo to vertical for reels
        if ratio > 1.3:
            cx     = (w - h) // 2
            center = img.crop((cx, 0, cx + h, h)).resize((512, 512), Image.LANCZOS)
            hashes.append(str(imagehash.phash(center, hash_size=16)))
            # Also left and right thirds
            left  = img.crop((0, 0, h, h)).resize((512, 512), Image.LANCZOS)
            right = img.crop((w - h, 0, w, h)).resize((512, 512), Image.LANCZOS)
            hashes.append(str(imagehash.phash(left,  hash_size=16)))
            hashes.append(str(imagehash.phash(right, hash_size=16)))

        # For portrait photos — also store center landscape crop
        elif ratio < 0.7:
            cy     = (h - w) // 2
            center = img.crop((0, cy, w, cy + w)).resize((512, 512), Image.LANCZOS)
            hashes.append(str(imagehash.phash(center, hash_size=16)))

        return "|".join(hashes)
    except Exception as e:
        print(f"  ⚠️  Photo fingerprint failed: {e}")
        return None


# ── Video fingerprinting ──────────────────────────────────────────────────────

def fingerprint_video(filepath: str):
    """
    Full video fingerprint:
    - Visual: dense pHash sampling (every 0.25s–3s based on duration)
    - Audio: RMS energy + Zero Crossing Rate fingerprint

    KEY BEHAVIOUR: Dense enough sampling that even a 1-second
    sub-clip used from an 8-second raw clip will be detected.

    Returns (phash_str, audio_fp, duration, frame_count) or None
    """
    cap = cv2.VideoCapture(filepath)
    if not cap.isOpened():
        print(f"  ⚠️  OpenCV cannot open {os.path.basename(filepath)} — trying ffmpeg...")
        return _fingerprint_via_ffmpeg(filepath)

    native_fps   = cap.get(cv2.CAP_PROP_FPS) or 25
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_sec = total_frames / native_fps

    if duration_sec <= 0:
        cap.release()
        return _fingerprint_via_ffmpeg(filepath)

    interval     = _get_interval(duration_sec)
    sample_times = [round(i * interval, 3)
                    for i in range(int(duration_sec / interval) + 1)]

    hashes = []
    for t in sample_times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ret, frame = cap.read()
        if not ret:
            continue
        try:
            img   = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            img_r = img.resize((512, 512), Image.LANCZOS)
            hashes.append(str(imagehash.phash(img_r, hash_size=16)))
        except Exception:
            continue

    cap.release()

    if not hashes:
        return _fingerprint_via_ffmpeg(filepath)

    audio_fp = extract_audio_fingerprint(filepath)

    print(f"     → {len(hashes)} keyframes @ 1 frame/{interval}s | audio: {'✅' if audio_fp else '❌'}")
    return "|".join(hashes), audio_fp, duration_sec, len(hashes)


def _fingerprint_via_ffmpeg(filepath: str):
    """Fallback for exotic formats like RED .r3d, ARRI, Blackmagic."""
    try:
        tmp_dir = tempfile.mkdtemp()
        cmd = [
            "ffmpeg", "-i", filepath,
            "-vf", "fps=1",
            "-q:v", "3",
            os.path.join(tmp_dir, "frame_%04d.jpg"),
            "-y", "-loglevel", "quiet"
        ]
        subprocess.run(cmd, capture_output=True, timeout=120)

        hashes = []
        for fname in sorted(os.listdir(tmp_dir)):
            if fname.endswith(".jpg"):
                try:
                    img   = Image.open(os.path.join(tmp_dir, fname)).convert("RGB")
                    img_r = img.resize((512, 512), Image.LANCZOS)
                    hashes.append(str(imagehash.phash(img_r, hash_size=16)))
                except Exception:
                    pass

        for f in os.listdir(tmp_dir):
            try:
                os.remove(os.path.join(tmp_dir, f))
            except Exception:
                pass
        os.rmdir(tmp_dir)

        if not hashes:
            return None

        audio_fp = extract_audio_fingerprint(filepath)
        return "|".join(hashes), audio_fp, float(len(hashes)), len(hashes)

    except Exception as e:
        print(f"  ❌ ffmpeg fallback also failed: {e}")
        return None


# ── Audio fingerprinting ──────────────────────────────────────────────────────

def extract_audio_fingerprint(filepath: str) -> str | None:
    """
    Two-layer audio fingerprint using ffmpeg:
    Layer 1 — RMS energy envelope (volume over time)
    Layer 2 — Zero Crossing Rate (tonal texture over time)
    32 segments each → stored as "rms_vals;zcr_vals"
    OPTIMIZED: 8kHz sample rate + 32 segments = 45-50% faster
    """
    try:
        tmp = tempfile.mktemp(suffix=".wav")
        cmd = [
            "ffmpeg", "-i", filepath,
            "-ar", "8000",    # 8kHz sample rate (optimized from 16kHz)
            "-ac", "1",       # mono
            "-f", "wav",
            "-y", tmp,
            "-loglevel", "quiet"
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode != 0 or not os.path.exists(tmp):
            return None

        with wave.open(tmp, "rb") as wf:
            sampwidth = wf.getsampwidth()
            raw       = wf.readframes(wf.getnframes())

        os.remove(tmp)

        # Parse to numpy
        if sampwidth == 2:
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        elif sampwidth == 4:
            samples = np.frombuffer(raw, dtype=np.int32).astype(np.float32)
        else:
            samples = np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128

        if len(samples) == 0:
            return None

        N = 32  # Optimized from 64 segments
        seg_size = max(1, len(samples) // N)
        rms_vals = []
        zcr_vals = []

        for i in range(N):
            seg = samples[i * seg_size:(i + 1) * seg_size]
            if len(seg) == 0:
                rms_vals.append(0.0)
                zcr_vals.append(0.0)
                continue
            rms_vals.append(float(np.sqrt(np.mean(seg ** 2))))
            zcr_vals.append(float(np.sum(np.abs(np.diff(np.sign(seg)))) / (2 * len(seg))))

        # Normalize
        max_rms = max(rms_vals) or 1.0
        max_zcr = max(zcr_vals) or 1.0
        rms_str = ",".join(str(round(v / max_rms, 4)) for v in rms_vals)
        zcr_str = ",".join(str(round(v / max_zcr, 4)) for v in zcr_vals)

        return f"{rms_str};{zcr_str}"

    except Exception as e:
        print(f"  ⚠️  Audio fingerprint failed: {e}")
        return None


def compare_audio_fingerprints(fp1: str, fp2: str) -> float:
    """Compare two audio fingerprints. Returns 0-100 similarity."""
    try:
        if not fp1 or not fp2:
            return 0.0

        def parse(fp):
            parts = fp.split(";")
            return (
                np.array([float(x) for x in parts[0].split(",")]),
                np.array([float(x) for x in parts[1].split(",")])
            )

        rms1, zcr1 = parse(fp1)
        rms2, zcr2 = parse(fp2)
        n = min(len(rms1), len(rms2))
        if n == 0:
            return 0.0

        rms_sim = max(0.0, (1 - float(np.mean(np.abs(rms1[:n] - rms2[:n])))) * 100)
        zcr_sim = max(0.0, (1 - float(np.mean(np.abs(zcr1[:n] - zcr2[:n])))) * 100)

        # RMS 60%, ZCR 40%
        return round(rms_sim * 0.6 + zcr_sim * 0.4, 2)

    except Exception:
        return 0.0


def get_scan_progress(project_id: int) -> dict:
    db  = get_db()
    row = db.execute(
        "SELECT * FROM scan_progress WHERE project_id=? ORDER BY id DESC LIMIT 1",
        (project_id,)
    ).fetchone()
    db.close()

    if not row:
        return {"status": "idle"}

    total   = row["total_found"] or 1
    proc    = row["processed"] or 0
    percent = round((proc / total) * 100, 1)

    return {
        "status":       row["status"],
        "total":        row["total_found"],
        "processed":    proc,
        "skipped":      row["skipped"],
        "failed":       row["failed"],
        "current_file": row["current_file"],
        "percent":      percent,
    }


def _backup_database():
    try:
        import shutil
        db_path    = os.path.join(os.path.dirname(__file__), "..", "framevault.db")
        backup_dir = os.path.join(os.path.dirname(__file__), "..", "backups")
        os.makedirs(backup_dir, exist_ok=True)
        dest = os.path.join(backup_dir, f"framevault_{datetime.now().strftime('%Y%m%d')}.db")
        shutil.copy2(db_path, dest)
        backups = sorted(f for f in os.listdir(backup_dir) if f.endswith(".db"))
        while len(backups) > 7:
            os.remove(os.path.join(backup_dir, backups.pop(0)))
        print(f"💾 Backup → {dest}")
    except Exception as e:
        print(f"⚠️  Backup failed: {e}")
