"""
Memory Consolidation Pipeline.

Scheduled consolidation jobs:
- Working → Episodic promotion (every 6 hours)
- Episodic → Semantic abstraction (LLM-based, every 6 hours)
- Preference extraction from patterns (every 24 hours)
- Procedural skill learning from repetitions (every 24 hours)
- Conflict resolution (timestamp + confidence)
"""

from __future__ import annotations
import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from core.config import load_config
from core.config.models import MemoryConfig, ConsolidationConfig as ConfigConsolidationConfig
from core.database import get_session
from core.database.models import ConsolidationRun, MemoryKind as DBMemoryKind, MemorySource as DBMemorySource, MemoryMetadata
from core.memory.models import Memory, MemoryKind, MemorySource, MemoryQuery, ConsolidationResult
from core.memory.store import MemoryStore, create_memory_store
from core.models.engine import get_model_router, TaskType
from core.models.models import CompletionRequest, Message
from core.structured_logging import get_logger, log_structured

logger = get_logger(__name__)


@dataclass
class ConsolidationConfig:
    """Consolidation configuration."""
    enabled: bool = True
    interval_hours: int = 6
    working_to_episodic_threshold: float = 0.7
    episodic_to_semantic_threshold: float = 0.8
    preference_extraction_enabled: bool = True
    procedural_learning_enabled: bool = True
    batch_size: int = 100
    max_concurrent: int = 2


