"""About Screen for ShareX."""

from textual.screen import Screen
from textual.containers import Vertical
from textual.widgets import Static, Button


class AboutScreen(Screen):
    """Screen showing application information."""

    DEFAULT_CSS = """
    AboutScreen {
        align: center middle;
    }

    AboutScreen .title {
        text-align: center;
        color: ansi_bright_cyan;
        text-style: bold;
        padding: 1 0;
    }

    AboutScreen .subtitle {
        text-align: center;
        color: dimgrey;
        padding: 0;
    }

    AboutScreen .info-box {
        background: #1a1a3e;
        border: solid blue;
        padding: 1;
        margin: 1 0;
        text-align: center;
        color: white;
    }

    AboutScreen .feature {
        color: ansi_bright_white;
        padding: 0 1;
    }

    AboutScreen Button {
        width: 100%;
        margin: 1 0;
    }
    """

    def compose(self) -> None:
        """Compose screen."""
        yield Static("ShareX", classes="title")
        yield Static("Secure File Sharing for Termux", classes="subtitle")
        yield Static("─" * 40, classes="subtitle")

        yield Static("Version: 1.0.0", classes="info-box")
        yield Static("Platform: Android / Termux", classes="info-box")
        yield Static("Python: 3.12+", classes="info-box")
        yield Static("Terminal: 44 cols x 22 rows", classes="info-box")

        yield Static("Features:", classes="info-box")
        yield Static("  Encrypted file transfers", classes="feature")
        yield Static("  mDNS device discovery", classes="feature")
        yield Static("  Web Share mode (browser)", classes="feature")
        yield Static("  QR Code pairing", classes="feature")
        yield Static("  SHA-256 verification", classes="feature")
        yield Static("  X25519 + ChaCha20-Poly1305", classes="feature")

        yield Button("Back", id="back")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "back":
            self.app.pop_screen()
