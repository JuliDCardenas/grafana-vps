import sqlite3
import os
import tempfile
from datetime import datetime, timezone
import shutil
import contextlib

SOURCE_DB_PATH = os.getenv("SOURCE_DB_PATH", "/var/lib/coding-jobs/jules_jobs.db")
DEST_DB_PATH = os.getenv("DEST_DB_PATH", "/var/lib/grafana-sqlite/exported_jobs.db")

def export_db():
    now = datetime.now(timezone.utc).isoformat()
    dest_dir = os.path.dirname(DEST_DB_PATH)
    os.makedirs(dest_dir, exist_ok=True)

    # Pre-check source existence
    if not os.path.exists(SOURCE_DB_PATH):
        print(f"[{now}] Source DB not found.")
        update_metadata_safe(now, "SOURCE_UNAVAILABLE")
        return

    # We will write to a temp file first
    fd, temp_dest_path = tempfile.mkstemp(dir=dest_dir, suffix=".db")
    os.close(fd)

    try:
        with contextlib.closing(sqlite3.connect(temp_dest_path)) as dest_conn:
            dest_cursor = dest_conn.cursor()

            dest_cursor.execute('''
                CREATE TABLE jules_jobs (
                    id TEXT PRIMARY KEY,
                    repo_name TEXT NOT NULL,
                    jules_agent_job_id TEXT,
                    status TEXT NOT NULL,
                    remote_state TEXT,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
            ''')

            dest_cursor.execute('''
                CREATE TABLE export_metadata (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    last_attempt_at TIMESTAMP NOT NULL,
                    last_success_at TIMESTAMP,
                    error_code TEXT NOT NULL
                )
            ''')

            uri = f"file:{os.path.abspath(SOURCE_DB_PATH)}?mode=ro"

            with contextlib.closing(sqlite3.connect(uri, uri=True, timeout=10.0)) as source_conn:
                source_cursor = source_conn.cursor()
                source_cursor.execute("PRAGMA query_only = ON;")

                source_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jules_jobs'")
                if not source_cursor.fetchone():
                    raise ValueError("INVALID_SCHEMA")

                # Verify columns exist
                source_cursor.execute("PRAGMA table_info(jules_jobs)")
                cols = {row[1] for row in source_cursor.fetchall()}
                required_cols = {'id', 'repo_name', 'jules_agent_job_id', 'status', 'remote_state', 'created_at', 'updated_at'}
                if not required_cols.issubset(cols):
                    raise ValueError("INVALID_SCHEMA")

                source_cursor.execute('''
                    SELECT id, repo_name, jules_agent_job_id, status, remote_state, created_at, updated_at
                    FROM jules_jobs
                ''')
                rows = source_cursor.fetchall()

            dest_cursor.executemany('''
                INSERT INTO jules_jobs (id, repo_name, jules_agent_job_id, status, remote_state, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', rows)

            dest_cursor.execute('''
                INSERT INTO export_metadata (id, last_attempt_at, last_success_at, error_code)
                VALUES (1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    last_attempt_at=excluded.last_attempt_at,
                    last_success_at=excluded.last_success_at,
                    error_code=excluded.error_code
            ''', (now, now, "NONE"))

            dest_conn.commit()

        os.chmod(temp_dest_path, 0o644)
        os.replace(temp_dest_path, DEST_DB_PATH)
        print(f"[{now}] Successfully exported {len(rows)} jobs.")

    except ValueError as ve:
        print(f"[{now}] Export failed with known error: {ve}")
        cleanup_temp(temp_dest_path)
        update_metadata_safe(now, str(ve))
    except Exception:
        print(f"[{now}] Export failed with UNKNOWN_ERROR.")
        cleanup_temp(temp_dest_path)
        update_metadata_safe(now, "UNKNOWN_ERROR")

def cleanup_temp(path):
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass

def update_metadata_safe(attempt_time, error_code):
    dest_dir = os.path.dirname(DEST_DB_PATH)
    os.makedirs(dest_dir, exist_ok=True)

    fd, temp_dest_path = tempfile.mkstemp(dir=dest_dir, suffix=".db")
    os.close(fd)

    last_success = None

    try:
        if os.path.exists(DEST_DB_PATH):
            shutil.copy2(DEST_DB_PATH, temp_dest_path)

            with contextlib.closing(sqlite3.connect(temp_dest_path, timeout=10.0)) as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute("SELECT last_success_at FROM export_metadata WHERE id=1")
                    row = cursor.fetchone()
                    if row:
                        last_success = row[0]
                except sqlite3.OperationalError:
                    pass

        with contextlib.closing(sqlite3.connect(temp_dest_path, timeout=10.0)) as conn:
            cursor = conn.cursor()

            # ALWAYS ensure jules_jobs table exists, so UI doesn't crash on 'no such table'
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS jules_jobs (
                    id TEXT PRIMARY KEY,
                    repo_name TEXT NOT NULL,
                    jules_agent_job_id TEXT,
                    status TEXT NOT NULL,
                    remote_state TEXT,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS export_metadata (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    last_attempt_at TIMESTAMP NOT NULL,
                    last_success_at TIMESTAMP,
                    error_code TEXT NOT NULL
                )
            ''')
            cursor.execute('''
                INSERT INTO export_metadata (id, last_attempt_at, last_success_at, error_code)
                VALUES (1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    last_attempt_at=excluded.last_attempt_at,
                    last_success_at=excluded.last_success_at,
                    error_code=excluded.error_code
            ''', (attempt_time, last_success, error_code))
            conn.commit()

        os.chmod(temp_dest_path, 0o644)
        os.replace(temp_dest_path, DEST_DB_PATH)
        print(f"[{attempt_time}] Updated metadata on failure: {error_code}")
    except Exception:
        print(f"[{attempt_time}] Failed to safely update metadata.")
        cleanup_temp(temp_dest_path)

if __name__ == '__main__':
    export_db()
