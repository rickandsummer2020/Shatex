"""Integration tests for ShareX transfer service."""

import asyncio
import tempfile
import shutil
import unittest
from pathlib import Path

from sharex.services.transfer_service import TransferService
from sharex.models.transfer import Transfer, TransferStatus, TransferDirection
from sharex.models.device import Device


class TestTransferService(unittest.TestCase):
    """Integration tests for TransferService."""

    def setUp(self) -> None:
        """Set up test environment."""
        self.service = TransferService()
        self.temp_dir = tempfile.mkdtemp()

        # Create test file
        self.test_file = Path(self.temp_dir) / "test.txt"
        self.test_file.write_text("Hello, World! This is a test file.")

    def tearDown(self) -> None:
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization(self) -> None:
        """Test service initialization."""
        self.assertIsNotNone(self.service)
        self.assertIsNotNone(self.service.crypto)
        self.assertEqual(len(self.service.get_active_transfers()), 0)

    def test_get_active_transfers_empty(self) -> None:
        """Test getting active transfers when empty."""
        transfers = self.service.get_active_transfers()
        self.assertIsInstance(transfers, list)
        self.assertEqual(len(transfers), 0)

    def test_get_transfer_not_found(self) -> None:
        """Test getting non-existent transfer."""
        transfer = self.service.get_transfer("nonexistent")
        self.assertIsNone(transfer)

    def test_cancel_nonexistent(self) -> None:
        """Test cancelling non-existent transfer."""
        result = self.service.cancel_transfer("nonexistent")
        self.assertFalse(result)

    def test_pause_nonexistent(self) -> None:
        """Test pausing non-existent transfer."""
        result = self.service.pause_transfer("nonexistent")
        self.assertFalse(result)

    def test_resume_nonexistent(self) -> None:
        """Test resuming non-existent transfer."""
        result = self.service.resume_transfer("nonexistent")
        self.assertFalse(result)

    def test_progress_callback(self) -> None:
        """Test progress callback."""
        progress_updates = []

        def on_progress(transfer):
            progress_updates.append(transfer.progress)

        service = TransferService(on_progress=on_progress)

        # Create a transfer and update progress
        transfer = Transfer(
            id="test-1",
            file_name="test.txt",
            file_path=str(self.test_file),
            file_size=100,
            direction=TransferDirection.SEND,
            device_id="device-1",
            device_name="Device1",
        )

        service._notify_progress(transfer)
        self.assertEqual(len(progress_updates), 1)
        self.assertEqual(progress_updates[0], 0.0)


if __name__ == "__main__":
    unittest.main()
