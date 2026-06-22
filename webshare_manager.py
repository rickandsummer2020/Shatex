"""Web Share Manager for ShareX.

Manages web share sessions including server lifecycle,
QR code generation, upload approvals, and browser session tracking.

ENHANCED: Browser session management, live status queries,
WebSocket support, real-time updates.
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
from ..services.webshare_server import WebShareServer, UploadRequest, BrowserSession
from ..config import get_config

logger = logging.getLogger(__name__)


class WebShareManager:
    """Manages web share functionality.

    Handles session creation, server management, QR code
    generation, upload approval workflow, and browser session tracking.
    """

    def __init__(
        self,
        on_upload_request: Optional[Callable[[UploadRequest], asyncio.Future]] = None,
        on_status_change: Optional[Callable[[WebShareStatus], None]] = None,
        on_browser_update: Optional[Callable[[List[BrowserSession]], None]] = None,
    ) -> None:
        """Initialize web share manager.

        Args:
            on_upload_request: Callback for upload approval.
            on_status_change: Callback for status changes.
            on_browser_update: Callback for browser session changes.
        """
        self.current_session: Optional[WebShareSession] = None
        self.server: Optional[WebShareServer] = None
        self.on_upload_request = on_upload_request
        self.on_status_change = on_status_change
        self.on_browser_update = on_browser_update
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
        """Create a new web share session."""
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
                on_status_change=self.on_status_change,
                on_browser_update=self.on_browser_update,
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
        """Add files to the current session."""
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
        """Approve or reject a pending upload."""
        if not self.server:
            return False
        return self.server.approve_upload(upload_id, approved)

    def get_pending_uploads(self) -> List[UploadRequest]:
        """Get pending upload requests."""
        if not self.server:
            return []
        return self.server.get_pending_uploads()

    def get_browser_sessions(self) -> List[BrowserSession]:
        """Get active browser sessions."""
        if not self.server:
            return []
        return self.server.get_active_browser_sessions()

    def get_browser_count(self) -> int:
        """Get count of active browser sessions."""
        if not self.server:
            return 0
        return self.server.get_browser_session_count()

    def get_websocket_count(self) -> int:
        """Get count of active WebSocket connections."""
        if not self.server:
            return 0
        return self.server._ws_manager.get_connection_count()

    def get_browser_summary(self) -> dict:
        """Get summary of browser connections."""
        sessions = self.get_browser_sessions()
        if not sessions:
            return {
                "count": 0,
                "browsers": [],
                "total_downloads": 0,
                "total_uploads": 0,
                "total_bytes": 0,
                "websocket_count": 0,
            }

        return {
            "count": len(sessions),
            "browsers": [s.to_dict() for s in sessions],
            "total_downloads": sum(s.files_downloaded for s in sessions),
            "total_uploads": sum(s.files_uploaded for s in sessions),
            "total_bytes": sum(s.bytes_transferred for s in sessions),
            "websocket_count": sum(1 for s in sessions if s.is_websocket),
        }

    def get_qr_code_lines(self) -> List[str]:
        """Get QR code as list of strings for terminal display."""
        if not self.current_session or not self.current_session.qr_code:
            return []
        return self.current_session.qr_code.split("\n")

    def _handle_status_change(self, status: WebShareStatus) -> None:
        """Handle server status changes."""
        if self.current_session:
            self.current_session.status = status
        if self.on_status_change:
            try:
                self.on_status_change(status)
            except Exception as e:
                logger.error(f"Status change callback error: {e}")

    def _handle_browser_update(self, sessions: List[BrowserSession]) -> None:
        """Handle browser session updates."""
        if self.on_browser_update:
            try:
                self.on_browser_update(sessions)
            except Exception as e:
                logger.error(f"Browser update callback error: {e}")

    @staticmethod
    def _get_local_ip() -> str:
        """Get the local IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
            finally:
                s.close()
            if ip and not ip.startswith("127."):
                return ip
        except Exception:
            pass

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
            for name, addrs in interfaces.items():
                for addr in addrs:
                    if addr.family == socket.AF_INET:
                        ip = addr.address
                        if ip and not ip.startswith("127."):
                            return ip
        except Exception:
            pass

        return "127.0.0.1"

    @staticmethod
    def _find_available_port(start_port: int = 8000, max_port: int = 9000) -> int:
        """Find an available port."""
        for port in range(start_port, max_port):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1)
                result = s.connect_ex(("127.0.0.1", port))
                s.close()
                if result != 0:
                    return port
            except Exception:
                continue
        import random
        return random.randint(10000, 65000)

    @staticmethod
    def _generate_qr_code(url: str, size: int = 10) -> str:
        """Generate ASCII QR code for terminal display."""
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=1,
                border=2,
            )
            qr.add_data(url)
            qr.make(fit=True)

            lines = []
            matrix = qr.get_matrix()
            lines.append(" " + "█" * (len(matrix[0]) + 2))
            for row in matrix:
                line = " █"
                for cell in row:
                    line += "██" if cell else "  "
                line += "█"
                lines.append(line)
            lines.append(" " + "█" * (len(matrix[0]) + 2))
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"QR code generation failed: {e}")
            return "QR Code unavailable"

    @property
    def is_running(self) -> bool:
        """Check if web share server is running."""
        return (
            self.server is not None
            and self.current_session is not None
            and self.current_session.is_active
        )

    @property
    def session_info(self) -> dict:
        """Get current session information."""
        if not self.current_session:
            return {}

        browser_summary = self.get_browser_summary()

        return {
            "id": self.current_session.id,
            "url": self.current_session.url,
            "ip": self.current_session.ip_address,
            "port": self.current_session.port,
            "status": self.current_session.status.value,
            "files_count": len(self.current_session.files),
            "uploaded_count": len(self.current_session.uploaded_files),
            "duration": self.current_session.formatted_duration,
            "browser_count": browser_summary["count"],
            "browser_sessions": browser_summary["browsers"],
            "total_browser_downloads": browser_summary["total_downloads"],
            "total_browser_uploads": browser_summary["total_uploads"],
            "total_browser_bytes": browser_summary["total_bytes"],
            "websocket_count": browser_summary["websocket_count"],
        }
