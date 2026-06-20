"""Trusted Devices Screen for ShareX."""

from textual.screen import Screen
from textual.containers import Vertical
from textual.widgets import Static, Button, ListView, ListItem, Label
from textual.reactive import reactive

from ...database.manager import get_database


class TrustedDevicesScreen(Screen):
    """Screen for managing trusted devices."""

    DEFAULT_CSS = """
    TrustedDevicesScreen {
        align: center middle;
    }

    TrustedDevicesScreen .title {
        text-align: center;
        color: ansi_bright_cyan;
        text-style: bold;
        padding: 1 0;
    }

    TrustedDevicesScreen .subtitle {
        text-align: center;
        color: dimgrey;
        padding: 0;
    }

    TrustedDevicesScreen .info-box {
        background: #1a1a3e;
        border: solid blue;
        padding: 1;
        margin: 1 0;
        text-align: center;
    }

    TrustedDevicesScreen ListView {
        height: 8;
        border: solid blue;
        background: #1a1a3e;
    }

    TrustedDevicesScreen ListItem {
        height: 2;
        color: white;
    }

    TrustedDevicesScreen ListItem:hover {
        background: #0f3460;
        color: ansi_bright_cyan;
    }

    TrustedDevicesScreen Button {
        width: 100%;
        margin: 1 0;
    }
    """

    devices: reactive[list] = reactive([])

    def compose(self) -> None:
        """Compose screen."""
        yield Static("Trusted Devices", classes="title")
        yield Static("Auto-accept from these devices", classes="subtitle")
        yield Static("─" * 40, classes="subtitle")

        yield ListView(id="trusted_list")
        yield Button("Add Device", id="add", variant="success")
        yield Button("Remove Selected", id="remove", variant="error")
        yield Button("Refresh", id="refresh", variant="primary")
        yield Button("Back", id="back")

        yield Static("0 trusted devices", id="count", classes="info-box")

    def on_mount(self) -> None:
        """Handle mount."""
        self._refresh_list()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        button_id = event.button.id

        if button_id == "back":
            self.app.pop_screen()
        elif button_id == "refresh":
            self._refresh_list()
        elif button_id == "add":
            self._add_device()
        elif button_id == "remove":
            self._remove_device()

    def _refresh_list(self) -> None:
        """Refresh trusted devices list."""
        try:
            db = get_database()
            self.devices = db.get_devices(trusted_only=True)
        except Exception:
            self.devices = []

        trusted_list = self.query_one("#trusted_list", ListView)
        trusted_list.clear()

        if self.devices:
            for device in self.devices:
                trusted_list.append(ListItem(Label(
                    f"✓ {device.display_name} ({device.ip_address})"
                )))
        else:
            # Demo data
            demo_trusted = [
                ("My Laptop", "192.168.1.5"),
                ("Work PC", "192.168.1.12"),
            ]
            for name, ip in demo_trusted:
                trusted_list.append(ListItem(Label(f"✓ {name} ({ip})")))

        count = self.query_one("#count", Static)
        count.update(f"{len(self.devices)} trusted devices")

    def _add_device(self) -> None:
        """Add a trusted device."""
        # TODO: Show device selection dialog
        pass

    def _remove_device(self) -> None:
        """Remove selected trusted device."""
        # TODO: Implement removal
        pass
