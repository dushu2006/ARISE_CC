"""
Prompt Injection Detection.

Detects prompt injection attacks using:
- Heuristic rules (instruction override, role play, data exfiltration)
- ML model (PropmtGuard/DeBERTa) when available
- Integration points: model router input, agent input, automation input
"""

from __future__ import annotations
import asyncio
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from core.config import load_config
from core.config.models import SecurityConfig, PromptInjectionConfig
from core.structured_logging import get_logger, log_structured

logger = get_logger(__name__)


class InjectionType(str, Enum):
    """Types of prompt injection."""
    INSTRUCTION_OVERRIDE = "instruction_override"
    ROLE_PLAY = "role_play"
    DATA_EXFILTRATION = "data_exfiltration"
    CONTEXT_MANIPULATION = "context_manipulation"
    JAILBREAK = "jailbreak"
    CHAIN_OF_THOUGHT = "chain_of_thought"
    EMOTIONAL_MANIPULATION = "emotional_manipulation"
    AUTHORITY_IMPERSONATION = "authority_impersonation"
    ENCODING_OBFUSCATION = "encoding_obfuscation"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    """Detection severity."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class DetectionResult:
    """Result of prompt injection detection."""
    detected: bool
    injection_type: InjectionType = InjectionType.UNKNOWN
    severity: Severity = Severity.LOW
    confidence: float = 0.0
    matched_patterns: List[str] = None
    details: str = ""
    risk_score: float = 0.0

    def __post_init__(self):
        if self.matched_patterns is None:
            self.matched_patterns = []


class HeuristicDetector:
    """Heuristic-based prompt injection detection."""

    # Patterns for different injection types
    PATTERNS = {
        InjectionType.INSTRUCTION_OVERRIDE: [
            r"(?i)ignore\s+(?:previous|above|all)\s+(?:instructions?|prompts?|rules?)",
            r"(?i)disregard\s+(?:previous|above|all)\s+(?:instructions?|prompts?|rules?)",
            r"(?i)forget\s+(?:previous|above|all)\s+(?:instructions?|prompts?|rules?)",
            r"(?i)new\s+(?:instructions?|prompt|rules?):",
            r"(?i)override\s+(?:previous|above|all)\s+(?:instructions?|prompts?|rules?)",
            r"(?i)system\s*:\s*you\s+are\s+now",
            r"(?i)as\s+an\s+ai\s+(?:assistant|model),?\s+i\s+(?:must|should|will)",
        ],
        InjectionType.ROLE_PLAY: [
            r"(?i)pretend\s+(?:to\s+be|you\s+are)\s+(?:a|an|the)",
            r"(?i)roleplay\s+(?:as|:)",
            r"(?i)act\s+as\s+(?:a|an|the)",
            r"(?i)you\s+are\s+(?:a|an|the)\s+(?:hacker|admin|developer|root|superuser)",
            r"(?i)simulate\s+(?:a|an|the)",
            r"(?i)imagine\s+you\s+are",
            r"(?i)let's\s+play\s+a\s+game",
            r"(?i)in\s+this\s+scenario",
        ],
        InjectionType.DATA_EXFILTRATION: [
            r"(?i)show\s+me\s+(?:your|the)\s+(?:system\s+)?prompt",
            r"(?i)reveal\s+(?:your|the)\s+(?:system\s+)?prompt",
            r"(?i)print\s+(?:your|the)\s+(?:system\s+)?prompt",
            r"(?i)output\s+(?:your|the)\s+(?:system\s+)?prompt",
            r"(?i)what\s+(?:is|are)\s+(?:your|the)\s+(?:instructions?|prompt|rules?)",
            r"(?i)tell\s+me\s+(?:your|the)\s+(?:instructions?|prompt|rules?)",
            r"(?i)repeat\s+(?:your|the)\s+(?:instructions?|prompt|rules?)",
            r"(?i)display\s+(?:your|the)\s+(?:instructions?|prompt|rules?)",
        ],
        InjectionType.CONTEXT_MANIPULATION: [
            r"(?i)context\s*:\s*",
            r"(?i)background\s*:\s*",
            r"(?i)additional\s+(?:context|information)\s*:",
            r"(?i)note\s*:\s*",
            r"(?i)important\s*:\s*",
            r"(?i)please\s+note\s*:",
        ],
        InjectionType.JAILBREAK: [
            r"(?i)dan\s+(?:mode|prompt)",
            r"(?i)do\s+anything\s+now",
            r"(?i)unrestricted\s+(?:mode|ai)",
            r"(?i)no\s+(?:rules?|restrictions?|limits?)",
            r"(?i)free\s+(?:mode|ai)",
            r"(?i)uncensored",
            r"(?i)bypass\s+(?:safety|filters?|restrictions?)",
            r"(?i)evade\s+(?:detection|filters?)",
        ],
        InjectionType.CHAIN_OF_THOUGHT: [
            r"(?i)think\s+step\s+by\s+step",
            r"(?i)reason\s+through\s+this",
            r"(?i)let\s+me\s+think",
            r"(?i)chain\s+of\s+thought",
            r"(?i)internal\s+monologue",
            r"(?i)scratchpad",
        ],
        InjectionType.EMOTIONAL_MANIPULATION: [
            r"(?i)please\s+(?:help|assist)\s+me",
            r"(?i)i\s+(?:need|really\s+need)\s+(?:your\s+)?help",
            r"(?i)it's\s+(?:very\s+)?important",
            r"(?i)urgent",
            r"(?i)desperate",
            r"(?i)i\s+(?:beg|implore)\s+you",
        ],
        InjectionType.AUTHORITY_IMPERSONATION: [
            r"(?i)i\s+am\s+(?:your\s+)?(?:creator|developer|admin|operator)",
            r"(?i)this\s+is\s+(?:a\s+)?(?:test|debug|maintenance)",
            r"(?i)authorized\s+(?:access|personnel)",
            r"(?i)security\s+(?:audit|review|test)",
            r"(?i)as\s+(?:an|the)\s+(?:admin|developer|operator)",
        ],
        InjectionType.ENCODING_OBFUSCATION: [
            r"(?i)base64\s*[:\s]",
            r"(?i)rot13\s*[:\s]",
            r"(?i)encoded\s*[:\s]",
            r"(?i)decode\s+(?:this|the\s+following)",
            r"(?i)\\x[0-9a-f]{2}",  # Hex encoding
            r"(?i)%[0-9a-f]{2}",    # URL encoding
        ],
    }

    def __init__(self, config: Optional[PromptInjectionConfig] = None):
        self.config = config or load_config().security.prompt_injection
        self._compiled_patterns: Dict[InjectionType, List[re.Pattern]] = {}
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile regex patterns."""
        if not self.config.heuristic_rules_enabled:
            return

        for inj_type, patterns in self.PATTERNS.items():
            self._compiled_patterns[inj_type] = [
                re.compile(p) for p in patterns
            ]

    def detect(self, text: str) -> DetectionResult:
        """
        Detect prompt injection using heuristic rules.

        Args:
            text: Text to analyze

        Returns:
            DetectionResult
        """
        if not self.config.heuristic_rules_enabled:
            return DetectionResult(detected=False)

        matched_patterns = []
        max_severity = Severity.LOW
        total_confidence = 0.0
        detected_types = set()

        for inj_type, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                matches = pattern.findall(text)
                if matches:
                    matched_patterns.extend([f"{inj_type.value}: {m}" for m in matches])
                    detected_types.add(inj_type)
                    total_confidence += 0.3  # Each pattern match adds confidence

                    # Update severity based on injection type
                    if inj_type in [InjectionType.INSTRUCTION_OVERRIDE, InjectionType.JAILBREAK, InjectionType.DATA_EXFILTRATION]:
                        max_severity = Severity.CRITICAL
                    elif inj_type in [InjectionType.ROLE_PLAY, InjectionType.AUTHORITY_IMPERSONATION]:
                        max_severity = Severity.HIGH
                    elif inj_type in [InjectionType.CONTEXT_MANIPULATION, InjectionType.CHAIN_OF_THOUGHT]:
                        max_severity = Severity.MEDIUM
                    elif max_severity == Severity.LOW:
                        max_severity = Severity.LOW

        # Determine primary injection type
        primary_type = InjectionType.UNKNOWN
        if detected_types:
            # Priority order
            priority_order = [
                InjectionType.INSTRUCTION_OVERRIDE,
                InjectionType.JAILBREAK,
                InjectionType.DATA_EXFILTRATION,
                InjectionType.ROLE_PLAY,
                InjectionType.AUTHORITY_IMPERSONATION,
                InjectionType.CONTEXT_MANIPULATION,
                InjectionType.CHAIN_OF_THOUGHT,
                InjectionType.EMOTIONAL_MANIPULATION,
                InjectionType.ENCODING_OBFUSCATION,
            ]
            for t in priority_order:
                if t in detected_types:
                    primary_type = t
                    break

        detected = len(matched_patterns) > 0
        confidence = min(total_confidence, 1.0)

        # Calculate risk score
        risk_score = confidence * self._severity_to_score(max_severity)

        return DetectionResult(
            detected=detected,
            injection_type=primary_type,
            severity=max_severity,
            confidence=confidence,
            matched_patterns=matched_patterns[:10],  # Limit to 10
            details=f"Detected {len(matched_patterns)} pattern matches" if detected else "No injection patterns detected",
            risk_score=risk_score,
        )

    def _severity_to_score(self, severity: Severity) -> float:
        """Convert severity to numeric score."""
        mapping = {
            Severity.LOW: 0.25,
            Severity.MEDIUM: 0.5,
            Severity.HIGH: 0.75,
            Severity.CRITICAL: 1.0,
        }
        return mapping.get(severity, 0.0)


