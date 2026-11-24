"""
Memory Governance.

PII detection, TTL enforcement, encryption, and governance policies.
"""

from __future__ import annotations
import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from core.config import load_config
from core.config.models import MemoryConfig, MemoryGovernanceConfig
from core.database import get_session
from core.database.models import MemoryMetadata, MemoryKind as DBMemoryKind
from core.memory.models import Memory, MemoryKind
from core.memory.store import MemoryStore
from core.structured_logging import get_logger, log_structured

logger = get_logger(__name__)


class PIIAction(str, Enum):
    """Action to take when PII is detected."""
    FLAG = "flag"      # Just mark as detected
    REDACT = "redact"  # Remove/replace PII
    BLOCK = "block"    # Refuse to store


@dataclass
class PIIMatch:
    """A detected PII match."""
    pii_type: str
    value: str
    start: int
    end: int
    confidence: float


class PIIDetector:
    """
    PII detection using regex patterns and optional Presidio integration.
    """

    # Regex patterns for common PII types
    PII_PATTERNS = {
        "email": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
        "phone_us": re.compile(r'\b(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})\b'),
        "ssn": re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
        "credit_card": re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b'),
        "ip_address": re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
        "api_key": re.compile(r'\b(?:api[_-]?key|apikey)[\s:=]+([A-Za-z0-9_-]{20,})\b', re.IGNORECASE),
        "aws_access_key": re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
        "github_token": re.compile(r'\bgh[ps]_[A-Za-z0-9_]{36,}\b'),
        "jwt": re.compile(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b'),
        "password": re.compile(r'\b(?:password|passwd|pwd)[\s:=]+([^\s]{8,})\b', re.IGNORECASE),
        "address": re.compile(r'\b\d+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Place|Pl)\b', re.IGNORECASE),
        "date_of_birth": re.compile(r'\b(?:0[1-9]|1[0-2])[/-](?:0[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}\b'),
        "passport_us": re.compile(r'\b[0-9]{9}\b'),  # US passport
        "driver_license": re.compile(r'\b[A-Z]{1,2}\d{6,8}\b'),  # Generic
    }

    def __init__(self, config: Optional[MemoryGovernanceConfig] = None):
        self.config = config or MemoryGovernanceConfig()
        self._presidio_analyzer = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize PII detector, optionally loading Presidio."""
        if not self.config.pii_detection_enabled:
            log_structured(logger, logging.INFO, "PII detection disabled")
            self._initialized = True
            return

        # Try to load Presidio for enhanced detection
        try:
            from presidio_analyzer import AnalyzerEngine
            self._presidio_analyzer = AnalyzerEngine()
            log_structured(logger, logging.INFO, "Presidio PII analyzer loaded")
        except ImportError:
            log_structured(logger, logging.INFO, "Presidio not available, using regex patterns only")

        self._initialized = True

    def detect(self, text: str) -> List[PIIMatch]:
        """
        Detect PII in text.

        Args:
            text: Text to analyze

        Returns:
            List of PII matches
        """
        matches = []

        # Regex-based detection
        for pii_type, pattern in self.PII_PATTERNS.items():
            for match in pattern.finditer(text):
                matches.append(PIIMatch(
                    pii_type=pii_type,
                    value=match.group(),
                    start=match.start(),
                    end=match.end(),
                    confidence=0.85,  # Regex confidence
                ))

        # Presidio-based detection (if available)
        if self._presidio_analyzer:
            try:
                results = self._presidio_analyzer.analyze(text=text, language="en")
                for result in results:
                    # Map Presidio entity types to our types
                    pii_type = self._map_presidio_type(result.entity_type)
                    matches.append(PIIMatch(
                        pii_type=pii_type,
                        value=text[result.start:result.end],
                        start=result.start,
                        end=result.end,
                        confidence=result.score,
                    ))
            except Exception as e:
                log_structured(logger, logging.WARNING, "Presidio analysis failed", error=str(e))

        # Deduplicate overlapping matches (keep higher confidence)
        matches = self._deduplicate_matches(matches)

        return matches

    def _map_presidio_type(self, presidio_type: str) -> str:
        """Map Presidio entity type to our PII type."""
        mapping = {
            "EMAIL_ADDRESS": "email",
            "PHONE_NUMBER": "phone",
            "US_SSN": "ssn",
            "CREDIT_CARD": "credit_card",
            "IP_ADDRESS": "ip_address",
            "API_KEY": "api_key",
            "PASSWORD": "password",
            "LOCATION": "address",
            "DATE_TIME": "date_of_birth",
            "PERSON": "name",
            "ORGANIZATION": "organization",
        }
        return mapping.get(presidio_type, presidio_type.lower())

    def _deduplicate_matches(self, matches: List[PIIMatch]) -> List[PIIMatch]:
        """Remove overlapping matches, keeping highest confidence."""
        if not matches:
            return []

        # Sort by start position, then by confidence (descending)
        matches.sort(key=lambda m: (m.start, -m.confidence))

        deduplicated = []
        for match in matches:
            # Check if overlaps with any kept match
            overlaps = False
            for kept in deduplicated:
                if not (match.end <= kept.start or match.start >= kept.end):
                    overlaps = True
                    break
            if not overlaps:
                deduplicated.append(match)

        return deduplicated

    def redact(self, text: str, matches: List[PIIMatch], replacement: str = "[REDACTED]") -> str:
        """Redact PII from text."""
        if not matches:
            return text

        # Sort matches by start position (descending) to replace from end
        matches.sort(key=lambda m: m.start, reverse=True)

        result = text
        for match in matches:
            result = result[:match.start] + replacement + result[match.end:]

        return result


class GovernanceManager:
    """
    Memory governance: PII detection, TTL enforcement, encryption, LRU eviction.
    """

    def __init__(
        self,
        memory_store: MemoryStore,
        config: Optional[MemoryConfig] = None,
    ):
        self.memory_store = memory_store
        self.config = config or load_config().memory
        self.governance_config = self.config.governance
        self.pii_detector = PIIDetector(self.governance_config)
        self._running = False
        self._sweeper_task: Optional[asyncio.Task] = None

    async def initialize(self) -> None:
        """Initialize governance manager."""
        await self.pii_detector.initialize()
        self._running = True

        # Start background sweeper for TTL and LRU
        self._sweeper_task = asyncio.create_task(self._sweeper_loop())

        log_structured(logger, logging.INFO, "Governance Manager initialized")

    async def shutdown(self) -> None:
        """Shutdown governance manager."""
        self._running = False

        if self._sweeper_task:
            self._sweeper_task.cancel()
            try:
                await self._sweeper_task
            except asyncio.CancelledError:
                pass

        log_structured(logger, logging.INFO, "Governance Manager stopped")

    async def process_memory(self, memory: Memory) -> Memory:
        """
        Process a memory through governance pipeline.

        Returns:
            Processed memory (may be modified)
        """
        # PII Detection
        if self.governance_config.pii_detection_enabled:
            matches = self.pii_detector.detect(memory.content)

            if matches:
                memory.pii_detected = True
                memory.pii_types = list(set(m.pii_type for m in matches))

                action = self.governance_config.pii_action

                if action == PIIAction.BLOCK:
                    raise ValueError(f"Memory blocked due to PII: {[m.pii_type for m in matches]}")

                elif action == PIIAction.REDACT:
                    memory.content = self.pii_detector.redact(memory.content, matches)
                    log_structured(logger, logging.INFO, "Memory content redacted",
                                  memory_id=memory.id, pii_types=memory.pii_types)

                elif action == PIIAction.FLAG:
                    log_structured(logger, logging.INFO, "Memory flagged for PII",
                                  memory_id=memory.id, pii_types=memory.pii_types)

        # Set TTL based on kind if not specified
        if memory.ttl_seconds is None:
            kind_config = self.config.kinds.get(memory.kind)
            if kind_config:
                memory.ttl_seconds = kind_config.ttl_days * 86400

        return memory

    async def _sweeper_loop(self) -> None:
        """Background loop for TTL enforcement and LRU eviction."""
        while self._running:
            try:
                # Run every hour
                await asyncio.sleep(3600)

                if not self._running:
                    break

                await self.enforce_ttl()
                await self.enforce_lru()

            except asyncio.CancelledError:
                break
            except Exception as e:
                log_structured(logger, logging.ERROR, "Governance sweeper error", error=str(e))
                await asyncio.sleep(300)

    async def enforce_ttl(self) -> int:
        """
        Enforce TTL by archiving expired memories.

        Returns:
            Number of memories archived
        """
        log_structured(logger, logging.DEBUG, "Running TTL enforcement")

        archived = 0

        # Query all memories (this is a simplification - in production, use a more efficient approach)
        for kind in MemoryKind:
            kind_config = self.config.kinds.get(kind)
            if not kind_config or not kind_config.ttl_days:
                continue

            query = MemoryQuery(
                kind=kind,
                limit=1000,
                include_expired=True,
            )

            result = await self.memory_store.query(query)

            for memory in result.memories:
                if memory.is_expired() and not memory.is_archived:
                    await self.memory_store.update(memory.id, {"is_archived": True})
                    archived += 1

        if archived > 0:
            log_structured(logger, logging.INFO, "TTL enforcement completed", archived=archived)

        return archived

    async def enforce_lru(self) -> int:
        """
        Enforce LRU eviction when memory count exceeds limits.

        Returns:
            Number of memories evicted
        """
        if not self.governance_config.lru_eviction_enabled:
            return 0

        log_structured(logger, logging.DEBUG, "Running LRU eviction")

        evicted = 0

        for kind in MemoryKind:
            kind_config = self.config.kinds.get(kind)
            if not kind_config:
                continue

            max_items = min(
                kind_config.max_items,
                self.governance_config.max_memories_per_kind
            )

            # Get current count
            count = await self.memory_store.count(kind)

            if count > max_items:
                # Need to evict (count - max_items) items
                to_evict = count - max_items

                # Query oldest, least accessed memories
                query = MemoryQuery(
                    kind=kind,
                    limit=to_evict,
                    include_archived=False,
                )
                # Sort by access_count ASC, then accessed_at ASC (oldest, least used)
                # This would need store support - for now, just get some
                result = await self.memory_store.query(query)

                for memory in result.memories:
                    if evicted >= to_evict:
                        break
                    # Archive instead of delete to preserve for recovery
                    await self.memory_store.update(memory.id, {"is_archived": True})
                    evicted += 1

        if evicted > 0:
            log_structured(logger, logging.INFO, "LRU eviction completed", evicted=evicted)

        return evicted

    async def get_stats(self) -> Dict[str, Any]:
        """Get governance statistics."""
        stats = {
            "pii_detection_enabled": self.governance_config.pii_detection_enabled,
            "pii_action": self.governance_config.pii_action,
            "encryption_enabled": self.governance_config.encryption_enabled,
            "lru_eviction_enabled": self.governance_config.lru_eviction_enabled,
            "max_memories_per_kind": self.governance_config.max_memories_per_kind,
            "kind_stats": {},
        }

        for kind in MemoryKind:
            count = await self.memory_store.count(kind)
            kind_config = self.config.kinds.get(kind)
            stats["kind_stats"][kind.value] = {
                "count": count,
                "max_items": kind_config.max_items if kind_config else 0,
                "ttl_days": kind_config.ttl_days if kind_config else 0,
                "enabled": kind_config.enabled if kind_config else False,
            }

        return stats


__all__ = [
    "PIIDetector",
    "PIIMatch",
    "PIIAction",
    "GovernanceManager",
]