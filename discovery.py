"""Network discovery module for ShareX.

Implements mDNS/Zeroconf device discovery and UDP
broadcast for finding nearby devices.
"""

import socket
import asyncio
import logging
import json
import time
from typing import Optional, List, Callable, Dict, Any
from dataclasses import asdict

from zeroconf import Zeroconf, ServiceInfo, ServiceBrowser, ServiceListener

from ..models.device import Device, DeviceStatus
from ..config import get_config, DISCOVERY_PORT, BROADCAST_INTERVAL

logger = logging.getLogger(__name__)


class DiscoveryListener(ServiceListener):
    """Listener for mDNS service discovery events."""

    def __init__(self, on_device_found: Callable[[Device], None]) -> None:
        """Initialize listener.

        Args:
            on_device_found: Callback when device is discovered.
        """
        self.on_device_found = on_device_found

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Handle new service discovery."""
        try:
            info = zc.get_service_info(type_, name)
            if info and info.addresses:
                device = Device(
                    id=info.properties.get(b"id", b"").decode("utf-8"),
                    name=info.properties.get(b"name", b"").decode("utf-8"),
                    nickname=info.properties.get(b"nickname", b"").decode("utf-8") or None,
                    ip_address=str(socket.inet_aton(info.addresses[0])),
                    port=info.port,
                    status=DeviceStatus.ONLINE,
                    last_seen=time.time(),
                    is_trusted=info.properties.get(b"trusted", b"0") == b"1",
                )
                self.on_device_found(device)
        except Exception as e:
            logger.error(f"Error processing discovered service: {e}")

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Handle service removal."""
        logger.info(f"Service removed: {name}")

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """Handle service update."""
        self.add_service(zc, type_, name)


class DiscoveryManager:
    """Manages device discovery via mDNS/Zeroconf.

    Handles broadcasting this device's presence and
    discovering other ShareX devices on the network.

    Attributes:
        zeroconf: Zeroconf instance.
        service_info: ServiceInfo for this device.
        browser: ServiceBrowser for discovery.
        devices: Discovered devices dictionary.
    """

    SERVICE_TYPE = "_sharex._tcp.local."

    def __init__(
        self,
        on_device_found: Optional[Callable[[Device], None]] = None,
        on_device_lost: Optional[Callable[[Device], None]] = None,
    ) -> None:
        """Initialize discovery manager.

        Args:
            on_device_found: Callback when device found.
            on_device_lost: Callback when device lost.
        """
        self.zeroconf: Optional[Zeroconf] = None
        self.service_info: Optional[ServiceInfo] = None
        self.browser: Optional[ServiceBrowser] = None
        self.devices: Dict[str, Device] = {}
        self.on_device_found = on_device_found
        self.on_device_lost = on_device_lost
        self._running = False
        self._broadcast_task: Optional[asyncio.Task] = None
        logger.info("DiscoveryManager initialized")

    async def start(self) -> None:
        """Start discovery service."""
        try:
            config = get_config()
            self.zeroconf = Zeroconf()

            # Register this device
            ip_address = self._get_local_ip()
            service_name = f"{config.config.device_name}.{self.SERVICE_TYPE}"

            self.service_info = ServiceInfo(
                type_=self.SERVICE_TYPE,
                name=service_name,
                addresses=[socket.inet_aton(ip_address)],
                port=config.config.port,
                properties={
                    b"id": config.config.device_name.encode("utf-8"),
                    b"name": config.config.device_name.encode("utf-8"),
                    b"nickname": (config.config.device_nickname or "").encode("utf-8"),
                    b"version": b"1.0.0",
                    b"trusted": b"0",
                },
            )

            self.zeroconf.register_service(self.service_info)

            # Start discovery browser
            listener = DiscoveryListener(self._handle_device_found)
            self.browser = ServiceBrowser(
                self.zeroconf,
                self.SERVICE_TYPE,
                listener,
            )

            self._running = True
            logger.info("Discovery service started")

        except Exception as e:
            logger.error(f"Failed to start discovery: {e}")
            raise

    async def stop(self) -> None:
        """Stop discovery service."""
        try:
            self._running = False

            if self.browser:
                self.browser.cancel()
                self.browser = None

            if self.zeroconf and self.service_info:
                self.zeroconf.unregister_service(self.service_info)
                self.zeroconf.close()
                self.zeroconf = None

            if self._broadcast_task:
                self._broadcast_task.cancel()
                try:
                    await self._broadcast_task
                except asyncio.CancelledError:
                    pass

            logger.info("Discovery service stopped")

        except Exception as e:
            logger.error(f"Error stopping discovery: {e}")

    def _handle_device_found(self, device: Device) -> None:
        """Handle discovered device.

        Args:
            device: Discovered device.
        """
        if device.id == get_config().config.device_name:
            return  # Ignore self

        existing = self.devices.get(device.id)
        if existing:
            existing.update_last_seen()
            if device.ip_address:
                existing.ip_address = device.ip_address
            if device.port:
                existing.port = device.port
        else:
            self.devices[device.id] = device
            logger.info(f"Device discovered: {device}")

        if self.on_device_found:
            try:
                self.on_device_found(device)
            except Exception as e:
                logger.error(f"Device found callback error: {e}")

    def get_devices(self) -> List[Device]:
        """Get list of discovered devices.

        Returns:
            List of Device objects.
        """
        # Remove stale devices
        current_time = time.time()
        stale_timeout = 30.0  # 30 seconds

        stale_devices = [
            device_id for device_id, device in self.devices.items()
            if current_time - device.last_seen > stale_timeout
        ]

        for device_id in stale_devices:
            device = self.devices.pop(device_id)
            if self.on_device_lost:
                try:
                    self.on_device_lost(device)
                except Exception as e:
                    logger.error(f"Device lost callback error: {e}")

        return list(self.devices.values())

    def get_device(self, device_id: str) -> Optional[Device]:
        """Get specific device by ID.

        Args:
            device_id: Device identifier.

        Returns:
            Device or None.
        """
        return self.devices.get(device_id)

    @staticmethod
    def _get_local_ip() -> str:
        """Get local IP address.

        Returns:
            IP address string.
        """
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(2)
            try:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
            finally:
                s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    @property
    def is_running(self) -> bool:
        """Check if discovery is active.

        Returns:
            True if running.
        """
        return self._running
