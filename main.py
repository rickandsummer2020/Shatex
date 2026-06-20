"""ShareX - Secure File Sharing for Termux.

Entry point for the ShareX application.
Optimized for mobile Termux on Android.

Usage:
    python main.py

Requirements:
    pip install -r requirements.txt
"""

import sys
import os
import logging

# Ensure Python 3.12+
if sys.version_info < (3, 12):
    print("Error: Python 3.12+ required")
    print(f"Current version: {sys.version_info.major}.{sys.version_info.minor}")
    sys.exit(1)

# Add sharex to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sharex.config import init_logging, get_config
from sharex.utils.terminal import check_terminal_size
from sharex.ui.app import ShareXApp


def main() -> int:
    """Main entry point.

    Returns:
        Exit code.
    """
    try:
        # Initialize logging
        init_logging()
        logger = logging.getLogger(__name__)
        logger.info("ShareX starting...")

        # Check terminal size
        is_valid, error = check_terminal_size()
        if not is_valid:
            print("ShareX")
            print("─" * 40)
            print(f"Terminal too small!")
            print(f"{error}")
            print()
            print("Please enlarge the terminal")
            print("Recommended: 44 columns x 22 rows")
            return 1

        # Load configuration
        config = get_config()
        logger.info(f"Configuration loaded for: {config.config.device_name}")

        # Run application
        app = ShareXApp()
        app.run()

        return 0

    except KeyboardInterrupt:
        print("\nShareX interrupted by user")
        return 0
    except Exception as e:
        logger.exception("Fatal error")
        print(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
