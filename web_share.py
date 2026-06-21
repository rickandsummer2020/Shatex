"""Web Share screen for ShareX.

Provides UI for managing web share sessions including
start/stop, QR code display, file management, upload
approvals, and live browser status.

ENHANCED: Live browser count, browser session display,
real-time browser status updates.
"""

import asyncio
import logging
from typing import Optional, List
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, Container
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import (
    Static,
    Button,
    Label,
    ListView,
    ListItem,
    Input,
    Checkbox,
    Header,
    Footer,
)
from textual.worker import Worker, WorkerState

from ..services.webshare_manager import WebShareManager
from ..services.webshare_server import UploadRequest, BrowserSession
from ..models.file_info import FileInfo
from ..models.webshare import WebShareStatus
from ..ui.modals import (
    UploadApprovalDialog,
    ErrorDialog,
    SuccessDialog,
    ConfirmDialog,
)
from ..config import get_config

logger = logging.getLogger(__name__)


class WebShareScreen(Screen):
    """Screen for managing web share sessions.

    Allows users to start/stop web share, view QR code,
    manage shared files, approve uploads, and monitor
    connected browser sessions.

    ENHANCED: Live browser status display and updates.
    """

    CSS = """
    Screen { align: center middle; }

    .webshare-container {
        width: 100%;
        height: 100%;
        padding: 0 1;
    }

    .header-section {
        height: auto;
        padding: 1 0;
        border-bottom: solid $primary;
    }

    .title {
        text-align: center;
        color: $primary;
        text-style: bold;
    }

    .status-bar {
        height: auto;
        padding: 0 1;
        margin: 1 0;
    }

    .status-active { color: $success; }
    .status-inactive { color: $warning; }
    .status-error { color: $error; }

    .qr-section {
        height: auto;
        padding: 1;
        border: solid $primary-darken-2;
        margin: 1 0;
    }

    .qr-code {
        text-align: center;
        color: $primary;
    }

    .url-display {
        text-align: center;
        color: $success;
        text-style: bold;
    }

    .info-grid {
        layout: grid;
        grid-size: 2;
        grid-gutter: 1;
        height: auto;
        padding: 1 0;
    }

    .info-item {
        padding: 0 1;
    }

    .info-label {
        color: $text-muted;
    }

    .info-value {
        color: $text;
        text-style: bold;
    }

    .files-section {
        height: 1fr;
        border: solid $primary-darken-2;
        padding: 1;
    }

    .section-title {
        color: $primary;
        text-style: bold;
        padding: 0 0 1 0;
    }

    .file-list {
        height: 1fr;
        border: solid $surface-darken-1;
    }

    .controls {
        height: auto;
        padding: 1 0;
    }

    .btn-start { background: $success; color: $text; }
    .btn-stop { background: $error; color: $text; }
    .btn-add { background: $primary; color: $text; }
    .btn-clear { background: $warning; color: $text; }

    .uploads-section {
        height: auto;
        max-height: 8;
        border: solid $warning-darken-2;
        padding: 1;
        margin: 1 0;
    }

    .upload-item {
        padding: 0 1;
        color: $warning;
    }

    .empty-state {
        text-align: center;
        color: $text-muted;
        padding: 2;
    }

    .browser-section {
        height: auto;
        max-height: 10;
        border: solid $primary-darken-2;
        padding: 1;
        margin: 1 0;
    }

    .browser-item {
        padding: 0 1;
        color: $text;
    }

    .browser-active {
        color: $success;
    }

    .browser-count {
        text-align: center;
        color: $primary;
        text-style: bold;
        padding: 1 0;
    }

    .browser-stats {
        layout: grid;
        grid-size: 3;
        grid-gutter: 1;
        height: auto;
        padding: 1 0;
    }

    .browser-stat {
        text-align: center;
    }

    .browser-stat-value {
        color: $primary;
        text-style: bold;
    }

    .browser-stat-label {
        color: $text-muted;
        text-style: italic;
    }
    """

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("q", "quit", "Quit"),
        ("s", "toggle_share", "Toggle Share"),
        ("a", "add_files", "Add Files"),
        ("c", "clear_files", "Clear Files"),
    ]

    # Reactive properties for live updates
    is_sharing: reactive[bool] = reactive(False)
    session_url: reactive[str] = reactive("")
    session_status: reactive[str] = reactive("inactive")
    shared_files_count: reactive[int] = reactive(0)
    uploaded_files_count: reactive[int] = reactive(0)
    session_duration: reactive[str] = reactive("0s")

    # NEW: Browser session reactive properties
    browser_count: reactive[int] = reactive(0)
    browser_sessions: reactive[List[dict]] = reactive([])
    total_browser_downloads: reactive[int] = reactive(0)
    total_browser_uploads: reactive[int] = reactive(0)
    total_browser_bytes: reactive[str] = reactive("0 B")

    def __init__(self, webshare_manager: Optional[WebShareManager] = None) -> None:
        """Initialize web share screen.

        Args:
            webshare_manager: WebShareManager instance.
        """
        super().__init__()
        self.webshare_manager = webshare_manager
        self._update_task: Optional[asyncio.Task] = None
        self._pending_uploads: List[UploadRequest] = []
        self._browser_update_task: Optional[asyncio.Task] = None

    def compose(self) -> ComposeResult:
        """Compose the screen layout."""
        yield Header(show_clock=True)

        with Container(classes="webshare-container"):
            # Header
            with Container(classes="header-section"):
                yield Static("Web Share", classes="title")

            # Status bar
            with Container(classes="status-bar"):
                yield Static(
                    "Status: Not Sharing",
                    id="status-text",
                    classes="status-inactive",
                )

            # QR Code section (visible when sharing)
            with Container(classes="qr-section", id="qr-section"):
                yield Static("", classes="qr-code", id="qr-code")
                yield Static("", classes="url-display", id="url-display")

            # Info grid
            with Container(classes="info-grid", id="info-grid"):
                with Container(classes="info-item"):
                    yield Static("Files:", classes="info-label")
                    yield Static("0", classes="info-value", id="files-count")
                with Container(classes="info-item"):
                    yield Static("Uploaded:", classes="info-label")
                    yield Static("0", classes="info-value", id="uploaded-count")
                with Container(classes="info-item"):
                    yield Static("Duration:", classes="info-label")
                    yield Static("0s", classes="info-value", id="duration")
                with Container(classes="info-item"):
                    yield Static("Port:", classes="info-label")
                    yield Static("-", classes="info-value", id="port")

            # NEW: Browser sessions section
            with Container(classes="browser-section", id="browser-section"):
                yield Static("Connected Browsers", classes="section-title")
                yield Static(
                    "No browsers connected",
                    classes="browser-count",
                    id="browser-count",
                )
                with Container(classes="browser-stats", id="browser-stats"):
                    with Container(classes="browser-stat"):
                        yield Static("0", classes="browser-stat-value", id="stat-downloads")
                        yield Static("Downloads", classes="browser-stat-label")
                    with Container(classes="browser-stat"):
                        yield Static("0", classes="browser-stat-value", id="stat-uploads")
                        yield Static("Uploads", classes="browser-stat-label")
                    with Container(classes="browser-stat"):
                        yield Static("0 B", classes="browser-stat-value", id="stat-bytes")
                        yield Static("Transferred", classes="browser-stat-label")
                yield ListView(id="browser-list")

            # Files section
            with Container(classes="files-section"):
                yield Static("Shared Files", classes="section-title")
                yield ListView(id="file-list")
                yield Static(
                    "No files shared",
                    classes="empty-state",
                    id="empty-files",
                )

            # Pending uploads
            with Container(classes="uploads-section", id="uploads-section"):
                yield Static("Pending Uploads", classes="section-title")
                yield Static(
                    "No pending uploads",
                    classes="empty-state",
                    id="empty-uploads",
                )

            # Controls
            with Container(classes="controls"):
                with Horizontal():
                    yield Button(
                        "Start Sharing",
                        id="btn-start",
                        variant="success",
                        classes="btn-start",
                    )
                    yield Button(
                        "Stop Sharing",
                        id="btn-stop",
                        variant="error",
                        classes="btn-stop",
                        disabled=True,
                    )
                    yield Button(
                        "Add Files",
                        id="btn-add",
                        variant="primary",
                        classes="btn-add",
                    )
                    yield Button(
                        "Clear Files",
                        id="btn-clear",
                        variant="warning",
                        classes="btn-clear",
                    )

        yield Footer()

    def on_mount(self) -> None:
        """Handle screen mount."""
        self._update_ui_state()
        self._start_update_loop()
        self._start_browser_update_loop()  # NEW

    def on_unmount(self) -> None:
        """Handle screen unmount."""
        self._stop_update_loop()
        self._stop_browser_update_loop()  # NEW

    def _start_update_loop(self) -> None:
        """Start periodic UI update loop."""
        if self._update_task is None:
            self._update_task = asyncio.create_task(self._update_loop())

    def _stop_update_loop(self) -> None:
        """Stop periodic UI update loop."""
        if self._update_task:
            self._update_task.cancel()
            self._update_task = None

    # NEW: Browser update loop
    def _start_browser_update_loop(self) -> None:
        """Start periodic browser status update loop."""
        if self._browser_update_task is None:
            self._browser_update_task = asyncio.create_task(
                self._browser_update_loop()
            )

    def _stop_browser_update_loop(self) -> None:
        """Stop periodic browser status update loop."""
        if self._browser_update_task:
            self._browser_update_task.cancel()
            self._browser_update_task = None

    async def _update_loop(self) -> None:
        """Periodic update loop for session info."""
        try:
            while True:
                await asyncio.sleep(2)
                if self.webshare_manager and self.webshare_manager.is_running:
                    self._update_session_info()
                    self._update_uploads_list()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Update loop error: {e}")

    # NEW: Browser update loop
    async def _browser_update_loop(self) -> None:
        """Periodic update loop for browser sessions."""
        try:
            while True:
                await asyncio.sleep(3)  # Update every 3 seconds
                if self.webshare_manager and self.webshare_manager.is_running:
                    self._update_browser_info()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Browser update loop error: {e}")

    def _update_session_info(self) -> None:
        """Update reactive properties from manager."""
        if not self.webshare_manager:
            return

        info = self.webshare_manager.session_info
        if info:
            self.session_url = info.get("url", "")
            self.session_status = info.get("status", "inactive")
            self.shared_files_count = info.get("files_count", 0)
            self.uploaded_files_count = info.get("uploaded_count", 0)
            self.session_duration = info.get("duration", "0s")

            # NEW: Update browser reactive properties
            self.browser_count = info.get("browser_count", 0)
            self.browser_sessions = info.get("browser_sessions", [])
            self.total_browser_downloads = info.get("total_browser_downloads", 0)
            self.total_browser_uploads = info.get("total_browser_uploads", 0)
            total_bytes = info.get("total_browser_bytes", 0)
            self.total_browser_bytes = self._format_size(total_bytes)

    def _update_browser_info(self) -> None:
        """Update browser session display."""
        if not self.webshare_manager or not self.webshare_manager.is_running:
            return

        try:
            summary = self.webshare_manager.get_browser_summary()
            self.browser_count = summary["count"]
            self.browser_sessions = summary["browsers"]
            self.total_browser_downloads = summary["total_downloads"]
            self.total_browser_uploads = summary["total_uploads"]
            self.total_browser_bytes = self._format_size(summary["total_bytes"])
        except Exception as e:
            logger.error(f"Error updating browser info: {e}")

    def _update_uploads_list(self) -> None:
        """Update pending uploads display."""
        if not self.webshare_manager:
            return

        uploads = self.webshare_manager.get_pending_uploads()
        self._pending_uploads = uploads

        uploads_container = self.query_one("#uploads-section", Container)
        empty_uploads = self.query_one("#empty-uploads", Static)

        if uploads:
            empty_uploads.display = False
            # Clear and rebuild upload list
            for child in list(uploads_container.children):
                if isinstance(child, Static) and child.id != "empty-uploads":
                    child.remove()

            for upload in uploads:
                upload_text = f"{upload.filename} ({self._format_size(upload.file_size)}) from {upload.client_ip}"
                uploads_container.mount(
                    Static(upload_text, classes="upload-item")
                )
        else:
            empty_uploads.display = True
            # Clear upload items
            for child in list(uploads_container.children):
                if isinstance(child, Static) and child.id != "empty-uploads":
                    child.remove()

    def watch_is_sharing(self, sharing: bool) -> None:
        """Watch is_sharing changes."""
        self._update_ui_state()

    def watch_session_url(self, url: str) -> None:
        """Watch session_url changes."""
        url_display = self.query_one("#url-display", Static)
        if url:
            url_display.update(f"URL: {url}")
        else:
            url_display.update("")

    def watch_session_status(self, status: str) -> None:
        """Watch session_status changes."""
        status_text = self.query_one("#status-text", Static)
        if status == "active":
            status_text.update("Status: Active")
            status_text.classes = "status-active"
        elif status == "error":
            status_text.update("Status: Error")
            status_text.classes = "status-error"
        else:
            status_text.update("Status: Not Sharing")
            status_text.classes = "status-inactive"

    def watch_shared_files_count(self, count: int) -> None:
        """Watch shared_files_count changes."""
        files_count = self.query_one("#files-count", Static)
        files_count.update(str(count))

    def watch_uploaded_files_count(self, count: int) -> None:
        """Watch uploaded_files_count changes."""
        uploaded_count = self.query_one("#uploaded-count", Static)
        uploaded_count.update(str(count))

    def watch_session_duration(self, duration: str) -> None:
        """Watch session_duration changes."""
        duration_display = self.query_one("#duration", Static)
        duration_display.update(duration)

    # NEW: Watch browser reactive properties
    def watch_browser_count(self, count: int) -> None:
        """Watch browser_count changes."""
        browser_count = self.query_one("#browser-count", Static)
        if count == 0:
            browser_count.update("No browsers connected")
        elif count == 1:
            browser_count.update("1 browser connected")
        else:
            browser_count.update(f"{count} browsers connected")

    def watch_browser_sessions(self, sessions: List[dict]) -> None:
        """Watch browser_sessions changes."""
        browser_list = self.query_one("#browser-list", ListView)
        browser_list.clear()

        if sessions:
            for session in sessions:
                display_name = session.get("display_name", "Unknown Browser")
                duration = session.get("duration", "0s")
                downloads = session.get("files_downloaded", 0)
                uploads = session.get("files_uploaded", 0)

                text = f"{display_name} - {duration} | ↓{downloads} ↑{uploads}"
                browser_list.append(ListItem(Static(text, classes="browser-item")))
        else:
            browser_list.append(ListItem(Static("No active browsers", classes="empty-state")))

    def watch_total_browser_downloads(self, count: int) -> None:
        """Watch total_browser_downloads changes."""
        stat = self.query_one("#stat-downloads", Static)
        stat.update(str(count))

    def watch_total_browser_uploads(self, count: int) -> None:
        """Watch total_browser_uploads changes."""
        stat = self.query_one("#stat-uploads", Static)
        stat.update(str(count))

    def watch_total_browser_bytes(self, size: str) -> None:
        """Watch total_browser_bytes changes."""
        stat = self.query_one("#stat-bytes", Static)
        stat.update(size)

    def _update_ui_state(self) -> None:
        """Update UI based on current state."""
        qr_section = self.query_one("#qr-section", Container)
        info_grid = self.query_one("#info-grid", Container)
        browser_section = self.query_one("#browser-section", Container)
        btn_start = self.query_one("#btn-start", Button)
        btn_stop = self.query_one("#btn-stop", Button)
        btn_add = self.query_one("#btn-add", Button)
        btn_clear = self.query_one("#btn-clear", Button)

        if self.is_sharing:
            qr_section.display = True
            info_grid.display = True
            browser_section.display = True
            btn_start.disabled = True
            btn_stop.disabled = False
            btn_add.disabled = False
            btn_clear.disabled = False
        else:
            qr_section.display = False
            info_grid.display = False
            browser_section.display = False
            btn_start.disabled = False
            btn_stop.disabled = True
            btn_add.disabled = True
            btn_clear.disabled = True

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "btn-start":
            await self._start_sharing()
        elif button_id == "btn-stop":
            await self._stop_sharing()
        elif button_id == "btn-add":
            await self._add_files()
        elif button_id == "btn-clear":
            await self._clear_files()

    async def _start_sharing(self) -> None:
        """Start web share session."""
        try:
            if not self.webshare_manager:
                self.app.push_screen(
                    ErrorDialog("WebShareManager not available")
                )
                return

            # Get files from engine
            files = []
            if hasattr(self.app, "engine") and self.app.engine:
                # Try to get selected files from engine
                pass

            # Create session
            session = await self.webshare_manager.create_session(
                files=files,
                allow_upload=True,
            )

            # Start server with callbacks
            await self.webshare_manager.start_server()

            self.is_sharing = True
            self.session_url = session.url
            self.session_status = "active"

            # Update QR code display
            qr_code = self.webshare_manager.get_qr_code_lines()
            qr_display = self.query_one("#qr-code", Static)
            qr_display.update("\n".join(qr_code))

            # Update port display
            port_display = self.query_one("#port", Static)
            port_display.update(str(session.port))

            self.app.notify("Web share started!", severity="information")
            logger.info(f"Web share started: {session.url}")

        except Exception as e:
            logger.error(f"Failed to start web share: {e}")
            self.app.push_screen(
                ErrorDialog(f"Failed to start web share: {e}")
            )

    async def _stop_sharing(self) -> None:
        """Stop web share session."""
        try:
            if self.webshare_manager:
                await self.webshare_manager.stop_server()

            self.is_sharing = False
            self.session_url = ""
            self.session_status = "inactive"
            self.shared_files_count = 0
            self.uploaded_files_count = 0
            self.session_duration = "0s"

            # NEW: Reset browser stats
            self.browser_count = 0
            self.browser_sessions = []
            self.total_browser_downloads = 0
            self.total_browser_uploads = 0
            self.total_browser_bytes = "0 B"

            self.app.notify("Web share stopped", severity="information")
            logger.info("Web share stopped")

        except Exception as e:
            logger.error(f"Error stopping web share: {e}")
            self.app.push_screen(
                ErrorDialog(f"Error stopping web share: {e}")
            )

    async def _add_files(self) -> None:
        """Add files to web share session."""
        try:
            if not self.webshare_manager or not self.webshare_manager.is_running:
                self.app.notify("Start sharing first", severity="warning")
                return

            # Show file picker or get files from engine
            # For now, show a message
            self.app.notify("File selection not implemented in UI", severity="warning")

        except Exception as e:
            logger.error(f"Error adding files: {e}")
            self.app.push_screen(
                ErrorDialog(f"Error adding files: {e}")
            )

    async def _clear_files(self) -> None:
        """Clear shared files."""
        try:
            if not self.webshare_manager or not self.webshare_manager.is_running:
                return

            # Clear files from session
            if self.webshare_manager.current_session:
                self.webshare_manager.current_session.files = []
                self.shared_files_count = 0

            self.app.notify("Shared files cleared", severity="information")

        except Exception as e:
            logger.error(f"Error clearing files: {e}")

    async def _handle_upload_request(self, request: UploadRequest) -> bool:
        """Handle upload approval request.

        Args:
            request: Upload request to approve.

        Returns:
            True if approved.
        """
        try:
            # Show approval dialog
            result = await self.app.push_screen_wait(
                UploadApprovalDialog(
                    filename=request.filename,
                    file_size=self._format_size(request.file_size),
                    client_ip=request.client_ip,
                )
            )
            return result
        except Exception as e:
            logger.error(f"Upload approval error: {e}")
            return False

    def _handle_browser_update(self, sessions: List[BrowserSession]) -> None:
        """Handle browser session updates from server.

        NEW: Callback for real-time browser updates.

        Args:
            sessions: Updated browser sessions.
        """
        try:
            # Update reactive properties
            self.browser_count = len(sessions)
            self.browser_sessions = [s.to_dict() for s in sessions]

            # Calculate totals
            self.total_browser_downloads = sum(s.files_downloaded for s in sessions)
            self.total_browser_uploads = sum(s.files_uploaded for s in sessions)
            total_bytes = sum(s.bytes_transferred for s in sessions)
            self.total_browser_bytes = self._format_size(total_bytes)

            # Notify user of new connections
            if len(sessions) > getattr(self, '_last_browser_count', 0):
                new_count = len(sessions) - getattr(self, '_last_browser_count', 0)
                if new_count > 0:
                    self.app.notify(
                        f"{new_count} new browser{'s' if new_count > 1 else ''} connected",
                        severity="information"
                    )

            self._last_browser_count = len(sessions)

        except Exception as e:
            logger.error(f"Browser update handler error: {e}")

    @staticmethod
    def _format_size(size: int) -> str:
        """Format bytes to human-readable string.

        Args:
            size: Size in bytes.

        Returns:
            Formatted string.
        """
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def action_toggle_share(self) -> None:
        """Toggle web share on/off."""
        if self.is_sharing:
            asyncio.create_task(self._stop_sharing())
        else:
            asyncio.create_task(self._start_sharing())

    def action_add_files(self) -> None:
        """Add files action."""
        asyncio.create_task(self._add_files())

    def action_clear_files(self) -> None:
        """Clear files action."""
        asyncio.create_task(self._clear_files())

    def _show_demo_data(self) -> None:
        """Show demo data when engine is not available."""
        self.is_sharing = True
        self.session_url = "http://192.168.1.100:8080"
        self.session_status = "active"
        self.shared_files_count = 3
        self.uploaded_files_count = 1
        self.session_duration = "5m 30s"

        # NEW: Demo browser data
        self.browser_count = 2
        self.browser_sessions = [
            {
                "display_name": "Chrome on Android",
                "duration": "2m 15s",
                "files_downloaded": 1,
                "files_uploaded": 0,
            },
            {
                "display_name": "Safari on iOS",
                "duration": "1m 45s",
                "files_downloaded": 0,
                "files_uploaded": 1,
            },
        ]
        self.total_browser_downloads = 1
        self.total_browser_uploads = 1
        self.total_browser_bytes = "15.5 MB"

        # Update QR code
        qr_display = self.query_one("#qr-code", Static)
        qr_display.update("█▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀█\n" +
                         "█  ▄▄▄▄▄  ▄▄▄▄▄  ▄▄▄▄▄  ▄▄▄▄▄  ▄▄▄▄▄  █\n" +
                         "█  █   █  █   █  █   █  █   █  █   █  █\n" +
                         "█  █   █  █   █  █   █  █   █  █   █  █\n" +
                         "█  ▀▀▀▀▀  ▀▀▀▀▀  ▀▀▀▀▀  ▀▀▀▀▀  ▀▀▀▀▀  █\n" +
                         "█▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀█")

        # Update file list
        file_list = self.query_one("#file-list", ListView)
        file_list.append(ListItem(Static("document.pdf (2.5 MB)")))
        file_list.append(ListItem(Static("image.jpg (1.8 MB)")))
        file_list.append(ListItem(Static("archive.zip (15.2 MB)")))
