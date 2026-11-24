# core/errors/factory.py
from core.errors.base import (
    AriseError, ErrorCode, ErrorContext,
    TaskError, PolicyError, ModelError, VoiceError,
    MemoryError, AgentError, AutomationError, SecurityError,
    ConfigurationError, EventError, DatabaseError
)
from typing import Optional, Dict, Any, List
import time


def create_error_context(
    component: str,
    operation: str,
    correlation_id: str = "",
    causation_id: str = "",
    task_id: str = "",
    agent_id: str = "",
    session_id: str = "",
    **metadata
) -> ErrorContext:
    """Create standardized error context"""
    return ErrorContext(
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        component=component,
        operation=operation,
        correlation_id=correlation_id,
        causation_id=causation_id,
        task_id=task_id,
        agent_id=agent_id,
        session_id=session_id,
        metadata=metadata,
    )


# Factory functions for common errors

def capability_denied(
    capability: str,
    resource: str = "",
    context: ErrorContext = None,
) -> PolicyError:
    ctx = context or create_error_context("policy", "check_capability")
    ctx.metadata.update({"capability": capability, "resource": resource})
    return PolicyError(
        code=ErrorCode.CAPABILITY_DENIED,
        message=f"Capability denied: {capability}" + (f" for {resource}" if resource else ""),
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Request user approval for this capability",
            "Check if capability grant exists and hasn't expired",
            "Verify capability scope matches resource",
        ],
    )


def approval_required(
    risk_level: str,
    capability: str,
    resource: str,
    context: ErrorContext = None,
) -> PolicyError:
    ctx = context or create_error_context("policy", "assess_risk")
    ctx.metadata.update({"risk_level": risk_level, "capability": capability, "resource": resource})
    return PolicyError(
        code=ErrorCode.APPROVAL_DENIED,
        message=f"Action requires {risk_level} approval: {capability} on {resource}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Wait for user approval via UI",
            "Check approval timeout (default 5 minutes)",
        ],
    )


def approval_expired(
    approval_id: str,
    context: ErrorContext = None,
) -> PolicyError:
    ctx = context or create_error_context("policy", "check_approval")
    ctx.metadata.update({"approval_id": approval_id})
    return PolicyError(
        code=ErrorCode.APPROVAL_EXPIRED,
        message=f"Approval expired: {approval_id}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Re-request approval from user",
        ],
    )


def risk_too_high(
    risk_level: str,
    capability: str,
    resource: str,
    max_allowed: str,
    context: ErrorContext = None,
) -> PolicyError:
    ctx = context or create_error_context("policy", "assess_risk")
    ctx.metadata.update({
        "risk_level": risk_level,
        "capability": capability,
        "resource": resource,
        "max_allowed": max_allowed,
    })
    return PolicyError(
        code=ErrorCode.RISK_TOO_HIGH,
        message=f"Risk level {risk_level} exceeds maximum allowed {max_allowed} for {capability} on {resource}",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Reduce operation scope or risk level",
            "Request policy exception from administrator",
        ],
    )


def grant_expired(
    grant_id: str,
    context: ErrorContext = None,
) -> PolicyError:
    ctx = context or create_error_context("policy", "check_grant")
    ctx.metadata.update({"grant_id": grant_id})
    return PolicyError(
        code=ErrorCode.GRANT_EXPIRED,
        message=f"Capability grant expired: {grant_id}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Request new capability grant",
            "Check grant TTL and renewal policy",
        ],
    )


def provider_unavailable(
    provider: str,
    task_type: str,
    context: ErrorContext = None,
) -> ModelError:
    ctx = context or create_error_context("model_router", "complete")
    ctx.metadata.update({"provider": provider, "task_type": task_type})
    return ModelError(
        code=ErrorCode.PROVIDER_UNAVAILABLE,
        message=f"Provider {provider} unavailable for {task_type}",
        context=ctx,
        recoverable=True,
        retry_after=30.0,
        suggested_actions=[
            "Request will be routed to fallback provider",
            "Check provider API status",
            "Verify API credentials",
        ],
    )


