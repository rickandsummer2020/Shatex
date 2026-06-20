"""Web Share Screen for ShareX."""

import asyncio
from typing import Optional
from textual.screen import Screen
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Button, Input, Label
from textual.reactive import reactive
from rich.text import Text

from ...config import get_config
from ...services.webshare_manager import WebShareManager
from ...models.webshare import WebShareSession, WebShareStatus
from ...models.file_info import FileInfo
from ...ui.modals import UploadApprovalDialog


class WebShareScreen(Screen):
    """Screen for Web Share mode - browser-based transfers."""

    DEFAULT_CSS = """
    WebShareScreen {
        align: center middle;
    }

    WebShareScreen .title {
        text-align: center;
        color: ansi_bright_cyan;
        text-style: bold;
        padding: 0;
        margin-top: 1;
    }

    WebShareScreen .subtitle {
        text-align: center;
        color: dimgrey;
        padding: 0;
        margin-bottom: 1;
    }

    WebShareScreen .status-box {
        background: #1a1a3e;
        border: solid blue;
        padding: 0 1;
        margin: 0 0 1 0;
        text-align: center;
        height: 3;
    }

    WebShareScreen .active {
        color: ansi_bright_green;
        border: solid green;
    }

    WebShareScreen .inactive {
        color: ansi_bright_red;
        border: solid red;
    }

    WebShareScreen .url-box {
        background: #0f0f23;
        border: solid ansi_bright_green;
        padding: 0 1;
        margin: 0 0 1 0;
        text-align: center;
        color: ansi_bright_green;
        text-style: bold;
        height: 3;
        display: none;
    }

    WebShareScreen .url-box.visible {
        display: block;
    }

    WebShareScreen .qr-container {
        align: center middle;
        height: auto;
        margin: 0 0 1 0;
    }

    WebShareScreen .qr-box {
        background: #000000;
        color: #ffffff;
        text-style: bold;
        width: auto;
        height: auto;
        padding: 1 2;
        display: none;
    }

    WebShareScreen .qr-box.visible {
        display: block;
    }

    WebShareScreen .info-box {
        background: #1a1a3e;
        border: solid blue;
        padding: 0 1;
        margin: 0 0 1 0;
        text-align: center;
        color: white;
        height: 3;
        display: none;
    }

    WebShareScreen .info-box.visible {
        display: block;
    }

    WebShareScreen .button-row {
        height: 3;
        margin-top: 1;
    }

    WebShareScreen .button-row Button {
        width: 1fr;
        margin: 0 1;
    }

    WebShareScreen .back-row {
        height: 3;
        margin-top: 1;
    }

    WebShareScreen .back-row Button {
        width: 100%;
        margin: 0 1;
    }
    """

    is_web_running: reactive[bool] = reactive(False)
    session_url: reactive[str] = reactive("")
    session_info: reactive[str] = reactive("Status: Stopped")
    qr_display: reactive[str] = reactive("")

    def __init__(self) -> None:
        """Initialize web share screen."""
        super().__init__()
        self.webshare_manager: WebShareManager | None = None
        self._update_task: asyncio.Task | None = None

    def compose(self) -> None:
        """Compose screen."""
        yield Static("Web Share", classes="title")
        yield Static("Share via browser - no install needed", classes="subtitle")
        yield Static("─" * 40, classes="subtitle")

        status_classes = "status-box active" if self.is_web_running else "status-box inactive"
        yield Static(self.session_info, id="status", classes=status_classes)

        url_classes = "url-box visible" if self.is_web_running and self.session_url else "url-box"
        url_text = f"URL: {self.session_url}" if self.session_url else ""
        yield Static(url_text, id="url", classes=url_classes)

        # Center the QR code inside a horizontal row container
        with Horizontal(classes="qr-container"):
            qr_classes = "qr-box visible" if self.is_web_running and self.qr_display else "qr-box"
            qr_content = Text(self.qr_display) if self.qr_display else ""
            yield Static(qr_content, id="qr", classes=qr_classes)

        info_classes = "info-box visible" if self.is_web_running else "info-box"
        yield Static("", id="details", classes=info_classes)

        # Grouping buttons horizontally to save valuable screen height
        with Horizontal(classes="button-row"):
            if self.is_web_running:
                yield Button("Stop Web Share", id="stop", variant="error")
            else:
                yield Button("Start Web Share", id="start", variant="success")

        # Back button in its own row to ensure visibility
        with Horizontal(classes="back-row"):
            yield Button("Back", id="back")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        button_id = event.button.id

        if button_id == "back":
            self.app.pop_screen()
        elif button_id == "start":
            asyncio.create_task(self._start_webshare())
        elif button_id == "stop":
            asyncio.create_task(self._stop_webshare())

    def _get_compact_qr(self, url: str) -> str:
        """Generate highly compact Unicode half-block QR code for terminals."""
        try:
            import qrcode
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=1,
                border=1,
            )
            qr.add_data(url)
            qr.make(fit=True)
            matrix = qr.get_matrix()
            
            lines = []
            # Bundle 2 rows into 1 printed terminal line using half-block characters
            for r in range(0, len(matrix), 2):
                row1 = matrix[r]
                row2 = matrix[r+1] if r+1 < len(matrix) else [False] * len(row1)
                
                line = ""
                for c in range(len(row1)):
                    top = row1[c]
                    bottom = row2[c]
                    if top and bottom:
                        line += "█"
                    elif top:
                        line += "▀"
                    elif bottom:
                        line += "▄"
                    else:
                        line += " "
                lines.append(line)
            return "\n".join(lines)
        except Exception as e:
            return "QR Code Error"

    async def _start_webshare(self) -> None:
        """Start web share server."""
        try:
            self.webshare_manager = WebShareManager(
                on_upload_request=self._handle_upload_request,
                on_status_change=self._handle_status_change,
            )

            session = await self.webshare_manager.create_session(
                allow_upload=True,
            )
            await self.webshare_manager.start_server()

            self.is_web_running = True
            self.session_url = session.url
            self.session_info = f"Active - {session.ip_address}:{session.port}"

            # Calculate the compact QR display data locally
            self.qr_display = self._get_compact_qr(session.url)

            # Rebuild UI with fresh data
            self.refresh(recompose=True)

            try:
                details = self.query_one("#details", Static)
                if details:
                    details.update(
                        f"Files: {len(session.files)} | "
                        f"Uploaded: {len(session.uploaded_files)}"
                    )
            except Exception:
                pass

            # Start periodic update
            self._update_task = asyncio.create_task(self._update_loop())

        except Exception as e:
            self.session_info = f"Error: {str(e)[:30]}"
            self.refresh(recompose=True)

    async def _stop_webshare(self) -> None:
        """Stop web share server."""
        if self.webshare_manager:
            await self.webshare_manager.stop_server()
            self.webshare_manager = None

        if self._update_task:
            self._update_task.cancel()
            self._update_task = None

        self.is_web_running = False
        self.session_url = ""
        self.session_info = "Status: Stopped"
        self.qr_display = ""

        self.refresh(recompose=True)

    async def _update_loop(self) -> None:
        """Periodic UI update loop."""
        try:
            while self.is_web_running and self.webshare_manager:
                await asyncio.sleep(2)
                if self.webshare_manager and self.webshare_manager.current_session:
                    session = self.webshare_manager.current_session
                    try:
                        details = self.query_one("#details", Static)
                        if details:
                            details.update(
                                f"Files: {len(session.files)} | "
                                f"Uploaded: {len(session.uploaded_files)} | "
                                f"Duration: {session.formatted_duration}"
                            )
                    except Exception:
                        pass
        except asyncio.CancelledError:
            pass

    async def _handle_upload_request(self, request) -> bool:
        """Handle upload approval request without requiring a worker context."""
        from ...utils.terminal import format_bytes
        size_str = format_bytes(request.file_size)

        loop = asyncio.get_running_loop()
        future = loop.create_future()

        def on_dismiss(result: Optional[bool]) -> None:
            if not future.done():
                future.set_result(result if result is not None else False)

        self.app.push_screen(
            UploadApprovalDialog(
                device_ip=request.client_ip,
                filename=request.filename,
                file_size=size_str,
            ),
            callback=on_dismiss
        )

        return await future

    def _handle_status_change(self, status: WebShareStatus) -> None:
        """Handle status change."""
        try:
            status_widget = self.query_one("#status", Static)
            if status_widget:
                status_widget.update(f"Status: {status.value.title()}")
        except Exception:
            pass

    def on_unmount(self) -> None:
        """Cleanup on unmount."""
        if self._update_task:
            self._update_task.cancel()
