"""Unit tests for ShareX database module."""

import os
import tempfile
import shutil
import unittest
from pathlib import Path

from sharex.database.manager import DatabaseManager
from sharex.models.transfer import Transfer, TransferStatus, TransferDirection
from sharex.models.device import Device, DeviceStatus


class TestDatabaseManager(unittest.TestCase):
    """Tests for DatabaseManager."""

    def setUp(self) -> None:
        """Set up test database."""
        self.test_dir = tempfile.mkdtemp()
        self.db_path = Path(self.test_dir) / "test.db"
        self.db = DatabaseManager(db_path=self.db_path)

    def tearDown(self) -> None:
        """Clean up."""
        self.db.close()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_init(self) -> None:
        """Test database initialization."""
        self.assertTrue(self.db_path.exists())
        self.assertIsNotNone(self.db.connection)

    def test_save_transfer(self) -> None:
        """Test saving transfer."""
        transfer = Transfer(
            id="test-1",
            file_name="test.txt",
            file_path="/tmp/test.txt",
            file_size=100,
            direction=TransferDirection.SEND,
            device_id="device-1",
            device_name="Device1",
        )

        result = self.db.save_transfer(transfer)
        self.assertTrue(result)

    def test_get_transfers(self) -> None:
        """Test getting transfers."""
        # Save a transfer
        transfer = Transfer(
            id="test-1",
            file_name="test.txt",
            file_path="/tmp/test.txt",
            file_size=100,
            direction=TransferDirection.SEND,
            device_id="device-1",
            device_name="Device1",
            status=TransferStatus.COMPLETED,
        )
        self.db.save_transfer(transfer)

        # Retrieve
        transfers = self.db.get_transfers()
        self.assertEqual(len(transfers), 1)
        self.assertEqual(transfers[0].id, "test-1")
        self.assertEqual(transfers[0].status, TransferStatus.COMPLETED)

    def test_get_transfers_by_status(self) -> None:
        """Test filtering by status."""
        # Save transfers with different statuses
        for i, status in enumerate([TransferStatus.COMPLETED, TransferStatus.FAILED]):
            transfer = Transfer(
                id=f"test-{i}",
                file_name=f"test{i}.txt",
                file_path=f"/tmp/test{i}.txt",
                file_size=100,
                direction=TransferDirection.SEND,
                device_id="device-1",
                device_name="Device1",
                status=status,
            )
            self.db.save_transfer(transfer)

        completed = self.db.get_transfers(status=TransferStatus.COMPLETED)
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0].status, TransferStatus.COMPLETED)

    def test_delete_transfer(self) -> None:
        """Test deleting transfer."""
        transfer = Transfer(
            id="test-1",
            file_name="test.txt",
            file_path="/tmp/test.txt",
            file_size=100,
            direction=TransferDirection.SEND,
            device_id="device-1",
            device_name="Device1",
        )
        self.db.save_transfer(transfer)

        result = self.db.delete_transfer("test-1")
        self.assertTrue(result)

        transfers = self.db.get_transfers()
        self.assertEqual(len(transfers), 0)

    def test_clear_history(self) -> None:
        """Test clearing history."""
        transfer = Transfer(
            id="test-1",
            file_name="test.txt",
            file_path="/tmp/test.txt",
            file_size=100,
            direction=TransferDirection.SEND,
            device_id="device-1",
            device_name="Device1",
        )
        self.db.save_transfer(transfer)

        result = self.db.clear_history()
        self.assertTrue(result)

        transfers = self.db.get_transfers()
        self.assertEqual(len(transfers), 0)

    def test_save_device(self) -> None:
        """Test saving device."""
        device = Device(
            id="device-1",
            name="TestDevice",
            ip_address="192.168.1.1",
            status=DeviceStatus.ONLINE,
            is_trusted=True,
        )

        result = self.db.save_device(device)
        self.assertTrue(result)

    def test_get_devices(self) -> None:
        """Test getting devices."""
        device = Device(
            id="device-1",
            name="TestDevice",
            ip_address="192.168.1.1",
            status=DeviceStatus.ONLINE,
            is_trusted=True,
        )
        self.db.save_device(device)

        devices = self.db.get_devices()
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].id, "device-1")
        self.assertTrue(devices[0].is_trusted)

    def test_get_trusted_devices(self) -> None:
        """Test getting trusted devices."""
        # Save trusted device
        trusted = Device(
            id="trusted-1",
            name="Trusted",
            is_trusted=True,
        )
        self.db.save_device(trusted)

        # Save untrusted device
        untrusted = Device(
            id="untrusted-1",
            name="Untrusted",
            is_trusted=False,
        )
        self.db.save_device(untrusted)

        trusted_devices = self.db.get_devices(trusted_only=True)
        self.assertEqual(len(trusted_devices), 1)
        self.assertEqual(trusted_devices[0].id, "trusted-1")

    def test_save_and_get_setting(self) -> None:
        """Test settings operations."""
        result = self.db.save_setting("test_key", "test_value")
        self.assertTrue(result)

        value = self.db.get_setting("test_key")
        self.assertEqual(value, "test_value")

    def test_get_setting_default(self) -> None:
        """Test getting setting with default."""
        value = self.db.get_setting("nonexistent", "default")
        self.assertEqual(value, "default")

    def test_log_message(self) -> None:
        """Test logging."""
        result = self.db.log_message("INFO", "Test message", "test")
        self.assertTrue(result)

        logs = self.db.get_logs()
        self.assertGreaterEqual(len(logs), 1)

    def test_get_logs_by_level(self) -> None:
        """Test filtering logs by level."""
        self.db.log_message("INFO", "Info message", "test")
        self.db.log_message("ERROR", "Error message", "test")

        error_logs = self.db.get_logs(level="ERROR")
        self.assertEqual(len(error_logs), 1)
        self.assertEqual(error_logs[0]["level"], "ERROR")

    def test_clear_logs(self) -> None:
        """Test clearing logs."""
        self.db.log_message("INFO", "Test", "test")

        result = self.db.clear_logs()
        self.assertTrue(result)

        logs = self.db.get_logs()
        self.assertEqual(len(logs), 0)


if __name__ == "__main__":
    unittest.main()
