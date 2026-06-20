"""Integration tests for ShareX WebShare module."""

import asyncio
import unittest

from sharex.services.webshare_manager import WebShareManager
from sharex.services.webshare_server import WebShareServer, UploadRequest
from sharex.models.webshare import WebShareSession, WebShareStatus


class TestWebShareManager(unittest.TestCase):
    """Integration tests for WebShareManager."""

    def setUp(self) -> None:
        """Set up test environment."""
        self.manager = WebShareManager()

    def tearDown(self) -> None:
        """Clean up."""
        if self.manager.is_running:
            asyncio.run(self.manager.stop_server())

    def test_initialization(self) -> None:
        """Test manager initialization."""
        self.assertIsNotNone(self.manager)
        self.assertFalse(self.manager.is_running)
        self.assertIsNone(self.manager.current_session)

    def test_get_local_ip(self) -> None:
        """Test local IP detection."""
        ip = WebShareManager._get_local_ip()
        self.assertIsNotNone(ip)
        self.assertIsInstance(ip, str)
        self.assertGreater(len(ip), 0)

    def test_find_available_port(self) -> None:
        """Test port finding."""
        port = WebShareManager._find_available_port(start_port=30000)
        self.assertIsInstance(port, int)
        self.assertGreater(port, 0)
        self.assertLess(port, 65536)

    def test_generate_qr_code(self) -> None:
        """Test QR code generation."""
        qr = WebShareManager._generate_qr_code("http://192.168.1.1:8080")
        self.assertIsInstance(qr, str)
        self.assertGreater(len(qr), 0)


class TestUploadRequest(unittest.TestCase):
    """Tests for UploadRequest."""

    def test_create_request(self) -> None:
        """Test upload request creation."""
        request = UploadRequest(
            id="test-1",
            filename="test.txt",
            file_size=1024,
            client_ip="192.168.1.1",
            temp_path="/tmp/test.tmp",
            session_id="session-1",
        )

        self.assertEqual(request.id, "test-1")
        self.assertEqual(request.filename, "test.txt")
        self.assertEqual(request.file_size, 1024)
        self.assertEqual(request.client_ip, "192.168.1.1")
        self.assertIsNone(request.approved)


if __name__ == "__main__":
    unittest.main()
