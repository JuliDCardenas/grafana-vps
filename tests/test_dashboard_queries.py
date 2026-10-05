import unittest
import sqlite3
import os
import json
import tempfile
from datetime import datetime, timezone, timedelta

def run_query(db_path, query):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        return cursor.fetchall()

class TestDashboardQueries(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "exported_jobs.db")

        # Extract queries from JSON
        json_path = os.path.join(os.path.dirname(__file__), '..', 'grafana', 'provisioning_jules', 'dashboards', 'jules_jobs.json')
        with open(json_path, 'r') as f:
            dashboard = json.load(f)
            self.metadata_query = dashboard['panels'][0]['targets'][0]['rawQueryText']
            self.jobs_query = dashboard['panels'][1]['targets'][0]['rawQueryText']

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def create_fixture(self, error_code, attempt_time, success_time, has_jobs=True):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE jules_jobs (
                    id TEXT PRIMARY KEY,
                    repo_name TEXT NOT NULL,
                    jules_agent_job_id TEXT,
                    status TEXT NOT NULL,
                    remote_state TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''')

            cursor.execute('''
                CREATE TABLE export_metadata (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    last_attempt_at TEXT NOT NULL,
                    last_success_at TEXT,
                    error_code TEXT NOT NULL
                )
            ''')

            cursor.execute('''
                INSERT INTO export_metadata (id, last_attempt_at, last_success_at, error_code)
                VALUES (1, ?, ?, ?)
            ''', (attempt_time, success_time, error_code))

            if has_jobs:
                cursor.execute('''
                    INSERT INTO jules_jobs (id, repo_name, jules_agent_job_id, status, remote_state, created_at, updated_at)
                    VALUES ('job1', 'repo1', 'agent1', 'DONE', 'SYNCED', '2023-01-01T00:00:00Z', '2023-01-01T00:01:00Z')
                ''')
            conn.commit()

    def test_metadata_query_success(self):
        now = datetime.now(timezone.utc)
        self.create_fixture('NONE', now.isoformat(), now.isoformat())
        res = run_query(self.db_path, self.metadata_query)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0][0], 'Exportación exitosa')

    def test_metadata_query_obsolete(self):
        old = datetime.now(timezone.utc) - timedelta(minutes=5)
        self.create_fixture('NONE', old.isoformat(), old.isoformat())
        res = run_query(self.db_path, self.metadata_query)
        self.assertEqual(len(res), 1)
        self.assertTrue(res[0][0].startswith('Desactualizado'))

    def test_metadata_query_error_initial_empty(self):
        now = datetime.now(timezone.utc)
        self.create_fixture('SOURCE_UNAVAILABLE', now.isoformat(), None, has_jobs=False)
        res = run_query(self.db_path, self.metadata_query)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0][0], 'Error: SOURCE_UNAVAILABLE')

    def test_jobs_query_returns_rows_with_coalesce(self):
        now = datetime.now(timezone.utc)
        self.create_fixture('NONE', now.isoformat(), now.isoformat())

        # Add a job with NULL remote_state to test COALESCE
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO jules_jobs (id, repo_name, status, remote_state, created_at, updated_at)
                VALUES ('job2', 'repo2', 'RUNNING', NULL, '2023-01-02T00:00:00Z', '2023-01-02T00:01:00Z')
            ''')
            conn.commit()

        res = run_query(self.db_path, self.jobs_query)
        self.assertEqual(len(res), 2)
        # Verify ordering (latest created first)
        self.assertEqual(res[0][0], 'job2')
        self.assertEqual(res[0][2], 'Sin dato') # Coalesced NULL

if __name__ == '__main__':
    unittest.main()
