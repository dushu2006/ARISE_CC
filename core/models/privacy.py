"""
Privacy Filter Module for ARISE.

Provides privacy filtering capabilities for requests and responses including:
- PII detection and redaction using Presidio (with regex fallback)
- Privacy mode enforcement (OFF, STANDARD, REDACT, LOCAL_ONLY)
- Audit logging for redaction events
"""

from __future__ import annotations
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import List

from core.config.models import PrivacyMode as ConfigPrivacyMode
from core.models.models import CompletionRequest, Message
from core.structured_logging import get_logger, log_structured

logger = get_logger("arise.privacy")


class PrivacyMode(str, Enum):
    """Privacy mode for request/response filtering."""
    OFF = "off"
    STANDARD = "standard"
    REDACT = "redact"
    LOCAL_ONLY = "local_only"

    @classmethod
    def from_config(cls, mode: ConfigPrivacyMode) -> "PrivacyMode":
        """Convert from config PrivacyMode to this enum."""
        mapping = {
            ConfigPrivacyMode.OFF: cls.OFF,
            ConfigPrivacyMode.STANDARD: cls.STANDARD,
            ConfigPrivacyMode.REDACT: cls.REDACT,
            ConfigPrivacyMode.LOCAL_ONLY: cls.LOCAL_ONLY,
        }
        return mapping.get(mode, cls.STANDARD)


# Presidio availability check
_PRESIDIO_AVAILABLE = False
try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_anonymizer import AnonymizerEngine
    from presidio_anonymizer.entities import OperatorConfig
    _PRESIDIO_AVAILABLE = True
except ImportError:
    _PRESIDIO_AVAILABLE = False
    logger.warning("Presidio not available, using regex fallback for PII detection")


@dataclass
class RedactionEvent:
    """Event representing a PII redaction."""
    entity_type: str
    start: int
    end: int
    original_text: str
    replacement: str
    confidence: float


