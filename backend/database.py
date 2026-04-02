import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'framevault.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            raw_folder TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            status TEXT DEFAULT 'idle',
            total_files INTEGER DEFAULT 0,
            used_files INTEGER DEFAULT 0,
            unused_files INTEGER DEFAULT 0,
            review_files INTEGER DEFAULT 0,
            total_size_bytes INTEGER DEFAULT 0,
            unused_size_bytes INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS media_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            filepath TEXT NOT NULL,
            filename TEXT NOT NULL,
            extension TEXT,
            size_bytes INTEGER DEFAULT 0,
            file_type TEXT,
            status TEXT DEFAULT 'unanalyzed',
            confidence REAL DEFAULT 0,
            protected INTEGER DEFAULT 0,
            indexed_at TEXT,
            modified_at REAL,
            is_original INTEGER DEFAULT 0,
            original_id INTEGER,
            FOREIGN KEY (project_id) REFERENCES projects(id),
            FOREIGN KEY (original_id) REFERENCES media_files(id)
        );

        CREATE TABLE IF NOT EXISTS file_hashes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            phash TEXT,
            audio_fp TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (file_id) REFERENCES media_files(id)
        );

        CREATE TABLE IF NOT EXISTS final_videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            uploaded_at TEXT DEFAULT (datetime('now')),
            fps_mode TEXT DEFAULT 'adaptive',
            analysis_status TEXT DEFAULT 'pending',
            ad_type TEXT DEFAULT 'video_with_audio',
            FOREIGN KEY (project_id) REFERENCES projects(id)
        );

        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            video_id INTEGER NOT NULL,
            confidence REAL DEFAULT 0,
            matched_at_second REAL,
            FOREIGN KEY (file_id) REFERENCES media_files(id),
            FOREIGN KEY (video_id) REFERENCES final_videos(id)
        );

        CREATE TABLE IF NOT EXISTS trash (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            original_path TEXT NOT NULL,
            trash_path TEXT NOT NULL,
            deleted_at TEXT DEFAULT (datetime('now')),
            expires_at TEXT,
            restored INTEGER DEFAULT 0,
            permanently_deleted INTEGER DEFAULT 0,
            FOREIGN KEY (file_id) REFERENCES media_files(id)
        );

        CREATE TABLE IF NOT EXISTS scan_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            total_found INTEGER DEFAULT 0,
            processed INTEGER DEFAULT 0,
            skipped INTEGER DEFAULT 0,
            failed INTEGER DEFAULT 0,
            current_file TEXT DEFAULT '',
            status TEXT DEFAULT 'running',
            started_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (project_id) REFERENCES projects(id)
        );

        CREATE INDEX IF NOT EXISTS idx_media_project ON media_files(project_id);
        CREATE INDEX IF NOT EXISTS idx_media_status ON media_files(status);
        CREATE INDEX IF NOT EXISTS idx_hashes_file ON file_hashes(file_id);
        CREATE INDEX IF NOT EXISTS idx_matches_file ON matches(file_id);
    """)
    conn.commit()
    conn.close()
    print("✅ Database initialized")
