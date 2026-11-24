"""
ARISE Secret Providers
Multiple secret backend implementations for secure credential management.
"""

import os
import json
import base64
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field

from .models import Settings

logger = logging.getLogger(__name__)


# =============================================================================
# Secret Provider Interface
# =============================================================================

class SecretProvider(ABC):
    """Abstract base class for secret providers."""

    @abstractmethod
    def get_secret(self, key: str) -> Optional[str]:
        """Get a secret value by key."""
        pass

    @abstractmethod
    def set_secret(self, key: str, value: str) -> bool:
        """Set a secret value."""
        pass

    @abstractmethod
    def delete_secret(self, key: str) -> bool:
        """Delete a secret."""
        pass

    @abstractmethod
    def list_secrets(self) -> List[str]:
        """List all secret keys."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass


# =============================================================================
# Environment Variable Provider
# =============================================================================

class EnvSecretProvider(SecretProvider):
    """Secret provider using environment variables."""

    def __init__(self, prefix: str = "ARISE_"):
        self.prefix = prefix

    @property
    def name(self) -> str:
        return "env"

    def is_available(self) -> bool:
        return True

    def get_secret(self, key: str) -> Optional[str]:
        env_key = f"{self.prefix}{key.upper()}"
        return os.getenv(env_key)

    def set_secret(self, key: str, value: str) -> bool:
        env_key = f"{self.prefix}{key.upper()}"
        os.environ[env_key] = value
        return True

    def delete_secret(self, key: str) -> bool:
        env_key = f"{self.prefix}{key.upper()}"
        if env_key in os.environ:
            del os.environ[env_key]
            return True
        return False

    def list_secrets(self) -> List[str]:
        secrets = []
        for key in os.environ:
            if key.startswith(self.prefix):
                secrets.append(key[len(self.prefix):].lower())
        return secrets


# =============================================================================
# Windows Credential Manager Provider (DPAPI)
# =============================================================================

class WindowsCredentialManager(SecretProvider):
    """Secret provider using Windows Credential Manager (DPAPI)."""

    def __init__(self, target_name: str = "ARISE"):
        self.target_name = target_name
        self._cred_mgmt = None

    @property
    def name(self) -> str:
        return "windows_credential_manager"

    def is_available(self) -> bool:
        try:
            import win32cred
            return True
        except ImportError:
            logger.warning("pywin32 not available, Windows Credential Manager disabled")
            return False

    def _get_cred_mgmt(self):
        if self._cred_mgmt is None:
            try:
                import win32cred
                self._cred_mgmt = win32cred
            except ImportError:
                raise RuntimeError("pywin32 required for Windows Credential Manager")
        return self._cred_mgmt

    def get_secret(self, key: str) -> Optional[str]:
        if not self.is_available():
            return None
        try:
            cred_mgmt = self._get_cred_mgmt()
            cred = cred_mgmt.CredRead(self._make_target(key), cred_mgmt.CRED_TYPE_GENERIC)
            if cred:
                return cred["CredentialBlob"].decode("utf-16-le")
        except Exception as e:
            logger.debug(f"Failed to read secret {key}: {e}")
        return None

    def set_secret(self, key: str, value: str) -> bool:
        if not self.is_available():
            return False
        try:
            cred_mgmt = self._get_cred_mgmt()
            cred = {
                "Type": cred_mgmt.CRED_TYPE_GENERIC,
                "TargetName": self._make_target(key),
                "CredentialBlob": value,  # Pass as string, win32cred handles encoding
                "Persist": cred_mgmt.CRED_PERSIST_LOCAL_MACHINE,
            }
            cred_mgmt.CredWrite(cred, 0)
            return True
        except Exception as e:
            logger.error(f"Failed to write secret {key}: {e}")
            return False

    def delete_secret(self, key: str) -> bool:
        if not self.is_available():
            return False
        try:
            cred_mgmt = self._get_cred_mgmt()
            cred_mgmt.CredDelete(self._make_target(key), cred_mgmt.CRED_TYPE_GENERIC)
            return True
        except Exception as e:
            logger.debug(f"Failed to delete secret {key}: {e}")
            return False

    def list_secrets(self) -> List[str]:
        if not self.is_available():
            return []
        try:
            cred_mgmt = self._get_cred_mgmt()
            creds = cred_mgmt.CredEnumerate(self._make_target("*"))
            secrets = []
            for cred in creds:
                target = cred["TargetName"]
                if target.startswith(f"{self.target_name}:"):
                    secrets.append(target[len(self.target_name)+1:])
            return secrets
        except Exception:
            return []

    def _make_target(self, key: str) -> str:
        return f"{self.target_name}:{key}"


# =============================================================================
# File-based Secret Provider
# =============================================================================

class FileSecretProvider(SecretProvider):
    """Secret provider using encrypted file storage."""

    def __init__(self, file_path: Optional[Path] = None, encryption_key: Optional[bytes] = None):
        self.file_path = file_path or Path.home() / ".arise" / "secrets.enc"
        self.encryption_key = encryption_key or self._derive_key()
        self._ensure_file_exists()

    @property
    def name(self) -> str:
        return "file"

    def is_available(self) -> bool:
        return True

    def _derive_key(self) -> bytes:
        """Derive encryption key from machine-specific data."""
        import hashlib
        import platform
        machine_id = f"{platform.node()}{platform.machine()}{os.getuid() if hasattr(os, 'getuid') else '0'}"
        return hashlib.sha256(machine_id.encode()).digest()

    def _ensure_file_exists(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self.file_path.write_bytes(b"")

    def _encrypt(self, data: str) -> bytes:
        from cryptography.fernet import Fernet
        key = base64.urlsafe_b64encode(self.encryption_key[:32])
        f = Fernet(key)
        return f.encrypt(data.encode())

    def _decrypt(self, data: bytes) -> str:
        from cryptography.fernet import Fernet
        key = base64.urlsafe_b64encode(self.encryption_key[:32])
        f = Fernet(key)
        return f.decrypt(data).decode()

    def get_secret(self, key: str) -> Optional[str]:
        try:
            secrets = self._load_secrets()
            if key in secrets:
                return self._decrypt(secrets[key])
        except Exception as e:
            logger.debug(f"Failed to read secret {key}: {e}")
        return None

    def set_secret(self, key: str, value: str) -> bool:
        try:
            secrets = self._load_secrets()
            secrets[key] = self._encrypt(value).decode()
            self._save_secrets(secrets)
            return True
        except Exception as e:
            logger.error(f"Failed to write secret {key}: {e}")
            return False

    def delete_secret(self, key: str) -> bool:
        try:
            secrets = self._load_secrets()
            if key in secrets:
                del secrets[key]
                self._save_secrets(secrets)
                return True
        except Exception:
            pass
        return False

    def list_secrets(self) -> List[str]:
        try:
            return list(self._load_secrets().keys())
        except Exception:
            return []

    def _load_secrets(self) -> Dict[str, str]:
        if not self.file_path.exists() or self.file_path.stat().st_size == 0:
            return {}
        try:
            data = self.file_path.read_text()
            return json.loads(data)
        except Exception:
            return {}

    def _save_secrets(self, secrets: Dict[str, str]) -> None:
        self.file_path.write_text(json.dumps(secrets))


# =============================================================================
# HashiCorp Vault Provider
# =============================================================================

class VaultSecretProvider(SecretProvider):
    """Secret provider using HashiCorp Vault."""

    def __init__(
        self,
        url: Optional[str] = None,
        token: Optional[str] = None,
        mount_point: str = "secret",
        path: str = "arise",
    ):
        self.url = url or os.getenv("VAULT_ADDR", "http://localhost:8200")
        self.token = token or os.getenv("VAULT_TOKEN")
        self.mount_point = mount_point
        self.path = path
        self._client = None

    @property
    def name(self) -> str:
        return "vault"

    def is_available(self) -> bool:
        try:
            import hvac
            return bool(self.token)
        except ImportError:
            logger.warning("hvac not available, Vault provider disabled")
            return False

    def _get_client(self):
        if self._client is None:
            try:
                import hvac
                self._client = hvac.Client(url=self.url, token=self.token)
                if not self._client.is_authenticated():
                    raise RuntimeError("Vault authentication failed")
            except ImportError:
                raise RuntimeError("hvac required for Vault provider")
        return self._client

    def get_secret(self, key: str) -> Optional[str]:
        if not self.is_available():
            return None
        try:
            client = self._get_client()
            secret = client.secrets.kv.v2.read_secret_version(
                path=f"{self.path}/{key}",
                mount_point=self.mount_point,
            )
            return secret["data"]["data"].get("value")
        except Exception as e:
            logger.debug(f"Failed to read secret {key} from Vault: {e}")
        return None

    def set_secret(self, key: str, value: str) -> bool:
        if not self.is_available():
            return False
        try:
            client = self._get_client()
            client.secrets.kv.v2.create_or_update_secret(
                path=f"{self.path}/{key}",
                secret={"value": value},
                mount_point=self.mount_point,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to write secret {key} to Vault: {e}")
            return False

    def delete_secret(self, key: str) -> bool:
        if not self.is_available():
            return False
        try:
            client = self._get_client()
            client.secrets.kv.v2.delete_metadata_and_all_versions(
                path=f"{self.path}/{key}",
                mount_point=self.mount_point,
            )
            return True
        except Exception as e:
            logger.debug(f"Failed to delete secret {key} from Vault: {e}")
            return False

    def list_secrets(self) -> List[str]:
        if not self.is_available():
            return []
        try:
            client = self._get_client()
            secrets = client.secrets.kv.v2.list_secrets(
                path=self.path,
                mount_point=self.mount_point,
            )
            return secrets["data"]["keys"]
        except Exception:
            return []


# =============================================================================
# Keyring Provider (Cross-platform)
# =============================================================================

class KeyringProvider(SecretProvider):
    """Secret provider using system keyring (cross-platform)."""

    def __init__(self, service_name: str = "ARISE"):
        self.service_name = service_name

    @property
    def name(self) -> str:
        return "keyring"

    def is_available(self) -> bool:
        try:
            import keyring
            return True
        except ImportError:
            logger.warning("keyring not available")
            return False

    def get_secret(self, key: str) -> Optional[str]:
        if not self.is_available():
            return None
        try:
            import keyring
            return keyring.get_password(self.service_name, key)
        except Exception as e:
            logger.debug(f"Failed to read secret {key} from keyring: {e}")
        return None

    def set_secret(self, key: str, value: str) -> bool:
        if not self.is_available():
            return False
        try:
            import keyring
            keyring.set_password(self.service_name, key, value)
            return True
        except Exception as e:
            logger.error(f"Failed to write secret {key} to keyring: {e}")
            return False

    def delete_secret(self, key: str) -> bool:
        if not self.is_available():
            return False
        try:
            import keyring
            keyring.delete_password(self.service_name, key)
            return True
        except Exception as e:
            logger.debug(f"Failed to delete secret {key} from keyring: {e}")
            return False

    def list_secrets(self) -> List[str]:
        if not self.is_available():
            return []
        try:
            import keyring
            # Keyring doesn't support listing, return empty
            return []
        except Exception:
            return []


# =============================================================================
# Secret Manager (Orchestrator)
# =============================================================================

@dataclass
class SecretManager:
    """
    Secret manager that coordinates multiple providers with fallback chain.
    """
    providers: List[SecretProvider] = field(default_factory=list)
    primary_provider: Optional[SecretProvider] = None

    def __post_init__(self):
        if not self.providers:
            self._initialize_default_providers()

    def _initialize_default_providers(self) -> None:
        """Initialize default provider chain based on platform."""
        import platform

        # Primary provider based on platform
        if platform.system() == "Windows":
            self.providers.append(WindowsCredentialManager())
        else:
            self.providers.append(KeyringProvider())

        # Fallback providers
        self.providers.append(FileSecretProvider())
        self.providers.append(EnvSecretProvider())

        # Optional Vault provider
        if os.getenv("VAULT_ADDR") and os.getenv("VAULT_TOKEN"):
            self.providers.append(VaultSecretProvider())

        # Set first available as primary
        for provider in self.providers:
            if provider.is_available():
                self.primary_provider = provider
                break

    def get_secret(self, key: str) -> Optional[str]:
        """Get secret from first available provider."""
        for provider in self.providers:
            if provider.is_available():
                value = provider.get_secret(key)
                if value is not None:
                    return value
        return None

    def set_secret(self, key: str, value: str) -> bool:
        """Set secret in primary provider."""
        if self.primary_provider and self.primary_provider.is_available():
            return self.primary_provider.set_secret(key, value)
        # Fallback to first available
        for provider in self.providers:
            if provider.is_available():
                return provider.set_secret(key, value)
        return False

    def delete_secret(self, key: str) -> bool:
        """Delete secret from all providers."""
        deleted = False
        for provider in self.providers:
            if provider.is_available():
                if provider.delete_secret(key):
                    deleted = True
        return deleted

    def list_secrets(self) -> List[str]:
        """List secrets from all providers."""
        all_secrets = set()
        for provider in self.providers:
            if provider.is_available():
                all_secrets.update(provider.list_secrets())
        return sorted(all_secrets)

    def get_all_secrets(self) -> Dict[str, str]:
        """Get all secrets as a flat dictionary."""
        secrets = {}
        for provider in self.providers:
            if provider.is_available():
                for key in provider.list_secrets():
                    value = provider.get_secret(key)
                    if value is not None:
                        secrets[key] = value
        return secrets

    def add_provider(self, provider: SecretProvider, primary: bool = False) -> None:
        """Add a custom provider."""
        if primary:
            self.providers.insert(0, provider)
            self.primary_provider = provider
        else:
            self.providers.append(provider)

    def get_provider(self, name: str) -> Optional[SecretProvider]:
        """Get a provider by name."""
        for provider in self.providers:
            if provider.name == name:
                return provider
        return None


# Global secret manager instance
_secret_manager: Optional[SecretManager] = None


def get_secret_manager() -> SecretManager:
    """Get or create the global secret manager."""
    global _secret_manager
    if _secret_manager is None:
        _secret_manager = SecretManager()
    return _secret_manager


def get_secret(key: str) -> Optional[str]:
    """Get a secret value."""
    return get_secret_manager().get_secret(key)


def set_secret(key: str, value: str) -> bool:
    """Set a secret value."""
    return get_secret_manager().set_secret(key, value)


def delete_secret(key: str) -> bool:
    """Delete a secret."""
    return get_secret_manager().delete_secret(key)