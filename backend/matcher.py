import os
import cv2
import numpy as np
import imagehash
from PIL import Image
import time
from datetime import datetime
from database import get_db
from scanner import (
    extract_audio_fingerprint,
    compare_audio_fingerprints,
    fingerprint_photo,
    SUPPORTED_VIDEOS,
)

analysis_progress_dict = {}
cancelled_analyses = set()

def get_analysis_progress(project_id: int) -> dict:
    return analysis_progress_dict.get(project_id, {"status": "idle"})

def cancel_analysis(project_id: int):
    cancelled_analyses.add(project_id)

TEMP_DIR = os.path.join(os.path.dirname(__file__), "..", "temp", "frames")

# ── Confidence thresholds ─────────────────────────────────────────────────────
USED_THRESHOLD   = 93.0   # Above this = USED
REVIEW_THRESHOLD = 85.0   # Above this = REVIEW, below = UNUSED

# Weight: audio now carries more influence in final classification
# Visual still primary, but audio acts as stronger confirming/rejecting signal
VISUAL_WEIGHT = 0.50
AUDIO_WEIGHT  = 0.50

# FPS modes for extracting frames from the FINAL AD
FPS_MODES = {
    "quick":    4,
    "standard": 8,
    "high":     15,
    "maximum":  24,
    "adaptive": None,
}


# ── Main analysis entry point ─────────────────────────────────────────────────

def analyze_video(project_id: int, video_id: int, video_path: str, fps_mode: str = "adaptive", ad_type: str = "video_with_audio"):
    """
    Core logic:
    1. Extract frames from final ad at high FPS (up to 24fps)
    2. Extract audio fingerprint from final ad (if ad_type is 'video_with_audio')
    3. For every raw file (photo or video clip):
       - Photos: compare single hash against all ad frames
       - Videos: compare ALL keyframe hashes against all ad frames
                 → If ANY single frame of the raw clip matches ANY
                   frame of the final ad above threshold, the ENTIRE
                   raw clip is marked USED
    4. Classify: USED / REVIEW / UNUSED
    
    ad_type:
       - 'video_with_audio': Use balanced audio + visual (60% visual, 40% audio)
       - 'acted_ads': Use audio-prioritized matching (40% visual, 60% audio)
         → For dialogue-heavy ads where audio/sound is critical for identification
       - 'product_photoshoot': Use ONLY visual hashing (100% weight)
         → Audio fingerprinting is completely disabled
         → Applied to ALL raw files (photos AND videos)
         → Even video files in product photoshoots won't be audio-compared
    """
    db = get_db()
    os.makedirs(TEMP_DIR, exist_ok=True)

    # ── Determine weights based on ad_type ────────────────────────────────────
    if ad_type == "product_photoshoot":
        visual_weight = 1.0
        audio_weight = 0.0
        print(f"\n🖼️  AD TYPE: Product Photoshoot")
        print(f"   → Using IMAGE HASHING ONLY (100% visual weight)")
        print(f"   → Audio fingerprinting COMPLETELY DISABLED")
        print(f"   → Applies to ALL files (photos AND videos - raw audio is ignored)\n")
    elif ad_type == "acted_ads":
        visual_weight = 0.40
        audio_weight = 0.60
        print(f"\n🎭 AD TYPE: Acted Ads (High Audio Importance)")
        print(f"   → Using AUDIO-PRIMARY matching (40% visual, 60% audio)")
        print(f"   → Audio fingerprinting PRIORITIZED (dialogue/sound critical)\n")
    else:  # video_with_audio (default)
        visual_weight = 0.60
        audio_weight = 0.40
        print(f"\n🎥 AD TYPE: Video with Audio")
        print(f"   → Using BALANCED matching (60% visual, 40% audio)")
        print(f"   → Audio fingerprinting ENABLED\n")

    try:
        print(f"{'='*60}")
        print(f"🎬 ANALYSIS START")
        print(f"   File: {os.path.basename(video_path)}")
        print(f"   Mode: {fps_mode}")
        print(f"{'='*60}\n")

        analysis_progress_dict[project_id] = {
            "status": "extracting",
            "total": 0,
            "processed": 0,
            "current_file": "",
            "percent": 0.0,
            "current_time": 0,
            "duration": 0,
            "phase": "Initializing..."
        }

        _set_status(db, video_id, "extracting")

        # Step 1 — Extract frames from final ad
        print("📽️  Extracting frames from final ad...")
        ad_frames = _extract_ad_frames(video_path, fps_mode, project_id)
        print(f"   ✅ {len(ad_frames)} frames extracted\n")

        # Step 2 — Extract audio from final ad (only when audio_weight > 0)
        # Applies to: video_with_audio, acted_ads
        # Skips: product_photoshoot
        if audio_weight > 0:
            print("🎵  Extracting audio from final ad...")
            ad_audio_fp = extract_audio_fingerprint(video_path)
            print(f"   {'✅ Audio fingerprint ready' if ad_audio_fp else '⚠️  No audio detected'}\n")
        else:
            ad_audio_fp = None
            print("🎵  Skipping audio extraction (audio not used for this ad type)\n")

        _set_status(db, video_id, "matching")

        # Step 3 — Load all raw files from library
        raw_files = db.execute("""
            SELECT mf.id, mf.filepath, mf.filename, mf.file_type,
                   mf.size_bytes, fh.phash, fh.audio_fp
            FROM media_files mf
            JOIN file_hashes fh ON fh.file_id = mf.id
            WHERE mf.project_id = ? AND mf.protected = 0
              AND mf.status != 'trashed'
        """, (project_id,)).fetchall()

        print(f"🔍  Matching {len(raw_files)} raw files against {len(ad_frames)} ad frames...\n")

        photos_count = sum(1 for r in raw_files if r["file_type"] == "photo")
        videos_count = sum(1 for r in raw_files if r["file_type"] == "video")
        print(f"   📷 Photos: {photos_count}  🎬 Videos: {videos_count}\n")

        total_files = len(raw_files)
        # Get the duration from extraction phase (already stored)
        current_duration = analysis_progress_dict[project_id].get("duration", 0)
        analysis_progress_dict[project_id].update({
            "status": "matching",
            "total": total_files,
            "processed": 0,
            "percent": 30.0,   # global range: matching = 30-80%
            "current_file": "",
            "duration": current_duration,
            "phase": "Matching files..."
        })

        match_scores = {}
        
        # OPTIMIZATION: Pre-cache all audio fingerprints to avoid repeated list comprehensions
        audio_fp_cache = {}
        for raw in raw_files:
            if raw["file_type"] == "video" and raw["audio_fp"]:
                audio_fp_cache[raw["id"]] = raw["audio_fp"]

        # Pre-compute ad frames boolean matrix
        ad_hashes_bools = []
        ad_frame_seconds = []
        ad_hash_weights = []
        
        for frame in ad_frames:
            ad_hashes_bools.append(frame["phash_obj"].hash.flatten())
            ad_frame_seconds.append(frame["timestamp_sec"])
            ad_hash_weights.append(1.0)
            
            for rh in frame.get("region_hashes", []):
                ad_hashes_bools.append(rh.hash.flatten())
                ad_frame_seconds.append(frame["timestamp_sec"])
                ad_hash_weights.append(0.85)  # cropped matches are slightly less certain
            
        if ad_hashes_bools:
            ad_matrix = np.array(ad_hashes_bools, dtype=bool)
            ad_weights = np.array(ad_hash_weights, dtype=float)
            ad_seconds = np.array(ad_frame_seconds, dtype=float)
        else:
            ad_matrix = np.empty((0, 256), dtype=bool)

        for idx, raw in enumerate(raw_files):
            time.sleep(0.001)  # explicit GIL yield allows API to serve live UI updates
            
            if project_id in cancelled_analyses:
                raise Exception("Analysis cancelled by user")
            
            file_id   = raw["id"]
            filename  = raw["filename"]
            file_type = raw["file_type"]
            raw_hashes = raw["phash"].split("|") if raw["phash"] else []

            analysis_progress_dict[project_id].update({
                "processed": idx,
                "current_file": filename,
                # global range: matching = 30-80% (50 point span)
                "percent": round(30 + (idx / total_files) * 50, 1) if total_files else 30.0
            })

            if not raw_hashes:
                match_scores[file_id] = {"confidence": 0.0, "visual": 0.0, "audio": 0.0, "second": 0.0}
                continue

            # ── VISUAL MATCHING ───────────────────────────────────────────────
            # For videos: compare EVERY keyframe hash against EVERY ad frame
            # The best single match across all keyframes wins
            # → If 1 second of an 8-second clip appears in the ad, it gets detected
            best_visual = 0.0
            best_second = 0.0

            # Pre-convert raw hashes to boolean flat arrays
            raw_hashes_bools = []
            for rh_str in raw_hashes:
                try:
                    obj = imagehash.hex_to_hash(rh_str)
                    flat = obj.hash.flatten()
                    # Only append if shape matches ad_matrix (prevent broadcast crashes from legacy DB hashes)
                    if flat.size == 256:
                        raw_hashes_bools.append(flat)
                except Exception:
                    pass

            if raw_hashes_bools and ad_matrix.shape[0] > 0:
                raw_matrix = np.array(raw_hashes_bools, dtype=bool)
                for r_idx in range(raw_matrix.shape[0]):
                    r_hash = raw_matrix[r_idx]
                    
                    # Vectorized Hamming distance against ALL ad frames AND region crops
                    diffs = ad_matrix != r_hash
                    dists = np.count_nonzero(diffs, axis=1)
                    
                    sims = (1.0 - dists / 256.0) * 100.0 * ad_weights
                    max_sim = np.max(sims)
                    
                    if max_sim > best_visual:
                        best_visual = max_sim
                        best_dist_idx = np.argmax(sims)
                        best_second = ad_seconds[best_dist_idx]
                    
                    if best_visual >= 99.0:
                        break

            # ── AUDIO MATCHING (videos only) ──────────────────────────────────
            # Compare audio envelope of raw clip against final ad audio
            # For product_photoshoot: ad_audio_fp is None, so audio comparison
            #   is skipped entirely (even if raw files are videos)
            # For video_with_audio: compares audio if available (40% weight)
            # For acted_ads: compares audio if available (60% weight - prioritized)
            # OPTIMIZATION: Skip if visual already 99%+ confident
            audio_score = 0.0
            if file_type == "video" and ad_audio_fp and best_visual < 99.0:
                raw_audio_fp = audio_fp_cache.get(file_id)
                if raw_audio_fp:
                    audio_score = compare_audio_fingerprints(raw_audio_fp, ad_audio_fp)

            # ── COMBINED SCORE ────────────────────────────────────────────────
            # If audio is available and audio_weight > 0: weighted combination
            # Otherwise: visual only
            if audio_score > 0 and file_type == "video" and audio_weight > 0:
                final_score = (best_visual * visual_weight) + (audio_score * audio_weight)
            else:
                final_score = best_visual

            # Clamp to 100
            final_score = min(final_score, 100.0)

            match_scores[file_id] = {
                "confidence": round(final_score, 2),
                "visual":     round(best_visual, 2),
                "audio":      round(audio_score, 2),
                "second":     best_second,
            }

            # Log result
            icon = "✅" if final_score >= USED_THRESHOLD else ("⚠️" if final_score >= REVIEW_THRESHOLD else "❌")
            tag  = "🎬" if file_type == "video" else "🖼️ "
            n_kf = len(raw_hashes_bools)
            print(f"  {icon} {tag} {filename[:40]:<40} "
                  f"kf:{n_kf:>3} V:{best_visual:5.1f}% "
                  f"{'A:'+str(audio_score)+'%' if audio_score>0 else '':>10} "
                  f"→ {final_score:5.1f}%")

        # Step 4 — Classify and save
        print(f"\n📊  Classifying and saving results...\n")
        
        # Update progress to show classification phase
        analysis_progress_dict[project_id].update({
            "status": "classifying",
            "phase": "Classifying results...",
            "percent": 80.0,   # global range: classifying = 80-100%
            "processed": 0,
            "total": len(raw_files)
        })
        
        used = unused = review = 0
        total_to_classify = len(raw_files)

        for classify_idx, raw in enumerate(raw_files):
            time.sleep(0.001)  # explicit GIL yield allows API to serve live UI updates
            
            if project_id in cancelled_analyses:
                raise Exception("Analysis cancelled by user")
            
            file_id    = raw["id"]
            score      = match_scores.get(file_id, {"confidence": 0.0, "second": 0.0})
            confidence = score["confidence"]
            second     = score["second"]

            if confidence >= USED_THRESHOLD:
                status = "used";   used   += 1
            elif confidence >= REVIEW_THRESHOLD:
                status = "review"; review += 1
            else:
                status = "unused"; unused += 1

            db.execute(
                "UPDATE media_files SET status=?, confidence=? WHERE id=?",
                (status, confidence, file_id)
            )

            if confidence >= REVIEW_THRESHOLD:
                db.execute("""
                    INSERT OR REPLACE INTO matches
                    (file_id, video_id, confidence, matched_at_second)
                    VALUES (?, ?, ?, ?)
                """, (file_id, video_id, confidence, second))
            
            # Update progress during classification
            analysis_progress_dict[project_id].update({
                "processed": classify_idx + 1,
                "total": total_to_classify,
                # global range: classifying = 80-100% (20 point span)
                "percent": round(80 + ((classify_idx + 1) / total_to_classify) * 20, 1) if total_to_classify else 80.0,
                "current_file": raw["filename"]
            })

        # Step 5 — Update project stats
        unused_size = db.execute("""
            SELECT SUM(size_bytes) as s FROM media_files
            WHERE project_id=? AND status='unused'
        """, (project_id,)).fetchone()["s"] or 0

        used_size = db.execute("""
            SELECT SUM(size_bytes) as s FROM media_files
            WHERE project_id=? AND status='used'
        """, (project_id,)).fetchone()["s"] or 0

        review_size = db.execute("""
            SELECT SUM(size_bytes) as s FROM media_files
            WHERE project_id=? AND status='review'
        """, (project_id,)).fetchone()["s"] or 0

        db.execute("""
            UPDATE projects
            SET used_files=?, unused_files=?, review_files=?,
                used_size_bytes=?, unused_size_bytes=?, review_size_bytes=?, status='analyzed'
            WHERE id=?
        """, (used, unused, review, used_size, unused_size, review_size, project_id))

        db.commit()
        _set_status(db, video_id, "complete")
        _cleanup_temp()

        print(f"\n{'='*60}")
        print(f"✅ ANALYSIS COMPLETE")
        print(f"   ✅ Used:   {used} files → {used_size/1024/1024:.0f} MB")
        print(f"   ⚠️  Review: {review} files → {review_size/1024/1024:.0f} MB")
        print(f"   ❌ Unused: {unused} files → {unused_size/1024/1024:.0f} MB")
        print(f"   💾 Reclaimable: {unused_size/1024/1024:.0f} MB")
        print(f"{'='*60}\n")
        
        return {
            "used": used, "unused": unused, "review": review,
            "used_size": used_size, "unused_size": unused_size, "review_size": review_size
        }

    except Exception as e:
        if str(e) == "Analysis cancelled by user":
            print(f"🛑 Analysis cancelled for project {project_id}")
            _set_status(db, video_id, "error")
        else:
            _set_status(db, video_id, "error")
            import traceback
            print(f"❌ Analysis failed: {e}")
            traceback.print_exc()
        db.commit()
        raise
    finally:
        if project_id in analysis_progress_dict:
            del analysis_progress_dict[project_id]
        if project_id in cancelled_analyses:
            cancelled_analyses.discard(project_id)
        db.close()


