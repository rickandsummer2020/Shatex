"""Main UI Application for ShareX.

Textual-based terminal UI optimized for mobile Termux.
Maximum 44 columns, 22 rows.
"""

import asyncio
import logging
from typing import Optional

from textual.app import App
from textual.reactive import reactive
from textual.binding import Binding

from ..config import get_config, MAX_TERMINAL_WIDTH, MAX_TERMINAL_HEIGHT, init_logging
from ..core.engine_integration import ExtendedEngine
from ..utils.terminal import check_terminal_size
from .screens.main_menu import MainMenuScreen
from .screens.send_files import SendFilesScreen
from .screens.receive_files import ReceiveFilesScreen
from .screens.nearby_devices import NearbyDevicesScreen
from .screens.transfer_history import TransferHistoryScreen
from .screens.trusted_devices import TrustedDevicesScreen
from .screens.web_share import WebShareScreen
from .screens.settings import SettingsScreen
from .screens.about import AboutScreen
from .screens.transfer_progress import TransferProgressScreen
from .screens.send_to_browser import SendToBrowserScreen
from .screens.transfer_queue_screen import TransferQueueScreen

logger = logging.getLogger(__name__)


class ShareXApp(App):
    """Main ShareX Terminal Application.

    Optimized for mobile Termux with 44x22 terminal.
    Dark theme with modern styling.

    Key Bindings:
        q: Quit
        s: Send Files
        r: Receive Files
        d: Nearby Devices
        h: History
        t: Trusted Devices
        w: Web Share
        escape: Back/Cancel
    """

    CSS = """
    Screen {
        align: center middle;
        background: #0f0f23;
        color: #eaeaea;
    }

    .title {
        text-align: center;
        color: #00d9ff;
        text-style: bold;
        padding: 1;
    }

    .subtitle {
        text-align: center;
        color: #a0a0a0;
        padding: 0;
    }

    Button {
        width: 100%;
        background: #1a1a3e;
        color: #eaeaea;
        border: solid #0f3460;
        content-align: center middle;
        height: 3;
    }

    Button:hover {
        background: #0f3460;
        color: #00d9ff;
    }

    Button:focus {
        background: #00d9ff;
        color: #0f0f23;
    }

    Button.primary {
        background: #00d9ff;
        color: #0f0f23;
    }

    Button.success {
        background: #00ff88;
        color: #0f0f23;
    }

    Button.error {
        background: #e94560;
        color: #fff;
    }

    Input {
        background: #1a1a3e;
        color: #eaeaea;
        border: solid #0f3460;
    }

    Input:focus {
        border: solid #00d9ff;
    }

    ListView {
        background: #1a1a3e;
        border: solid #0f3460;
        height: auto;
        max-height: 12;
    }

    ListItem {
        background: #1a1a3e;
        color: #eaeaea;
        height: 2;
    }

    ListItem:hover {
        background: #0f3460;
        color: #00d9ff;
    }

    Static {
        color: #eaeaea;
    }

    Label {
        color: #eaeaea;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("s", "send", "Send", show=True),
        Binding("r", "receive", "Receive", show=True),
        Binding("d", "devices", "Devices", show=True),
        Binding("h", "history", "History", show=True),
        Binding("w", "webshare", "WebShare", show=True),
        Binding("b", "send_to_browser", "Send to Browser", show=True),
        Binding("t", "transfer_queue", "Transfer Queue", show=True),
        Binding("escape", "back", "Back", show=True),
    ]

    SCREENS = {
        "main_menu": MainMenuScreen,
        "send_files": SendFilesScreen,
        "receive_files": ReceiveFilesScreen,
        "nearby_devices": NearbyDevicesScreen,
        "transfer_history": TransferHistoryScreen,
        "trusted_devices": TrustedDevicesScreen,
        "web_share": WebShareScreen,
        "settings": SettingsScreen,
        "about": AboutScreen,
        "transfer_progress": TransferProgressScreen,
        "send_to_browser": SendToBrowserScreen,
        "transfer_queue": TransferQueueScreen,
    }

    def __init__(self) -> None:
        """Initialize ShareX application."""
        super().__init__()
        self.engine: Optional[ShareXEngine] = None
        logger.info("ShareXApp initialized")

    def on_mount(self) -> None:
        """Handle app mount."""
        # Initialize engine
        self.engine = ExtendedEngine(
            on_device_update=self._on_device_update,
            on_transfer_update=self._on_transfer_update,
            on_notification=self._on_notification,
            on_queue_change=self._on_queue_change,
        )
        self.push_screen("main_menu")
        logger.info("ShareXApp mounted")

    async def on_exit(self) -> None:
        """Handle app exit."""
        if self.engine:
            await self.engine.stop()
        logger.info("ShareXApp exiting")

    def _on_device_update(self, devices) -> None:
        """Handle device list update."""
        pass  # Screens handle their own updates

    def _on_transfer_update(self, transfer) -> None:
        """Handle transfer progress update."""
        pass  # Screens handle their own updates

    def _on_notification(self, message: str, notification_type: str) -> None:
        """Handle notification."""
        logger.info(f"[{notification_type}] {message}")

    def action_send(self) -> None:
        """Action: Send files."""
        self.push_screen("send_files")

    def action_receive(self) -> None:
        """Action: Receive files."""
        self.push_screen("receive_files")

    def action_devices(self) -> None:
        """Action: Show devices."""
        self.push_screen("nearby_devices")

    def action_history(self) -> None:
        """Action: Show history."""
        self.push_screen("transfer_history")

    def action_webshare(self) -> None:
        """Action: Web Share mode."""
        self.push_screen("web_share")
    def action_send_to_browser(self) -> None:
        """Open Send to Browser screen."""
        self.push_screen(SendToBrowserScreen(
            webshare_manager=getattr(self, 'webshare_manager', None)
        ))

    def action_transfer_queue(self) -> None:
        """Open Transfer Queue screen."""
        self.push_screen(TransferQueueScreen(
            transfer_queue=self.engine.transfer_queue
        ))

    def _on_queue_change(self, queue_items) -> None:
        """Handle queue changes."""
        pass


    def action_back(self) -> None:
        """Action: Go back."""
        if len(self.screen_stack) > 1:
            self.pop_screen()

    def get_css(self) -> str:
        """Get CSS with terminal size constraints."""
        return self.CSS