# Regex patterns for PII detection (fallback when Presidio not available)
PII_PATTERNS = {
    "EMAIL": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
    "PHONE": re.compile(r'(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b'),
    "SSN": re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
    "CREDIT_CARD": re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b'),
    "API_KEY": re.compile(r'(?:sk|pk|api|ghp|ghs|gho|ghu|ghr)[_-][A-Za-z0-9_-]{20,}'),
    "IP_ADDRESS": re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
    "IPV6": re.compile(r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b'),
    "AWS_ACCESS_KEY": re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
    "AWS_SECRET_KEY": re.compile(r'\b[0-9a-zA-Z/+=]{40}\b'),
    "GITHUB_TOKEN": re.compile(r'\bgh[psou]_[A-Za-z0-9]{36}\b'),
    "JWT": re.compile(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b'),
    "PRIVATE_KEY": re.compile(r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----'),
}


class PrivacyFilter:
    """
    Privacy filter for requests and responses.

    Handles PII detection and redaction based on privacy mode:
    - OFF: No filtering
    - STANDARD: Log PII detection but don't modify
    - REDACT: Detect and redact PII
    - LOCAL_ONLY: Force local provider (Ollama) + redact PII
    """

    def __init__(self, mode: PrivacyMode = PrivacyMode.STANDARD):
        """
        Initialize PrivacyFilter.

        Args:
            mode: Privacy mode to use for filtering
        """
        self.mode = mode
        self._analyzer = None
        self._anonymizer = None
        self._init_presidio()

        log_structured(
            logger, logging.INFO,
            "PrivacyFilter initialized",
            mode=mode.value,
            presidio_available=_PRESIDIO_AVAILABLE,
        )

    def _init_presidio(self) -> None:
        """Initialize Presidio engines if available."""
        if _PRESIDIO_AVAILABLE:
            try:
                # Create NLP engine with spaCy
                nlp_provider = NlpEngineProvider(nlp_configuration={
                    "nlp_engine_name": "spacy",
                    "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
                })
                nlp_engine = nlp_provider.create_engine()

                self._analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
                self._anonymizer = AnonymizerEngine()

                log_structured(
                    logger, logging.INFO,
                    "Presidio initialized successfully",
                )
            except Exception as e:
                log_structured(
                    logger, logging.WARNING,
                    "Failed to initialize Presidio, falling back to regex",
                    error=str(e),
                )
                self._analyzer = None
                self._anonymizer = None

    def filter_request(self, request: CompletionRequest) -> CompletionRequest:
        """
        Apply privacy filtering to a completion request.

        Args:
            request: The completion request to filter

        Returns:
            Filtered completion request
        """
        if self.mode == PrivacyMode.OFF:
            return request

        # Create a copy to avoid modifying the original
        filtered_request = CompletionRequest(
            messages=request.messages.copy(),
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            tools=request.tools,
            tool_choice=request.tool_choice,
            response_format=request.response_format,
            stream=request.stream,
            metadata=request.metadata.copy() if request.metadata else None,
            privacy_mode=request.privacy_mode,
        )

        # Filter message content
        filtered_messages = []
        for msg in filtered_request.messages:
            if isinstance(msg.content, str):
                filtered_content, events = self._filter_text(msg.content)
                if events:
                    self._log_redaction_events(events, "request", msg.role)
                filtered_messages.append(Message(
                    role=msg.role,
                    content=filtered_content,
                    name=msg.name,
                    tool_call_id=msg.tool_call_id,
                    tool_calls=msg.tool_calls,
                ))
            else:
                filtered_messages.append(msg)

        filtered_request.messages = filtered_messages

        # Enforce LOCAL_ONLY mode
        if self.mode == PrivacyMode.LOCAL_ONLY:
            filtered_request = self.enforce_local_only(filtered_request)

        return filtered_request

    def filter_response(self, response: str) -> str:
        """
        Filter response text if needed.

        Args:
            response: The response text to filter

        Returns:
            Filtered response text
        """
        if self.mode == PrivacyMode.OFF or self.mode == PrivacyMode.STANDARD:
            return response

        filtered, events = self._filter_text(response)
        if events:
            self._log_redaction_events(events, "response", "assistant")

        return filtered

    def redact_pii(self, text: str) -> str:
        """
        Redact PII from text using Presidio or regex fallback.

        Args:
            text: Text to redact

        Returns:
            Text with PII redacted
        """
        redacted, _ = self._filter_text(text)
        return redacted

    def enforce_local_only(self, request: CompletionRequest) -> CompletionRequest:
        """
        Force provider to Ollama for LOCAL_ONLY mode.

        Args:
            request: The completion request

        Returns:
            Request with model set to Ollama
        """
        # Check if model is already Ollama
        if request.model and "ollama" in request.model.lower():
            return request

        # Create new request with ollama model
        local_request = CompletionRequest(
            messages=request.messages.copy(),
            model="ollama/llama3.1",  # Default Ollama model
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            tools=request.tools,
            tool_choice=request.tool_choice,
            response_format=request.response_format,
            stream=request.stream,
            metadata=request.metadata.copy() if request.metadata else None,
            privacy_mode=PrivacyMode.LOCAL_ONLY,
        )

        log_structured(
            logger, logging.INFO,
            "LOCAL_ONLY mode enforced, provider changed to Ollama",
            original_model=request.model,
            new_model=local_request.model,
        )

        return local_request

    def _filter_text(self, text: str) -> tuple[str, List[RedactionEvent]]:
        """
        Filter text for PII using Presidio or regex.

        Args:
            text: Text to filter

        Returns:
            Tuple of (filtered_text, redaction_events)
        """
        if self._analyzer and self._anonymizer:
            return self._filter_with_presidio(text)
        else:
            return self._filter_with_regex(text)

    def _filter_with_presidio(self, text: str) -> tuple[str, List[RedactionEvent]]:
        """Filter text using Presidio analyzer and anonymizer."""
        events = []

        # Analyze text for PII
        results = self._analyzer.analyze(
            text=text,
            language="en",
            return_decision_process=False,
        )

        if not results:
            return text, events

        # Define operators for anonymization
        operators = {
            "DEFAULT": OperatorConfig("replace", {"new_value": "[REDACTED]"}),
            "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[EMAIL]"}),
            "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[PHONE]"}),
            "US_SSN": OperatorConfig("replace", {"new_value": "[SSN]"}),
            "CREDIT_CARD": OperatorConfig("replace", {"new_value": "[CREDIT_CARD]"}),
            "IP_ADDRESS": OperatorConfig("replace", {"new_value": "[IP]"}),
            "API_KEY": OperatorConfig("replace", {"new_value": "[API_KEY]"}),
            "AWS_ACCESS_KEY": OperatorConfig("replace", {"new_value": "[AWS_KEY]"}),
            "AWS_SECRET_KEY": OperatorConfig("replace", {"new_value": "[AWS_SECRET]"}),
        }

        # Anonymize
        anonymized = self._anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=operators,
        )

        # Create redaction events
        for result in results:
            original = text[result.start:result.end]
            entity_type = result.entity_type
            replacement = operators.get(entity_type, operators["DEFAULT"]).params["new_value"]

            events.append(RedactionEvent(
                entity_type=entity_type,
                start=result.start,
                end=result.end,
                original_text=original,
                replacement=replacement,
                confidence=result.score,
            ))

        return anonymized.text, events

    def _filter_with_regex(self, text: str) -> tuple[str, List[RedactionEvent]]:
        """Filter text using regex patterns (fallback)."""
        events = []
        filtered_text = text

        # Track offsets due to replacements
        offset = 0

        for entity_type, pattern in PII_PATTERNS.items():
            for match in pattern.finditer(text):
                start, end = match.span()
                original = match.group()

                # Determine replacement based on entity type
                replacements = {
                    "EMAIL": "[EMAIL]",
                    "PHONE": "[PHONE]",
                    "SSN": "[SSN]",
                    "CREDIT_CARD": "[CREDIT_CARD]",
                    "API_KEY": "[API_KEY]",
                    "IP_ADDRESS": "[IP]",
                    "IPV6": "[IP]",
                    "AWS_ACCESS_KEY": "[AWS_KEY]",
                    "AWS_SECRET_KEY": "[AWS_SECRET]",
                    "GITHUB_TOKEN": "[GITHUB_TOKEN]",
                    "JWT": "[JWT]",
                    "PRIVATE_KEY": "[PRIVATE_KEY]",
                }
                replacement = replacements.get(entity_type, "[REDACTED]")

                # Adjust positions for previous replacements
                adjusted_start = start + offset
                adjusted_end = end + offset

                # Replace in filtered text
                filtered_text = (
                    filtered_text[:adjusted_start] +
                    replacement +
                    filtered_text[adjusted_end:]
                )

                # Update offset
                offset += len(replacement) - len(original)

                events.append(RedactionEvent(
                    entity_type=entity_type,
                    start=start,
                    end=end,
                    original_text=original,
                    replacement=replacement,
                    confidence=0.8,  # Default confidence for regex
                ))

        return filtered_text, events

    def _log_redaction_events(
        self,
        events: List[RedactionEvent],
        context: str,
        role: str
    ) -> None:
        """Log redaction events for audit."""
        for event in events:
            log_structured(
                logger, logging.INFO,
                "PII redaction applied",
                context=context,
                role=role,
                entity_type=event.entity_type,
                original_length=len(event.original_text),
                replacement=event.replacement,
                confidence=event.confidence,
                privacy_mode=self.mode.value,
            )


