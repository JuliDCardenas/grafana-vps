import sqlite3
import os
import shutil
import tempfile
from datetime import datetime, timezone

SOURCE_DB_PATH = os.getenv("SOURCE_DB_PATH", "/var/lib/coding-jobs/jules_jobs.db")
DEST_DB_PATH = os.getenv("DEST_DB_PATH", "/var/lib/grafana-sqlite/exported_jobs.db")

def export_db():
    if not os.path.exists(SOURCE_DB_PATH):
        print(f"Source DB {SOURCE_DB_PATH} not found.")
        update_metadata(success=False, error_msg="Source DB not found")
        return

    dest_dir = os.path.dirname(DEST_DB_PATH)
    os.makedirs(dest_dir, exist_ok=True)

    # We will write to a temp file first
    fd, temp_dest_path = tempfile.mkstemp(dir=dest_dir, suffix=".db")
    os.close(fd)

    try:
        # Create schema in the temp DB
        dest_conn = sqlite3.connect(temp_dest_path)
        dest_cursor = dest_conn.cursor()

        dest_cursor.execute('''
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

        dest_cursor.execute('''
            CREATE TABLE IF NOT EXISTS export_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                last_export_time TIMESTAMP NOT NULL,
                success BOOLEAN NOT NULL,
                error_message TEXT
            )
        ''')

        # Connect to source DB in read-only mode using URI
        uri = f"file:{os.path.abspath(SOURCE_DB_PATH)}?mode=ro"

        # Read from source
        source_conn = sqlite3.connect(uri, uri=True, timeout=10.0)
        source_cursor = source_conn.cursor()

        # Check if table exists
        source_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jules_jobs'")
        if not source_cursor.fetchone():
            raise Exception("Table jules_jobs not found in source database")

        source_cursor.execute('''
            SELECT id, repo_name, jules_agent_job_id, status, remote_state, created_at, updated_at
            FROM jules_jobs
        ''')
        rows = source_cursor.fetchall()

        # Insert into dest
        dest_cursor.executemany('''
            INSERT INTO jules_jobs (id, repo_name, jules_agent_job_id, status, remote_state, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', rows)

        now = datetime.now(timezone.utc).isoformat()
        dest_cursor.execute('''
            INSERT INTO export_metadata (last_export_time, success, error_message)
            VALUES (?, ?, ?)
        ''', (now, True, None))

        dest_conn.commit()

        source_conn.close()
        dest_conn.close()

        # Atomically replace destination DB
        os.replace(temp_dest_path, DEST_DB_PATH)
        # Ensure it is readable by non-root Grafana user (UID 472)
        os.chmod(DEST_DB_PATH, 0o644)
        print(f"Successfully exported {len(rows)} jobs at {now}")

    except Exception as e:
        print(f"Error during export: {e}")
        # Clean up temp file on failure
        if os.path.exists(temp_dest_path):
            os.remove(temp_dest_path)
        update_metadata(success=False, error_msg=str(e))

def update_metadata(success, error_msg):
    dest_dir = os.path.dirname(DEST_DB_PATH)
    os.makedirs(dest_dir, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    try:
        # Create or update destination DB to add error metadata even if it's completely missing
        conn = sqlite3.connect(DEST_DB_PATH, timeout=10.0)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS export_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                last_export_time TIMESTAMP NOT NULL,
                success BOOLEAN NOT NULL,
                error_message TEXT
            )
        ''')
        cursor.execute('''
            INSERT INTO export_metadata (last_export_time, success, error_message)
            VALUES (?, ?, ?)
        ''', (now, success, error_msg))
        conn.commit()
        conn.close()
        print(f"Updated metadata on failure at {now}: {error_msg}")
    except Exception as e:
        print(f"Failed to update metadata: {e}")

if __name__ == '__main__':
    export_db()