# ── Extract frames from final ad video ───────────────────────────────────────

def _extract_ad_frames(video_path: str, fps_mode: str, project_id: int) -> list:
    """
    Extract frames from the final compiled ad.
    High FPS to catch every moment — up to 24fps.
    Each frame stores a pre-parsed imagehash object for fast comparison.
    Also stores region hashes (9 zones) for composite detection.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    native_fps   = cap.get(cv2.CAP_PROP_FPS) or 25
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_sec = total_frames / native_fps

    print(f"   Duration: {duration_sec:.1f}s | Native: {native_fps:.0f}fps")

    # Build timestamp list
    if fps_mode == "adaptive":
        timestamps = _adaptive_timestamps(cap, duration_sec, native_fps, project_id)
    else:
        target_fps = FPS_MODES.get(fps_mode, 8)
        interval   = 1.0 / target_fps
        timestamps = [round(i * interval, 4)
                      for i in range(int(duration_sec / interval) + 1)]

    print(f"   Extracting {len(timestamps)} frames ({fps_mode} mode)...")

    frames = []
    for t in timestamps:
        time.sleep(0.001)  # explicit GIL yield allows API to serve live UI updates
        
        if project_id in cancelled_analyses:
            raise Exception("Analysis cancelled by user")
            
        if project_id in analysis_progress_dict:
            
            analysis_progress_dict[project_id].update({
                "status": "extracting",
                # global range: extracting = 0-30%
                # adaptive: scene-scan uses 0-15%, so hashing uses 15-30%
                # non-adaptive: hashing goes full 0-30%
                "percent": round(
                    (15.0 if fps_mode == "adaptive" else 0.0)
                    + ((t / duration_sec) * (0.5 if fps_mode == "adaptive" else 1.0)) * 30,
                    1
                ) if duration_sec else 0.0,
                "current_time": round(t, 2),
                "duration": round(duration_sec, 2),
                "phase": "Hashing frames..."
            })
            
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ret, frame = cap.read()
        if not ret:
            continue

        try:
            # OpenCV resize is dramatically faster than PIL Lanczos for high volumes
            frame_resized = cv2.resize(frame, (512, 512), interpolation=cv2.INTER_AREA)
            img    = Image.fromarray(cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB))
            
            ph     = imagehash.phash(img, hash_size=16)
            region_hashes = _region_hashes(img)

            frames.append({
                "timestamp_sec": t,
                "phash_obj":     ph,
                "region_hashes": region_hashes
            })

        except Exception:
            continue

    cap.release()
    return frames


def _adaptive_timestamps(cap, duration_sec: float, native_fps: float, project_id: int) -> list:
    """
    Adaptive extraction:
    Base: 8fps throughout entire ad
    Burst: 24fps for ±0.5s around every scene cut
    This maximises frame coverage at edit points.
    """
    timestamps = set()

    # Base 8fps
    t = 0.0
    while t <= duration_sec:
        timestamps.add(round(t, 4))
        t += 1.0 / 8

    # Scene cut detection
    prev_gray   = None
    scene_cuts  = []
    sample_step = max(1, int(native_fps / 4))
    total_vid   = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    for frame_num in range(0, total_vid, sample_step):
        time.sleep(0.001)  # explicit GIL yield allows API to serve live UI updates
        
        if project_id in cancelled_analyses:
            raise Exception("Analysis cancelled by user")
            
        t = frame_num / native_fps
        if project_id in analysis_progress_dict:
            # global range: scene scanning = 0-15% (first half of the 0-30% extraction range)
            analysis_progress_dict[project_id].update({
                "status": "extracting",
                "percent": round(((t / duration_sec) * 0.5) * 30, 1) if duration_sec else 0.0,
                "current_time": round(t, 2),
                "duration": round(duration_sec, 2),
                "phase": "Scanning scenes..."
            })
            
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        if not ret:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (64, 64))
        if prev_gray is not None:
            diff = float(np.mean(np.abs(gray.astype(float) - prev_gray.astype(float))))
            if diff > 20:
                scene_cuts.append(frame_num / native_fps)
        prev_gray = gray

    print(f"   ✂️  {len(scene_cuts)} scene cuts detected — adding 24fps burst zones")

    # 24fps burst around each cut
    for cut_t in scene_cuts:
        t = max(0.0, cut_t - 0.5)
        while t <= min(duration_sec, cut_t + 0.5):
            timestamps.add(round(t, 4))
            t += 1.0 / 24

    return sorted(timestamps)


def _region_hashes(img512: Image.Image) -> list:
    """Split 512x512 into 9 zones, return hash objects with hash_size=16 for numpy."""
    w, h   = img512.size
    rw, rh = w // 3, h // 3
    hashes = []
    for row in range(3):
        for col in range(3):
            region = img512.crop((col * rw, row * rh, (col + 1) * rw, (row + 1) * rh))
            hashes.append(imagehash.phash(region, hash_size=16))
    return hashes


def _set_status(db, video_id, status):
    db.execute("UPDATE final_videos SET analysis_status=? WHERE id=?", (status, video_id))
    db.commit()


def detect_duplicates(project_id: int):
    """
    Detect duplicate files with confidence > 97% match.
    Mark earliest (by modification time) with higher quality as original.
    Others marked as duplicates linked to original.
    """
    db = get_db()
    try:
        # Get all files with hash info
        files = db.execute("""
            SELECT mf.id, mf.filename, mf.file_type, mf.modified_at, fh.phash
            FROM media_files mf
            JOIN file_hashes fh ON fh.file_id = mf.id
            WHERE mf.project_id = ? AND mf.status != 'trashed' AND mf.protected = 0
            ORDER BY mf.modified_at ASC
        """, (project_id,)).fetchall()

        if not files or len(files) < 2:
            print("Not enough files to detect duplicates")
            return

        # Group by perceptual hash similarity
        groups = []  # [ [file1, file2, ...], ...]
        processed = set()

        for i, file1 in enumerate(files):
            if file1['id'] in processed:
                continue
                
            group = [file1]
            processed.add(file1['id'])

            if not file1['phash']:
                continue

            # Compare against remaining files
            hash1_str = file1['phash'].split('|')[0]  # Get first keyframe hash
            try:
                hash1_obj = imagehash.hex_to_hash(hash1_str)
                hash1_bool = hash1_obj.hash.flatten()
            except Exception:
                continue

            for j, file2 in enumerate(files[i+1:], start=i+1):
                if file2['id'] in processed or not file2['phash']:
                    continue

                hash2_str = file2['phash'].split('|')[0]
                try:
                    hash2_obj = imagehash.hex_to_hash(hash2_str)
                    hash2_bool = hash2_obj.hash.flatten()

                    # Calculate similarity
                    if hash1_bool.size == hash2_bool.size == 256:
                        diffs = hash1_bool != hash2_bool
                        dist = np.count_nonzero(diffs)
                        similarity = (1.0 - dist / 256.0) * 100.0

                        if similarity > 97.0:
                            group.append(file2)
                            processed.add(file2['id'])
                except Exception:
                    continue

            if len(group) > 1:
                groups.append(group)

        # Process groups: mark originals and duplicates
        duplicates_count = 0
        for group in groups:
            # Sort by: 1) earlier mod time, 2) smaller file size (higher quality)
            group.sort(key=lambda f: (f['modified_at'] or 0, f['id']))
            original = group[0]

            print(f"\n🔗 Duplicate Group ({len(group)} files):")
            print(f"   📌 Original: {original['filename']} (ID: {original['id']})")

            # Mark original
            db.execute(
                "UPDATE media_files SET is_original=1, original_id=NULL WHERE id=?",
                (original['id'],)
            )

            # Mark duplicates
            for dup in group[1:]:
                db.execute(
                    "UPDATE media_files SET is_original=0, original_id=? WHERE id=?",
                    (original['id'], dup['id'])
                )
                print(f"      🔀 Duplicate: {dup['filename']} (ID: {dup['id']})")
                duplicates_count += 1

        db.commit()
        print(f"\n✅ Detected {duplicates_count} duplicate files across {len(groups)} groups")
        return duplicates_count

    except Exception as e:
        print(f"❌ Duplicate detection failed: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


def _cleanup_temp():
    if os.path.exists(TEMP_DIR):
        for f in os.listdir(TEMP_DIR):
            try:
                os.remove(os.path.join(TEMP_DIR, f))
            except Exception:
                pass


def get_analysis_status(video_id: int) -> dict:
    db  = get_db()
    row = db.execute(
        "SELECT analysis_status FROM final_videos WHERE id=?", (video_id,)
    ).fetchone()
    db.close()
    return {"status": row["analysis_status"] if row else "not_found"}
