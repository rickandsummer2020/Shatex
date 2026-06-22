"""Browser Push Service for ShareX.

Implements 'Send to Browser' functionality allowing users
to push files directly to connected browser sessions.
The browser receives a notification and auto-downloads the file.
"""

import os
import asyncio
import logging
import json
import hashlib
from pathlib import Path
from typing import Optional, Dict, List, Callable
from dataclasses import dataclass

from ..models.file_info import FileInfo
from ..models.webshare import WebShareSession
from ..services.webshare_server import WebShareServer, BrowserSession, WSMessage

logger = logging.getLogger(__name__)


@dataclass
class BrowserPushRequest:
    """Request to push a file to a browser."""
    file_path: str
    file_name: str
    file_size: int
    checksum: str
    target_session_id: str
    push_id: str
    download_url: str


class BrowserPushService:
    """Service for pushing files to connected browsers.

    Workflow:
    1. User selects files and target browser
    2. File is added to current WebShare session
    3. WebSocket notification sent to target browser
    4. Browser auto-initiates download via HTTP
    """

    def __init__(
        self,
        webshare_server: Optional[WebShareServer] = None,
        on_push_complete: Optional[Callable[[str, bool], None]] = None,
    ) -> None:
        """Initialize browser push service."""
        self.webshare_server = webshare_server
        self.on_push_complete = on_push_complete
        self._pending_pushes: Dict[str, BrowserPushRequest] = {}
        self._lock = asyncio.Lock()

    def attach_server(self, webshare_server: WebShareServer) -> None:
        """Attach to a running web share server."""
        self.webshare_server = webshare_server
        logger.info("BrowserPushService attached to WebShareServer")

    async def push_file(
        self,
        file_path: str,
        browser_session: BrowserSession,
        webshare_session: WebShareSession,
    ) -> Optional[BrowserPushRequest]:
        """Push a file to a specific browser session."""
        if not self.webshare_server:
            logger.error("No WebShareServer attached")
            return None

        path = Path(file_path)
        if not path.exists():
            logger.error(f"File not found: {file_path}")
            return None

        # Calculate checksum
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                sha256.update(chunk)
        checksum = sha256.hexdigest()

        # Add file to web share session
        file_info = FileInfo(
            name=path.name,
            path=str(path.resolve()),
            size=path.stat().st_size,
        )
        webshare_session.add_file(
            file_name=file_info.name,
            file_path=file_info.path,
            file_size=file_info.size,
        )

        # Create push request
        push_id = hashlib.sha256(
            f"{file_path}{browser_session.id}{asyncio.get_event_loop().time()}".encode()
        ).hexdigest()[:16]

        download_url = f"/download/{path.name}"

        request = BrowserPushRequest(
            file_path=str(path.resolve()),
            file_name=path.name,
            file_size=path.stat().st_size,
            checksum=checksum,
            target_session_id=browser_session.id,
            push_id=push_id,
            download_url=download_url,
        )

        async with self._lock:
            self._pending_pushes[push_id] = request

        # Send WebSocket notification to browser
        success = await self._notify_browser(browser_session, request)
        if not success:
            logger.warning(f"Failed to notify browser {browser_session.id}")
            return None

        logger.info(f"Push initiated: {path.name} → {browser_session.display_name}")
        return request

    async def push_files(
        self,
        file_paths: List[str],
        browser_session: BrowserSession,
        webshare_session: WebShareSession,
    ) -> List[BrowserPushRequest]:
        """Push multiple files to a browser."""
        results = []
        for path in file_paths:
            try:
                req = await self.push_file(path, browser_session, webshare_session)
                if req:
                    results.append(req)
            except Exception as e:
                logger.error(f"Push failed for {path}: {e}")
        return results

    async def _notify_browser(
        self,
        browser_session: BrowserSession,
        request: BrowserPushRequest,
    ) -> bool:
        """Send WebSocket notification to browser for auto-download."""
        if not self.webshare_server:
            return False

        try:
            message = WSMessage(
                type="file_push",
                payload={
                    "push_id": request.push_id,
                    "file_name": request.file_name,
                    "file_size": request.file_size,
                    "checksum": request.checksum,
                    "download_url": request.download_url,
                    "auto_download": True,
                    "timestamp": asyncio.get_event_loop().time(),
                }
            )

            await self.webshare_server._ws_manager.send_to_session(
                browser_session.id,
                message,
            )
            return True

        except Exception as e:
            logger.error(f"Browser notification error: {e}")
            return False

    async def handle_download_complete(self, push_id: str, success: bool) -> None:
        """Handle browser download completion."""
        async with self._lock:
            request = self._pending_pushes.pop(push_id, None)

        if request:
            logger.info(f"Push {push_id} completed: success={success}")

        if self.on_push_complete:
            try:
                self.on_push_complete(push_id, success)
            except Exception as e:
                logger.error(f"Push complete callback error: {e}")

    def get_pending_pushes(self) -> List[BrowserPushRequest]:
        """Get list of pending push requests."""
        return list(self._pending_pushes.values())

    def get_pending_for_browser(self, session_id: str) -> List[BrowserPushRequest]:
        """Get pending pushes for a specific browser session."""
        return [
            req for req in self._pending_pushes.values()
            if req.target_session_id == session_id
        ]
