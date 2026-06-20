"""Custom widgets for ShareX UI.

Mobile-optimized widgets for 44-column terminal.
"""

import asyncio
from typing import Optional

from textual.widgets import Static, ProgressBar
from textual.reactive import reactive
from rich.text import Text
from rich.panel import Panel
from rich.align import Align


class AnimatedProgressBar(Static):
    """Animated progress bar with speed and ETA display.

    Optimized for mobile terminal width.
    """

    progress: reactive[float] = reactive(0.0)
    speed: reactive[str] = reactive("0 B/s")
    eta: reactive[str] = reactive("Calculating...")
    file_name: reactive[str] = reactive("")
    file_size: reactive[str] = reactive("")

    def __init__(self, **kwargs) -> None:
        """Initialize progress bar."""
        super().__init__(**kwargs)
        self._animation_task: Optional[asyncio.Task] = None

    def render(self) -> Panel:
        """Render the progress bar."""
        bar_width = 38
        filled = int(bar_width * self.progress / 100)
        empty = bar_width - filled

        bar = "█" * filled + "░" * empty

        content = Text()
        content.append(f"{self.file_name[:20]:<20} ", style="ansi_bright_white")
        content.append(f"{self.file_size:>12}\n", style="cyan")
        content.append(f"[{bar}] ", style="ansi_bright_cyan")
        content.append(f"{self.progress:>5.1f}%\n", style="ansi_bright_white")
        content.append(f"Speed: {self.speed:<15} ", style="green")
        content.append(f"ETA: {self.eta}", style="yellow")

        return Panel(
            content,
            border_style="cyan",
            padding=(0, 1),
        )

    def update_progress(self, progress: float, speed: str = "", eta: str = "") -> None:
        """Update progress values.

        Args:
            progress: Progress percentage (0-100).
            speed: Transfer speed string.
            eta: ETA string.
        """
        self.progress = min(100.0, max(0.0, progress))
        if speed:
            self.speed = speed
        if eta:
            self.eta = eta
        self.refresh()

    def set_file(self, name: str, size: str = "") -> None:
        """Set file information.

        Args:
            name: File name.
            size: Formatted file size.
        """
        self.file_name = name
        self.file_size = size
        self.refresh()


class NotificationToast(Static):
    """Notification toast widget.

    Displays temporary notifications at bottom of screen.
    """

    message: reactive[str] = reactive("")
    notification_type: reactive[str] = reactive("info")
    visible: reactive[bool] = reactive(False)

    def __init__(self, **kwargs) -> None:
        """Initialize notification."""
        super().__init__(**kwargs)
        self._hide_task: Optional[asyncio.Task] = None

    def render(self) -> Panel:
        """Render notification."""
        if not self.visible or not self.message:
            return Text("")

        styles = {
            "info": ("ansi_bright_cyan", "cyan"),
            "success": ("ansi_bright_green", "green"),
            "warning": ("ansi_bright_yellow", "yellow"),
            "error": ("ansi_bright_red", "red"),
        }

        text_style, border_style = styles.get(self.notification_type, ("white", "white"))

        text = Text(self.message[:42], style=text_style, justify="center")
        return Panel(
            text,
            border_style=border_style,
            padding=(0, 1),
        )

    async def show(self, message: str, notification_type: str = "info", duration: float = 3.0) -> None:
        """Show notification.

        Args:
            message: Notification text.
            notification_type: Type of notification.
            duration: Display duration in seconds.
        """
        self.message = message
        self.notification_type = notification_type
        self.visible = True
        self.refresh()

        if self._hide_task:
            self._hide_task.cancel()

        self._hide_task = asyncio.create_task(self._hide_after(duration))

    async def _hide_after(self, duration: float) -> None:
        """Hide notification after delay.

        Args:
            duration: Delay in seconds.
        """
        try:
            await asyncio.sleep(duration)
            self.visible = False
            self.refresh()
        except asyncio.CancelledError:
            pass


class LoadingSpinner(Static):
    """Animated loading spinner.

    Shows rotating animation while loading.
    """

    text: reactive[str] = reactive("Loading...")
    active: reactive[bool] = reactive(False)

    def __init__(self, **kwargs) -> None:
        """Initialize spinner."""
        super().__init__(**kwargs)
        self._spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._spinner_index = 0
        self._animation_task: Optional[asyncio.Task] = None

    def render(self) -> Text:
        """Render spinner."""
        if not self.active:
            return Text("")

        char = self._spinner_chars[self._spinner_index % len(self._spinner_chars)]
        return Text(
            f"{char} {self.text[:38]}",
            style="ansi_bright_cyan",
            justify="center",
        )

    def start(self, text: str = "Loading...") -> None:
        """Start spinner animation.

        Args:
            text: Loading text.
        """
        self.text = text
        self.active = True
        self._animation_task = asyncio.create_task(self._animate())
        self.refresh()

    def stop(self) -> None:
        """Stop spinner animation."""
        self.active = False
        if self._animation_task:
            self._animation_task.cancel()
            self._animation_task = None
        self.refresh()

    async def _animate(self) -> None:
        """Animate spinner."""
        try:
            while self.active:
                self._spinner_index += 1
                self.refresh()
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass


