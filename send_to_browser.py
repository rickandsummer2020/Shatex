"""Send to Browser screen for ShareX.

Allows users to select files and push them to connected
browser sessions. The browser receives a notification and
auto-downloads the files.
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
    Static, Button, Label, ListView, ListItem, Input, Header, Footer,
)

from ..services.webshare_manager import WebShareManager
from ..services.webshare_server import BrowserSession
from ..services.browser_push import BrowserPushService
from ..models.file_info import FileInfo
from ..models.webshare import WebShareStatus
from ..ui.modals import ConfirmDialog, ErrorDialog, SuccessDialog

logger = logging.getLogger(__name__)


class BrowserListItem(ListItem):
    """Custom list item for browser sessions."""
    def __init__(self, browser: BrowserSession) -> None:
        self.browser = browser
        super().__init__(Label(f"{browser.display_name} ({browser.ip_address})"))


class SendToBrowserScreen(Screen):
    """Screen for sending files to connected browsers."""

    CSS = """
    Screen { align: center middle; }
    .container { width: 100%; height: 100%; padding: 0 1; }
    .header { height: auto; text-align: center; color: $primary; text-style: bold; padding: 1 0; border-bottom: solid $primary; }
    .browser-section { height: 1fr; border: solid $primary-darken-2; padding: 1; margin: 1 0; }
    .files-section { height: 1fr; border: solid $success-darken-2; padding: 1; margin: 1 0; }
    .section-title { color: $primary; text-style: bold; padding: 0 0 1 0; }
    .controls { height: auto; padding: 1 0; }
    .status-bar { height: auto; text-align: center; color: $text-muted; padding: 1 0; }
    .empty-state { text-align: center; color: $text-muted; padding: 2; }
    """

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("q", "quit", "Quit"),
        ("b", "refresh_browsers", "Refresh"),
        ("s", "send_files", "Send"),
        ("a", "add_files", "Add Files"),
        ("c", "clear_files", "Clear"),
    ]

    selected_browser: reactive[Optional[BrowserSession]] = reactive(None)
    selected_files: reactive[List[str]] = reactive([])
    browser_sessions: reactive[List[BrowserSession]] = reactive([])
    is_sending: reactive[bool] = reactive(False)

    def __init__(
        self,
        webshare_manager: Optional[WebShareManager] = None,
        browser_push: Optional[BrowserPushService] = None,
    ) -> None:
        super().__init__()
        self.webshare_manager = webshare_manager
        self.browser_push = browser_push or BrowserPushService()
        self._file_paths: List[str] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(classes="container"):
            yield Static("Send to Browser", classes="header")
            with Container(classes="browser-section"):
                yield Static("Connected Browsers", classes="section-title")
                yield Static("No browsers connected. Start Web Share first.", classes="empty-state", id="empty-browsers")
                yield ListView(id="browser-list")
            with Container(classes="files-section"):
                yield Static("Selected Files", classes="section-title")
                yield Static("No files selected", classes="empty-state", id="empty-files")
                yield ListView(id="file-list")
            with Container(classes="controls"):
                with Horizontal():
                    yield Button("Refresh", id="btn-refresh", variant="primary")
                    yield Button("Add Files", id="btn-add", variant="primary")
                    yield Button("Clear", id="btn-clear", variant="warning")
                    yield Button("Send", id="btn-send", variant="success", disabled=True)
            yield Static("Select a browser and files, then click Send", classes="status-bar", id="status-text")
        yield Footer()

    async def on_mount(self) -> None:
        await self._refresh_browsers()

    async def _refresh_browsers(self) -> None:
        if not self.webshare_manager or not self.webshare_manager.server:
            self._update_browser_list([])
            return
        sessions = self.webshare_manager.get_browser_sessions()
        self.browser_sessions = sessions
        self._update_browser_list(sessions)

    def _update_browser_list(self, sessions: List[BrowserSession]) -> None:
        browser_list = self.query_one("#browser-list", ListView)
        empty = self.query_one("#empty-browsers", Static)
        browser_list.clear()
        if not sessions:
            empty.styles.display = "block"
            return
        empty.styles.display = "none"
        for session in sessions:
            browser_list.append(BrowserListItem(session))

    def _update_file_list(self) -> None:
        file_list = self.query_one("#file-list", ListView)
        empty = self.query_one("#empty-files", Static)
        file_list.clear()
        if not self._file_paths:
            empty.styles.display = "block"
            return
        empty.styles.display = "none"
        for path in self._file_paths:
            name = Path(path).name
            size = Path(path).stat().st_size
            size_str = self._format_size(size)
            file_list.append(ListItem(Label(f"{name} ({size_str})")))
        self._update_send_button()

    def _format_size(self, size: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def _update_send_button(self) -> None:
        btn = self.query_one("#btn-send", Button)
        can_send = (
            self.selected_browser is not None
            and len(self._file_paths) > 0
            and not self.is_sending
        )
        btn.disabled = not can_send
        status = self.query_one("#status-text", Static)
        if can_send:
            status.update(f"Ready: {len(self._file_paths)} file(s) → {self.selected_browser.display_name}")
        elif not self.selected_browser:
            status.update("Select a browser from the list above")
        elif not self._file_paths:
            status.update("Add files to send")
        else:
            status.update("Sending...")

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, BrowserListItem):
            self.selected_browser = event.item.browser
            self._update_send_button()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn-refresh":
            await self._refresh_browsers()
        elif btn_id == "btn-add":
            await self._add_files()
        elif btn_id == "btn-clear":
            self._file_paths.clear()
            self._update_file_list()
            self._update_send_button()
        elif btn_id == "btn-send":
            await self._send_files()

    async def _add_files(self) -> None:
        dialog = InputDialog(title="Add File Path", placeholder="/path/to/file")
        path = await self.app.push_screen(dialog)
        if path and Path(path).exists():
            self._file_paths.append(path)
            self._update_file_list()
        elif path:
            self.app.push_screen(ErrorDialog(f"File not found: {path}"))

    async def _send_files(self) -> None:
        if not self.selected_browser or not self._file_paths:
            return
        if not self.webshare_manager or not self.webshare_manager.current_session:
            self.app.push_screen(ErrorDialog("Web Share session not active"))
            return

        self.is_sending = True
        self._update_send_button()
        try:
            if self.webshare_manager.server and not self.browser_push.webshare_server:
                self.browser_push.attach_server(self.webshare_manager.server)
            results = await self.browser_push.push_files(
                file_paths=self._file_paths,
                browser_session=self.selected_browser,
                webshare_session=self.webshare_manager.current_session,
            )
            if results:
                self.app.push_screen(SuccessDialog(
                    f"Sent {len(results)} file(s) to {self.selected_browser.display_name}\nBrowser will auto-download."
                ))
                self._file_paths.clear()
                self._update_file_list()
            else:
                self.app.push_screen(ErrorDialog("Failed to push files"))
        except Exception as e:
            logger.error(f"Send to browser error: {e}")
            self.app.push_screen(ErrorDialog(f"Error: {e}"))
        finally:
            self.is_sending = False
            self._update_send_button()

    async def action_refresh_browsers(self) -> None:
        await self._refresh_browsers()

    async def action_send_files(self) -> None:
        await self._send_files()

    async def action_add_files(self) -> None:
        await self._add_files()

    async def action_clear_files(self) -> None:
        self._file_paths.clear()
        self._update_file_list()
        self._update_send_button()
