"""Nearby Devices Screen for ShareX."""

import asyncio
from textual.screen import Screen
from textual.containers import Vertical
from textual.widgets import Static, Button, ListView, ListItem, Label
from textual.reactive import reactive
from textual.worker import Worker

from ...models.device import Device, DeviceStatus


class NearbyDevicesScreen(Screen):
    """Screen for discovering and managing nearby devices."""

    DEFAULT_CSS = """
    NearbyDevicesScreen {
        align: center middle;
    }

    NearbyDevicesScreen .title {
        text-align: center;
        color: ansi_bright_cyan;
        text-style: bold;
        padding: 1 0;
    }

    NearbyDevicesScreen .subtitle {
        text-align: center;
        color: dimgrey;
        padding: 0;
    }

    NearbyDevicesScreen .info-box {
        background: #1a1a3e;
        border: solid blue;
        padding: 1;
        margin: 1 0;
        text-align: center;
    }

    NearbyDevicesScreen ListView {
        height: 10;
        border: solid blue;
        background: #1a1a3e;
    }

    NearbyDevicesScreen ListItem {
        height: 2;
        color: white;
    }

    NearbyDevicesScreen ListItem:hover {
        background: #0f3460;
        color: ansi_bright_cyan;
    }

    NearbyDevicesScreen Button {
        width: 100%;
        margin: 1 0;
    }
    """

    devices: reactive[list] = reactive([])
    is_scanning: reactive[bool] = reactive(False)

    def compose(self) -> None:
        """Compose screen."""
        yield Static("Nearby Devices", classes="title")
        yield Static("Discover devices on network", classes="subtitle")
        yield Static("─" * 40, classes="subtitle")

        yield ListView(id="device_list")
        yield Button("Scan Network", id="scan", variant="primary")
        yield Button("QR Pair", id="qr_pair")
        yield Button("Back", id="back")

        yield Static("0 devices found", id="count", classes="info-box")

    def on_mount(self) -> None:
        """Handle mount."""
        self._refresh_devices()
        # Start periodic refresh
        self.set_interval(3.0, self._refresh_devices)

    async def _auto_refresh(self) -> None:
        """Auto-refresh device list."""
        try:
            while self.is_active:
                await asyncio.sleep(3)
                if self.is_active:
                    self._refresh_devices()
        except asyncio.CancelledError:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        button_id = event.button.id

        if button_id == "back":
            self.app.pop_screen()
        elif button_id == "scan":
            self._scan_network()
        elif button_id == "qr_pair":
            self.app.push_screen("web_share")

    def _scan_network(self) -> None:
        """Trigger network scan."""
        self.is_scanning = True
        count = self.query_one("#count", Static)
        count.update("Scanning...")

        # Use engine if available
        app = self.app
        if hasattr(app, "engine") and app.engine:
            devices = app.engine.get_devices()
            self.devices = devices
            self._update_device_list()

        self.is_scanning = False

    def _refresh_devices(self) -> None:
        """Refresh device list from engine."""
        app = self.app
        if hasattr(app, "engine") and app.engine:
            devices = app.engine.get_devices()
            if devices != self.devices:
                self.devices = devices
                self._update_device_list()
        else:
            # Show demo devices if no engine
            self._show_demo_devices()

    def _update_device_list(self) -> None:
        """Update the device list widget."""
        device_list = self.query_one("#device_list", ListView)
        device_list.clear()

        for device in self.devices:
            status_icon = "●" if device.is_online else "○"
            status_color = "green" if device.is_online else "red"
            trusted = " [Trusted]" if device.is_trusted else ""
            device_list.append(ListItem(Label(
                f"{status_icon} {device.display_name} ({device.ip_address}){trusted}"
            )))

        count = self.query_one("#count", Static)
        count.update(f"{len(self.devices)} devices found")

    def _show_demo_devices(self) -> None:
        """Show demo devices."""
        device_list = self.query_one("#device_list", ListView)
        device_list.clear()

        demo_devices = [
            ("Phone-A", "192.168.1.10", "Online"),
            ("Laptop-B", "192.168.1.15", "Online"),
            ("Tablet-C", "192.168.1.20", "Busy"),
        ]

        for name, ip, status in demo_devices:
            device_list.append(ListItem(Label(f"● {name} ({ip}) - {status}")))

        count = self.query_one("#count", Static)
        count.update(f"{len(demo_devices)} devices found (demo)")
