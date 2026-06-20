"""Unit tests for ShareX cryptography module."""

import os
import tempfile
import unittest

from sharex.crypto.manager import CryptoManager


class TestCryptoManager(unittest.TestCase):
    """Tests for CryptoManager."""

    def setUp(self) -> None:
        """Set up crypto manager."""
        self.crypto = CryptoManager()
        self.crypto2 = CryptoManager()

        # Simulate key exchange
        self.crypto.derive_shared_secret(self.crypto2.get_public_key_bytes())
        self.crypto2.derive_shared_secret(self.crypto.get_public_key_bytes())

    def test_key_generation(self) -> None:
        """Test key pair generation."""
        self.assertIsNotNone(self.crypto.private_key)
        self.assertIsNotNone(self.crypto.public_key)

    def test_public_key_bytes(self) -> None:
        """Test public key export."""
        key_bytes = self.crypto.get_public_key_bytes()
        self.assertEqual(len(key_bytes), 32)

    def test_shared_secret(self) -> None:
        """Test shared secret derivation."""
        self.assertIsNotNone(self.crypto.session_key)
        self.assertEqual(len(self.crypto.session_key), 32)

        # Both parties should have same key
        self.assertEqual(self.crypto.session_key, self.crypto2.session_key)

    def test_encrypt_decrypt(self) -> None:
        """Test encryption and decryption."""
        plaintext = b"Hello, World!"
        ciphertext, nonce = self.crypto.encrypt_chunk(plaintext, 0)

        self.assertIsInstance(ciphertext, bytes)
        self.assertIsInstance(nonce, bytes)

        decrypted = self.crypto2.decrypt_chunk(ciphertext, nonce)
        self.assertEqual(decrypted, plaintext)

    def test_encrypt_decrypt_multiple_chunks(self) -> None:
        """Test encryption with different chunk indices."""
        for i in range(10):
            plaintext = f"Chunk {i}".encode()
            ciphertext, nonce = self.crypto.encrypt_chunk(plaintext, i)
            decrypted = self.crypto2.decrypt_chunk(ciphertext, nonce)
            self.assertEqual(decrypted, plaintext)

    def test_large_data(self) -> None:
        """Test with large data."""
        plaintext = os.urandom(1024 * 1024)  # 1MB
        ciphertext, nonce = self.crypto.encrypt_chunk(plaintext, 0)
        decrypted = self.crypto2.decrypt_chunk(ciphertext, nonce)
        self.assertEqual(decrypted, plaintext)

    def test_calculate_sha256(self) -> None:
        """Test SHA-256 calculation."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"Test data")
            temp_path = f.name

        try:
            checksum = CryptoManager.calculate_sha256(temp_path)
            self.assertEqual(len(checksum), 64)

            # Verify consistency
            checksum2 = CryptoManager.calculate_sha256(temp_path)
            self.assertEqual(checksum, checksum2)
        finally:
            os.unlink(temp_path)

    def test_verify_checksum(self) -> None:
        """Test checksum verification."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"Test data")
            temp_path = f.name

        try:
            checksum = CryptoManager.calculate_sha256(temp_path)
            self.assertTrue(CryptoManager.verify_checksum(temp_path, checksum))
            self.assertFalse(CryptoManager.verify_checksum(temp_path, "invalid"))
        finally:
            os.unlink(temp_path)

    def test_generate_random_key(self) -> None:
        """Test random key generation."""
        key1 = CryptoManager.generate_random_key()
        key2 = CryptoManager.generate_random_key()

        self.assertEqual(len(key1), 32)
        self.assertEqual(len(key2), 32)
        self.assertNotEqual(key1, key2)

    def test_hash_password(self) -> None:
        """Test password hashing."""
        password = "test_password"
        key1, salt1 = CryptoManager.hash_password(password)
        key2, salt2 = CryptoManager.hash_password(password, salt1)

        self.assertEqual(len(key1), 32)
        self.assertEqual(len(salt1), 16)
        self.assertEqual(key1, key2)

    def test_reset(self) -> None:
        """Test crypto reset."""
        old_key = self.crypto.session_key
        self.crypto.reset()

        self.assertIsNone(self.crypto.session_key)
        self.assertIsNotNone(self.crypto.private_key)


if __name__ == "__main__":
    unittest.main()