def circuit_open(
    provider: str,
    retry_after: float,
    context: ErrorContext = None,
) -> ModelError:
    ctx = context or create_error_context("model_router", "complete")
    ctx.metadata.update({"provider": provider, "circuit_state": "open"})
    return ModelError(
        code=ErrorCode.CIRCUIT_OPEN,
        message=f"Circuit breaker open for {provider}, retry after {retry_after}s",
        context=ctx,
        recoverable=True,
        retry_after=retry_after,
        suggested_actions=[
            f"Wait {retry_after}s for half-open test",
            "Check provider health endpoint",
        ],
    )


def model_timeout(
    provider: str,
    model: str,
    timeout_seconds: float,
    context: ErrorContext = None,
) -> ModelError:
    ctx = context or create_error_context("model_router", "complete")
    ctx.metadata.update({"provider": provider, "model": model, "timeout_seconds": timeout_seconds})
    return ModelError(
        code=ErrorCode.MODEL_TIMEOUT,
        message=f"Model {model} on {provider} timed out after {timeout_seconds}s",
        context=ctx,
        recoverable=True,
        retry_after=10.0,
        suggested_actions=[
            "Retry with shorter prompt",
            "Increase timeout setting",
            "Try fallback provider",
        ],
    )


def token_limit_exceeded(
    provider: str,
    model: str,
    tokens_requested: int,
    tokens_available: int,
    context: ErrorContext = None,
) -> ModelError:
    ctx = context or create_error_context("model_router", "complete")
    ctx.metadata.update({
        "provider": provider,
        "model": model,
        "tokens_requested": tokens_requested,
        "tokens_available": tokens_available,
    })
    return ModelError(
        code=ErrorCode.TOKEN_LIMIT_EXCEEDED,
        message=f"Token limit exceeded: requested {tokens_requested}, available {tokens_available} for {model} on {provider}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Reduce prompt length",
            "Use model with larger context window",
            "Split request into smaller chunks",
        ],
    )


def content_filtered(
    provider: str,
    reason: str,
    context: ErrorContext = None,
) -> ModelError:
    ctx = context or create_error_context("model_router", "complete")
    ctx.metadata.update({"provider": provider, "filter_reason": reason})
    return ModelError(
        code=ErrorCode.CONTENT_FILTERED,
        message=f"Content filtered by {provider}: {reason}",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Review content for policy violations",
            "Modify request to comply with content policy",
        ],
    )


def provider_auth_failed(
    provider: str,
    context: ErrorContext = None,
) -> ModelError:
    ctx = context or create_error_context("model_router", "authenticate")
    ctx.metadata.update({"provider": provider})
    return ModelError(
        code=ErrorCode.PROVIDER_AUTH_FAILED,
        message=f"Authentication failed for provider {provider}",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Verify API key is valid and not expired",
            "Check credential storage",
            "Regenerate API key if needed",
        ],
    )


def provider_rate_limited(
    provider: str,
    retry_after: float,
    context: ErrorContext = None,
) -> ModelError:
    ctx = context or create_error_context("model_router", "complete")
    ctx.metadata.update({"provider": provider, "retry_after": retry_after})
    return ModelError(
        code=ErrorCode.PROVIDER_RATE_LIMITED,
        message=f"Rate limited by {provider}, retry after {retry_after}s",
        context=ctx,
        recoverable=True,
        retry_after=retry_after,
        suggested_actions=[
            f"Wait {retry_after}s before retrying",
            "Implement request batching",
        ],
    )


def wake_word_not_loaded(context: ErrorContext = None) -> VoiceError:
    ctx = context or create_error_context("voice", "detect_wake_word")
    return VoiceError(
        code=ErrorCode.WAKE_WORD_NOT_LOADED,
        message="Wake word model not loaded",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Restart voice pipeline",
            "Check Porcupine model file exists",
            "Verify model license key",
        ],
    )