class StatusBar(Static):
    """Status bar widget.

    Shows device info and connection status.
    """

    device_name: reactive[str] = reactive("ShareX")
    status: reactive[str] = reactive("Ready")
    wifi_status: reactive[str] = reactive("Offline")

    def render(self) -> Panel:
        """Render status bar."""
        content = Text()
        content.append(f"{self.device_name[:15]}", style="ansi_bright_cyan")
        content.append(" | ", style="dim")
        content.append(f"{self.status[:12]}", style="ansi_bright_white")
        content.append(" | ", style="dim")
        content.append(f"{self.wifi_status[:10]}", style="green" if "Online" in self.wifi_status else "red")

        return Panel(
            Align.center(content),
            border_style="blue",
            height=3,
        )


class MobileMenuItem(Static):
    """Mobile-optimized menu item.

    Large touch-friendly menu item for phone screens.
    """

    label: reactive[str] = reactive("")
    shortcut: reactive[str] = reactive("")
    icon: reactive[str] = reactive("▶")

    def __init__(self, label: str = "", shortcut: str = "", icon: str = "▶", **kwargs) -> None:
        """Initialize menu item.

        Args:
            label: Menu item text.
            shortcut: Keyboard shortcut.
            icon: Item icon.
        """
        super().__init__(**kwargs)
        self.label = label
        self.shortcut = shortcut
        self.icon = icon

    def render(self) -> Panel:
        """Render menu item."""
        content = Text()
        content.append(f"{self.icon} ", style="ansi_bright_cyan")
        content.append(f"{self.label[:25]}", style="ansi_bright_white")
        if self.shortcut:
            content.append(f" [{self.shortcut}]", style="dim")

        return Panel(
            content,
            border_style="blue",
            padding=(0, 1),
        )


class DeviceListItem(Static):
    """Device list item widget.

    Shows device info in a compact format.
    """

    device_name: reactive[str] = reactive("")
    device_ip: reactive[str] = reactive("")
    device_status: reactive[str] = reactive("offline")
    is_trusted: reactive[bool] = reactive(False)

    def render(self) -> Panel:
        """Render device item."""
        status_colors = {
            "online": "green",
            "offline": "red",
            "busy": "yellow",
            "trusted": "cyan",
        }

        content = Text()
        content.append(f"{self.device_name[:20]:<20}", style="ansi_bright_white")
        content.append(f"{self.device_ip[:15]:>15}\n", style="dim")

        status_color = status_colors.get(self.device_status, "white")
        content.append(f"Status: ", style="dim")
        content.append(f"{self.device_status[:8]}", style=status_color)

        if self.is_trusted:
            content.append("  [Trusted]", style="ansi_bright_cyan")

        return Panel(
            content,
            border_style=status_color,
            padding=(0, 1),
        )


class TransferListItem(Static):
    """Transfer list item widget.

    Shows transfer info with mini progress bar.
    """

    file_name: reactive[str] = reactive("")
    file_size: reactive[str] = reactive("")
    progress: reactive[float] = reactive(0.0)
    status: reactive[str] = reactive("pending")
    direction: reactive[str] = reactive("send")

    def render(self) -> Panel:
        """Render transfer item."""
        status_colors = {
            "pending": "yellow",
            "transferring": "cyan",
            "completed": "green",
            "failed": "red",
            "cancelled": "red",
            "paused": "yellow",
        }

        bar_width = 20
        filled = int(bar_width * self.progress / 100)
        bar = "█" * filled + "░" * (bar_width - filled)

        direction_icon = "↑" if self.direction == "send" else "↓"

        content = Text()
        content.append(f"{direction_icon} ", style="ansi_bright_cyan")
        content.append(f"{self.file_name[:18]:<18}", style="ansi_bright_white")
        content.append(f"{self.file_size:>10}\n", style="dim")
        content.append(f"[{bar}] ", style=status_colors.get(self.status, "white"))
        content.append(f"{self.progress:>5.1f}% ", style="ansi_bright_white")
        content.append(f"{self.status[:10]}", style=status_colors.get(self.status, "white"))

        return Panel(
            content,
            border_style=status_colors.get(self.status, "white"),
            padding=(0, 1),
        )
