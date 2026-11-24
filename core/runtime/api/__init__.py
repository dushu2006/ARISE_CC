# core/runtime/api/__init__.py
"""
API Router Package - Exports all API routers.
"""

from core.runtime.api.tasks import router as tasks_router
from core.runtime.api.memory import router as memory_router
from core.runtime.api.voice import router as voice_router
from core.runtime.api.agents import router as agents_router
from core.runtime.api.automation import router as automation_router
from core.runtime.api.models import router as models_router
from core.runtime.api.policy import router as policy_router

__all__ = [
    "tasks_router",
    "memory_router",
    "voice_router",
    "agents_router",
    "automation_router",
    "models_router",
    "policy_router",
]