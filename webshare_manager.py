"""Web Share Manager for ShareX.

Manages web share sessions including server lifecycle,
QR code generation, and upload approvals.
"""

import os
import socket
import asyncio
import logging
import secrets
from pathlib import Path
from typing import Optional, List, Callable

import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import SquareModuleDrawer

from ..models.webshare import WebShareSession, WebShareStatus
from ..models.file_info import FileInfo
from ..services.webshare_server import WebShareServer, UploadRequest
from ..config import get_config

logger = logging.getLogger(__name__)


class WebShareManager:
    """Manages web share functionality.

    Handles session creation, server management, QR code
    generation, and upload approval workflow.

    Attributes:
        current_session: Active web share session.
        server: WebShareServer instance.
        on_upload_request: Callback for upload approval.
        on_status_change: Callback for status changes.
    """

    def __init__(
        self,
        on_upload_request: Optional[Callable[[UploadRequest], asyncio.Future]] = None,
        on_status_change: Optional[Callable[[WebShareStatus], None]] = None,
    ) -> None:
        """Initialize web share manager.

        Args:
            on_upload_request: Callback for upload approval.
            on_status_change: Callback for status changes.
        """
        self.current_session: Optional[WebShareSession] = None
        self.server: Optional[WebShareServer] = None
        self.on_upload_request = on_upload_request
        self.on_status_change = on_status_change
        self._lock = asyncio.Lock()
        logger.info("WebShareManager initialized")

    async def create_session(
        self,
        files: Optional[List[FileInfo]] = None,
        allow_upload: bool = True,
        require_password: bool = False,
        password: Optional[str] = None,
        expires_minutes: Optional[int] = None,
    ) -> WebShareSession:
        """Create a new web share session.

        Args:
            files: Files to share.
            allow_upload: Whether to allow uploads.
            require_password: Whether to require password.
            password: Session password.
            expires_minutes: Session expiration in minutes.

        Returns:
            New WebShareSession instance.
        """
        try:
            ip_address = self._get_local_ip()
            port = self._find_available_port()
            session_id = secrets.token_hex(8)
            url = f"http://{ip_address}:{port}"

            session = WebShareSession(
                id=session_id,
                ip_address=ip_address,
                port=port,
                url=url,
                allow_upload=allow_upload,
                require_password=require_password,
                password=password,
            )

            if expires_minutes:
                import time
                session.expires_at = time.time() + (expires_minutes * 60)

            # Add files to session
            if files:
                for file_info in files:
                    if file_info.is_directory:
                        for child in file_info.get_all_files():
                            session.add_file(
                                file_name=child.name,
                                file_path=child.path,
                                file_size=child.size,
                            )
                    else:
                        session.add_file(
                            file_name=file_info.name,
                            file_path=file_info.path,
                            file_size=file_info.size,
                        )

            # Generate QR code
            session.qr_code = self._generate_qr_code(url)

            self.current_session = session
            logger.info(f"Web share session created: {url}")
            return session

        except Exception as e:
            logger.error(f"Failed to create web share session: {e}")
            raise

    async def start_server(self) -> None:
        """Start the web share server."""
        if not self.current_session:
            raise RuntimeError("No active session. Create a session first.")

        async with self._lock:
            if self.server:
                logger.warning("Server already running")
                return

            self.server = WebShareServer(
                session=self.current_session,
                on_upload_request=self.on_upload_request,
                on_status_change=self._handle_status_change,
            )
            await self.server.start()

    async def stop_server(self) -> None:
        """Stop the web share server."""
        async with self._lock:
            if self.server:
                await self.server.stop()
                self.server = None
            self.current_session = None
            logger.info("Web share server stopped")

    async def add_files(self, files: List[FileInfo]) -> None:
        """Add files to the current session.

        Args:
            files: Files to add.
        """
        if not self.current_session:
            raise RuntimeError("No active session")

        for file_info in files:
            if file_info.is_directory:
                for child in file_info.get_all_files():
                    self.current_session.add_file(
                        file_name=child.name,
                        file_path=child.path,
                        file_size=child.size,
                    )
            else:
                self.current_session.add_file(
                    file_name=file_info.name,
                    file_path=file_info.path,
                    file_size=file_info.size,
                )

        logger.info(f"Added {len(files)} items to web share session")

    def approve_upload(self, upload_id: str, approved: bool = True) -> bool:
        """Approve or reject a pending upload.

        Args:
            upload_id: Upload request ID.
            approved: Whether to approve.

        Returns:
            True if successful.
        """
        if not self.server:
            return False
        return self.server.approve_upload(upload_id, approved)

    def get_pending_uploads(self) -> List[UploadRequest]:
        """Get pending upload requests.

        Returns:
            List of pending uploads.
        """
        if not self.server:
            return []
        return self.server.get_pending_uploads()

    def get_qr_code_lines(self) -> List[str]:
        """Get QR code as list of strings for terminal display.

        Returns:
            List of QR code lines.
        """
        if not self.current_session or not self.current_session.qr_code:
            return []
        return self.current_session.qr_code.split("\n")

    def _handle_status_change(self, status: WebShareStatus) -> None:
        """Handle server status changes.

        Args:
            status: New status.
        """
        if self.current_session:
            self.current_session.status = status
        if self.on_status_change:
            try:
                self.on_status_change(status)
            except Exception as e:
                logger.error(f"Status change callback error: {e}")

    @staticmethod
    def _get_local_ip() -> str:
        """Get the local IP address.

        Attempts to find the best local IP for sharing
        on the same Wi-Fi network.

        Returns:
            Local IP address string.
        """
        try:
            # Try to get IP by connecting to a remote address
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
            finally:
                s.close()

            # Validate it's not localhost
            if ip and not ip.startswith("127."):
                return ip
        except Exception:
            pass

        # Fallback: get all interfaces
        try:
            import psutil
            interfaces = psutil.net_if_addrs()
            priority = ["wlan", "wifi", "wl", "eth", "en"]

            for prefix in priority:
                for name, addrs in interfaces.items():
                    if name.lower().startswith(prefix):
                        for addr in addrs:
                            if addr.family == socket.AF_INET:
                                ip = addr.address
                                if ip and not ip.startswith("127."):
                                    return ip

            # Any non-localhost IPv4
            for name, addrs in interfaces.items():
                for addr in addrs:
                    if addr.family == socket.AF_INET:
                        ip = addr.address
                        if ip and not ip.startswith("127."):
                            return ip
        except Exception:
            pass

        # Final fallback
        return "127.0.0.1"

    @staticmethod
    def _find_available_port(start_port: int = 8000, max_port: int = 9000) -> int:
        """Find an available port.

        Args:
            start_port: Starting port number.
            max_port: Maximum port number.

        Returns:
            Available port number.
        """
        for port in range(start_port, max_port):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1)
                result = s.connect_ex(("127.0.0.1", port))
                s.close()
                if result != 0:  # Port is available
                    return port
            except Exception:
                continue

        # If no port found, return random high port
        import random
        return random.randint(10000, 65000)

    @staticmethod
    def _generate_qr_code(url: str, size: int = 10) -> str:
        """Generate ASCII QR code for terminal display.

        Args:
            url: URL to encode.
            size: QR code size.

        Returns:
            ASCII QR code string.
        """
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=1,
                border=2,
            )
            qr.add_data(url)
            qr.make(fit=True)

            # Generate ASCII art
            lines = []
            matrix = qr.get_matrix()

            # Top border
            lines.append(" " + "█" * (len(matrix[0]) + 2))

            for row in matrix:
                line = " █"
                for cell in row:
                    line += "██" if cell else "  "
                line += "█"
                lines.append(line)

            # Bottom border
            lines.append(" " + "█" * (len(matrix[0]) + 2))

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"QR code generation failed: {e}")
            return "QR Code unavailable"

    @property
    def is_running(self) -> bool:
        """Check if web share server is running.

        Returns:
            True if server is active.
        """
        return (
            self.server is not None
            and self.current_session is not None
            and self.current_session.is_active
        )

    @property
    def session_info(self) -> dict:
        """Get current session information.

        Returns:
            Dictionary with session details.
        """
        if not self.current_session:
            return {}

        return {
            "id": self.current_session.id,
            "url": self.current_session.url,
            "ip": self.current_session.ip_address,
            "port": self.current_session.port,
            "status": self.current_session.status.value,
            "files_count": len(self.current_session.files),
            "uploaded_count": len(self.current_session.uploaded_files),
            "duration": self.current_session.formatted_duration,
        }
