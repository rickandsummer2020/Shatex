"""Database migrations for queue state and resume checkpoints."""

import sqlite3
import logging
from typing import Optional

logger = logging.getLogger(__name__)

QUEUE_STATE_TABLE = """
CREATE TABLE IF NOT EXISTS queue_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    state_json TEXT NOT NULL,
    updated_at REAL DEFAULT (unixepoch())
);
"""

CHECKPOINTS_TABLE = """
CREATE TABLE IF NOT EXISTS transfer_checkpoints (
    transfer_id TEXT PRIMARY KEY,
    checkpoint_json TEXT NOT NULL,
    updated_at REAL DEFAULT (unixepoch())
);
"""

BROWSER_PUSH_TABLE = """
CREATE TABLE IF NOT EXISTS browser_push_history (
    push_id TEXT PRIMARY KEY,
    file_name TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    browser_session_id TEXT NOT NULL,
    success INTEGER DEFAULT 0,
    created_at REAL DEFAULT (unixepoch()),
    completed_at REAL
);
"""

def run_migrations(conn: sqlite3.Connection) -> None:
    """Run all migrations."""
    try:
        conn.execute(QUEUE_STATE_TABLE)
        conn.execute(CHECKPOINTS_TABLE)
        conn.execute(BROWSER_PUSH_TABLE)
        conn.commit()
        logger.info("Database migrations completed")
    except Exception as e:
        logger.error(f"Migration error: {e}")
        raise

class DatabaseQueueExtensions:
    """Extended database methods for queue and resume support."""
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        run_migrations(conn)

    def save_queue_state(self, state: dict) -> None:
        import json
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO queue_state (id, state_json, updated_at) VALUES (1, ?, unixepoch())",
            (json.dumps(state),)
        )
        self.conn.commit()

    def load_queue_state(self) -> Optional[dict]:
        import json
        cursor = self.conn.cursor()
        cursor.execute("SELECT state_json FROM queue_state WHERE id = 1 ORDER BY updated_at DESC LIMIT 1")
        row = cursor.fetchone()
        if row:
            return json.loads(row[0])
        return None

    def save_checkpoint(self, checkpoint: dict) -> None:
        import json
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO transfer_checkpoints (transfer_id, checkpoint_json, updated_at) VALUES (?, ?, unixepoch())",
            (checkpoint["transfer_id"], json.dumps(checkpoint))
        )
        self.conn.commit()

    def load_checkpoint(self, transfer_id: str) -> Optional[dict]:
        import json
        cursor = self.conn.cursor()
        cursor.execute("SELECT checkpoint_json FROM transfer_checkpoints WHERE transfer_id = ?", (transfer_id,))
        row = cursor.fetchone()
        if row:
            return json.loads(row[0])
        return None

    def load_all_checkpoints(self) -> list:
        import json
        cursor = self.conn.cursor()
        cursor.execute("SELECT checkpoint_json FROM transfer_checkpoints")
        return [json.loads(row[0]) for row in cursor.fetchall()]

    def delete_checkpoint(self, transfer_id: str) -> None:
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM transfer_checkpoints WHERE transfer_id = ?", (transfer_id,))
        self.conn.commit()

    def save_browser_push(self, push_id: str, file_name: str, file_size: int,
                         browser_session_id: str, success: bool = False) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO browser_push_history (push_id, file_name, file_size, browser_session_id, success, created_at) "
            "VALUES (?, ?, ?, ?, ?, unixepoch())",
            (push_id, file_name, file_size, browser_session_id, int(success))
        )
        self.conn.commit()

    def complete_browser_push(self, push_id: str, success: bool) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE browser_push_history SET success = ?, completed_at = unixepoch() WHERE push_id = ?",
            (int(success), push_id)
        )
        self.conn.commit()
