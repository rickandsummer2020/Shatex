"""Database Manager Extensions for Queue and Resume.

Add these methods to the existing DatabaseManager class in manager.py.
"""

# Add these imports at top of manager.py:
# import json

# Add these methods to DatabaseManager class:

def save_queue_state(self, state: dict) -> None:
    """Save queue state to database.

    Args:
        state: Queue state dictionary.
    """
    cursor = self.conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS queue_state (
            id INTEGER PRIMARY KEY,
            state_json TEXT NOT NULL,
            updated_at REAL DEFAULT (unixepoch())
        )
    """)
    cursor.execute("""
        INSERT OR REPLACE INTO queue_state (id, state_json, updated_at)
        VALUES (1, ?, unixepoch())
    """, (json.dumps(state),))
    self.conn.commit()

def load_queue_state(self) -> Optional[dict]:
    """Load queue state from database.

    Returns:
        Queue state dictionary or None.
    """
    cursor = self.conn.cursor()
    cursor.execute("""
        SELECT state_json FROM queue_state WHERE id = 1
    """)
    row = cursor.fetchone()
    if row:
        return json.loads(row[0])
    return None

def save_checkpoint(self, checkpoint: dict) -> None:
    """Save transfer checkpoint.

    Args:
        checkpoint: Checkpoint dictionary with transfer_id.
    """
    cursor = self.conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transfer_checkpoints (
            transfer_id TEXT PRIMARY KEY,
            checkpoint_json TEXT NOT NULL,
            updated_at REAL DEFAULT (unixepoch())
        )
    """)
    cursor.execute("""
        INSERT OR REPLACE INTO transfer_checkpoints
        (transfer_id, checkpoint_json, updated_at)
        VALUES (?, ?, unixepoch())
    """, (checkpoint["transfer_id"], json.dumps(checkpoint)))
    self.conn.commit()

def load_checkpoint(self, transfer_id: str) -> Optional[dict]:
    """Load checkpoint by transfer ID.

    Args:
        transfer_id: Transfer ID.

    Returns:
        Checkpoint dictionary or None.
    """
    cursor = self.conn.cursor()
    cursor.execute("""
        SELECT checkpoint_json FROM transfer_checkpoints
        WHERE transfer_id = ?
    """, (transfer_id,))
    row = cursor.fetchone()
    if row:
        return json.loads(row[0])
    return None

def load_all_checkpoints(self) -> List[dict]:
    """Load all checkpoints.

    Returns:
        List of checkpoint dictionaries.
    """
    cursor = self.conn.cursor()
    cursor.execute("SELECT checkpoint_json FROM transfer_checkpoints")
    return [json.loads(row[0]) for row in cursor.fetchall()]

def delete_checkpoint(self, transfer_id: str) -> None:
    """Delete checkpoint.

    Args:
        transfer_id: Transfer ID.
    """
    cursor = self.conn.cursor()
    cursor.execute(
        "DELETE FROM transfer_checkpoints WHERE transfer_id = ?",
        (transfer_id,)
    )
    self.conn.commit()
