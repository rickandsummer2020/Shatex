"""Transfer Service for ShareX.

Handles all file transfer operations including:
- Chunk-based streaming (no full file loading)
- Pause/Resume support
- Automatic retry
- Progress tracking
- Encryption/decryption
- SHA-256 verification
- Parallel transfers
"""

import os
import asyncio
import logging
import hashlib
import struct
import time
import json
from pathlib import Path
from typing import Optional, Callable, Dict, List, Tuple
from dataclasses import dataclass, field

import aiofiles

from ..models.transfer import Transfer, TransferStatus, TransferDirection
from ..models.device import Device
from ..models.file_info import FileInfo
from ..crypto.manager import CryptoManager
from ..config import get_config, DEFAULT_CHUNK_SIZE, MAX_CHUNK_SIZE
from ..database.manager import get_database

logger = logging.getLogger(__name__)


# Protocol constants
PROTOCOL_MAGIC = b"SHX"  # ShareX protocol v1
HEADER_SIZE = 16
MAX_RETRIES = 3
RETRY_DELAY = 2.0

# Packet types
PKT_HELLO = 1
PKT_FILE_INFO = 2
PKT_CHUNK = 3
PKT_CHUNK_ACK = 4
PKT_COMPLETE = 5
PKT_VERIFY = 6
PKT_ERROR = 7
PKT_PAUSE = 8
PKT_RESUME = 9
PKT_CANCEL = 10


@dataclass
class ChunkInfo:
    """Information about a file chunk."""
    index: int
    offset: int
    size: int
    checksum: Optional[str] = None
    encrypted: bool = False
    nonce: Optional[bytes] = None