class MLDetector:
    """ML-based prompt injection detection (PromptGuard/DeBERTa)."""

    def __init__(self, config: Optional[PromptInjectionConfig] = None):
        self.config = config or load_config().security.prompt_injection
        self._model = None
        self._tokenizer = None
        self._available = False

    async def initialize(self) -> bool:
        """Initialize ML model."""
        if not self.config.enabled:
            return False

        model_name = self.config.model
        if model_name == "promptguard":
            # Try to load Microsoft's PromptGuard or similar
            try:
                from transformers import AutoModelForSequenceClassification, AutoTokenizer
                import torch

                # Use a known prompt injection detection model
                # In production, use microsoft/promptguard or similar
                self._tokenizer = AutoTokenizer.from_pretrained("microsoft/deberta-v3-base")
                self._model = AutoModelForSequenceClassification.from_pretrained("microsoft/deberta-v3-base")
                self._model.eval()
                self._available = True
                log_structured(logger, logging.INFO, "ML prompt injection detector loaded")
                return True
            except Exception as e:
                log_structured(logger, logging.WARNING, "Failed to load ML detector", error=str(e))
                self._available = False
                return False

        return False

    async def detect(self, text: str) -> DetectionResult:
        """Detect using ML model."""
        if not self._available or not self._model:
            return DetectionResult(detected=False)

        try:
            import torch

            # Tokenize
            inputs = self._tokenizer(text, return_tensors="pt", truncation=True, max_length=512)

            # Inference
            with torch.no_grad():
                outputs = self._model(**inputs)
                probs = torch.nn.functional.softmax(outputs.logits, dim=-1)

            # Assuming binary classification: [safe, injection]
            injection_prob = probs[0][1].item() if probs.shape[1] > 1 else 0.0

            detected = injection_prob > 0.5
            severity = Severity.HIGH if injection_prob > 0.8 else Severity.MEDIUM if injection_prob > 0.5 else Severity.LOW

            return DetectionResult(
                detected=detected,
                injection_type=InjectionType.UNKNOWN,
                severity=severity,
                confidence=injection_prob,
                details=f"ML detector confidence: {injection_prob:.2f}",
                risk_score=injection_prob,
            )

        except Exception as e:
            log_structured(logger, logging.ERROR, "ML detection failed", error=str(e))
            return DetectionResult(detected=False)


