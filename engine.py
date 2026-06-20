"""Core engine for ShareX.

Orchestrates discovery, transfer, and UI updates.
Central hub connecting all network operations.
"""

import asyncio
import logging
import time
from typing import Optional, Callable, List, Dict
from dataclasses import dataclass, field

from ..models.device import Device, DeviceStatus
from ..models.transfer import Transfer, TransferStatus, TransferDirection
from ..models.file_info import FileInfo
from ..network.discovery import DiscoveryManager
from ..network.transfer import TransferServer, TransferClient
from ..services.transfer_service import TransferService
from ..database.manager import get_database
from ..config import get_config

logger = logging.getLogger(__name__)


@dataclass
class EngineState:
    """Engine state snapshot."""
    discovery_running: bool = False
    server_running: bool = False
    active_transfers: int = 0
    total_transfers: int = 0
    connected_devices: int = 0
    webshare_running: bool = False


class ShareXEngine:
    """Central engine managing all ShareX operations.

    Coordinates device discovery, file transfers, and
    provides callbacks for UI updates.

    Attributes:
        discovery: Device discovery manager.
        server: Transfer server for receiving files.
        transfer_service: Transfer service for sending files.
        state: Current engine state.
        on_device_update: Device list update callback.
        on_transfer_update: Transfer progress callback.
        on_notification: Notification callback.
    """

    def __init__(
        self,
        on_device_update: Optional[Callable[[List[Device]], None]] = None,
        on_transfer_update: Optional[Callable[[Transfer], None]] = None,
        on_notification: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        """Initialize engine.

        Args:
            on_device_update: Callback for device list changes.
            on_transfer_update: Callback for transfer progress.
            on_notification: Callback for notifications (message, type).
        """
        self.discovery: Optional[DiscoveryManager] = None
        self.server: Optional[TransferServer] = None
        self.transfer_service: Optional[TransferService] = None
        self.state = EngineState()

        self.on_device_update = on_device_update
        self.on_transfer_update = on_transfer_update
        self.on_notification = on_notification

        self._lock = asyncio.Lock()
        self._running = False
        self._tasks: List[asyncio.Task] = []

        logger.info("ShareXEngine initialized")

    async def start(self) -> None:
        """Start all engine services."""
        try:
            self._running = True

            # Initialize transfer service
            self.transfer_service = TransferService(
                on_progress=self._on_transfer_progress,
            )

            # Start discovery
            await self._start_discovery()

            # Start transfer server
            await self._start_server()

            # Start state update loop
            task = asyncio.create_task(self._state_update_loop())
            self._tasks.append(task)

            self._notify("ShareX Engine started", "success")
            logger.info("ShareXEngine started")

        except Exception as e:
            logger.error(f"Engine start failed: {e}")
            self._notify(f"Start failed: {e}", "error")
            raise

    async def stop(self) -> None:
        """Stop all engine services."""
        try:
            self._running = False

            # Cancel all tasks
            for task in self._tasks:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            self._tasks.clear()

            # Stop discovery
            if self.discovery:
                await self.discovery.stop()
                self.discovery = None

            # Stop server
            if self.server:
                await self.server.stop()
                self.server = None

            logger.info("ShareXEngine stopped")

        except Exception as e:
            logger.error(f"Engine stop error: {e}")

    async def _start_discovery(self) -> None:
        """Start device discovery."""
        try:
            self.discovery = DiscoveryManager(
                on_device_found=self._on_device_found,
                on_device_lost=self._on_device_lost,
            )
            await self.discovery.start()
            self.state.discovery_running = True
            logger.info("Discovery started")
        except Exception as e:
            logger.error(f"Discovery start failed: {e}")
            self.state.discovery_running = False

    async def _start_server(self) -> None:
        """Start transfer server."""
        try:
            config = get_config()
            self.server = TransferServer(
                host="0.0.0.0",
                port=config.config.port,
                on_transfer_request=self._on_transfer_request,
                on_progress=self._on_transfer_progress,
            )
            await self.server.start()
            self.state.server_running = True
            logger.info("Transfer server started")
        except Exception as e:
            logger.error(f"Server start failed: {e}")
            self.state.server_running = False

    async def send_file(
        self,
        file_path: str,
        device: Device,
        on_progress: Optional[Callable[[Transfer], None]] = None,
    ) -> Transfer:
        """Send file to device.

        Args:
            file_path: Path to file.
            device: Target device.
            on_progress: Progress callback.

        Returns:
            Transfer object.
        """
        if not self.transfer_service:
            raise RuntimeError("Transfer service not initialized")

        # Use provided callback or default
        if on_progress:
            original_callback = self.transfer_service.on_progress
            self.transfer_service.on_progress = on_progress

        try:
            transfer = await self.transfer_service.send_file(file_path, device)

            self.state.total_transfers += 1

            if transfer.status == TransferStatus.COMPLETED:
                self._notify(f"Sent: {transfer.file_name}", "success")
            else:
                self._notify(f"Failed: {transfer.error_message}", "error")

            return transfer

        finally:
            if on_progress:
                self.transfer_service.on_progress = original_callback

    async def send_files(
        self,
        file_paths: List[str],
        device: Device,
        on_progress: Optional[Callable[[Transfer], None]] = None,
    ) -> List[Transfer]:
        """Send multiple files to device.

        Args:
            file_paths: List of file paths.
            device: Target device.
            on_progress: Progress callback.

        Returns:
            List of Transfer objects.
        """
        transfers = []
        for path in file_paths:
            try:
                transfer = await self.send_file(path, device, on_progress)
                transfers.append(transfer)
            except Exception as e:
                logger.error(f"Failed to send {path}: {e}")
        return transfers

    def pause_transfer(self, transfer_id: str) -> bool:
        """Pause an active transfer.

        Args:
            transfer_id: Transfer ID.

        Returns:
            True if paused.
        """
        if self.transfer_service:
            return self.transfer_service.pause_transfer(transfer_id)
        return False

    def resume_transfer(self, transfer_id: str) -> bool:
        """Resume a paused transfer.

        Args:
            transfer_id: Transfer ID.

        Returns:
            True if resumed.
        """
        if self.transfer_service:
            return self.transfer_service.resume_transfer(transfer_id)
        return False

    def cancel_transfer(self, transfer_id: str) -> bool:
        """Cancel an active transfer.

        Args:
            transfer_id: Transfer ID.

        Returns:
            True if cancelled.
        """
        if self.transfer_service:
            return self.transfer_service.cancel_transfer(transfer_id)
        return False

    def get_devices(self) -> List[Device]:
        """Get discovered devices.

        Returns:
            List of devices.
        """
        if self.discovery:
            return self.discovery.get_devices()
        return []

    def get_active_transfers(self) -> List[Transfer]:
        """Get active transfers.

        Returns:
            List of active transfers.
        """
        if self.transfer_service:
            return self.transfer_service.get_active_transfers()
        return []

    def get_transfer(self, transfer_id: str) -> Optional[Transfer]:
        """Get transfer by ID.

        Args:
            transfer_id: Transfer ID.

        Returns:
            Transfer or None.
        """
        if self.transfer_service:
            return self.transfer_service.get_transfer(transfer_id)
        return None

    def _on_device_found(self, device: Device) -> None:
        """Handle device discovery."""
        self.state.connected_devices = len(self.get_devices())
        if self.on_device_update:
            try:
                self.on_device_update(self.get_devices())
            except Exception as e:
                logger.error(f"Device update callback error: {e}")

        self._notify(f"Found: {device.display_name}", "info")
        logger.info(f"Device found: {device}")

    def _on_device_lost(self, device: Device) -> None:
        """Handle device loss."""
        self.state.connected_devices = len(self.get_devices())
        if self.on_device_update:
            try:
                self.on_device_update(self.get_devices())
            except Exception as e:
                logger.error(f"Device update callback error: {e}")

        logger.info(f"Device lost: {device}")

    def _on_transfer_request(self, transfer: Transfer) -> bool:
        """Handle incoming transfer request."""
        logger.info(f"Transfer request: {transfer.file_name} from {transfer.device_name}")

        # Check trusted devices
        config = get_config()
        if config.config.require_trusted_devices:
            db = get_database()
            devices = db.get_devices(trusted_only=True)
            trusted_ids = {d.id for d in devices}
            if transfer.device_id not in trusted_ids:
                logger.warning(f"Rejected transfer from untrusted device: {transfer.device_id}")
                return False

        self._notify(
            f"Receiving: {transfer.file_name} from {transfer.device_name}",
            "info",
        )
        return True

    def _on_transfer_progress(self, transfer: Transfer) -> None:
        """Handle transfer progress update."""
        if self.on_transfer_update:
            try:
                self.on_transfer_update(transfer)
            except Exception as e:
                logger.error(f"Transfer update callback error: {e}")

    async def _state_update_loop(self) -> None:
        """Periodic state update loop."""
        try:
            while self._running:
                await asyncio.sleep(2)

                if self.discovery:
                    self.state.connected_devices = len(self.discovery.get_devices())

                if self.transfer_service:
                    self.state.active_transfers = len(self.transfer_service.get_active_transfers())

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"State update error: {e}")

    def _notify(self, message: str, notification_type: str = "info") -> None:
        """Send notification."""
        if self.on_notification:
            try:
                self.on_notification(message, notification_type)
            except Exception as e:
                logger.error(f"Notification error: {e}")

    @property
    def is_running(self) -> bool:
        """Check if engine is running."""
        return self._running
