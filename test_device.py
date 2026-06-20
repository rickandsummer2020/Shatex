"""Unit tests for ShareX device model."""

import time
import unittest

from sharex.models.device import Device, DeviceStatus


class TestDevice(unittest.TestCase):
    """Tests for Device model."""

    def test_create_device(self) -> None:
        """Test device creation."""
        device = Device(
            id="test-id",
            name="TestDevice",
            ip_address="192.168.1.10",
            port=57575,
        )
        self.assertEqual(device.id, "test-id")
        self.assertEqual(device.name, "TestDevice")
        self.assertEqual(device.ip_address, "192.168.1.10")
        self.assertEqual(device.port, 57575)
        self.assertEqual(device.status, DeviceStatus.OFFLINE)

    def test_display_name(self) -> None:
        """Test display name property."""
        device = Device(id="1", name="Device")
        self.assertEqual(device.display_name, "Device")

        device.nickname = "MyDevice"
        self.assertEqual(device.display_name, "MyDevice")

    def test_is_online(self) -> None:
        """Test online status."""
        device = Device(id="1", name="Test", status=DeviceStatus.ONLINE)
        self.assertTrue(device.is_online)

        device.status = DeviceStatus.OFFLINE
        self.assertFalse(device.is_online)

        device.status = DeviceStatus.BUSY
        self.assertTrue(device.is_online)

    def test_address(self) -> None:
        """Test address property."""
        device = Device(id="1", name="Test", ip_address="192.168.1.1", port=1234)
        self.assertEqual(device.address, "192.168.1.1:1234")

        device.ip_address = None
        self.assertEqual(device.address, "Unknown")

    def test_update_last_seen(self) -> None:
        """Test last seen update."""
        device = Device(id="1", name="Test")
        old_time = device.last_seen
        time.sleep(0.01)
        device.update_last_seen()
        self.assertGreater(device.last_seen, old_time)

    def test_to_dict(self) -> None:
        """Test serialization to dict."""
        device = Device(
            id="1",
            name="Test",
            ip_address="192.168.1.1",
            status=DeviceStatus.ONLINE,
        )
        data = device.to_dict()
        self.assertEqual(data["id"], "1")
        self.assertEqual(data["name"], "Test")
        self.assertEqual(data["status"], "online")

    def test_from_dict(self) -> None:
        """Test deserialization from dict."""
        data = {
            "id": "1",
            "name": "Test",
            "ip_address": "192.168.1.1",
            "port": 57575,
            "status": "online",
            "is_trusted": True,
        }
        device = Device.from_dict(data)
        self.assertEqual(device.id, "1")
        self.assertEqual(device.status, DeviceStatus.ONLINE)
        self.assertTrue(device.is_trusted)

    def test_equality(self) -> None:
        """Test device equality."""
        d1 = Device(id="1", name="A")
        d2 = Device(id="1", name="B")
        d3 = Device(id="2", name="A")

        self.assertEqual(d1, d2)
        self.assertNotEqual(d1, d3)
        self.assertEqual(hash(d1), hash(d2))

    def test_invalid_creation(self) -> None:
        """Test invalid device creation."""
        with self.assertRaises(ValueError):
            Device(id="", name="Test")

        with self.assertRaises(ValueError):
            Device(id="1", name="")


if __name__ == "__main__":
    unittest.main()