class TransferService:
    """Service for managing file transfers.

    Handles sending and receiving files with full support
    for encryption, resume, retry, and progress tracking.

    Attributes:
        crypto: CryptoManager for encryption.
        active_transfers: Dictionary of active transfers.
        on_progress: Progress callback.
    """

    def __init__(
        self,
        crypto: Optional[CryptoManager] = None,
        on_progress: Optional[Callable[[Transfer], None]] = None,
    ) -> None:
        """Initialize transfer service.

        Args:
            crypto: CryptoManager instance.
            on_progress: Progress callback.
        """
        self.crypto = crypto or CryptoManager()
        self.on_progress = on_progress
        self._active_transfers: Dict[str, Transfer] = {}
        self._paused_transfers: Dict[str, Transfer] = {}
        self._lock = asyncio.Lock()
        logger.info("TransferService initialized")

    async def send_file(
        self,
        file_path: str,
        device: Device,
        transfer_id: Optional[str] = None,
        resume: bool = False,
    ) -> Transfer:
        """Send file to remote device.

        Args:
            file_path: Path to file.
            device: Target device.
            transfer_id: Optional transfer ID for resume.
            resume: Whether to resume interrupted transfer.

        Returns:
            Transfer object with results.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Create transfer object
        import secrets
        transfer = Transfer(
            id=transfer_id or secrets.token_hex(8),
            file_name=path.name,
            file_path=str(path.resolve()),
            file_size=path.stat().st_size,
            direction=TransferDirection.SEND,
            device_id=device.id,
            device_name=device.display_name,
        )

        async with self._lock:
            self._active_transfers[transfer.id] = transfer

        try:
            transfer.status = TransferStatus.CONNECTING
            self._notify_progress(transfer)

            # Connect to device
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(device.ip_address, device.port),
                timeout=10.0,
            )

            # Perform handshake
            await self._handshake(writer, reader, transfer)

            # Send file
            success = await self._send_file_data(
                writer, reader, transfer, resume
            )

            if success:
                transfer.complete()
                self._notify_progress(transfer)
                logger.info(f"File sent successfully: {transfer.file_name}")

            writer.close()
            await writer.wait_closed()

        except Exception as e:
            logger.error(f"Send failed: {e}")
            transfer.fail(str(e))
            self._notify_progress(transfer)

            # Auto-retry if enabled
            config = get_config()
            if config.config.auto_retry and transfer.retries < MAX_RETRIES:
                transfer.retries += 1
                transfer.status = TransferStatus.RETRYING
                self._notify_progress(transfer)
                logger.info(f"Retrying transfer ({transfer.retries}/{MAX_RETRIES})...")
                await asyncio.sleep(RETRY_DELAY)
                return await self.send_file(file_path, device, transfer.id, resume)

        finally:
            async with self._lock:
                self._active_transfers.pop(transfer.id, None)

            # Save to database
            db = get_database()
            db.save_transfer(transfer)

        return transfer

    async def receive_file(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        output_dir: str,
        on_request: Optional[Callable[[Transfer], bool]] = None,
    ) -> Transfer:
        """Receive file from remote device.

        Args:
            reader: Stream reader.
            writer: Stream writer.
            output_dir: Output directory.
            on_request: Callback for transfer approval.

        Returns:
            Transfer object.
        """
        transfer = Transfer(
            id="",
            file_name="",
            file_path="",
            file_size=0,
            direction=TransferDirection.RECEIVE,
            device_id="",
            device_name="",
        )

        try:
            # Perform handshake
            await self._handshake_responder(writer, reader, transfer)

            # Receive file info
            file_info = await self._recv_packet(reader)
            if file_info["type"] != PKT_FILE_INFO:
                raise ValueError("Expected file info packet")

            transfer.file_name = file_info["name"]
            transfer.file_size = file_info["size"]
            transfer.checksum = file_info.get("checksum")
            transfer.device_id = file_info.get("device_id", "unknown")
            transfer.device_name = file_info.get("device_name", "Unknown")
            transfer.id = file_info.get("transfer_id", "")

            # Request approval
            if on_request:
                approved = on_request(transfer)
                if not approved:
                    await self._send_packet(writer, PKT_ERROR, {"message": "Rejected"})
                    transfer.cancel()
                    return transfer

            # Create output path
            output_path = Path(output_dir) / transfer.file_name
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Handle duplicate filenames
            counter = 1
            original_path = output_path
            while output_path.exists():
                stem = original_path.stem
                suffix = original_path.suffix
                output_path = Path(output_dir) / f"{stem}_{counter}{suffix}"
                counter += 1

            transfer.file_path = str(output_path)

            async with self._lock:
                self._active_transfers[transfer.id] = transfer

            # Receive file data
            success = await self._receive_file_data(
                reader, writer, transfer
            )

            if success:
                transfer.complete()
                self._notify_progress(transfer)
                logger.info(f"File received: {transfer.file_name}")

        except Exception as e:
            logger.error(f"Receive failed: {e}")
            transfer.fail(str(e))
            self._notify_progress(transfer)

        finally:
            async with self._lock:
                self._active_transfers.pop(transfer.id, None)

            # Save to database
            db = get_database()
            db.save_transfer(transfer)

        return transfer

    async def _handshake(
        self,
        writer: asyncio.StreamWriter,
        reader: asyncio.StreamReader,
        transfer: Transfer,
    ) -> None:
        """Perform sender handshake.

        Args:
            writer: Stream writer.
            reader: Stream reader.
            transfer: Transfer object.
        """
        # Send protocol magic
        writer.write(PROTOCOL_MAGIC)

        # Send public key
        public_key = self.crypto.get_public_key_bytes()
        writer.write(struct.pack("!I", len(public_key)))
        writer.write(public_key)
        await writer.drain()

        # Receive peer public key
        key_len_data = await reader.readexactly(4)
        key_len = struct.unpack("!I", key_len_data)[0]
        peer_key = await reader.readexactly(key_len)

        # Derive shared secret
        self.crypto.derive_shared_secret(peer_key)

        transfer.status = TransferStatus.NEGOTIATING
        self._notify_progress(transfer)

    async def _handshake_responder(
        self,
        writer: asyncio.StreamWriter,
        reader: asyncio.StreamReader,
        transfer: Transfer,
    ) -> None:
        """Perform responder handshake.

        Args:
            writer: Stream writer.
            reader: Stream reader.
            transfer: Transfer object.
        """
        # Receive protocol magic
        magic = await reader.readexactly(len(PROTOCOL_MAGIC))
        if magic != PROTOCOL_MAGIC:
            raise ValueError("Invalid protocol magic")

        # Receive peer public key
        key_len_data = await reader.readexactly(4)
        key_len = struct.unpack("!I", key_len_data)[0]
        peer_key = await reader.readexactly(key_len)

        # Send our public key
        public_key = self.crypto.get_public_key_bytes()
        writer.write(struct.pack("!I", len(public_key)))
        writer.write(public_key)
        await writer.drain()

        # Derive shared secret
        self.crypto.derive_shared_secret(peer_key)

        transfer.status = TransferStatus.NEGOTIATING
        self._notify_progress(transfer)

    async def _send_file_data(
        self,
        writer: asyncio.StreamWriter,
        reader: asyncio.StreamReader,
        transfer: Transfer,
        resume: bool,
    ) -> bool:
        """Send file data chunks.

        Args:
            writer: Stream writer.
            reader: Stream reader.
            transfer: Transfer object.
            resume: Whether to resume.

        Returns:
            True if successful.
        """
        config = get_config()
        chunk_size = config.config.chunk_size
        file_size = transfer.file_size

        # Calculate SHA-256 if not already done
        if not transfer.checksum:
            transfer.checksum = CryptoManager.calculate_sha256(transfer.file_path)

        # Send file info
        await self._send_packet(writer, PKT_FILE_INFO, {
            "name": transfer.file_name,
            "size": file_size,
            "checksum": transfer.checksum,
            "device_id": get_config().config.device_name,
            "device_name": get_config().config.device_name,
            "transfer_id": transfer.id,
        })

        transfer.status = TransferStatus.TRANSFERRING
        self._notify_progress(transfer)

        # Determine resume offset
        start_offset = 0
        if resume:
            # Check for partial file
            partial_path = transfer.file_path + ".partial"
            if os.path.exists(partial_path):
                start_offset = os.path.getsize(partial_path)
                transfer.transferred_size = start_offset
                self._notify_progress(transfer)

        # Send chunks
        chunk_index = start_offset // chunk_size
        bytes_sent = start_offset
        start_time = time.time()

        async with aiofiles.open(transfer.file_path, "rb") as f:
            # Seek to resume position
            if start_offset > 0:
                await f.seek(start_offset)

            while bytes_sent < file_size:
                # Check if paused
                if transfer.id in self._paused_transfers:
                    transfer.status = TransferStatus.PAUSED
                    self._notify_progress(transfer)
                    while transfer.id in self._paused_transfers:
                        await asyncio.sleep(0.5)
                    transfer.status = TransferStatus.TRANSFERRING
                    self._notify_progress(transfer)

                # Check if cancelled
                if transfer.status == TransferStatus.CANCELLED:
                    await self._send_packet(writer, PKT_CANCEL, {})
                    return False

                # Read chunk
                chunk = await f.read(chunk_size)
                if not chunk:
                    break

                # Encrypt chunk if enabled
                config = get_config()
                if config.config.encryption_enabled and self.crypto.session_key:
                    encrypted_chunk, nonce = self.crypto.encrypt_chunk(chunk, chunk_index)
                    chunk_data = {
                        "index": chunk_index,
                        "offset": bytes_sent,
                        "size": len(chunk),
                        "data": encrypted_chunk.hex(),
                        "nonce": nonce.hex(),
                    }
                else:
                    chunk_data = {
                        "index": chunk_index,
                        "offset": bytes_sent,
                        "size": len(chunk),
                        "data": chunk.hex(),
                    }

                # Send chunk
                await self._send_packet(writer, PKT_CHUNK, chunk_data)

                # Wait for ACK
                ack = await self._recv_packet(reader)
                if ack["type"] != PKT_CHUNK_ACK:
                    raise ValueError("Expected chunk ACK")

                bytes_sent += len(chunk)
                chunk_index += 1

                # Update progress
                transfer.update_progress(bytes_sent)
                elapsed = time.time() - start_time
                if elapsed > 0:
                    transfer.speed = bytes_sent / elapsed
                    remaining = file_size - bytes_sent
                    if transfer.speed > 0:
                        transfer.eta = remaining / transfer.speed

                self._notify_progress(transfer)

        # Send completion
        await self._send_packet(writer, PKT_COMPLETE, {
            "checksum": transfer.checksum,
            "bytes_sent": bytes_sent,
        })

        # Wait for verification
        verify = await self._recv_packet(reader)
        if verify["type"] == PKT_VERIFY:
            if verify.get("checksum_match"):
                logger.info("Checksum verified by receiver")
            else:
                logger.warning("Checksum mismatch reported by receiver")

        return True

    async def _receive_file_data(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        transfer: Transfer,
    ) -> bool:
        """Receive file data chunks.

        Args:
            reader: Stream reader.
            writer: Stream writer.
            transfer: Transfer object.

        Returns:
            True if successful.
        """
        config = get_config()
        chunk_size = config.config.chunk_size
        file_size = transfer.file_size

        transfer.status = TransferStatus.TRANSFERRING
        self._notify_progress(transfer)

        # Create partial file for resume support
        partial_path = transfer.file_path + ".partial"
        bytes_received = 0
        start_time = time.time()

        async with aiofiles.open(partial_path, "wb") as f:
            while bytes_received < file_size:
                # Check if paused
                if transfer.id in self._paused_transfers:
                    transfer.status = TransferStatus.PAUSED
                    self._notify_progress(transfer)
                    while transfer.id in self._paused_transfers:
                        await asyncio.sleep(0.5)
                    transfer.status = TransferStatus.TRANSFERRING
                    self._notify_progress(transfer)

                # Receive packet
                packet = await self._recv_packet(reader)

                if packet["type"] == PKT_COMPLETE:
                    # Transfer complete
                    break
                elif packet["type"] == PKT_CANCEL:
                    transfer.cancel()
                    return False
                elif packet["type"] == PKT_ERROR:
                    raise ValueError(packet.get("message", "Unknown error"))
                elif packet["type"] != PKT_CHUNK:
                    raise ValueError(f"Unexpected packet type: {packet['type']}")

                # Process chunk
                chunk_data = bytes.fromhex(packet["data"])
                chunk_index = packet["index"]

                # Decrypt if needed
                if "nonce" in packet and self.crypto.session_key:
                    nonce = bytes.fromhex(packet["nonce"])
                    chunk_data = self.crypto.decrypt_chunk(chunk_data, nonce)

                # Write chunk
                await f.write(chunk_data)
                bytes_received += len(chunk_data)

                # Send ACK
                await self._send_packet(writer, PKT_CHUNK_ACK, {
                    "index": chunk_index,
                    "bytes_received": bytes_received,
                })

                # Update progress
                transfer.update_progress(bytes_received)
                elapsed = time.time() - start_time
                if elapsed > 0:
                    transfer.speed = bytes_received / elapsed
                    remaining = file_size - bytes_received
                    if transfer.speed > 0:
                        transfer.eta = remaining / transfer.speed

                self._notify_progress(transfer)

        # Verify checksum
        if transfer.checksum:
            actual_checksum = CryptoManager.calculate_sha256(partial_path)
            if actual_checksum != transfer.checksum:
                os.unlink(partial_path)
                raise ValueError("Checksum mismatch - file corrupted")

        # Move to final location
        os.rename(partial_path, transfer.file_path)

        # Send verification
        await self._send_packet(writer, PKT_VERIFY, {
            "checksum_match": True,
        })

        return True

    async def _send_packet(
        self,
        writer: asyncio.StreamWriter,
        packet_type: int,
        data: Dict,
    ) -> None:
        """Send a protocol packet.

        Args:
            writer: Stream writer.
            packet_type: Packet type.
            data: Packet data.
        """
        payload = json.dumps(data).encode("utf-8")
        header = struct.pack("!II", len(payload), packet_type)
        writer.write(header + payload)
        await writer.drain()

    async def _recv_packet(
        self,
        reader: asyncio.StreamReader,
    ) -> Dict:
        """Receive a protocol packet.

        Args:
            reader: Stream reader.

        Returns:
            Packet dictionary.
        """
        header = await reader.readexactly(8)
        payload_len, packet_type = struct.unpack("!II", header)
        payload = await reader.readexactly(payload_len)
        data = json.loads(payload.decode("utf-8"))
        data["type"] = packet_type
        return data

    def pause_transfer(self, transfer_id: str) -> bool:
        """Pause an active transfer.

        Args:
            transfer_id: Transfer ID.

        Returns:
            True if paused.
        """
        if transfer_id in self._active_transfers:
            self._paused_transfers[transfer_id] = self._active_transfers[transfer_id]
            logger.info(f"Transfer paused: {transfer_id}")
            return True
        return False

    def resume_transfer(self, transfer_id: str) -> bool:
        """Resume a paused transfer.

        Args:
            transfer_id: Transfer ID.

        Returns:
            True if resumed.
        """
        if transfer_id in self._paused_transfers:
            self._paused_transfers.pop(transfer_id, None)
            logger.info(f"Transfer resumed: {transfer_id}")
            return True
        return False

    def cancel_transfer(self, transfer_id: str) -> bool:
        """Cancel an active transfer.

        Args:
            transfer_id: Transfer ID.

        Returns:
            True if cancelled.
        """
        if transfer_id in self._active_transfers:
            transfer = self._active_transfers[transfer_id]
            transfer.cancel()
            self._paused_transfers.pop(transfer_id, None)
            logger.info(f"Transfer cancelled: {transfer_id}")
            return True
        return False

    def get_active_transfers(self) -> List[Transfer]:
        """Get list of active transfers.

        Returns:
            List of active transfers.
        """
        return list(self._active_transfers.values())

    def get_transfer(self, transfer_id: str) -> Optional[Transfer]:
        """Get transfer by ID.

        Args:
            transfer_id: Transfer ID.

        Returns:
            Transfer or None.
        """
        return self._active_transfers.get(transfer_id)

    def _notify_progress(self, transfer: Transfer) -> None:
        """Notify progress callback.

        Args:
            transfer: Transfer object.
        """
        if self.on_progress:
            try:
                self.on_progress(transfer)
            except Exception as e:
                logger.error(f"Progress callback error: {e}")
