import unittest
import sqlite3
import os
import tempfile
from datetime import datetime, timezone

# Override env vars before importing exporter
test_dir = tempfile.mkdtemp()
mock_source_db = os.path.join(test_dir, "source.db")
mock_dest_db = os.path.join(test_dir, "dest.db")

os.environ["SOURCE_DB_PATH"] = mock_source_db
os.environ["DEST_DB_PATH"] = mock_dest_db

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'jules_exporter')))
import exporter

class TestExporter(unittest.TestCase):
    def setUp(self):
        if os.path.exists(mock_source_db):
            os.remove(mock_source_db)
        if os.path.exists(mock_dest_db):
            os.remove(mock_dest_db)

    def create_mock_source(self):
        conn = sqlite3.connect(mock_source_db)
        # Enable WAL mode for realistic test
        conn.execute('PRAGMA journal_mode=WAL;')
        cursor = conn.cursor()
        # Simulate original DB schema WITH sensitive payloads
        cursor.execute('''
            CREATE TABLE jules_jobs (
                id TEXT PRIMARY KEY,
                repo_name TEXT NOT NULL,
                task_description TEXT NOT NULL,
                jules_agent_job_id TEXT,
                status TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                remote_state TEXT,
                followup_pending_since TIMESTAMP,
                activities_cursor TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE jules_events (
                id INTEGER PRIMARY KEY,
                job_id TEXT,
                payload TEXT
            )
        ''')
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute('''
            INSERT INTO jules_jobs
            (id, repo_name, task_description, jules_agent_job_id, status, created_at, updated_at, remote_state)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', ("job123", "org/repo", "secret task", "agent123", "running", now, now, "in_progress"))

        cursor.execute('''
            INSERT INTO jules_events (job_id, payload) VALUES (?, ?)
        ''', ("job123", "secret payload event"))
        conn.commit()
        conn.close()

    def test_successful_export_filters_columns(self):
        self.create_mock_source()
        exporter.export_db()

        self.assertTrue(os.path.exists(mock_dest_db))

        # Verify permissions
        st = os.stat(mock_dest_db)
        # 0o644 is octal 0644. Check lower 9 bits.
        self.assertEqual(st.st_mode & 0o777, 0o644)

        conn = sqlite3.connect(mock_dest_db)
        cursor = conn.cursor()

        # Verify schema is stripped
        cursor.execute("PRAGMA table_info(jules_jobs)")
        columns = [col[1] for col in cursor.fetchall()]

        expected_cols = ['id', 'repo_name', 'jules_agent_job_id', 'status', 'remote_state', 'created_at', 'updated_at']
        self.assertEqual(sorted(columns), sorted(expected_cols))
        self.assertNotIn('task_description', columns)

        # Verify events table is NOT exported
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jules_events'")
        self.assertIsNone(cursor.fetchone())

        # Verify metadata
        cursor.execute("SELECT error_code, last_success_at FROM export_metadata WHERE id=1")
        meta = cursor.fetchone()

        # Verify table size limits
        cursor.execute("SELECT count(*) FROM export_metadata")
        self.assertEqual(cursor.fetchone()[0], 1)
        self.assertEqual(meta[0], "NONE")
        self.assertIsNotNone(meta[1])

        conn.close()

    def test_missing_source_db_creates_error_metadata_and_empty_jobs_table(self):
        exporter.export_db()
        self.assertTrue(os.path.exists(mock_dest_db))
        conn = sqlite3.connect(mock_dest_db)
        cursor = conn.cursor()

        # Verify jules_jobs table IS created even if source is missing to prevent Grafana 'no such table'
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jules_jobs'")
        self.assertIsNotNone(cursor.fetchone())

        # Verify it is empty
        cursor.execute("SELECT count(*) FROM jules_jobs")
        self.assertEqual(cursor.fetchone()[0], 0)

        cursor.execute("SELECT error_code FROM export_metadata WHERE id=1")
        meta = cursor.fetchone()
        self.assertEqual(meta[0], "SOURCE_UNAVAILABLE")

        cursor.execute("SELECT count(*) FROM export_metadata")
        self.assertEqual(cursor.fetchone()[0], 1)
        conn.close()

    def test_missing_source_db_preserves_old_data_and_adds_error(self):
        self.create_mock_source()
        exporter.export_db() # Successful run

        os.remove(mock_source_db) # Now source is gone

        exporter.export_db() # Should fail but preserve

        conn = sqlite3.connect(mock_dest_db)
        cursor = conn.cursor()

        # Jobs should still exist
        cursor.execute("SELECT count(*) FROM jules_jobs")
        self.assertEqual(cursor.fetchone()[0], 1)

        # Latest metadata should show failure
        cursor.execute("SELECT error_code, last_success_at FROM export_metadata WHERE id=1")
        meta = cursor.fetchone()
        self.assertEqual(meta[0], "SOURCE_UNAVAILABLE")
        self.assertIsNotNone(meta[1]) # Prev success date should be preserved

        cursor.execute("SELECT count(*) FROM export_metadata")
        self.assertEqual(cursor.fetchone()[0], 1)
        conn.close()

    def test_invalid_schema_preserves_data(self):
        self.create_mock_source()
        exporter.export_db()

        # Corrupt the source schema (drop table)
        conn = sqlite3.connect(mock_source_db)
        conn.execute("DROP TABLE jules_jobs")
        conn.commit()
        conn.close()

        exporter.export_db()

        dest_conn = sqlite3.connect(mock_dest_db)
        cursor = dest_conn.cursor()

        cursor.execute("SELECT count(*) FROM jules_jobs")
        self.assertEqual(cursor.fetchone()[0], 1)

        cursor.execute("SELECT error_code FROM export_metadata WHERE id=1")
        meta = cursor.fetchone()
        self.assertEqual(meta[0], "INVALID_SCHEMA")

        cursor.execute("SELECT count(*) FROM export_metadata")
        self.assertEqual(cursor.fetchone()[0], 1) # Size remains 1
        dest_conn.close()

    def test_missing_columns_results_in_invalid_schema(self):
        self.create_mock_source()

        # Corrupt the schema by renaming a required column
        conn = sqlite3.connect(mock_source_db)
        conn.execute("ALTER TABLE jules_jobs RENAME COLUMN status TO _status")
        conn.commit()
        conn.close()

        exporter.export_db()

        dest_conn = sqlite3.connect(mock_dest_db)
        cursor = dest_conn.cursor()

        cursor.execute("SELECT error_code FROM export_metadata WHERE id=1")
        meta = cursor.fetchone()
        self.assertEqual(meta[0], "INVALID_SCHEMA")
        dest_conn.close()

if __name__ == '__main__':
    unittest.main()
