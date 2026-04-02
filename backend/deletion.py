import os
import shutil
from datetime import datetime, timedelta
from database import get_db

TRASH_DIR      = os.path.join(os.path.dirname(__file__), '..', 'trash')
REPORTS_DIR    = os.path.join(os.path.dirname(__file__), '..', 'reports')
DEFAULT_EXPIRY = 30  # days


def move_to_trash(file_ids: list, expiry_days: int = DEFAULT_EXPIRY) -> dict:
    """
    Safely move files to trash folder.
    Never permanently deletes - just moves aside.
    """
    db = get_db()
    os.makedirs(TRASH_DIR, exist_ok=True)

    moved    = []
    failed   = []
    freed_bytes = 0

    for file_id in file_ids:
        row = db.execute(
            "SELECT * FROM media_files WHERE id=?",
            (file_id,)
        ).fetchone()

        if not row:
            failed.append({'id': file_id, 'reason': 'not found in database'})
            continue

        if row['protected']:
            failed.append({'id': file_id, 'reason': 'file is protected'})
            continue

        original_path = row['filepath']

        if not os.path.exists(original_path):
            # File already gone — just mark in DB
            db.execute(
                "UPDATE media_files SET status='missing' WHERE id=?",
                (file_id,)
            )
            db.commit()
            failed.append({'id': file_id, 'reason': 'file not found on disk'})
            continue

        try:
            # Build trash path preserving folder structure
            # e.g. D:/AdShoots/Nike/photo.jpg → trash/Nike/photo.jpg
            rel_path   = os.path.relpath(original_path, os.path.dirname(original_path))
            trash_path = os.path.join(
                TRASH_DIR,
                f"project_{row['project_id']}",
                str(file_id) + '_' + row['filename']
            )

            os.makedirs(os.path.dirname(trash_path), exist_ok=True)
            shutil.move(original_path, trash_path)

            expires_at = (datetime.now() + timedelta(days=expiry_days)).isoformat()

            # Record in trash table
            db.execute("""
                INSERT INTO trash
                (file_id, original_path, trash_path, expires_at)
                VALUES (?, ?, ?, ?)
            """, (file_id, original_path, trash_path, expires_at))

            db.execute(
                "UPDATE media_files SET status='trashed' WHERE id=?",
                (file_id,)
            )

            freed_bytes += row['size_bytes']
            moved.append({
                'id':       file_id,
                'filename': row['filename'],
                'size':     row['size_bytes']
            })

        except Exception as e:
            failed.append({'id': file_id, 'reason': str(e)})

    db.commit()
    db.close()

    return {
        'moved':       len(moved),
        'failed':      len(failed),
        'freed_bytes': freed_bytes,
        'details':     moved,
        'errors':      failed
    }


def restore_from_trash(file_ids: list) -> dict:
    """Restore files from trash back to original location."""
    db = get_db()
    restored = []
    failed   = []

    for file_id in file_ids:
        trash_row = db.execute(
            "SELECT * FROM trash WHERE file_id=? AND restored=0 AND permanently_deleted=0",
            (file_id,)
        ).fetchone()

        if not trash_row:
            failed.append({'id': file_id, 'reason': 'not in trash'})
            continue

        try:
            trash_path    = trash_row['trash_path']
            original_path = trash_row['original_path']

            if not os.path.exists(trash_path):
                failed.append({'id': file_id, 'reason': 'trash file missing from disk'})
                continue

            # Recreate original directory if needed
            os.makedirs(os.path.dirname(original_path), exist_ok=True)
            shutil.move(trash_path, original_path)

            db.execute(
                "UPDATE trash SET restored=1 WHERE id=?",
                (trash_row['id'],)
            )
            db.execute(
                "UPDATE media_files SET status='unanalyzed' WHERE id=?",
                (file_id,)
            )

            restored.append(file_id)

        except Exception as e:
            failed.append({'id': file_id, 'reason': str(e)})

    db.commit()
    db.close()

    return {'restored': len(restored), 'failed': len(failed), 'errors': failed}


def permanent_delete(file_ids: list) -> dict:
    """Permanently delete files from trash. Cannot be undone."""
    db = get_db()
    deleted      = []
    failed       = []
    freed_bytes  = 0

    for file_id in file_ids:
        trash_row = db.execute(
            "SELECT t.*, mf.size_bytes FROM trash t JOIN media_files mf ON mf.id=t.file_id WHERE t.file_id=?",
            (file_id,)
        ).fetchone()

        if not trash_row:
            failed.append({'id': file_id, 'reason': 'not in trash'})
            continue

        try:
            trash_path = trash_row['trash_path']
            if os.path.exists(trash_path):
                os.remove(trash_path)

            freed_bytes += trash_row['size_bytes'] or 0

            db.execute(
                "UPDATE trash SET permanently_deleted=1 WHERE file_id=?",
                (file_id,)
            )
            deleted.append(file_id)

        except Exception as e:
            failed.append({'id': file_id, 'reason': str(e)})

    db.commit()
    db.close()

    return {
        'deleted':     len(deleted),
        'failed':      len(failed),
        'freed_bytes': freed_bytes,
        'errors':      failed
    }


def run_expiry_cleanup() -> dict:
    """Auto-expire and permanently delete old trash items."""
    db = get_db()
    now  = datetime.now().isoformat()
    rows = db.execute("""
        SELECT t.file_id, t.trash_path FROM trash t
        WHERE t.expires_at <= ? AND t.restored=0 AND t.permanently_deleted=0
    """, (now,)).fetchall()

    cleaned     = 0
    freed_bytes = 0

    for row in rows:
        try:
            if os.path.exists(row['trash_path']):
                size = os.path.getsize(row['trash_path'])
                os.remove(row['trash_path'])
                freed_bytes += size

            db.execute(
                "UPDATE trash SET permanently_deleted=1 WHERE file_id=?",
                (row['file_id'],)
            )
            cleaned += 1
        except Exception:
            pass

    db.commit()
    db.close()
    return {'expired_deleted': cleaned, 'freed_bytes': freed_bytes}


def get_trash_list(project_id: int = None) -> list:
    """Get all items currently in trash."""
    db = get_db()
    query = """
        SELECT t.*, mf.filename, mf.file_type, mf.size_bytes, mf.project_id
        FROM trash t
        JOIN media_files mf ON mf.id = t.file_id
        WHERE t.restored=0 AND t.permanently_deleted=0
    """
    params = []
    if project_id:
        query  += " AND mf.project_id=?"
        params.append(project_id)

    rows   = db.execute(query, params).fetchall()
    result = [dict(r) for r in rows]
    db.close()
    return result


def toggle_protect(file_id: int, protected: bool) -> dict:
    """Mark a file as protected (will never be deleted)."""
    db = get_db()
    db.execute(
        "UPDATE media_files SET protected=? WHERE id=?",
        (1 if protected else 0, file_id)
    )
    db.commit()
    db.close()
    return {'file_id': file_id, 'protected': protected}
