"""Network transfer module for ShareX.

Implements TCP-based file transfer with encryption,
progress tracking, and resume support.
Uses TransferService for actual transfer logic.
"""

import os
import asyncio
import logging
from typing import Optional, Callable

from ..models.transfer import Transfer, TransferDirection
from ..models.device import Device
from ..services.transfer_service import TransferService
from ..config import get_config

logger = logging.getLogger(__name__)


class TransferServer:
    """TCP server for receiving file transfers.

    Listens for incoming connections and delegates
    to TransferService for handling.

    Attributes:
        host: Listen address.
        port: Listen port.
        on_transfer_request: Callback for transfer requests.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 57575,
        on_transfer_request: Optional[Callable[[Transfer], bool]] = None,
        on_progress: Optional[Callable[[Transfer], None]] = None,
    ) -> None:
        """Initialize transfer server.

        Args:
            host: Listen address.
            port: Listen port.
            on_transfer_request: Callback for incoming transfers.
            on_progress: Progress callback.
        """
        self.host = host
        self.port = port
        self.on_transfer_request = on_transfer_request
        self.on_progress = on_progress
        self.server: Optional[asyncio.Server] = None
        self._running = False
        self._transfer_service: Optional[TransferService] = None
        logger.info(f"TransferServer initialized on {host}:{port}")

    async def start(self) -> None:
        """Start the transfer server."""
        try:
            self._transfer_service = TransferService(
                on_progress=self.on_progress,
            )

            self.server = await asyncio.start_server(
                self._handle_connection,
                self.host,
                self.port,
            )
            self._running = True
            logger.info(f"Transfer server started on {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to start transfer server: {e}")
            raise

    async def stop(self) -> None:
        """Stop the transfer server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self._running = False
            logger.info("Transfer server stopped")

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle incoming connection.

        Args:
            reader: Stream reader.
            writer: Stream writer.
        """
        client_addr = writer.get_extra_info("peername")
        logger.info(f"Incoming connection from {client_addr}")

        try:
            config = get_config()

            # Use TransferService to handle the receive
            if self._transfer_service:
                transfer = await self._transfer_service.receive_file(
                    reader,
                    writer,
                    config.config.download_folder,
                    on_request=self.on_transfer_request,
                )

                if transfer.status.value == "completed":
                    logger.info(f"Transfer completed: {transfer.file_name}")
                else:
                    logger.warning(f"Transfer failed: {transfer.error_message}")

        except Exception as e:
            logger.error(f"Connection error: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    @property
    def is_running(self) -> bool:
        """Check if server is running.

        Returns:
            True if running.
        """
        return self._running


class TransferClient:
    """Client for sending files to remote devices.

    Uses TransferService for actual transfer logic.

    Attributes:
        device: Target device.
    """

    def __init__(self, device: Device) -> None:
        """Initialize transfer client.

        Args:
            device: Target device.
        """
        self.device = device
        logger.info(f"TransferClient initialized for {device}")

    async def send_file(
        self,
        file_path: str,
        transfer: Transfer,
        on_progress: Optional[Callable[[Transfer], None]] = None,
    ) -> bool:
        """Send file to device.

        Args:
            file_path: Path to file.
            transfer: Transfer object.
            on_progress: Progress callback.

        Returns:
            True if successful.
        """
        # This is now handled by TransferService in the engine
        # Keeping for backward compatibility
        logger.warning("TransferClient.send_file is deprecated, use TransferService")
        return False