def asr_failed(
    reason: str,
    audio_duration_ms: float = 0,
    context: ErrorContext = None,
) -> VoiceError:
    ctx = context or create_error_context("voice", "transcribe")
    ctx.metadata.update({"reason": reason, "audio_duration_ms": audio_duration_ms})
    return VoiceError(
        code=ErrorCode.ASR_FAILED,
        message=f"Speech recognition failed: {reason}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Try speaking more clearly",
            "Reduce background noise",
            "Check microphone input level",
            "Fallback to cloud ASR if available",
        ],
    )


def tts_failed(
    reason: str,
    text_length: int = 0,
    context: ErrorContext = None,
) -> VoiceError:
    ctx = context or create_error_context("voice", "synthesize")
    ctx.metadata.update({"reason": reason, "text_length": text_length})
    return VoiceError(
        code=ErrorCode.TTS_FAILED,
        message=f"Text-to-speech failed: {reason}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Try shorter text",
            "Check TTS provider availability",
            "Fallback to alternative TTS engine",
        ],
    )


def session_expired(
    session_id: str,
    context: ErrorContext = None,
) -> VoiceError:
    ctx = context or create_error_context("voice", "session")
    ctx.metadata.update({"session_id": session_id})
    return VoiceError(
        code=ErrorCode.SESSION_EXPIRED,
        message=f"Voice session expired: {session_id}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Start new voice session",
            "Check session timeout settings",
        ],
    )


def audio_device_error(
    device_name: str,
    error: str,
    context: ErrorContext = None,
) -> VoiceError:
    ctx = context or create_error_context("voice", "audio_device")
    ctx.metadata.update({"device_name": device_name, "error": error})
    return VoiceError(
        code=ErrorCode.AUDIO_DEVICE_ERROR,
        message=f"Audio device error ({device_name}): {error}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Check audio device connection",
            "Verify device permissions",
            "Try alternative audio device",
        ],
    )


def voice_pipeline_error(
    stage: str,
    error: str,
    context: ErrorContext = None,
) -> VoiceError:
    ctx = context or create_error_context("voice", "pipeline")
    ctx.metadata.update({"stage": stage, "error": error})
    return VoiceError(
        code=ErrorCode.VOICE_PIPELINE_ERROR,
        message=f"Voice pipeline error at {stage}: {error}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Restart voice pipeline",
            "Check pipeline component logs",
        ],
    )


def barge_in_failed(
    reason: str,
    context: ErrorContext = None,
) -> VoiceError:
    ctx = context or create_error_context("voice", "barge_in")
    ctx.metadata.update({"reason": reason})
    return VoiceError(
        code=ErrorCode.BARGE_IN_FAILED,
        message=f"Barge-in failed: {reason}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Check audio input is not muted",
            "Verify wake word detection is active",
        ],
    )


def memory_store_full(
    kind: str,
    current_count: int,
    max_count: int,
    context: ErrorContext = None,
) -> MemoryError:
    ctx = context or create_error_context("memory", "store")
    ctx.metadata.update({"kind": kind, "current_count": current_count, "max_count": max_count})
    return MemoryError(
        code=ErrorCode.MEMORY_STORE_FULL,
        message=f"Memory store full for {kind} memories: {current_count}/{max_count}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Run consolidation to free space",
            "Increase max_memories_per_kind limit",
            "Delete old/low-confidence memories",
        ],
    )


def pii_detected(
    pii_types: List[str],
    content_preview: str,
    context: ErrorContext = None,
) -> MemoryError:
    ctx = context or create_error_context("memory", "detect_pii")
    ctx.metadata.update({"pii_types": pii_types, "content_preview": content_preview[:100]})
    return MemoryError(
        code=ErrorCode.PII_DETECTED,
        message=f"PII detected in content: {', '.join(pii_types)}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Review and redact PII before storing",
            "Configure PII action: flag, redact, or block",
            "Use memory.governance to handle",
        ],
    )


