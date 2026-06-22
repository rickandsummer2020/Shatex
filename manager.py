"""Database manager for ShareX.

Handles SQLite persistence for history, trusted devices,
settings, and logs.
Now includes queue state and transfer checkpoint support.
"""

import sqlite3
import json
import logging
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import asdict

from ..config import get_config
from ..models.transfer import Transfer, TransferStatus, TransferDirection
from ..models.device import Device, DeviceStatus
from ..models.settings import Settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages SQLite database operations.

    Provides persistent storage for application data
    including transfer history, trusted devices, settings,
    queue states, and transfer checkpoints.

    Attributes:
        db_path: Path to SQLite database file.
        connection: Active database connection.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """Initialize database manager.

        Args:
            db_path: Path to database file. Defaults to app config directory.
        """
        if db_path is None:
            config = get_config()
            db_path = config.config_dir / "sharex.db"

        self.db_path = db_path
        self.connection: Optional[sqlite3.Connection] = None
        self._init_database()
        logger.info(f"Database initialized at {self.db_path}")

    def _init_database(self) -> None:
        """Initialize database schema."""
        try:
            self.connection = sqlite3.connect(str(self.db_path))
            self.connection.row_factory = sqlite3.Row
            self._create_tables()
        except sqlite3.Error as e:
            logger.error(f"Database initialization error: {e}")
            raise

    def _create_tables(self) -> None:
        """Create database tables if they don't exist."""
        if not self.connection:
            return

        cursor = self.connection.cursor()

        # Transfers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transfers (
                id TEXT PRIMARY KEY,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                transferred_size INTEGER DEFAULT 0,
                direction TEXT NOT NULL,
                status TEXT NOT NULL,
                device_id TEXT NOT NULL,
                device_name TEXT NOT NULL,
                speed REAL DEFAULT 0.0,
                eta REAL DEFAULT 0.0,
                progress REAL DEFAULT 0.0,
                checksum TEXT,
                encrypted INTEGER DEFAULT 1,
                retries INTEGER DEFAULT 0,
                error_message TEXT,
                start_time REAL NOT NULL,
                end_time REAL,
                metadata TEXT,
                created_at REAL DEFAULT (strftime('%s', 'now'))
            )
        """)

        # Devices table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                nickname TEXT,
                ip_address TEXT,
                port INTEGER DEFAULT 57575,
                status TEXT DEFAULT 'offline',
                last_seen REAL DEFAULT (strftime('%s', 'now')),
                is_trusted INTEGER DEFAULT 0,
                public_key TEXT,
                metadata TEXT,
                created_at REAL DEFAULT (strftime('%s', 'now'))
            )
        """)

        # Settings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at REAL DEFAULT (strftime('%s', 'now'))
            )
        """)

        # Logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                source TEXT,
                timestamp REAL DEFAULT (strftime('%s', 'now'))
            )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transfers_status ON transfers(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transfers_device ON transfers(device_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_devices_status ON devices(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp)")

        self.connection.commit()
        logger.info("Database tables created successfully")

    def save_transfer(self, transfer: Transfer) -> bool:
        """Save or update a transfer record.

        Args:
            transfer: Transfer object to save.

        Returns:
            True if successful.
        """
        try:
            if not self.connection:
                return False

            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO transfers (
                    id, file_name, file_path, file_size, transferred_size,
                    direction, status, device_id, device_name, speed, eta,
                    progress, checksum, encrypted, retries, error_message,
                    start_time, end_time, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                transfer.id,
                transfer.file_name,
                transfer.file_path,
                transfer.file_size,
                transfer.transferred_size,
                transfer.direction.value,
                transfer.status.value,
                transfer.device_id,
                transfer.device_name,
                transfer.speed,
                transfer.eta,
                transfer.progress,
                transfer.checksum,
                1 if transfer.encrypted else 0,
                transfer.retries,
                transfer.error_message,
                transfer.start_time,
                transfer.end_time,
                json.dumps(transfer.metadata) if transfer.metadata else None,
            ))
            self.connection.commit()
            return True

        except sqlite3.Error as e:
            logger.error(f"Failed to save transfer: {e}")
            return False

    def get_transfers(
        self,
        status: Optional[TransferStatus] = None,
        limit: int = 100,
    ) -> List[Transfer]:
        """Get transfer history.

        Args:
            status: Filter by status.
            limit: Maximum number of records.

        Returns:
            List of Transfer objects.
        """
        try:
            if not self.connection:
                return []

            cursor = self.connection.cursor()

            if status:
                cursor.execute("""
                    SELECT * FROM transfers
                    WHERE status = ?
                    ORDER BY start_time DESC
                    LIMIT ?
                """, (status.value, limit))
            else:
                cursor.execute("""
                    SELECT * FROM transfers
                    ORDER BY start_time DESC
                    LIMIT ?
                """, (limit,))

            rows = cursor.fetchall()
            transfers = []

            for row in rows:
                transfer = Transfer(
                    id=row["id"],
                    file_name=row["file_name"],
                    file_path=row["file_path"],
                    file_size=row["file_size"],
                    direction=TransferDirection(row["direction"]),
                    device_id=row["device_id"],
                    device_name=row["device_name"],
                    transferred_size=row["transferred_size"],
                    status=TransferStatus(row["status"]),
                    speed=row["speed"],
                    eta=row["eta"],
                    progress=row["progress"],
                    checksum=row["checksum"],
                    encrypted=bool(row["encrypted"]),
                    retries=row["retries"],
                    error_message=row["error_message"],
                    start_time=row["start_time"],
                    end_time=row["end_time"],
                    metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                )
                transfers.append(transfer)

            return transfers

        except sqlite3.Error as e:
            logger.error(f"Failed to get transfers: {e}")
            return []

    def delete_transfer(self, transfer_id: str) -> bool:
        """Delete a transfer record.

        Args:
            transfer_id: Transfer ID to delete.

        Returns:
            True if successful.
        """
        try:
            if not self.connection:
                return False

            cursor = self.connection.cursor()
            cursor.execute("DELETE FROM transfers WHERE id = ?", (transfer_id,))
            self.connection.commit()
            return cursor.rowcount > 0

        except sqlite3.Error as e:
            logger.error(f"Failed to delete transfer: {e}")
            return False

    def clear_history(self) -> bool:
        """Clear all transfer history.

        Returns:
            True if successful.
        """
        try:
            if not self.connection:
                return False

            cursor = self.connection.cursor()
            cursor.execute("DELETE FROM transfers")
            self.connection.commit()
            logger.info("Transfer history cleared")
            return True

        except sqlite3.Error as e:
            logger.error(f"Failed to clear history: {e}")
            return False

    def save_device(self, device: Device) -> bool:
        """Save or update a device record.

        Args:
            device: Device object to save.

        Returns:
            True if successful.
        """
        try:
            if not self.connection:
                return False

            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO devices (
                    id, name, nickname, ip_address, port, status,
                    last_seen, is_trusted, public_key, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                device.id,
                device.name,
                device.nickname,
                device.ip_address,
                device.port,
                device.status.value,
                device.last_seen,
                1 if device.is_trusted else 0,
                device.public_key.hex() if device.public_key else None,
                json.dumps(device.metadata) if device.metadata else None,
            ))
            self.connection.commit()
            return True

        except sqlite3.Error as e:
            logger.error(f"Failed to save device: {e}")
            return False

    def get_devices(
        self,
        trusted_only: bool = False,
    ) -> List[Device]:
        """Get device list.

        Args:
            trusted_only: Only return trusted devices.

        Returns:
            List of Device objects.
        """
        try:
            if not self.connection:
                return []

            cursor = self.connection.cursor()

            if trusted_only:
                cursor.execute("""
                    SELECT * FROM devices
                    WHERE is_trusted = 1
                    ORDER BY last_seen DESC
                """)
            else:
                cursor.execute("""
                    SELECT * FROM devices
                    ORDER BY last_seen DESC
                """)

            rows = cursor.fetchall()
            devices = []

            for row in rows:
                device = Device(
                    id=row["id"],
                    name=row["name"],
                    nickname=row["nickname"],
                    ip_address=row["ip_address"],
                    port=row["port"],
                    status=DeviceStatus(row["status"]),
                    last_seen=row["last_seen"],
                    is_trusted=bool(row["is_trusted"]),
                    public_key=bytes.fromhex(row["public_key"]) if row["public_key"] else None,
                    metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                )
                devices.append(device)

            return devices

        except sqlite3.Error as e:
            logger.error(f"Failed to get devices: {e}")
            return []

    def delete_device(self, device_id: str) -> bool:
        """Delete a device record.

        Args:
            device_id: Device ID to delete.

        Returns:
            True if successful.
        """
        try:
            if not self.connection:
                return False

            cursor = self.connection.cursor()
            cursor.execute("DELETE FROM devices WHERE id = ?", (device_id,))
            self.connection.commit()
            return cursor.rowcount > 0

        except sqlite3.Error as e:
            logger.error(f"Failed to delete device: {e}")
            return False

    def save_setting(self, key: str, value: Any) -> bool:
        """Save a setting value.

        Args:
            key: Setting key.
            value: Setting value (will be JSON serialized).

        Returns:
            True if successful.
        """
        try:
            if not self.connection:
                return False

            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO settings (key, value, updated_at)
                VALUES (?, ?, strftime('%s', 'now'))
            """, (key, json.dumps(value)))
            self.connection.commit()
            return True

        except sqlite3.Error as e:
            logger.error(f"Failed to save setting: {e}")
            return False

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting value.

        Args:
            key: Setting key.
            default: Default value if not found.

        Returns:
            Setting value or default.
        """
        try:
            if not self.connection:
                return default

            cursor = self.connection.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()

            if row:
                return json.loads(row["value"])
            return default

        except sqlite3.Error as e:
            logger.error(f"Failed to get setting: {e}")
            return default

    def log_message(self, level: str, message: str, source: str = "") -> bool:
        """Store a log message in database.

        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR).
            message: Log message.
            source: Source component.

        Returns:
            True if successful.
        """
        try:
            if not self.connection:
                return False

            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO logs (level, message, source, timestamp)
                VALUES (?, ?, ?, strftime('%s', 'now'))
            """, (level, message, source))
            self.connection.commit()
            return True

        except sqlite3.Error as e:
            logger.error(f"Failed to log message: {e}")
            return False

    def get_logs(
        self,
        level: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get log messages.

        Args:
            level: Filter by level.
            limit: Maximum records.

        Returns:
            List of log entries.
        """
        try:
            if not self.connection:
                return []

            cursor = self.connection.cursor()

            if level:
                cursor.execute("""
                    SELECT * FROM logs
                    WHERE level = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (level, limit))
            else:
                cursor.execute("""
                    SELECT * FROM logs
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except sqlite3.Error as e:
            logger.error(f"Failed to get logs: {e}")
            return []

    def clear_logs(self) -> bool:
        """Clear all log messages.

        Returns:
            True if successful.
        """
        try:
            if not self.connection:
                return False

            cursor = self.connection.cursor()
            cursor.execute("DELETE FROM logs")
            self.connection.commit()
            logger.info("Logs cleared")
            return True

        except sqlite3.Error as e:
            logger.error(f"Failed to clear logs: {e}")
            return False

    # =================================================================
    # NEW METHODS - ADD THESE (from 3_db_extensions.py)
    # Queue State and Transfer Checkpoint Support
    # =================================================================

    def save_queue_state(self, state: dict) -> None:
        """Save queue state to database.

        Args:
            state: Queue state dictionary.
        """
        cursor = self.connection.cursor()
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
        self.connection.commit()

    def load_queue_state(self) -> Optional[dict]:
        """Load queue state from database.

        Returns:
            Queue state dictionary or None.
        """
        cursor = self.connection.cursor()
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
        cursor = self.connection.cursor()
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
        self.connection.commit()

    def load_checkpoint(self, transfer_id: str) -> Optional[dict]:
        """Load checkpoint by transfer ID.

        Args:
            transfer_id: Transfer ID.

        Returns:
            Checkpoint dictionary or None.
        """
        cursor = self.connection.cursor()
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
        cursor = self.connection.cursor()
        cursor.execute("SELECT checkpoint_json FROM transfer_checkpoints")
        return [json.loads(row[0]) for row in cursor.fetchall()]

    def delete_checkpoint(self, transfer_id: str) -> None:
        """Delete checkpoint.

        Args:
            transfer_id: Transfer ID.
        """
        cursor = self.connection.cursor()
        cursor.execute(
            "DELETE FROM transfer_checkpoints WHERE transfer_id = ?",
            (transfer_id,)
        )
        self.connection.commit()

    # =================================================================
    # END OF NEW METHODS
    # =================================================================

    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.info("Database connection closed")

    def __del__(self) -> None:
        """Cleanup on destruction."""
        self.close()


# Global database instance
_db_manager: Optional[DatabaseManager] = None


def get_database() -> DatabaseManager:
    """Get global database manager instance.

    Returns:
        DatabaseManager instance.
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager
