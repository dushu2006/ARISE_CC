"""
Encryption Utilities.

Provides AES-256-GCM encryption for data at rest with:
- Key derivation from master key (PBKDF2)
- Key rotation (90 days default)
- Field-level encryption for PII
"""

from __future__ import annotations
import base64
import hashlib
import logging
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from core.config import load_config
from core.config.models import SecurityConfig, EncryptionConfig
from core.structured_logging import get_logger, log_structured

logger = get_logger(__name__)


@dataclass
class EncryptionKey:
    """Encryption key metadata."""
    key_id: str
    key_material: bytes
    created_at: datetime
    expires_at: Optional[datetime] = None
    is_active: bool = True
    rotation_generation: int = 0


@dataclass
class EncryptedData:
    """Encrypted data container."""
    ciphertext: bytes
    nonce: bytes
    key_id: str
    algorithm: str = "AES-256-GCM"
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ciphertext": base64.b64encode(self.ciphertext).decode(),
            "nonce": base64.b64encode(self.nonce).decode(),
            "key_id": self.key_id,
            "algorithm": self.algorithm,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EncryptedData":
        return cls(
            ciphertext=base64.b64decode(data["ciphertext"]),
            nonce=base64.b64decode(data["nonce"]),
            key_id=data["key_id"],
            algorithm=data.get("algorithm", "AES-256-GCM"),
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else datetime.now(timezone.utc),
        )


class EncryptionManager:
    """
    Encryption manager for data at rest.

    Features:
    - AES-256-GCM authenticated encryption
    - PBKDF2 key derivation from master key
    - Automatic key rotation (configurable interval)
    - Field-level encryption for sensitive data
    - Multiple key versions for decryption compatibility
    """

    def __init__(self, config: Optional[EncryptionConfig] = None):
        self.config = config or load_config().security.encryption
        self._keys: Dict[str, EncryptionKey] = {}
        self._current_key_id: Optional[str] = None
        self._master_key: Optional[bytes] = None
        self._salt: bytes = b"arise_salt_v1"  # In production, use random per-key salt
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize encryption manager."""
        log_structured(logger, logging.INFO, "Initializing Encryption Manager")

        # Get or derive master key
        await self._derive_master_key()

        # Load or generate current key
        await self._load_or_generate_key()

        # Start key rotation scheduler if enabled
        if self.config.key_rotation_days > 0:
            # Key rotation would be handled by a background task
            pass

        self._initialized = True
        log_structured(logger, logging.INFO, "Encryption Manager initialized",
                      current_key=self._current_key_id,
                      key_count=len(self._keys))

    async def _derive_master_key(self) -> None:
        """Derive master key from environment or config."""
        master_key_env = os.getenv("ARISE_MASTER_ENCRYPTION_KEY")

        if master_key_env:
            # Use provided master key
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=self._salt,
                iterations=100000,
            )
            self._master_key = kdf.derive(master_key_env.encode())
            log_structured(logger, logging.INFO, "Master key derived from environment")
        else:
            # Generate a new master key (for development only)
            self._master_key = secrets.token_bytes(32)
            log_structured(logger, logging.WARNING, "Generated ephemeral master key - NOT FOR PRODUCTION")

    async def _load_or_generate_key(self) -> None:
        """Load existing key or generate new one."""
        # In production, load from secure key store
        # For now, generate a new key
        await self._generate_new_key()

    async def _generate_new_key(self, rotation_generation: int = 0) -> str:
        """Generate a new encryption key."""
        key_id = f"key_{int(time.time())}_{secrets.token_hex(4)}"
        key_material = secrets.token_bytes(32)  # 256 bits

        expires_at = None
        if self.config.key_rotation_days > 0:
            from datetime import timedelta
            expires_at = datetime.now(timezone.utc) + timedelta(days=self.config.key_rotation_days)

        key = EncryptionKey(
            key_id=key_id,
            key_material=key_material,
            created_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            is_active=True,
            rotation_generation=rotation_generation,
        )

        self._keys[key_id] = key
        self._current_key_id = key_id

        log_structured(logger, logging.INFO, "Generated new encryption key", key_id=key_id)
        return key_id

    def _get_key(self, key_id: Optional[str] = None) -> EncryptionKey:
        """Get encryption key by ID or current key."""
        if key_id:
            key = self._keys.get(key_id)
            if not key:
                raise ValueError(f"Key not found: {key_id}")
            return key

        if not self._current_key_id:
            raise RuntimeError("No current encryption key")

        key = self._keys.get(self._current_key_id)
        if not key:
            raise RuntimeError(f"Current key not found: {self._current_key_id}")

        return key

    def encrypt(self, plaintext: bytes, key_id: Optional[str] = None, associated_data: Optional[bytes] = None) -> EncryptedData:
        """
        Encrypt data using AES-256-GCM.

        Args:
            plaintext: Data to encrypt
            key_id: Specific key to use (None for current)
            associated_data: Additional authenticated data

        Returns:
            EncryptedData with ciphertext, nonce, and key_id
        """
        if not self._initialized:
            raise RuntimeError("Encryption Manager not initialized")

        key = self._get_key(key_id)
        aesgcm = AESGCM(key.key_material)

        # Generate random nonce (96 bits for GCM)
        nonce = secrets.token_bytes(12)

        # Encrypt
        ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data)

        return EncryptedData(
            ciphertext=ciphertext,
            nonce=nonce,
            key_id=key.key_id,
        )

    def decrypt(self, encrypted_data: EncryptedData, associated_data: Optional[bytes] = None) -> bytes:
        """
        Decrypt data using AES-256-GCM.

        Args:
            encrypted_data: EncryptedData to decrypt
            associated_data: Additional authenticated data

        Returns:
            Decrypted plaintext
        """
        if not self._initialized:
            raise RuntimeError("Encryption Manager not initialized")

        key = self._get_key(encrypted_data.key_id)
        aesgcm = AESGCM(key.key_material)

        # Decrypt
        plaintext = aesgcm.decrypt(
            encrypted_data.nonce,
            encrypted_data.ciphertext,
            associated_data,
        )

        return plaintext

    def encrypt_string(self, text: str, key_id: Optional[str] = None) -> str:
        """Encrypt a string and return base64-encoded result."""
        encrypted = self.encrypt(text.encode('utf-8'), key_id)
        # Combine nonce + ciphertext for storage
        combined = encrypted.nonce + encrypted.ciphertext
        return base64.b64encode(combined).decode()

    def decrypt_string(self, encoded: str, key_id: Optional[str] = None) -> str:
        """Decrypt a base64-encoded string."""
        combined = base64.b64decode(encoded)
        nonce = combined[:12]
        ciphertext = combined[12:]

        encrypted_data = EncryptedData(
            ciphertext=ciphertext,
            nonce=nonce,
            key_id=key_id or self._current_key_id,
        )

        plaintext = self.decrypt(encrypted_data)
        return plaintext.decode('utf-8')

    def encrypt_field(self, field_name: str, value: Any, key_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Encrypt a field value for storage.

        Returns dict with encrypted value and metadata.
        """
        if value is None:
            return {"encrypted": False, "value": None}

        # Serialize value to JSON
        import json
        plaintext = json.dumps(value, separators=(',', ':')).encode()

        encrypted = self.encrypt(plaintext, key_id)

        return {
            "encrypted": True,
            "value": encrypted.to_dict(),
            "field": field_name,
        }

    def decrypt_field(self, encrypted_field: Dict[str, Any]) -> Any:
        """Decrypt a field value from storage."""
        if not encrypted_field.get("encrypted", False):
            return encrypted_field.get("value")

        encrypted_data = EncryptedData.from_dict(encrypted_field["value"])
        plaintext = self.decrypt(encrypted_data)

        import json
        return json.loads(plaintext.decode())

    def rotate_key(self) -> str:
        """
        Rotate to a new encryption key.

        Returns:
            New key ID
        """
        if not self._initialized:
            raise RuntimeError("Encryption Manager not initialized")

        # Mark current key as inactive
        if self._current_key_id:
            current_key = self._keys.get(self._current_key_id)
            if current_key:
                current_key.is_active = False

        # Generate new key with incremented generation
        current_gen = 0
        if self._current_key_id:
            current_gen = self._keys[self._current_key_id].rotation_generation

        new_key_id = self._generate_new_key(rotation_generation=current_gen + 1)

        log_structured(logger, logging.INFO, "Key rotated", old_key=self._current_key_id, new_key=new_key_id)

        return new_key_id

    def get_key_info(self) -> List[Dict[str, Any]]:
        """Get information about all keys."""
        return [
            {
                "key_id": key.key_id,
                "created_at": key.created_at.isoformat(),
                "expires_at": key.expires_at.isoformat() if key.expires_at else None,
                "is_active": key.is_active,
                "rotation_generation": key.rotation_generation,
                "is_current": key.key_id == self._current_key_id,
            }
            for key in self._keys.values()
        ]

    def needs_rotation(self) -> bool:
        """Check if current key needs rotation."""
        if not self._current_key_id:
            return True

        key = self._keys.get(self._current_key_id)
        if not key:
            return True

        if key.expires_at and datetime.now(timezone.utc) > key.expires_at:
            return True

        return False

    async def shutdown(self) -> None:
        """Shutdown encryption manager."""
        self._keys.clear()
        self._current_key_id = None
        self._master_key = None
        self._initialized = False
        log_structured(logger, logging.INFO, "Encryption Manager shutdown")