def memory_not_found(
    memory_id: str,
    context: ErrorContext = None,
) -> MemoryError:
    ctx = context or create_error_context("memory", "retrieve")
    ctx.metadata.update({"memory_id": memory_id})
    return MemoryError(
        code=ErrorCode.MEMORY_NOT_FOUND,
        message=f"Memory not found: {memory_id}",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Verify memory ID is correct",
            "Check if memory was deleted or expired",
        ],
    )


def consolidation_failed(
    kind: str,
    reason: str,
    context: ErrorContext = None,
) -> MemoryError:
    ctx = context or create_error_context("memory", "consolidate")
    ctx.metadata.update({"kind": kind, "reason": reason})
    return MemoryError(
        code=ErrorCode.CONSOLIDATION_FAILED,
        message=f"Consolidation failed for {kind} memories: {reason}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Check consolidation pipeline logs",
            "Verify LLM provider availability",
            "Retry consolidation manually",
        ],
    )


def embedding_failed(
    text_length: int,
    model: str,
    reason: str,
    context: ErrorContext = None,
) -> MemoryError:
    ctx = context or create_error_context("memory", "embed")
    ctx.metadata.update({"text_length": text_length, "model": model, "reason": reason})
    return MemoryError(
        code=ErrorCode.EMBEDDING_FAILED,
        message=f"Embedding failed for {model}: {reason}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Try alternative embedding model",
            "Reduce text length",
            "Check embedding service availability",
        ],
    )


def vector_store_error(
    operation: str,
    reason: str,
    context: ErrorContext = None,
) -> MemoryError:
    ctx = context or create_error_context("memory", "vector_store")
    ctx.metadata.update({"operation": operation, "reason": reason})
    return MemoryError(
        code=ErrorCode.VECTOR_STORE_ERROR,
        message=f"Vector store error ({operation}): {reason}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Check ChromaDB connection",
            "Verify collection exists",
            "Restart vector store service",
        ],
    )


def retention_policy_violation(
    kind: str,
    memory_id: str,
    policy: str,
    context: ErrorContext = None,
) -> MemoryError:
    ctx = context or create_error_context("memory", "retention")
    ctx.metadata.update({"kind": kind, "memory_id": memory_id, "policy": policy})
    return MemoryError(
        code=ErrorCode.RETENTION_POLICY_VIOLATION,
        message=f"Retention policy violation for {kind} memory {memory_id}: {policy}",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Review retention policies",
            "Adjust memory governance settings",
        ],
    )


def agent_unhealthy(
    agent_id: str,
    reason: str,
    context: ErrorContext = None,
) -> AgentError:
    ctx = context or create_error_context("agent", "health_check", agent_id=agent_id)
    ctx.metadata.update({"reason": reason})
    return AgentError(
        code=ErrorCode.AGENT_UNHEALTHY,
        message=f"Agent {agent_id} unhealthy: {reason}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Agent will be restarted automatically",
            "Check agent logs for errors",
            "Verify agent dependencies",
        ],
    )


def agent_timeout(
    agent_id: str,
    timeout_seconds: float,
    context: ErrorContext = None,
) -> AgentError:
    ctx = context or create_error_context("agent", "execute", agent_id=agent_id)
    ctx.metadata.update({"timeout_seconds": timeout_seconds})
    return AgentError(
        code=ErrorCode.AGENT_TIMEOUT,
        message=f"Agent {agent_id} timed out after {timeout_seconds}s",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Increase agent timeout",
            "Check for infinite loops in agent code",
            "Simplify task for agent",
        ],
    )


def verification_failed(
    agent_id: str,
    issues: List[Dict[str, Any]],
    context: ErrorContext = None,
) -> AgentError:
    ctx = context or create_error_context("agent", "verify", agent_id=agent_id)
    ctx.metadata.update({"issues": issues})
    critical = any(i.get("severity") == "critical" for i in issues)
    return AgentError(
        code=ErrorCode.VERIFICATION_FAILED,
        message=f"Verification failed for {agent_id}: {len(issues)} issues",
        context=ctx,
        recoverable=not critical,
        suggested_actions=[
            "Review verification issues",
            "Apply suggested fix if available",
            "Re-run with corrected input",
        ] if not critical else [
            "Critical issue - manual intervention required",
            "Check agent output for security violations",
        ],
    )


def delegation_failed(
    from_agent: str,
    to_agent: str,
    reason: str,
    context: ErrorContext = None,
) -> AgentError:
    ctx = context or create_error_context("agent", "delegate")
    ctx.metadata.update({"from_agent": from_agent, "to_agent": to_agent, "reason": reason})
    return AgentError(
        code=ErrorCode.DELEGATION_FAILED,
        message=f"Delegation failed from {from_agent} to {to_agent}: {reason}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Check target agent health",
            "Verify delegation protocol",
            "Try alternative agent",
        ],
    )


def agent_not_found(
    agent_id: str,
    context: ErrorContext = None,
) -> AgentError:
    ctx = context or create_error_context("agent", "find")
    ctx.metadata.update({"agent_id": agent_id})
    return AgentError(
        code=ErrorCode.AGENT_NOT_FOUND,
        message=f"Agent not found: {agent_id}",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Register agent in registry",
            "Check agent ID spelling",
        ],
    )


def coordinator_unavailable(
    context: ErrorContext = None,
) -> AgentError:
    ctx = context or create_error_context("agent", "coordinator")
    return AgentError(
        code=ErrorCode.COORDINATOR_UNAVAILABLE,
        message="Central coordinator unavailable",
        context=ctx,
        recoverable=True,
        retry_after=5.0,
        suggested_actions=[
            "Wait for coordinator to restart",
            "Check coordinator health endpoint",
        ],
    )


def uia_element_not_found(
    app_name: str,
    selector: Dict[str, Any],
    context: ErrorContext = None,
) -> AutomationError:
    ctx = context or create_error_context("automation", "find_element")
    ctx.metadata.update({"app_name": app_name, "selector": selector})
    return AutomationError(
        code=ErrorCode.UIA_ELEMENT_NOT_FOUND,
        message=f"UIA element not found in {app_name}: {selector}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Verify application is running and visible",
            "Try alternative selector (name, class, automation_id)",
            "Fall back to Playwright or CV/OCR",
            "Increase wait timeout",
        ],
    )


def playwright_navigation_failed(
    url: str,
    reason: str,
    context: ErrorContext = None,
) -> AutomationError:
    ctx = context or create_error_context("automation", "navigate")
    ctx.metadata.update({"url": url, "reason": reason})
    return AutomationError(
        code=ErrorCode.PLAYWRIGHT_NAVIGATION_FAILED,
        message=f"Playwright navigation failed for {url}: {reason}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Check URL is accessible",
            "Verify browser context is valid",
            "Increase navigation timeout",
            "Check for CAPTCHA or login walls",
        ],
    )


def cv_ocr_low_confidence(
    confidence: float,
    threshold: float,
    image_info: str,
    context: ErrorContext = None,
) -> AutomationError:
    ctx = context or create_error_context("automation", "ocr")
    ctx.metadata.update({"confidence": confidence, "threshold": threshold, "image_info": image_info})
    return AutomationError(
        code=ErrorCode.CV_OCR_LOW_CONFIDENCE,
        message=f"OCR confidence {confidence:.2f} below threshold {threshold:.2f} for {image_info}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Improve image quality/lighting",
            "Try alternative OCR engine",
            "Lower confidence threshold if appropriate",
            "Use UIA or Playwright fallback",
        ],
    )


def automation_timeout(
    operation: str,
    timeout_seconds: float,
    context: ErrorContext = None,
) -> AutomationError:
    ctx = context or create_error_context("automation", operation)
    ctx.metadata.update({"timeout_seconds": timeout_seconds})
    return AutomationError(
        code=ErrorCode.AUTOMATION_TIMEOUT,
        message=f"Automation timeout for {operation} after {timeout_seconds}s",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Increase automation timeout",
            "Break operation into smaller steps",
            "Check for blocking UI elements",
        ],
    )