class ConsolidationPipeline:
    """
    Memory consolidation pipeline.

    Runs scheduled consolidation jobs:
    1. Working → Episodic: Promote frequently accessed working memories
    2. Episodic → Semantic: Abstract patterns into semantic knowledge
    3. Preference Extraction: Learn user preferences from patterns
    4. Procedural Learning: Extract skills from repeated procedures
    """

    def __init__(
        self,
        memory_store: MemoryStore,
        config: Optional[ConsolidationConfig] = None,
        model_router_config: Optional[MemoryConfig] = None,
    ):
        self.memory_store = memory_store
        self.config = config or ConsolidationConfig()
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._shutdown_event = asyncio.Event()

        # Load app config for model router
        self._app_config = load_config()
        self._model_router = None

    async def initialize(self) -> None:
        """Initialize the consolidation pipeline."""
        log_structured(logger, logging.INFO, "Initializing Consolidation Pipeline")

        # Initialize model router
        try:
            self._model_router = await get_model_router()
        except Exception as e:
            log_structured(logger, logging.WARNING, "Model router not available for consolidation", error=str(e))

        self._running = True

        # Start scheduled consolidation loop
        task = asyncio.create_task(self._consolidation_loop())
        self._tasks.append(task)

        log_structured(logger, logging.INFO, "Consolidation Pipeline started")

    async def shutdown(self) -> None:
        """Shutdown the consolidation pipeline."""
        log_structured(logger, logging.INFO, "Shutting down Consolidation Pipeline")
        self._running = False
        self._shutdown_event.set()

        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()

        log_structured(logger, logging.INFO, "Consolidation Pipeline stopped")

    async def _consolidation_loop(self) -> None:
        """Main consolidation loop."""
        while self._running:
            try:
                await asyncio.sleep(self.config.interval_hours * 3600)

                if not self._running:
                    break

                await self.run_consolidation()

            except asyncio.CancelledError:
                break
            except Exception as e:
                log_structured(logger, logging.ERROR, "Consolidation loop error", error=str(e))
                await asyncio.sleep(300)  # Wait 5 min before retry

    async def run_consolidation(self, kind: Optional[str] = None) -> List[ConsolidationResult]:
        """
        Run consolidation for all kinds or a specific kind.

        Args:
            kind: Specific consolidation kind to run, or None for all

        Returns:
            List of consolidation results
        """
        results = []

        if kind is None or kind == "working_to_episodic":
            result = await self._working_to_episodic()
            results.append(result)

        if kind is None or kind == "episodic_to_semantic":
            result = await self._episodic_to_semantic()
            results.append(result)

        if kind is None or kind == "preference_extraction":
            result = await self._extract_preferences()
            results.append(result)

        if kind is None or kind == "procedural_learning":
            result = await self._learn_procedures()
            results.append(result)

        return results

    async def _working_to_episodic(self) -> ConsolidationResult:
        """Promote working memories to episodic based on access patterns."""
        start = datetime.now(timezone.utc)
        kind = "working_to_episodic"

        log_structured(logger, logging.INFO, "Starting working→episodic consolidation")

        try:
            # Query working memories with high access count
            query = MemoryQuery(
                kind=MemoryKind.WORKING,
                limit=self.config.batch_size,
                filters={"access_count": {"$gte": 3}},
                min_confidence=self.config.working_to_episodic_threshold,
            )

            result = await self.memory_store.query(query)

            promoted = 0
            for memory in result.memories:
                # Check if should promote
                if memory.access_count >= 3 and memory.confidence >= self.config.working_to_episodic_threshold:
                    # Create episodic memory
                    episodic_memory = Memory(
                        kind=MemoryKind.EPISODIC,
                        content=memory.content,
                        embedding=memory.embedding,
                        confidence=memory.confidence,
                        metadata={
                            **memory.metadata,
                            "promoted_from": "working",
                            "original_id": memory.id,
                            "access_count_at_promotion": memory.access_count,
                        },
                        tags=memory.tags + ["promoted"],
                        source=MemorySource.CONSOLIDATION,
                        ttl_seconds=memory.ttl_seconds or 86400 * 365,  # 1 year default
                    )

                    await self.memory_store.store(episodic_memory)

                    # Archive original working memory
                    await self.memory_store.update(memory.id, {"is_archived": True})

                    promoted += 1

            duration = (datetime.now(timezone.utc) - start).total_seconds()

            # Record consolidation run
            await self._record_consolidation_run(
                kind=kind,
                input_count=len(result.memories),
                output_count=promoted,
                status="completed",
                duration_seconds=duration,
            )

            log_structured(logger, logging.INFO, "Working→episodic consolidation completed",
                          input=len(result.memories), promoted=promoted, duration=duration)

            return ConsolidationResult(
                kind=kind,
                input_count=len(result.memories),
                output_count=promoted,
                status="completed",
                duration_seconds=duration,
            )

        except Exception as e:
            duration = (datetime.now(timezone.utc) - start).total_seconds()
            log_structured(logger, logging.ERROR, "Working→episodic consolidation failed", error=str(e))

            await self._record_consolidation_run(
                kind=kind,
                input_count=0,
                output_count=0,
                status="failed",
                error=str(e),
                duration_seconds=duration,
            )

            return ConsolidationResult(
                kind=kind,
                input_count=0,
                output_count=0,
                status="failed",
                error=str(e),
                duration_seconds=duration,
            )

    async def _episodic_to_semantic(self) -> ConsolidationResult:
        """Abstract episodic memories into semantic knowledge using LLM."""
        start = datetime.now(timezone.utc)
        kind = "episodic_to_semantic"

        log_structured(logger, logging.INFO, "Starting episodic→semantic consolidation")

        if not self._model_router:
            return ConsolidationResult(
                kind=kind,
                input_count=0,
                output_count=0,
                status="skipped",
                error="Model router not available",
                duration_seconds=0,
            )

        try:
            # Query episodic memories ready for abstraction
            query = MemoryQuery(
                kind=MemoryKind.EPISODIC,
                limit=self.config.batch_size,
                filters={"metadata.promoted_from": "working"},
                min_confidence=self.config.episodic_to_semantic_threshold,
            )

            result = await self.memory_store.query(query)

            if not result.memories:
                return ConsolidationResult(
                    kind=kind,
                    input_count=0,
                    output_count=0,
                    status="completed",
                    duration_seconds=(datetime.now(timezone.utc) - start).total_seconds(),
                )

            # Group memories by theme/topic for batch processing
            grouped = self._group_by_theme(result.memories)

            created = 0
            for theme, memories in grouped.items():
                if len(memories) < 2:
                    continue  # Need at least 2 to abstract

                # Use LLM to extract semantic knowledge
                semantic_content = await self._extract_semantic_knowledge(memories, theme)
                if not semantic_content:
                    continue

                # Create semantic memory
                semantic_memory = Memory(
                    kind=MemoryKind.SEMANTIC,
                    content=semantic_content,
                    confidence=sum(m.confidence for m in memories) / len(memories),
                    metadata={
                        "extracted_from": "episodic",
                        "source_memory_ids": [m.id for m in memories],
                        "theme": theme,
                        "memory_count": len(memories),
                    },
                    tags=["extracted", theme],
                    source=MemorySource.CONSOLIDATION,
                    ttl_seconds=86400 * 3650,  # 10 years
                )

                await self.memory_store.store(semantic_memory)
                created += 1

                # Optionally archive source episodic memories
                for m in memories:
                    await self.memory_store.update(m.id, {"is_archived": True})

            duration = (datetime.now(timezone.utc) - start).total_seconds()

            await self._record_consolidation_run(
                kind=kind,
                input_count=len(result.memories),
                output_count=created,
                status="completed",
                duration_seconds=duration,
            )

            log_structured(logger, logging.INFO, "Episodic→semantic consolidation completed",
                          input=len(result.memories), created=created, duration=duration)

            return ConsolidationResult(
                kind=kind,
                input_count=len(result.memories),
                output_count=created,
                status="completed",
                duration_seconds=duration,
            )

        except Exception as e:
            duration = (datetime.now(timezone.utc) - start).total_seconds()
            log_structured(logger, logging.ERROR, "Episodic→semantic consolidation failed", error=str(e))

            await self._record_consolidation_run(
                kind=kind,
                input_count=0,
                output_count=0,
                status="failed",
                error=str(e),
                duration_seconds=duration,
            )

            return ConsolidationResult(
                kind=kind,
                input_count=0,
                output_count=0,
                status="failed",
                error=str(e),
                duration_seconds=duration,
            )

    def _group_by_theme(self, memories: List[Memory]) -> Dict[str, List[Memory]]:
        """Group memories by theme using tags or content similarity."""
        grouped = {}

        for memory in memories:
            # Use first tag as theme, or derive from content
            theme = memory.tags[0] if memory.tags else "general"

            # Simple keyword-based grouping
            content_lower = memory.content.lower()
            if any(kw in content_lower for kw in ["code", "function", "api", "programming"]):
                theme = "programming"
            elif any(kw in content_lower for kw in ["meeting", "schedule", "calendar", "appointment"]):
                theme = "scheduling"
            elif any(kw in content_lower for kw in ["prefer", "like", "dislike", "want"]):
                theme = "preferences"

            if theme not in grouped:
                grouped[theme] = []
            grouped[theme].append(memory)

        return grouped

    async def _extract_semantic_knowledge(self, memories: List[Memory], theme: str) -> Optional[str]:
        """Use LLM to extract semantic knowledge from episodic memories."""
        if not self._model_router:
            return None

        # Build prompt
        memory_texts = "\n\n".join([f"- {m.content}" for m in memories[:10]])

        prompt = f"""Extract a concise, generalizable piece of knowledge from these related memories about {theme}:

{memories}

Provide a single, clear statement that captures the common pattern or principle. Focus on facts, rules, or concepts that can be applied broadly."""

        try:
            request = CompletionRequest(
                messages=[Message(role="user", content=prompt)],
                model=None,  # Let router choose
                temperature=0.3,
                max_tokens=500,
                stream=False,
            )

            response = await self._model_router.complete(
                task_type=TaskType.ANALYSIS,
                request=request,
            )

            if response.choices and response.choices[0].message.content:
                return response.choices[0].message.content.strip()

        except Exception as e:
            log_structured(logger, logging.WARNING, "LLM extraction failed", error=str(e))

        return None

    async def _extract_preferences(self) -> ConsolidationResult:
        """Extract user preferences from memory patterns."""
        start = datetime.now(timezone.utc)
        kind = "preference_extraction"

        if not self.config.preference_extraction_enabled:
            return ConsolidationResult(kind=kind, input_count=0, output_count=0, status="disabled")

        log_structured(logger, logging.INFO, "Starting preference extraction")

        try:
            # Query episodic and working memories with preference indicators
            query = MemoryQuery(
                kinds=[MemoryKind.EPISODIC, MemoryKind.WORKING],
                limit=self.config.batch_size,
                filters={"tags": {"$in": ["preference", "prefer", "like", "dislike"]}},
            )

            result = await self.memory_store.query(query)

            created = 0
            for memory in result.memories:
                # Extract preference using simple heuristics
                pref = self._extract_preference_from_memory(memory)
                if pref:
                    pref_memory = Memory(
                        kind=MemoryKind.PREFERENCE,
                        content=pref,
                        confidence=memory.confidence * 0.9,  # Slightly lower confidence
                        metadata={
                            "extracted_from": memory.kind.value,
                            "source_memory_id": memory.id,
                        },
                        tags=["extracted", "preference"],
                        source=MemorySource.CONSOLIDATION,
                        ttl_seconds=86400 * 3650,
                    )

                    await self.memory_store.store(pref_memory)
                    created += 1

            duration = (datetime.now(timezone.utc) - start).total_seconds()

            await self._record_consolidation_run(
                kind=kind,
                input_count=len(result.memories),
                output_count=created,
                status="completed",
                duration_seconds=duration,
            )

            return ConsolidationResult(
                kind=kind,
                input_count=len(result.memories),
                output_count=created,
                status="completed",
                duration_seconds=duration,
            )

        except Exception as e:
            duration = (datetime.now(timezone.utc) - start).total_seconds()
            log_structured(logger, logging.ERROR, "Preference extraction failed", error=str(e))

            return ConsolidationResult(
                kind=kind,
                input_count=0,
                output_count=0,
                status="failed",
                error=str(e),
                duration_seconds=duration,
            )

    def _extract_preference_from_memory(self, memory: Memory) -> Optional[str]:
        """Extract preference statement from memory content."""
        content = memory.content.lower()

        # Simple pattern matching for preferences
        if "prefer" in content or "like" in content or "dislike" in content:
            # Return the sentence containing the preference
            sentences = memory.content.split(".")
            for sent in sentences:
                if any(kw in sent.lower() for kw in ["prefer", "like", "dislike", "want", "need"]):
                    return sent.strip() + "."

        return None

    async def _learn_procedures(self) -> ConsolidationResult:
        """Learn procedural skills from repeated action patterns."""
        start = datetime.now(timezone.utc)
        kind = "procedural_learning"

        if not self.config.procedural_learning_enabled:
            return ConsolidationResult(kind=kind, input_count=0, output_count=0, status="disabled")

        log_structured(logger, logging.INFO, "Starting procedural learning")

        try:
            # Query episodic memories with procedure indicators
            query = MemoryQuery(
                kind=MemoryKind.EPISODIC,
                limit=self.config.batch_size,
                filters={"tags": {"$in": ["procedure", "workflow", "steps", "how to"]}},
            )

            result = await self.memory_store.query(query)

            created = 0
            for memory in result.memories:
                # Extract procedure steps
                procedure = self._extract_procedure_from_memory(memory)
                if procedure:
                    proc_memory = Memory(
                        kind=MemoryKind.PROCEDURAL,
                        content=procedure,
                        confidence=memory.confidence * 0.85,
                        metadata={
                            "extracted_from": "episodic",
                            "source_memory_id": memory.id,
                        },
                        tags=["extracted", "procedure"],
                        source=MemorySource.CONSOLIDATION,
                        ttl_seconds=86400 * 3650,
                    )

                    await self.memory_store.store(proc_memory)
                    created += 1

            duration = (datetime.now(timezone.utc) - start).total_seconds()

            await self._record_consolidation_run(
                kind=kind,
                input_count=len(result.memories),
                output_count=created,
                status="completed",
                duration_seconds=duration,
            )

            return ConsolidationResult(
                kind=kind,
                input_count=len(result.memories),
                output_count=created,
                status="completed",
                duration_seconds=duration,
            )

        except Exception as e:
            duration = (datetime.now(timezone.utc) - start).total_seconds()
            log_structured(logger, logging.ERROR, "Procedural learning failed", error=str(e))

            return ConsolidationResult(
                kind=kind,
                input_count=0,
                output_count=0,
                status="failed",
                error=str(e),
                duration_seconds=duration,
            )

    def _extract_procedure_from_memory(self, memory: Memory) -> Optional[str]:
        """Extract procedure from memory content."""
        content = memory.content

        # Look for numbered steps or bullet points
        lines = content.split("\n")
        steps = []

        for line in lines:
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith(("-", "*", "•"))):
                steps.append(line.lstrip("0123456789.-*• "))

        if len(steps) >= 2:
            return "Procedure: " + " → ".join(steps)

        return None

    async def _record_consolidation_run(
        self,
        kind: str,
        input_count: int,
        output_count: int,
        status: str,
        error: Optional[str] = None,
        duration_seconds: float = 0.0,
    ) -> None:
        """Record consolidation run in database."""
        try:
            async with get_session() as session:
                run = ConsolidationRun(
                    kind=kind,
                    started_at=datetime.now(timezone.utc) - timedelta(seconds=duration_seconds),
                    completed_at=datetime.now(timezone.utc),
                    input_count=input_count,
                    output_count=output_count,
                    status=status,
                    error=error,
                    config_json={
                        "threshold": self.config.working_to_episodic_threshold
                        if kind == "working_to_episodic"
                        else self.config.episodic_to_semantic_threshold,
                    },
                )
                session.add(run)
                await session.commit()
        except Exception as e:
            log_structured(logger, logging.WARNING, "Failed to record consolidation run", error=str(e))

    async def trigger_manual_consolidation(self, kind: str) -> ConsolidationResult:
        """Manually trigger a specific consolidation kind."""
        log_structured(logger, logging.INFO, "Manual consolidation triggered", kind=kind)
        results = await self.run_consolidation(kind)
        return results[0] if results else ConsolidationResult(kind=kind, status="no_op")


__all__ = [
    "ConsolidationPipeline",
    "ConsolidationConfig",
]