# ShareX - Secure File Sharing for Termux

A production-quality, terminal-based file sharing application optimized for **Termux on Android**. Share files securely with nearby devices using encrypted transfers, mDNS discovery, QR code pairing, and a built-in Web Share mode for browser-based transfers.

## Features

- **Encrypted Transfers**: X25519 key exchange + ChaCha20-Poly1305 authenticated encryption
- **mDNS Discovery**: Automatically find nearby ShareX devices on the same network
- **QR Code Pairing**: Quick device pairing with QR codes
- **Web Share Mode**: Share files via any web browser - no installation required
- **Chunk-Based Streaming**: Transfer files of any size without loading into memory
- **Pause/Resume**: Pause and resume transfers
- **Auto-Retry**: Automatic retry on failure (configurable)
- **SHA-256 Verification**: Every file verified with checksum
- **Transfer History**: SQLite-backed history of all transfers
- **Trusted Devices**: Auto-accept transfers from trusted devices
- **Dark Theme**: Beautiful mobile-optimized terminal UI

## Requirements

- **Python 3.12+**
- **Termux** (Android)
- Terminal size: minimum 32x16, recommended 44x22

## Installation

```bash
# Clone or download the project
cd sharex

# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

## Usage

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `S` | Send Files |
| `R` | Receive Files |
| `D` | Nearby Devices |
| `H` | Transfer History |
| `W` | Web Share Mode |
| `Q` | Quit |
| `Esc` | Go Back |

### Send Files

1. Press `S` or select "Send Files"
2. Enter the file path or browse downloads
3. Select a discovered device
4. Monitor transfer progress

### Receive Files

1. Press `R` or select "Receive Files"
2. Start the server
3. Wait for incoming transfers
4. Accept or reject transfer requests

### Web Share Mode

1. Press `W` or select "Web Share"
2. Start the web server
3. Scan the QR code or open the URL in any browser
4. Upload or download files via the web interface

## Architecture

```
sharex/
  main.py                 # Entry point
  requirements.txt        # Dependencies
  sharex/
    config.py             # Configuration management
    core/
      engine.py           # Central orchestration
    crypto/
      manager.py          # X25519 + ChaCha20-Poly1305
    database/
      manager.py          # SQLite persistence
    models/
      device.py           # Device model
      transfer.py         # Transfer model
      file_info.py        # File info model
      settings.py         # Settings model
      webshare.py         # WebShare session model
    network/
      discovery.py        # mDNS/Zeroconf discovery
      transfer.py         # TCP transfer protocol
    services/
      transfer_service.py # Transfer business logic
      webshare_manager.py # WebShare management
      webshare_server.py  # HTTP server for WebShare
    ui/
      app.py              # Main Textual application
      widgets.py          # Custom UI widgets
      modals.py           # Dialog modals
      screens/            # All UI screens
    utils/
      terminal.py         # Terminal utilities
```

## Security

- **X25519**: Elliptic curve key exchange
- **ChaCha20-Poly1305**: Authenticated encryption with associated data
- **SHA-256**: File integrity verification
- **Session Keys**: Unique per-transfer encryption keys
- **No Internet Required**: All transfers are local network only

## License

MIT License

## Author

ShareX Team