def application_not_found(
    app_name: str,
    context: ErrorContext = None,
) -> AutomationError:
    ctx = context or create_error_context("automation", "find_app")
    ctx.metadata.update({"app_name": app_name})
    return AutomationError(
        code=ErrorCode.APPLICATION_NOT_FOUND,
        message=f"Application not found: {app_name}",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Verify application is installed",
            "Check application name/executable",
            "Start application before automation",
        ],
    )


def permission_denied(
    operation: str,
    resource: str,
    context: ErrorContext = None,
) -> AutomationError:
    ctx = context or create_error_context("automation", operation)
    ctx.metadata.update({"resource": resource})
    return AutomationError(
        code=ErrorCode.PERMISSION_DENIED,
        message=f"Permission denied for {operation} on {resource}",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Run with administrator privileges",
            "Check application permissions",
            "Verify UIA/Playwright access rights",
        ],
    )


def credential_not_found(
    category: str,
    key: str,
    context: ErrorContext = None,
) -> SecurityError:
    ctx = context or create_error_context("security", "get_credential")
    ctx.metadata.update({"category": category, "key": key})
    return SecurityError(
        code=ErrorCode.CREDENTIAL_NOT_FOUND,
        message=f"Credential not found: {category}/{key}",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            f"Store credential via Credential Manager: {category}/{key}",
            "Check credential spelling and case",
            "Verify credential hasn't been deleted",
        ],
    )


def network_blocked(
    destination: str,
    capability: str,
    context: ErrorContext = None,
) -> SecurityError:
    ctx = context or create_error_context("security", "check_egress")
    ctx.metadata.update({"destination": destination, "capability": capability})
    return SecurityError(
        code=ErrorCode.NETWORK_BLOCKED,
        message=f"Network egress blocked to {destination} (requires {capability})",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Add destination to network allow-list",
            "Verify required capability is granted",
            "Check network policy configuration",
        ],
    )


def audit_tampered(
    log_id: str,
    expected_hash: str,
    actual_hash: str,
    context: ErrorContext = None,
) -> SecurityError:
    ctx = context or create_error_context("security", "verify_audit")
    ctx.metadata.update({"log_id": log_id, "expected_hash": expected_hash, "actual_hash": actual_hash})
    return SecurityError(
        code=ErrorCode.AUDIT_TAMPERED,
        message=f"Audit log tampered: {log_id} hash mismatch",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Investigate security breach",
            "Restore from backup",
            "Rotate encryption keys",
        ],
    )


def prompt_injection_detected(
    input_text: str,
    confidence: float,
    context: ErrorContext = None,
) -> SecurityError:
    ctx = context or create_error_context("security", "detect_prompt_injection")
    ctx.metadata.update({"input_preview": input_text[:100], "confidence": confidence})
    return SecurityError(
        code=ErrorCode.PROMPT_INJECTION_DETECTED,
        message=f"Prompt injection detected with confidence {confidence:.2f}",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Block request and log security event",
            "Review input sanitization",
            "Alert security team",
        ],
    )


def encryption_failed(
    operation: str,
    algorithm: str,
    reason: str,
    context: ErrorContext = None,
) -> SecurityError:
    ctx = context or create_error_context("security", "encrypt")
    ctx.metadata.update({"operation": operation, "algorithm": algorithm, "reason": reason})
    return SecurityError(
        code=ErrorCode.ENCRYPTION_FAILED,
        message=f"Encryption {operation} failed ({algorithm}): {reason}",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Check key availability and format",
            "Verify cryptography library",
            "Check system entropy",
        ],
    )


def key_rotation_failed(
    key_id: str,
    reason: str,
    context: ErrorContext = None,
) -> SecurityError:
    ctx = context or create_error_context("security", "rotate_key")
    ctx.metadata.update({"key_id": key_id, "reason": reason})
    return SecurityError(
        code=ErrorCode.KEY_ROTATION_FAILED,
        message=f"Key rotation failed for {key_id}: {reason}",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Check key management service",
            "Verify old key is still valid",
            "Manual rotation required",
        ],
    )


def config_validation_failed(
    config_path: str,
    errors: List[str],
    context: ErrorContext = None,
) -> ConfigurationError:
    ctx = context or create_error_context("config", "validate")
    ctx.metadata.update({"config_path": config_path, "errors": errors})
    return ConfigurationError(
        code=ErrorCode.CONFIG_VALIDATION_FAILED,
        message=f"Configuration validation failed for {config_path}: {len(errors)} errors",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Fix validation errors in config file",
            "Check config schema documentation",
        ],
    )


def secret_not_found(
    secret_key: str,
    context: ErrorContext = None,
) -> ConfigurationError:
    ctx = context or create_error_context("config", "get_secret")
    ctx.metadata.update({"secret_key": secret_key})
    return ConfigurationError(
        code=ErrorCode.SECRET_NOT_FOUND,
        message=f"Secret not found: {secret_key}",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Store secret in configured provider",
            "Check secret key spelling",
            "Verify secret provider is accessible",
        ],
    )


def feature_flag_not_found(
    flag_name: str,
    context: ErrorContext = None,
) -> ConfigurationError:
    ctx = context or create_error_context("config", "get_feature_flag")
    ctx.metadata.update({"flag_name": flag_name})
    return ConfigurationError(
        code=ErrorCode.FEATURE_FLAG_NOT_FOUND,
        message=f"Feature flag not found: {flag_name}",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Register feature flag in config",
            "Check flag name spelling",
        ],
    )


def migration_failed(
    version: str,
    reason: str,
    context: ErrorContext = None,
) -> ConfigurationError:
    ctx = context or create_error_context("config", "migrate")
    ctx.metadata.update({"version": version, "reason": reason})
    return ConfigurationError(
        code=ErrorCode.MIGRATION_FAILED,
        message=f"Config migration {version} failed: {reason}",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Check migration script",
            "Restore from backup",
            "Manually apply migration",
        ],
    )


def event_store_error(
    operation: str,
    reason: str,
    context: ErrorContext = None,
) -> EventError:
    ctx = context or create_error_context("events", "store")
    ctx.metadata.update({"operation": operation, "reason": reason})
    return EventError(
        code=ErrorCode.EVENT_STORE_ERROR,
        message=f"Event store error ({operation}): {reason}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Check event store database connection",
            "Verify event schema",
            "Check disk space",
        ],
    )


def projection_error(
    projection_name: str,
    event_id: str,
    reason: str,
    context: ErrorContext = None,
) -> EventError:
    ctx = context or create_error_context("events", "project")
    ctx.metadata.update({"projection_name": projection_name, "event_id": event_id, "reason": reason})
    return EventError(
        code=ErrorCode.PROJECTION_ERROR,
        message=f"Projection {projection_name} failed for event {event_id}: {reason}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Check projection logic",
            "Verify event data format",
            "Replay projection from checkpoint",
        ],
    )


def dead_letter_queue_full(
    queue_size: int,
    max_size: int,
    context: ErrorContext = None,
) -> EventError:
    ctx = context or create_error_context("events", "dead_letter")
    ctx.metadata.update({"queue_size": queue_size, "max_size": max_size})
    return EventError(
        code=ErrorCode.DEAD_LETTER_QUEUE_FULL,
        message=f"Dead letter queue full: {queue_size}/{max_size}",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Process dead letter events",
            "Increase dead letter queue size",
            "Fix root cause of failures",
        ],
    )


def database_connection_failed(
    database_url: str,
    reason: str,
    context: ErrorContext = None,
) -> DatabaseError:
    ctx = context or create_error_context("database", "connect")
    ctx.metadata.update({"database_url": database_url, "reason": reason})
    return DatabaseError(
        code=ErrorCode.DATABASE_CONNECTION_FAILED,
        message=f"Database connection failed: {reason}",
        context=ctx,
        recoverable=True,
        retry_after=5.0,
        suggested_actions=[
            "Check database server is running",
            "Verify connection string",
            "Check network connectivity",
        ],
    )


