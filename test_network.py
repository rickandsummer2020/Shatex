"""Integration tests for ShareX network module."""

import asyncio
import tempfile
import shutil
import unittest
from pathlib import Path

from sharex.network.discovery import DiscoveryManager
from sharex.network.transfer import TransferServer, TransferClient
from sharex.models.transfer import Transfer, TransferDirection
from sharex.models.device import Device


class TestDiscoveryManager(unittest.TestCase):
    """Integration tests for DiscoveryManager."""

    def setUp(self) -> None:
        """Set up test environment."""
        self.discovery = DiscoveryManager()

    def tearDown(self) -> None:
        """Clean up."""
        if self.discovery.is_running:
            asyncio.run(self.discovery.stop())

    def test_initialization(self) -> None:
        """Test discovery manager initialization."""
        self.assertIsNotNone(self.discovery)
        self.assertFalse(self.discovery.is_running)
        self.assertEqual(len(self.discovery.get_devices()), 0)

    def test_get_local_ip(self) -> None:
        """Test local IP detection."""
        ip = DiscoveryManager._get_local_ip()
        self.assertIsNotNone(ip)
        self.assertIsInstance(ip, str)
        self.assertGreater(len(ip), 0)

    def test_device_dict(self) -> None:
        """Test device dictionary operations."""
        device = Device(
            id="test-1",
            name="TestDevice",
            ip_address="192.168.1.1",
        )

        self.discovery.devices["test-1"] = device
        self.assertEqual(len(self.discovery.get_devices()), 1)

        found = self.discovery.get_device("test-1")
        self.assertIsNotNone(found)
        self.assertEqual(found.id, "test-1")


class TestTransferServer(unittest.TestCase):
    """Integration tests for TransferServer."""

    def setUp(self) -> None:
        """Set up test environment."""
        self.server = TransferServer(
            host="127.0.0.1",
            port=57575,
        )

    def tearDown(self) -> None:
        """Clean up."""
        if self.server.is_running:
            asyncio.run(self.server.stop())

    def test_initialization(self) -> None:
        """Test server initialization."""
        self.assertIsNotNone(self.server)
        self.assertFalse(self.server.is_running)
        self.assertEqual(self.server.host, "127.0.0.1")
        self.assertEqual(self.server.port, 57575)


class TestTransferProtocol(unittest.TestCase):
    """Integration tests for transfer protocol."""

    def setUp(self) -> None:
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = Path(self.temp_dir) / "test.txt"
        self.test_file.write_text("Hello, World!")

    def tearDown(self) -> None:
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_file_creation(self) -> None:
        """Test test file creation."""
        self.assertTrue(self.test_file.exists())
        self.assertEqual(self.test_file.read_text(), "Hello, World!")


if __name__ == "__main__":
    unittest.main()
