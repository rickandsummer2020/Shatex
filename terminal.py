"""Terminal utilities for ShareX.

Handles terminal size detection, mobile optimization,
and display formatting.
"""

import os
import sys
import shutil
import logging
from typing import Tuple, Optional

from rich.console import Console
from rich.text import Text

from ..config import MAX_TERMINAL_WIDTH, MAX_TERMINAL_HEIGHT, MIN_TERMINAL_WIDTH, MIN_TERMINAL_HEIGHT

logger = logging.getLogger(__name__)

# Global console instance optimized for mobile
console = Console(
    width=MAX_TERMINAL_WIDTH,
    height=MAX_TERMINAL_HEIGHT,
    soft_wrap=False,
    force_terminal=True,
)


def get_terminal_size() -> Tuple[int, int]:
    """Get current terminal size.

    Returns:
        Tuple of (width, height).
    """
    try:
        size = shutil.get_terminal_size()
        return size.columns, size.lines
    except Exception:
        return MAX_TERMINAL_WIDTH, MAX_TERMINAL_HEIGHT


def check_terminal_size() -> Tuple[bool, Optional[str]]:
    """Check if terminal size is adequate for ShareX.

    Returns:
        Tuple of (is_valid, error_message).
    """
    width, height = get_terminal_size()

    if width < MIN_TERMINAL_WIDTH:
        return False, f"Terminal too small: {width} cols. Min: {MIN_TERMINAL_WIDTH}"

    if height < MIN_TERMINAL_HEIGHT:
        return False, f"Terminal too small: {height} rows. Min: {MIN_TERMINAL_HEIGHT}"

    return True, None


def format_center(text: str, width: int = MAX_TERMINAL_WIDTH, fill: str = " ") -> str:
    """Center text within given width.

    Args:
        text: Text to center.
        width: Total width.
        fill: Fill character.

    Returns:
        Centered string.
    """
    if len(text) >= width:
        return text[:width]
    padding = (width - len(text)) // 2
    return text.center(width, fill)


def format_right(text: str, width: int = MAX_TERMINAL_WIDTH, fill: str = " ") -> str:
    """Right-align text within given width.

    Args:
        text: Text to right-align.
        width: Total width.
        fill: Fill character.

    Returns:
        Right-aligned string.
    """
    if len(text) >= width:
        return text[:width]
    return text.rjust(width, fill)


def truncate_text(text: str, max_width: int, suffix: str = "...") -> str:
    """Truncate text to fit within width.

    Args:
        text: Text to truncate.
        max_width: Maximum width.
        suffix: Suffix for truncated text.

    Returns:
        Truncated string.
    """
    if len(text) <= max_width:
        return text
    if max_width <= len(suffix):
        return suffix[:max_width]
    return text[:max_width - len(suffix)] + suffix


def draw_horizontal_line(
    char: str = "─",
    width: int = MAX_TERMINAL_WIDTH,
    style: str = "cyan",
) -> Text:
    """Draw a horizontal line.

    Args:
        char: Line character.
        width: Line width.
        style: Rich style.

    Returns:
        Rich Text object.
    """
    line = char * width
    return Text(line, style=style)


def draw_box_border(
    width: int = MAX_TERMINAL_WIDTH,
    style: str = "cyan",
) -> Tuple[Text, Text, Text]:
    """Draw box border components.

    Args:
        width: Box width.
        style: Rich style.

    Returns:
        Tuple of (top, middle, bottom) borders.
    """
    top = Text(f"┌{'─' * (width - 2)}┐", style=style)
    middle = Text(f"│{' ' * (width - 2)}│", style=style)
    bottom = Text(f"└{'─' * (width - 2)}┘", style=style)
    return top, middle, bottom


def clear_screen() -> None:
    """Clear the terminal screen."""
    os.system("clear" if os.name != "nt" else "cls")


def move_cursor_home() -> None:
    """Move cursor to home position."""
    sys.stdout.write("\033[H")
    sys.stdout.flush()


def hide_cursor() -> None:
    """Hide terminal cursor."""
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()


def show_cursor() -> None:
    """Show terminal cursor."""
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()


def get_progress_bar(
    progress: float,
    width: int = 30,
    fill_char: str = "█",
    empty_char: str = "░",
    style: str = "ansi_bright_cyan",
) -> Text:
    """Generate a progress bar.

    Args:
        progress: Progress percentage (0-100).
        width: Bar width.
        fill_char: Filled character.
        empty_char: Empty character.
        style: Rich style.

    Returns:
        Rich Text object.
    """
    filled = int(width * progress / 100)
    empty = width - filled
    bar = fill_char * filled + empty_char * empty
    return Text(bar, style=style)


def format_bytes(size: int) -> str:
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


def format_duration(seconds: int) -> str:
    """Format seconds to human-readable duration.

    Args:
        seconds: Duration in seconds.

    Returns:
        Formatted string.
    """
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"


def format_speed(bytes_per_sec: float) -> str:
    """Format transfer speed.

    Args:
        bytes_per_sec: Speed in bytes/second.

    Returns:
        Formatted string.
    """
    return f"{format_bytes(int(bytes_per_sec))}/s"