def migration_error(
    revision: str,
    reason: str,
    context: ErrorContext = None,
) -> DatabaseError:
    ctx = context or create_error_context("database", "migrate")
    ctx.metadata.update({"revision": revision, "reason": reason})
    return DatabaseError(
        code=ErrorCode.MIGRATION_ERROR,
        message=f"Migration {revision} failed: {reason}",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Check migration script syntax",
            "Verify database state",
            "Run migration manually",
        ],
    )


def constraint_violation(
    constraint: str,
    table: str,
    details: str,
    context: ErrorContext = None,
) -> DatabaseError:
    ctx = context or create_error_context("database", "constraint")
    ctx.metadata.update({"constraint": constraint, "table": table, "details": details})
    return DatabaseError(
        code=ErrorCode.CONSTRAINT_VIOLATION,
        message=f"Constraint violation ({constraint}) on {table}: {details}",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Check data integrity",
            "Verify foreign key references",
            "Check unique constraint values",
        ],
    )


def task_not_found(
    task_id: str,
    context: ErrorContext = None,
) -> TaskError:
    ctx = context or create_error_context("task", "find")
    ctx.metadata.update({"task_id": task_id})
    return TaskError(
        code=ErrorCode.TASK_NOT_FOUND,
        message=f"Task not found: {task_id}",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Verify task ID is correct",
            "Check if task was deleted",
        ],
    )


def task_not_cancellable(
    task_id: str,
    status: str,
    context: ErrorContext = None,
) -> TaskError:
    ctx = context or create_error_context("task", "cancel")
    ctx.metadata.update({"task_id": task_id, "status": status})
    return TaskError(
        code=ErrorCode.TASK_NOT_CANCELLABLE,
        message=f"Task {task_id} cannot be cancelled (status: {status})",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Wait for task to complete",
            "Check task status before cancelling",
        ],
    )


def task_already_completed(
    task_id: str,
    context: ErrorContext = None,
) -> TaskError:
    ctx = context or create_error_context("task", "complete")
    ctx.metadata.update({"task_id": task_id})
    return TaskError(
        code=ErrorCode.TASK_ALREADY_COMPLETED,
        message=f"Task {task_id} already completed",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Check task status before operation",
        ],
    )


def task_dependency_failed(
    task_id: str,
    dependency_id: str,
    reason: str,
    context: ErrorContext = None,
) -> TaskError:
    ctx = context or create_error_context("task", "dependency")
    ctx.metadata.update({"task_id": task_id, "dependency_id": dependency_id, "reason": reason})
    return TaskError(
        code=ErrorCode.TASK_DEPENDENCY_FAILED,
        message=f"Task {task_id} dependency {dependency_id} failed: {reason}",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Retry failed dependency",
            "Check dependency task logs",
            "Resolve dependency issue",
        ],
    )


def task_timeout(
    task_id: str,
    timeout_seconds: float,
    context: ErrorContext = None,
) -> TaskError:
    ctx = context or create_error_context("task", "execute")
    ctx.metadata.update({"task_id": task_id, "timeout_seconds": timeout_seconds})
    return TaskError(
        code=ErrorCode.TASK_TIMEOUT,
        message=f"Task {task_id} timed out after {timeout_seconds}s",
        context=ctx,
        recoverable=True,
        suggested_actions=[
            "Increase task timeout",
            "Check for blocking operations",
            "Break task into smaller steps",
        ],
    )


def task_saga_compensation_failed(
    task_id: str,
    step_name: str,
    reason: str,
    context: ErrorContext = None,
) -> TaskError:
    ctx = context or create_error_context("task", "saga_compensation")
    ctx.metadata.update({"task_id": task_id, "step_name": step_name, "reason": reason})
    return TaskError(
        code=ErrorCode.TASK_SAGA_COMPENSATION_FAILED,
        message=f"Saga compensation failed for task {task_id} at step {step_name}: {reason}",
        context=ctx,
        recoverable=False,
        suggested_actions=[
            "Manual intervention required",
            "Check compensation logic",
            "Review saga execution logs",
        ],
    )