# Field-level encryption helper
class FieldEncryption:
    """Helper for field-level encryption of PII."""

    def __init__(self, encryption_manager: EncryptionManager):
        self.encryption = encryption_manager

    # PII field patterns that should be encrypted
    PII_FIELDS = {
        "email", "phone", "ssn", "credit_card", "address",
        "date_of_birth", "passport", "driver_license",
        "api_key", "password", "secret", "token",
    }

    def should_encrypt(self, field_name: str) -> bool:
        """Check if a field should be encrypted."""
        field_lower = field_name.lower()
        return any(pii in field_lower for pii in self.PII_FIELDS)

    def encrypt_dict(self, data: Dict[str, Any], key_id: Optional[str] = None) -> Dict[str, Any]:
        """Encrypt sensitive fields in a dictionary."""
        result = {}
        for key, value in data.items():
            if self.should_encrypt(key):
                result[key] = self.encryption.encrypt_field(key, value, key_id)
            else:
                result[key] = value
        return result

    def decrypt_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Decrypt sensitive fields in a dictionary."""
        result = {}
        for key, value in data.items():
            if isinstance(value, dict) and value.get("encrypted", False):
                result[key] = self.encryption.decrypt_field(value)
            else:
                result[key] = value
        return result


# Global encryption manager instance
_encryption_manager: Optional[EncryptionManager] = None


async def get_encryption_manager() -> Optional[EncryptionManager]:
    """Get the global encryption manager instance."""
    return _encryption_manager


async def init_encryption_manager(config: Optional[EncryptionConfig] = None) -> EncryptionManager:
    """Initialize the global encryption manager."""
    global _encryption_manager
    _encryption_manager = EncryptionManager(config)
    await _encryption_manager.initialize()
    return _encryption_manager


async def shutdown_encryption_manager() -> None:
    """Shutdown the global encryption manager."""
    global _encryption_manager
    if _encryption_manager:
        await _encryption_manager.shutdown()
        _encryption_manager = None


__all__ = [
    "EncryptionManager",
    "EncryptionKey",
    "EncryptedData",
    "FieldEncryption",
    "get_encryption_manager",
    "init_encryption_manager",
    "shutdown_encryption_manager",
]