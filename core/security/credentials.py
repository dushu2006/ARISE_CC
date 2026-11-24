"""
Credential Management System.

Supports multiple credential providers with priority-based fallback:
1. Windows Credential Manager (primary on Windows)
2. Keyring (cross-platform)
3. HashiCorp Vault
4. Environment variables
"""

from __future__ import annotations
import asyncio
import base64
import json
import logging
import os
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import load_config
from core.config.models import SecurityConfig, CredentialsConfig
from core.structured_logging import get_logger, log_structured

logger = get_logger(__name__)


class CredentialProvider(str, Enum):
    """Credential provider types."""
    WINDOWS_CREDENTIAL_MANAGER = "windows_credential_manager"
    KEYRING = "keyring"
    VAULT = "vault"
    ENV = "env"
    FILE = "file"


@dataclass
class Credential:
    """A stored credential."""
    category: str
    key: str
    value: str
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class CredentialProviderBase(ABC):
    """Abstract base class for credential providers."""

    @property
    @abstractmethod
    def name(self) -> CredentialProvider:
        """Provider name."""
        pass

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize provider. Returns True if available."""
        pass

    @abstractmethod
    async def get(self, category: str, key: str) -> Optional[str]:
        """Get a credential value."""
        pass

    @abstractmethod
    async def set(self, category: str, key: str, value: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Set a credential value."""
        pass

    @abstractmethod
    async def delete(self, category: str, key: str) -> bool:
        """Delete a credential."""
        pass

    @abstractmethod
    async def list(self, category: Optional[str] = None) -> List[Credential]:
        """List credentials."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check provider health."""
        pass


