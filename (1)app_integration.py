"""App Integration for new screens.

Shows how to extend ShareXApp with new screens and bindings.
This is a reference implementation - apply to existing app.py.
"""

from textual.app import App
from textual.screen import Screen

# Import new screens
from ..ui.screens.send_to_browser import SendToBrowserScreen
from ..ui.screens.transfer_queue_screen import TransferQueueScreen

# Existing imports (from current app.py)
from ..ui.screens.main_menu import MainMenuScreen
from ..ui.screens.send_files import SendFilesScreen
from ..ui.screens.receive_files import ReceiveFilesScreen
from ..ui.screens.nearby_devices import NearbyDevicesScreen
from ..ui.screens.transfer_history import TransferHistoryScreen
from ..ui.screens.web_share import WebShareScreen
from ..ui.screens.settings import SettingsScreen
from ..ui.screens.about import AboutScreen
from ..ui.screens.transfer_progress import TransferProgressScreen


class ShareXAppExtended(App):
    """Extended ShareX app with new screens.

    To integrate into existing ShareXApp:
    1. Add new screen imports
    2. Add new bindings
    3. Add new action methods
    4. Wire engine integration
    """

    # EXTENDED BINDINGS - add these to existing BINDINGS in app.py
    EXTENDED_BINDINGS = [
        ("b", "send_to_browser", "Send to Browser"),  # NEW
        ("t", "transfer_queue", "Transfer Queue"),    # NEW
    ]

    def __init__(self) -> None:
        super().__init__()
        # Use ExtendedEngine instead of ShareXEngine
        from ..core.engine_integration import ExtendedEngine
        self.engine = ExtendedEngine(
            on_device_update=self._on_device_update,
            on_transfer_update=self._on_transfer_update,
            on_notification=self._on_notification,
            on_queue_change=self._on_queue_change,
        )
        self.webshare_manager = None
        self.transfer_queue_screen = None
        self.send_to_browser_screen = None

    # =================================================================
    # NEW ACTIONS - add these methods to existing ShareXApp
    # =================================================================

    def action_send_to_browser(self) -> None:
        """Open Send to Browser screen (NEW)."""
        if not self.send_to_browser_screen:
            self.send_to_browser_screen = SendToBrowserScreen(
                webshare_manager=self.webshare_manager,
            )
        self.push_screen(self.send_to_browser_screen)

    def action_transfer_queue(self) -> None:
        """Open Transfer Queue screen (NEW)."""
        if not self.transfer_queue_screen:
            self.transfer_queue_screen = TransferQueueScreen(
                transfer_queue=self.engine.transfer_queue,
            )
        self.push_screen(self.transfer_queue_screen)

    # =================================================================
    # NEW CALLBACK - add to existing callbacks
    # =================================================================

    def _on_queue_change(self, queue_items) -> None:
        """Handle queue changes (NEW)."""
        # Update queue screen if visible
        if self.transfer_queue_screen and self.screen == self.transfer_queue_screen:
            self.transfer_queue_screen.queue_items = queue_items
            self.transfer_queue_screen._update_list(queue_items)
            self.transfer_queue_screen._update_stats()

    # =================================================================
    # WEBSHARE INTEGRATION - modify existing webshare setup
    # =================================================================

    def setup_webshare(self, webshare_manager) -> None:
        """Set up webshare manager and connect to engine."""
        self.webshare_manager = webshare_manager
        # NEW: Connect webshare to engine for browser push
        self.engine.set_webshare_manager(webshare_manager)

        # Update send_to_browser screen if exists
        if self.send_to_browser_screen:
            self.send_to_browser_screen.webshare_manager = webshare_manager