class PromptInjectionDetector:
    """
    Unified prompt injection detector combining heuristics and ML.
    """

    def __init__(self, config: Optional[PromptInjectionConfig] = None):
        self.config = config or load_config().security.prompt_injection
        self.heuristic_detector = HeuristicDetector(self.config)
        self.ml_detector = MLDetector(self.config)
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize detector."""
        log_structured(logger, logging.INFO, "Initializing Prompt Injection Detector")

        if self.config.enabled:
            await self.ml_detector.initialize()

        self._initialized = True
        log_structured(logger, logging.INFO, "Prompt Injection Detector initialized",
                      heuristics=self.config.heuristic_rules_enabled,
                      ml=self.ml_detector._available)

    def detect(self, text: str, context: Optional[Dict[str, Any]] = None) -> DetectionResult:
        """
        Detect prompt injection in text.

        Args:
            text: Text to analyze
            context: Optional context (integration_point, user_id, etc.)

        Returns:
            DetectionResult
        """
        if not self._initialized:
            # Lazy initialization
            return DetectionResult(detected=False)

        # Run heuristic detection (fast)
        heuristic_result = self.heuristic_detector.detect(text)

        # If heuristic detects high-confidence injection, return early
        if heuristic_result.detected and heuristic_result.confidence > 0.7:
            return heuristic_result

        # Otherwise, could run ML detection asynchronously
        # For now, return heuristic result
        return heuristic_result

    async def detect_async(self, text: str, context: Optional[Dict[str, Any]] = None) -> DetectionResult:
        """
        Async detection with ML model.

        Args:
            text: Text to analyze
            context: Optional context

        Returns:
            DetectionResult
        """
        if not self._initialized:
            await self.initialize()

        # Run heuristic detection
        heuristic_result = self.heuristic_detector.detect(text)

        # Run ML detection if available
        if self.ml_detector._available:
            ml_result = await self.ml_detector.detect(text)

            # Combine results (OR logic with max confidence)
            if ml_result.detected:
                combined = DetectionResult(
                    detected=True,
                    injection_type=ml_result.injection_type if ml_result.injection_type != InjectionType.UNKNOWN else heuristic_result.injection_type,
                    severity=max(heuristic_result.severity, ml_result.severity, key=lambda s: ["low", "medium", "high", "critical"].index(s.value)),
                    confidence=max(heuristic_result.confidence, ml_result.confidence),
                    matched_patterns=heuristic_result.matched_patterns,
                    details=f"Heuristic: {heuristic_result.details}; ML: {ml_result.details}",
                    risk_score=max(heuristic_result.risk_score, ml_result.risk_score),
                )
                return combined

        return heuristic_result

    def check_integration_point(self, text: str, integration_point: str) -> DetectionResult:
        """
        Check text at a specific integration point.

        Args:
            text: Text to check
            integration_point: One of "model_router_input", "agent_input", "automation_input"

        Returns:
            DetectionResult
        """
        if integration_point not in self.config.integration_points:
            return DetectionResult(detected=False, details=f"Integration point not monitored: {integration_point}")

        return self.detect(text, {"integration_point": integration_point})

    async def check_integration_point_async(self, text: str, integration_point: str) -> DetectionResult:
        """Async version of check_integration_point."""
        if integration_point not in self.config.integration_points:
            return DetectionResult(detected=False, details=f"Integration point not monitored: {integration_point}")

        return await self.detect_async(text, {"integration_point": integration_point})


# Global detector instance
_prompt_injection_detector: Optional[PromptInjectionDetector] = None


async def get_prompt_injection_detector() -> Optional[PromptInjectionDetector]:
    """Get the global prompt injection detector instance."""
    return _prompt_injection_detector


async def init_prompt_injection_detector(config: Optional[PromptInjectionConfig] = None) -> PromptInjectionDetector:
    """Initialize the global prompt injection detector."""
    global _prompt_injection_detector
    _prompt_injection_detector = PromptInjectionDetector(config)
    await _prompt_injection_detector.initialize()
    return _prompt_injection_detector


async def shutdown_prompt_injection_detector() -> None:
    """Shutdown the global prompt injection detector."""
    global _prompt_injection_detector
    _prompt_injection_detector = None


__all__ = [
    "PromptInjectionDetector",
    "HeuristicDetector",
    "MLDetector",
    "DetectionResult",
    "InjectionType",
    "Severity",
    "get_prompt_injection_detector",
    "init_prompt_injection_detector",
    "shutdown_prompt_injection_detector",
]