# core/errors/saga.py
import logging
from typing import List, Callable, Awaitable, Dict, Any, Optional
from dataclasses import dataclass, field
from core.errors.base import AriseError, ErrorCode, ErrorContext

logger = logging.getLogger(__name__)


@dataclass
class SagaStep:
    name: str
    execute: Callable[[], Awaitable[Any]]
    compensate: Callable[[Any], Awaitable[None]]  # Receives execute result
    execute_context: ErrorContext
    compensate_context: ErrorContext


@dataclass
class SagaExecution:
    steps: List[SagaStep] = field(default_factory=list)
    completed_steps: List[tuple] = field(default_factory=list)  # (step_name, result)
    status: str = "running"  # running, completed, compensating, failed
    error: Optional[AriseError] = None
    current_step: Optional[str] = None


class Saga:
    """Saga pattern for distributed transaction compensation"""

    def __init__(self, name: str):
        self.name = name
        self.execution = SagaExecution()

    def add_step(
        self,
        name: str,
        execute: Callable[[], Awaitable[Any]],
        compensate: Callable[[Any], Awaitable[None]],
        execute_context: ErrorContext = None,
        compensate_context: ErrorContext = None,
    ) -> 'Saga':
        self.execution.steps.append(SagaStep(
            name=name,
            execute=execute,
            compensate=compensate,
            execute_context=execute_context or ErrorContext(component="saga", operation=name),
            compensate_context=compensate_context or ErrorContext(component="saga", operation=f"compensate_{name}"),
        ))
        return self

    async def execute(self) -> Any:
        """Execute all steps, compensate on failure"""
        try:
            for step in self.execution.steps:
                self.execution.current_step = step.name
                logger.info(f"Saga {self.name}: executing step {step.name}")
                result = await step.execute()
                self.execution.completed_steps.append((step.name, result))

            self.execution.status = "completed"
            logger.info(f"Saga {self.name} completed successfully")
            return self.execution.completed_steps[-1][1] if self.execution.completed_steps else None

        except Exception as e:
            self.execution.error = e if isinstance(e, AriseError) else AriseError(
                code=ErrorCode.INTERNAL_ERROR,
                message=str(e),
                context=ErrorContext(component="saga", operation=self.name),
            )
            self.execution.status = "compensating"
            logger.error(f"Saga {self.name} failed at step {self.execution.current_step}: {e}")
            await self._compensate()
            self.execution.status = "failed"
            raise

    async def _compensate(self):
        """Run compensations in reverse order"""
        for step_name, result in reversed(self.execution.completed_steps):
            step = next(s for s in self.execution.steps if s.name == step_name)
            try:
                logger.info(f"Saga {self.name}: compensating step {step_name}")
                await step.compensate(result)
                logger.info(f"Saga {self.name}: compensated step {step_name}")
            except Exception as e:
                logger.error(f"Saga {self.name}: compensation failed for {step_name}: {e}")
                # Log but continue compensating other steps
                # Could add compensation error to a list for later review

    def get_status(self) -> Dict[str, Any]:
        """Get current saga execution status"""
        return {
            "name": self.name,
            "status": self.execution.status,
            "current_step": self.execution.current_step,
            "completed_steps": [name for name, _ in self.execution.completed_steps],
            "total_steps": len(self.execution.steps),
            "error": self.execution.error.to_dict() if self.execution.error else None,
        }


class SagaManager:
    """Manages saga executions with persistence support"""

    def __init__(self):
        self.active_sagas: Dict[str, SagaExecution] = {}

    def create_saga(self, name: str) -> Saga:
        """Create a new saga"""
        return Saga(name)

    def register_saga(self, saga: Saga) -> str:
        """Register saga for tracking"""
        saga_id = f"{saga.name}_{len(self.active_sagas)}"
        self.active_sagas[saga_id] = saga.execution
        return saga_id

    def get_saga(self, saga_id: str) -> Optional[SagaExecution]:
        """Get saga execution by ID"""
        return self.active_sagas.get(saga_id)

    def list_active_sagas(self) -> List[Dict[str, Any]]:
        """List all active sagas"""
        return [
            {
                "saga_id": sid,
                "name": exec_obj.steps[0].execute_context.component if exec_obj.steps else "unknown",
                "status": exec_obj.status,
                "current_step": exec_obj.current_step,
                "completed_steps": len(exec_obj.completed_steps),
                "total_steps": len(exec_obj.steps),
            }
            for sid, exec_obj in self.active_sagas.items()
        ]


# Global saga manager
_saga_manager: Optional[SagaManager] = None


def get_saga_manager() -> SagaManager:
    """Get global saga manager"""
    global _saga_manager
    if _saga_manager is None:
        _saga_manager = SagaManager()
    return _saga_manager