class WindowsCredentialManager(CredentialProviderBase):
    """Windows Credential Manager provider using PowerShell."""

    @property
    def name(self) -> CredentialProvider:
        return CredentialProvider.WINDOWS_CREDENTIAL_MANAGER

    def __init__(self):
        self._available = False

    async def initialize(self) -> bool:
        """Check if Windows Credential Manager is available."""
        try:
            # Test with a simple PowerShell command
            result = await asyncio.create_subprocess_exec(
                "powershell", "-Command", "Get-StoredCredential -ErrorAction SilentlyContinue",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await result.communicate()
            self._available = result.returncode == 0
            if self._available:
                log_structured(logger, logging.INFO, "Windows Credential Manager available")
            return self._available
        except Exception as e:
            log_structured(logger, logging.DEBUG, "Windows Credential Manager not available", error=str(e))
            self._available = False
            return False

    def _target_name(self, category: str, key: str) -> str:
        """Generate target name for Windows Credential Manager."""
        return f"ARISE/{category}/{key}"

    async def get(self, category: str, key: str) -> Optional[str]:
        """Get credential from Windows Credential Manager."""
        if not self._available:
            return None

        target = self._target_name(category, key)
        try:
            result = await asyncio.create_subprocess_exec(
                "powershell", "-Command",
                f"Get-StoredCredential -Target '{target}' | Select-Object -ExpandProperty Password",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0 and stdout:
                # Password is returned as SecureString, need to convert
                password = stdout.decode().strip()
                if password:
                    return password
        except Exception as e:
            log_structured(logger, logging.DEBUG, "Failed to get credential", target=target, error=str(e))
        return None

    async def set(self, category: str, key: str, value: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Set credential in Windows Credential Manager."""
        if not self._available:
            return False

        target = self._target_name(category, key)
        try:
            # Use PowerShell to store credential
            # Escape value for PowerShell
            escaped_value = value.replace("'", "''")
            script = f"""
            $securePassword = ConvertTo-SecureString '{escaped_value}' -AsPlainText -Force
            New-StoredCredential -Target '{target}' -UserName 'ARISE' -Password $securePassword -Persist LocalMachine -ErrorAction Stop
            """

            result = await asyncio.create_subprocess_exec(
                "powershell", "-Command", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                log_structured(logger, logging.INFO, "Credential stored", target=target)
                return True
            else:
                log_structured(logger, logging.ERROR, "Failed to store credential", target=target, error=stderr.decode())
                return False

        except Exception as e:
            log_structured(logger, logging.ERROR, "Exception storing credential", target=target, error=str(e))
            return False

    async def delete(self, category: str, key: str) -> bool:
        """Delete credential from Windows Credential Manager."""
        if not self._available:
            return False

        target = self._target_name(category, key)
        try:
            result = await asyncio.create_subprocess_exec(
                "powershell", "-Command",
                f"Remove-StoredCredential -Target '{target}' -ErrorAction SilentlyContinue",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await result.communicate()
            log_structured(logger, logging.INFO, "Credential deleted", target=target)
            return True
        except Exception as e:
            log_structured(logger, logging.ERROR, "Failed to delete credential", target=target, error=str(e))
            return False

    async def list(self, category: Optional[str] = None) -> List[Credential]:
        """List credentials from Windows Credential Manager."""
        if not self._available:
            return []

        try:
            filter_str = f"ARISE/{category}/*" if category else "ARISE/*"
            script = f"Get-StoredCredential | Where-Object {{ $_.TargetName -like '{filter_str}' }} | Select-Object TargetName, UserName | ConvertTo-Json"

            result = await asyncio.create_subprocess_exec(
                "powershell", "-Command", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0 and stdout:
                creds_data = json.loads(stdout.decode())
                if not isinstance(creds_data, list):
                    creds_data = [creds_data]

                credentials = []
                for cred in creds_data:
                    target = cred.get("TargetName", "")
                    parts = target.split("/")
                    if len(parts) >= 3:
                        cred_category = parts[1]
                        cred_key = "/".join(parts[2:])
                        # Get the actual value
                        value = await self.get(cred_category, cred_key)
                        if value:
                            credentials.append(Credential(
                                category=cred_category,
                                key=cred_key,
                                value=value,
                            ))
                return credentials
        except Exception as e:
            log_structured(logger, logging.ERROR, "Failed to list credentials", error=str(e))
        return []

    async def health_check(self) -> bool:
        """Check Windows Credential Manager health."""
        return self._available


class KeyringProvider(CredentialProviderBase):
    """Keyring provider (cross-platform)."""

    @property
    def name(self) -> CredentialProvider:
        return CredentialProvider.KEYRING

    def __init__(self):
        self._keyring = None
        self._available = False

    async def initialize(self) -> bool:
        """Initialize keyring."""
        try:
            import keyring
            self._keyring = keyring
            self._available = True
            log_structured(logger, logging.INFO, "Keyring provider available", backend=keyring.get_keyring().__class__.__name__)
            return True
        except ImportError:
            log_structured(logger, logging.DEBUG, "Keyring not available")
            self._available = False
            return False
        except Exception as e:
            log_structured(logger, logging.DEBUG, "Keyring initialization failed", error=str(e))
            self._available = False
            return False

    def _service_name(self, category: str) -> str:
        return f"ARISE-{category}"

    async def get(self, category: str, key: str) -> Optional[str]:
        """Get credential from keyring."""
        if not self._available:
            return None

        try:
            value = self._keyring.get_password(self._service_name(category), key)
            return value
        except Exception as e:
            log_structured(logger, logging.DEBUG, "Keyring get failed", category=category, key=key, error=str(e))
            return None

    async def set(self, category: str, key: str, value: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Set credential in keyring."""
        if not self._available:
            return False

        try:
            self._keyring.set_password(self._service_name(category), key, value)
            log_structured(logger, logging.INFO, "Credential stored in keyring", category=category, key=key)
            return True
        except Exception as e:
            log_structured(logger, logging.ERROR, "Keyring set failed", category=category, key=key, error=str(e))
            return False

    async def delete(self, category: str, key: str) -> bool:
        """Delete credential from keyring."""
        if not self._available:
            return False

        try:
            self._keyring.delete_password(self._service_name(category), key)
            log_structured(logger, logging.INFO, "Credential deleted from keyring", category=category, key=key)
            return True
        except Exception as e:
            log_structured(logger, logging.ERROR, "Keyring delete failed", category=category, key=key, error=str(e))
            return False

    async def list(self, category: Optional[str] = None) -> List[Credential]:
        """List credentials from keyring."""
        # Keyring doesn't support listing, return empty
        return []

    async def health_check(self) -> bool:
        """Check keyring health."""
        if not self._available:
            return False
        try:
            # Try a simple operation
            self._keyring.get_password("ARISE-health", "check")
            return True
        except Exception:
            return False


class VaultProvider(CredentialProviderBase):
    """HashiCorp Vault provider."""

    @property
    def name(self) -> CredentialProvider:
        return CredentialProvider.VAULT

    def __init__(self, config: CredentialsConfig):
        self.config = config
        self._client = None
        self._available = False

    async def initialize(self) -> bool:
        """Initialize Vault client."""
        try:
            import hvac
            vault_addr = self.config.vault_addr or os.getenv("VAULT_ADDR")
            vault_token = self.config.vault_token or os.getenv("VAULT_TOKEN")

            if not vault_addr or not vault_token:
                log_structured(logger, logging.DEBUG, "Vault not configured (missing VAULT_ADDR or VAULT_TOKEN)")
                return False

            self._client = hvac.Client(url=vault_addr, token=vault_token)
            if self._client.is_authenticated():
                self._available = True
                log_structured(logger, logging.INFO, "Vault provider available", addr=vault_addr)
                return True
            else:
                log_structured(logger, logging.WARNING, "Vault authentication failed")
                return False
        except ImportError:
            log_structured(logger, logging.DEBUG, "hvac not available")
            return False
        except Exception as e:
            log_structured(logger, logging.DEBUG, "Vault initialization failed", error=str(e))
            return False

    def _secret_path(self, category: str) -> str:
        return f"secret/data/arise/{category}"

    async def get(self, category: str, key: str) -> Optional[str]:
        """Get credential from Vault."""
        if not self._available:
            return None

        try:
            path = self._secret_path(category)
            response = self._client.secrets.kv.v2.read_secret_version(path=path)
            if response and "data" in response and "data" in response["data"]:
                return response["data"]["data"].get(key)
        except Exception as e:
            log_structured(logger, logging.DEBUG, "Vault get failed", category=category, key=key, error=str(e))
        return None

    async def set(self, category: str, key: str, value: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Set credential in Vault."""
        if not self._available:
            return False

        try:
            path = self._secret_path(category)
            # Read existing secrets
            existing = {}
            try:
                response = self._client.secrets.kv.v2.read_secret_version(path=path)
                if response and "data" in response and "data" in response["data"]:
                    existing = response["data"]["data"]
            except Exception:
                pass

            # Update with new value
            existing[key] = value

            # Write back
            self._client.secrets.kv.v2.create_or_update_secret(path=path, secret=existing)
            log_structured(logger, logging.INFO, "Credential stored in Vault", category=category, key=key)
            return True
        except Exception as e:
            log_structured(logger, logging.ERROR, "Vault set failed", category=category, key=key, error=str(e))
            return False

    async def delete(self, category: str, key: str) -> bool:
        """Delete credential from Vault."""
        if not self._available:
            return False

        try:
            path = self._secret_path(category)
            # Read existing, delete key, write back
            response = self._client.secrets.kv.v2.read_secret_version(path=path)
            if response and "data" in response and "data" in response["data"]:
                data = response["data"]["data"]
                if key in data:
                    del data[key]
                    self._client.secrets.kv.v2.create_or_update_secret(path=path, secret=data)
                    log_structured(logger, logging.INFO, "Credential deleted from Vault", category=category, key=key)
                    return True
        except Exception as e:
            log_structured(logger, logging.ERROR, "Vault delete failed", category=category, key=key, error=str(e))
        return False

    async def list(self, category: Optional[str] = None) -> List[Credential]:
        """List credentials from Vault."""
        if not self._available:
            return []

        credentials = []
        try:
            categories = [category] if category else ["api_keys", "grants", "oauth_tokens", "ssh_keys", "certificates", "passwords"]
            for cat in categories:
                path = self._secret_path(cat)
                try:
                    response = self._client.secrets.kv.v2.read_secret_version(path=path)
                    if response and "data" in response and "data" in response["data"]:
                        for k, v in response["data"]["data"].items():
                            credentials.append(Credential(category=cat, key=k, value=v))
                except Exception:
                    continue
        except Exception as e:
            log_structured(logger, logging.ERROR, "Vault list failed", error=str(e))
        return credentials

    async def health_check(self) -> bool:
        """Check Vault health."""
        if not self._available:
            return False
        try:
            return self._client.is_authenticated()
        except Exception:
            return False


class EnvProvider(CredentialProviderBase):
    """Environment variable provider."""

    @property
    def name(self) -> CredentialProvider:
        return CredentialProvider.ENV

    def __init__(self):
        self._available = True

    async def initialize(self) -> bool:
        return True

    def _env_key(self, category: str, key: str) -> str:
        return f"ARISE_{category.upper()}_{key.upper()}"

    async def get(self, category: str, key: str) -> Optional[str]:
        """Get credential from environment variable."""
        env_key = self._env_key(category, key)
        return os.getenv(env_key)

    async def set(self, category: str, key: str, value: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Set environment variable (only affects current process)."""
        env_key = self._env_key(category, key)
        os.environ[env_key] = value
        log_structured(logger, logging.INFO, "Credential set in environment", env_key=env_key)
        return True

    async def delete(self, category: str, key: str) -> bool:
        """Delete environment variable."""
        env_key = self._env_key(category, key)
        if env_key in os.environ:
            del os.environ[env_key]
            log_structured(logger, logging.INFO, "Credential deleted from environment", env_key=env_key)
            return True
        return False

    async def list(self, category: Optional[str] = None) -> List[Credential]:
        """List credentials from environment."""
        credentials = []
        prefix = f"ARISE_{category.upper()}_" if category else "ARISE_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                # Parse category and key from env var
                remainder = key[len(prefix):]
                if category:
                    cred_category = category
                    cred_key = remainder.lower()
                else:
                    parts = remainder.split("_", 1)
                    if len(parts) == 2:
                        cred_category = parts[0].lower()
                        cred_key = parts[1].lower()
                    else:
                        continue
                credentials.append(Credential(category=cred_category, key=cred_key, value=value))
        return credentials

    async def health_check(self) -> bool:
        return True


class FileProvider(CredentialProviderBase):
    """Encrypted file provider (Fernet)."""

    @property
    def name(self) -> CredentialProvider:
        return CredentialProvider.FILE

    def __init__(self, config: CredentialsConfig):
        self.config = config
        self._fernet = None
        self._file_path = Path("./data/credentials.enc")
        self._available = False

    async def initialize(self) -> bool:
        """Initialize encrypted file storage."""
        try:
            from cryptography.fernet import Fernet

            # Get or create encryption key
            key = os.getenv("ARISE_CREDENTIALS_KEY")
            if not key:
                # Generate a key from master encryption key if available
                master_key = os.getenv("ARISE_MASTER_ENCRYPTION_KEY")
                if master_key:
                    import hashlib
                    key = base64.urlsafe_b64encode(hashlib.sha256(master_key.encode()).digest()).decode()
                else:
                    log_structured(logger, logging.DEBUG, "No encryption key for file provider")
                    return False

            self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            self._available = True
            log_structured(logger, logging.INFO, "File credential provider initialized", path=str(self._file_path))
            return True
        except ImportError:
            log_structured(logger, logging.DEBUG, "cryptography not available for file provider")
            return False
        except Exception as e:
            log_structured(logger, logging.DEBUG, "File provider initialization failed", error=str(e))
            return False

    async def _load_credentials(self) -> Dict[str, Dict[str, str]]:
        """Load all credentials from file."""
        if not self._file_path.exists():
            return {}

        try:
            with open(self._file_path, "rb") as f:
                encrypted = f.read()
            decrypted = self._fernet.decrypt(encrypted)
            return json.loads(decrypted.decode())
        except Exception:
            return {}

    async def _save_credentials(self, data: Dict[str, Dict[str, str]]) -> bool:
        """Save credentials to file."""
        try:
            encrypted = self._fernet.encrypt(json.dumps(data).encode())
            # Write atomically
            temp_path = self._file_path.with_suffix(".tmp")
            with open(temp_path, "wb") as f:
                f.write(encrypted)
            temp_path.replace(self._file_path)
            return True
        except Exception as e:
            log_structured(logger, logging.ERROR, "Failed to save credentials file", error=str(e))
            return False

    async def get(self, category: str, key: str) -> Optional[str]:
        """Get credential from file."""
        if not self._available:
            return None

        data = await self._load_credentials()
        return data.get(category, {}).get(key)

    async def set(self, category: str, key: str, value: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Set credential in file."""
        if not self._available:
            return False

        data = await self._load_credentials()
        if category not in data:
            data[category] = {}
        data[category][key] = value
        return await self._save_credentials(data)

    async def delete(self, category: str, key: str) -> bool:
        """Delete credential from file."""
        if not self._available:
            return False

        data = await self._load_credentials()
        if category in data and key in data[category]:
            del data[category][key]
            if not data[category]:
                del data[category]
            return await self._save_credentials(data)
        return False

    async def list(self, category: Optional[str] = None) -> List[Credential]:
        """List credentials from file."""
        if not self._available:
            return []

        data = await self._load_credentials()
        credentials = []
        categories = [category] if category else data.keys()
        for cat in categories:
            if cat in data:
                for k, v in data[cat].items():
                    credentials.append(Credential(category=cat, key=k, value=v))
        return credentials

    async def health_check(self) -> bool:
        """Check file provider health."""
        return self._available


class CredentialManager:
    """
    Credential Manager with priority-based provider chain.

    Providers are tried in order until one succeeds.
    """

    def __init__(self, config: Optional[SecurityConfig] = None):
        self.config = config or load_config().security
        self.credentials_config = self.config.credentials
        self._providers: List[CredentialProviderBase] = []
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize all providers in priority order."""
        log_structured(logger, logging.INFO, "Initializing Credential Manager")

        # Create providers in priority order
        provider_classes = []

        # Windows Credential Manager (primary on Windows)
        if self.credentials_config.primary_provider == "windows_credential_manager" or os.name == "nt":
            provider_classes.append(("windows_credential_manager", WindowsCredentialManager))

        # Keyring
        if "keyring" in self.credentials_config.fallback_providers:
            provider_classes.append(("keyring", KeyringProvider))

        # Vault
        if "vault" in self.credentials_config.fallback_providers:
            provider_classes.append(("vault", lambda: VaultProvider(self.credentials_config)))

        # Environment variables
        if "env" in self.credentials_config.fallback_providers:
            provider_classes.append(("env", EnvProvider))

        # File (encrypted)
        if "file" in self.credentials_config.fallback_providers:
            provider_classes.append(("file", lambda: FileProvider(self.credentials_config)))

        # Initialize providers
        for name, factory in provider_classes:
            try:
                provider = factory()
                if await provider.initialize():
                    self._providers.append(provider)
                    log_structured(logger, logging.INFO, "Credential provider ready", provider=provider.name.value)
                else:
                    log_structured(logger, logging.DEBUG, "Credential provider not available", provider=name)
            except Exception as e:
                log_structured(logger, logging.WARNING, "Failed to initialize credential provider", provider=name, error=str(e))

        self._initialized = True
        log_structured(logger, logging.INFO, "Credential Manager initialized", providers=[p.name.value for p in self._providers])

    async def shutdown(self) -> None:
        """Shutdown all providers."""
        self._providers.clear()
        self._initialized = False

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("Credential Manager not initialized")

    async def get_credential(self, category: str, key: str) -> Optional[str]:
        """
        Get a credential, trying providers in priority order.

        Args:
            category: Credential category (api_keys, grants, etc.)
            key: Credential key

        Returns:
            Credential value or None if not found
        """
        self._ensure_initialized()

        for provider in self._providers:
            try:
                value = await provider.get(category, key)
                if value is not None:
                    log_structured(logger, logging.DEBUG, "Credential retrieved", category=category, key=key, provider=provider.name.value)
                    return value
            except Exception as e:
                log_structured(logger, logging.DEBUG, "Provider get failed", provider=provider.name.value, error=str(e))
                continue

        log_structured(logger, logging.DEBUG, "Credential not found in any provider", category=category, key=key)
        return None

    async def set_credential(self, category: str, key: str, value: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Set a credential in the primary provider.

        Args:
            category: Credential category
            key: Credential key
            value: Credential value
            metadata: Optional metadata

        Returns:
            True if successful
        """
        self._ensure_initialized()

        if not self._providers:
            log_structured(logger, logging.ERROR, "No credential providers available")
            return False

        # Try primary provider first
        primary = self._providers[0]
        try:
            success = await primary.set(category, key, value, metadata)
            if success:
                log_structured(logger, logging.INFO, "Credential stored", category=category, key=key, provider=primary.name.value)
                return True
        except Exception as e:
            log_structured(logger, logging.ERROR, "Primary provider set failed", provider=primary.name.value, error=str(e))

        # Fallback to other providers
        for provider in self._providers[1:]:
            try:
                success = await provider.set(category, key, value, metadata)
                if success:
                    log_structured(logger, logging.INFO, "Credential stored (fallback)", category=category, key=key, provider=provider.name.value)
                    return True
            except Exception as e:
                log_structured(logger, logging.DEBUG, "Fallback provider set failed", provider=provider.name.value, error=str(e))
                continue

        return False

    async def delete_credential(self, category: str, key: str) -> bool:
        """
        Delete a credential from all providers.

        Args:
            category: Credential category
            key: Credential key

        Returns:
            True if deleted from at least one provider
        """
        self._ensure_initialized()

        deleted = False
        for provider in self._providers:
            try:
                success = await provider.delete(category, key)
                if success:
                    deleted = True
                    log_structured(logger, logging.INFO, "Credential deleted", category=category, key=key, provider=provider.name.value)
            except Exception as e:
                log_structured(logger, logging.DEBUG, "Provider delete failed", provider=provider.name.value, error=str(e))

        return deleted

    async def list_credentials(self, category: Optional[str] = None) -> List[Credential]:
        """List credentials from all providers (deduplicated)."""
        self._ensure_initialized()

        seen = set()
        all_credentials = []

        for provider in self._providers:
            try:
                credentials = await provider.list(category)
                for cred in credentials:
                    identifier = f"{cred.category}/{cred.key}"
                    if identifier not in seen:
                        seen.add(identifier)
                        all_credentials.append(cred)
            except Exception as e:
                log_structured(logger, logging.DEBUG, "Provider list failed", provider=provider.name.value, error=str(e))

        return all_credentials

    async def health_check(self) -> Dict[str, bool]:
        """Check health of all providers."""
        self._ensure_initialized()

        results = {}
        for provider in self._providers:
            try:
                results[provider.name.value] = await provider.health_check()
            except Exception:
                results[provider.name.value] = False
        return results


# Global credential manager instance
_credential_manager: Optional[CredentialManager] = None


async def get_credential_manager() -> Optional[CredentialManager]:
    """Get the global credential manager instance."""
    return _credential_manager


async def init_credential_manager(config: Optional[SecurityConfig] = None) -> CredentialManager:
    """Initialize the global credential manager."""
    global _credential_manager
    _credential_manager = CredentialManager(config)
    await _credential_manager.initialize()
    return _credential_manager


async def shutdown_credential_manager() -> None:
    """Shutdown the global credential manager."""
    global _credential_manager
    if _credential_manager:
        await _credential_manager.shutdown()
        _credential_manager = None


__all__ = [
    "CredentialManager",
    "CredentialProvider",
    "CredentialProviderBase",
    "Credential",
    "WindowsCredentialManager",
    "KeyringProvider",
    "VaultProvider",
    "EnvProvider",
    "FileProvider",
    "get_credential_manager",
    "init_credential_manager",
    "shutdown_credential_manager",
]