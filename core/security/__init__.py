"""
Security Package.

Exports all security components:
- Credential management
- Network egress control
- Prompt injection detection
- Security audit logging
- Encryption utilities
"""

from core.security.credentials import (
    CredentialManager,
    CredentialProvider,
    CredentialProviderBase,
    Credential,
    WindowsCredentialManager,
    KeyringProvider,
    VaultProvider,
    EnvProvider,
    FileProvider,
    get_credential_manager,
    init_credential_manager,
    shutdown_credential_manager,
)

from core.security.network import (
    EgressController,
    NetworkRule,
    ConnectionRequest,
    ConnectionDecision,
    DNSResolver,
    get_egress_controller,
    init_egress_controller,
    shutdown_egress_controller,
)

from core.security.prompt_injection import (
    PromptInjectionDetector,
    HeuristicDetector,
    MLDetector,
    DetectionResult,
    InjectionType,
    Severity,
    get_prompt_injection_detector,
    init_prompt_injection_detector,
    shutdown_prompt_injection_detector,
)

from core.security.audit import (
    SecurityAuditLogger,
    SecurityAuditEntry,
    SecurityEventCategory,
    get_security_audit_logger,
    init_security_audit_logger,
    shutdown_security_audit_logger,
)

from core.security.encryption import (
    EncryptionManager,
    EncryptionKey,
    EncryptedData,
    FieldEncryption,
    get_encryption_manager,
    init_encryption_manager,
    shutdown_encryption_manager,
)

__all__ = [
    # Credentials
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
    # Network
    "EgressController",
    "NetworkRule",
    "ConnectionRequest",
    "ConnectionDecision",
    "DNSResolver",
    "get_egress_controller",
    "init_egress_controller",
    "shutdown_egress_controller",
    # Prompt Injection
    "PromptInjectionDetector",
    "HeuristicDetector",
    "MLDetector",
    "DetectionResult",
    "InjectionType",
    "Severity",
    "get_prompt_injection_detector",
    "init_prompt_injection_detector",
    "shutdown_prompt_injection_detector",
    # Audit
    "SecurityAuditLogger",
    "SecurityAuditEntry",
    "SecurityEventCategory",
    "get_security_audit_logger",
    "init_security_audit_logger",
    "shutdown_security_audit_logger",
    # Encryption
    "EncryptionManager",
    "EncryptionKey",
    "EncryptedData",
    "FieldEncryption",
    "get_encryption_manager",
    "init_encryption_manager",
    "shutdown_encryption_manager",
]