# Convenience function for quick access
def create_privacy_filter(mode: PrivacyMode = PrivacyMode.STANDARD) -> PrivacyFilter:
    """Create a PrivacyFilter instance."""
    return PrivacyFilter(mode=mode)


if __name__ == "__main__":
    # Test the privacy filter
    from core.structured_logging import setup_logging

    setup_logging(level="DEBUG", json_output=True)

    # Test with different modes
    print("=== Testing PrivacyFilter ===\n")

    test_text = """
    Contact John at john.doe@example.com or call 555-123-4567.
    His SSN is 123-45-6789 and credit card is 4111-1111-1111-1111.
    API key: sk-test-abcdefghijklmnopqrstuvwxyz123456
    AWS key: AKIAIOSFODNN7EXAMPLE
    """

    for mode in PrivacyMode:
        print(f"\n--- Mode: {mode.value} ---")
        filter = PrivacyFilter(mode=mode)

        if mode != PrivacyMode.OFF:
            # Test redaction
            redacted = filter.redact_pii(test_text)
            print(f"Original: {test_text.strip()}")
            print(f"Redacted: {redacted.strip()}")
        else:
            print("No filtering applied")

    # Test request filtering
    print("\n=== Testing Request Filtering ===")
    request = CompletionRequest(
        messages=[
            Message(role="user", content="My email is test@example.com and phone is 555-0199"),
            Message(role="assistant", content="I'll help you with that."),
        ],
        model="gpt-4",
        privacy_mode=PrivacyMode.REDACT,
    )

    filter = PrivacyFilter(mode=PrivacyMode.REDACT)
    filtered = filter.filter_request(request)
    print(f"Original: {request.messages[0].content}")
    print(f"Filtered: {filtered.messages[0].content}")

    # Test LOCAL_ONLY enforcement
    print("\n=== Testing LOCAL_ONLY Mode ===")
    local_filter = PrivacyFilter(mode=PrivacyMode.LOCAL_ONLY)
    local_request = local_filter.filter_request(request)
    print(f"Original model: {request.model}")
    print(f"Local model: {local_request.model}")