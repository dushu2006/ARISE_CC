"""
ARISE Configuration API Endpoints
FastAPI routes for configuration management.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
import logging

from ..config.loader import load_config, reload_config, get_config_loader
from ..config.models import AppConfig, Environment
from ..config.feature_flags import FeatureFlag, FlagType, FlagStatus
from ..config.feature_flags import get_flag_store, FeatureFlagStore, FeatureFlag as FFModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["configuration"])


# =============================================================================
# Request/Response Models
# =============================================================================

class ConfigResponse(BaseModel):
    config: AppConfig
    version: str
    environment: Environment


class FeatureFlagCreateRequest(BaseModel):
    key: str = Field(..., pattern=r"^[a-z0-9._-]+$")
    name: str
    description: str
    flag_type: FlagType = FlagType.BOOLEAN
    default_value: Any = False
    tags: List[str] = Field(default_factory=list)
    rollout_percentage: int = Field(default=100, ge=0, le=100)
    targeting_rules: List[Dict[str, Any]] = Field(default_factory=list)


class FeatureFlagUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    default_value: Optional[Any] = None
    status: Optional[FlagStatus] = None
    tags: Optional[List[str]] = None
    rollout_percentage: Optional[int] = Field(default=None, ge=0, le=100)
    targeting_rules: Optional[List[Dict[str, Any]]] = None


class FeatureFlagEvaluateRequest(BaseModel):
    key: str
    context: Optional[Dict[str, Any]] = None


class FeatureFlagEvaluateResponse(BaseModel):
    key: str
    value: Any
    source: str  # "default", "targeting", "rollout"


class FeatureFlagsResponse(BaseModel):
    flags: Dict[str, FeatureFlag]


class MigrationStatusResponse(BaseModel):
    current_version: str
    target_version: str
    pending_count: int
    pending_versions: List[str]
    history_count: int
    last_migration: Optional[str]


class MigrationRunRequest(BaseModel):
    target_version: Optional[str] = None
    dry_run: bool = False


class MigrationRunResponse(BaseModel):
    success: bool
    message: str
    applied: List[str] = Field(default_factory=list)


# =============================================================================
# Dependency Injection
# =============================================================================

def get_config_loader_dep():
    """Dependency to get config loader."""
    return get_config_loader()


def get_flag_store_dep() -> FeatureFlagStore:
    """Dependency to get feature flag store."""
    return get_flag_store()


# =============================================================================
# Configuration Endpoints
# =============================================================================

@router.get("", response_model=ConfigResponse)
async def get_config(loader=Depends(get_config_loader_dep)):
    """Get the complete application configuration."""
    config = loader.load()
    return ConfigResponse(
        config=config,
        version=config.version,
        environment=config.environment,
    )


@router.post("/reload", response_model=ConfigResponse)
async def reload_config_endpoint(loader=Depends(get_config_loader_dep)):
    """Force reload configuration from all sources."""
    config = loader.reload()
    return ConfigResponse(
        config=config,
        version=config.version,
        environment=config.environment,
    )


@router.get("/section/{section}")
async def get_config_section(section: str, loader=Depends(get_config_loader_dep)):
    """Get a specific configuration section."""
    config = loader.load()
    if not hasattr(config, section):
        raise HTTPException(status_code=404, detail=f"Config section '{section}' not found")
    return {section: getattr(config, section)}


@router.get("/env")
async def get_environment(loader=Depends(get_config_loader_dep)):
    """Get current environment."""
    return {
        "environment": loader.get_environment().value,
        "config_dir": str(loader.get_config_dir()),
    }


# =============================================================================
# Feature Flag Endpoints
# =============================================================================

@router.get("/feature-flags", response_model=FeatureFlagsResponse)
async def list_feature_flags(store: FeatureFlagStore = Depends(get_flag_store_dep)):
    """List all feature flags."""
    flags = store.get_all_flags()
    return FeatureFlagsResponse(
        flags={
            key: FeatureFlag(
                key=flag.key,
                name=flag.name,
                description=flag.description,
                flag_type=flag.flag_type,
                default_value=flag.default_value,
                status=flag.status,
                tags=list(flag.tags),
                rollout_percentage=flag.rollout_percentage,
                targeting_rules=flag.targeting_rules,
                created_at=flag.created_at.isoformat(),
                updated_at=flag.updated_at.isoformat(),
                created_by=flag.created_by,
            )
            for key, flag in flags.items()
        }
    )


@router.get("/feature-flags/{key}")
async def get_feature_flag(key: str, store: FeatureFlagStore = Depends(get_flag_store_dep)):
    """Get a specific feature flag."""
    flag = store.get_flag(key)
    if not flag:
        raise HTTPException(status_code=404, detail=f"Feature flag '{key}' not found")

    return FeatureFlag(
        key=flag.key,
        name=flag.name,
        description=flag.description,
        flag_type=flag.flag_type,
        default_value=flag.default_value,
        status=flag.status,
        tags=list(flag.tags),
        rollout_percentage=flag.rollout_percentage,
        targeting_rules=flag.targeting_rules,
        created_at=flag.created_at.isoformat(),
        updated_at=flag.updated_at.isoformat(),
        created_by=flag.created_by,
    )


@router.post("/feature-flags", response_model=FeatureFlag)
async def create_feature_flag(
    request: FeatureFlagCreateRequest,
    store: FeatureFlagStore = Depends(get_flag_store_dep),
):
    """Create a new feature flag."""
    if store.get_flag(request.key):
        raise HTTPException(status_code=409, detail=f"Feature flag '{request.key}' already exists")

    flag = store.create_flag(
        key=request.key,
        name=request.name,
        description=request.description,
        flag_type=request.flag_type,
        default_value=request.default_value,
        tags=set(request.tags),
        rollout_percentage=request.rollout_percentage,
        targeting_rules=request.targeting_rules,
    )

    return FeatureFlag(
        key=flag.key,
        name=flag.name,
        description=flag.description,
        flag_type=flag.flag_type,
        default_value=flag.default_value,
        status=flag.status,
        tags=list(flag.tags),
        rollout_percentage=flag.rollout_percentage,
        targeting_rules=flag.targeting_rules,
        created_at=flag.created_at.isoformat(),
        updated_at=flag.updated_at.isoformat(),
        created_by=flag.created_by,
    )


@router.patch("/feature-flags/{key}", response_model=FeatureFlag)
async def update_feature_flag(
    key: str,
    request: FeatureFlagUpdateRequest,
    store: FeatureFlagStore = Depends(get_flag_store_dep),
):
    """Update a feature flag."""
    flag = store.update_flag(key, **request.model_dump(exclude_unset=True))
    if not flag:
        raise HTTPException(status_code=404, detail=f"Feature flag '{key}' not found")

    return FeatureFlag(
        key=flag.key,
        name=flag.name,
        description=flag.description,
        flag_type=flag.flag_type,
        default_value=flag.default_value,
        status=flag.status,
        tags=list(flag.tags),
        rollout_percentage=flag.rollout_percentage,
        targeting_rules=flag.targeting_rules,
        created_at=flag.created_at.isoformat(),
        updated_at=flag.updated_at.isoformat(),
        created_by=flag.created_by,
    )


@router.delete("/feature-flags/{key}")
async def delete_feature_flag(key: str, store: FeatureFlagStore = Depends(get_flag_store_dep)):
    """Delete a feature flag."""
    if not store.delete_flag(key):
        raise HTTPException(status_code=404, detail=f"Feature flag '{key}' not found")
    return {"message": f"Feature flag '{key}' deleted"}


@router.post("/feature-flags/evaluate", response_model=FeatureFlagEvaluateResponse)
async def evaluate_feature_flag(
    request: FeatureFlagEvaluateRequest,
    store: FeatureFlagStore = Depends(get_flag_store_dep),
):
    """Evaluate a feature flag for a given context."""
    flag = store.get_flag(request.key)
    if not flag:
        raise HTTPException(status_code=404, detail=f"Feature flag '{request.key}' not found")

    value = flag.evaluate(request.context)

    # Determine source
    source = "default"
    if request.context and flag.targeting_rules:
        for rule in flag.targeting_rules:
            if flag._matches_rule(request.context, rule):
                source = "targeting"
                break
        else:
            if flag.rollout_percentage < 100:
                source = "rollout"

    return FeatureFlagEvaluateResponse(
        key=request.key,
        value=value,
        source=source,
    )


@router.get("/feature-flags/enabled/{key}")
async def is_feature_enabled(
    key: str,
    context: Optional[str] = Query(None, description="JSON context for evaluation"),
    store: FeatureFlagStore = Depends(get_flag_store_dep),
):
    """Check if a feature flag is enabled."""
    import json
    ctx = json.loads(context) if context else None
    enabled = store.is_enabled(key, ctx)
    return {"key": key, "enabled": enabled}


# =============================================================================
# Migration Endpoints
# =============================================================================

@router.get("/migrations/status", response_model=MigrationStatusResponse)
async def get_migration_status(loader=Depends(get_config_loader_dep)):
    """Get migration status."""
    from ..config.migration import create_migrator

    config_dir = loader.get_config_dir()
    migrator = create_migrator(config_dir)
    status = migrator.get_status()

    return MigrationStatusResponse(**status)


@router.post("/migrations/run", response_model=MigrationRunResponse)
async def run_migrations(
    request: MigrationRunRequest,
    loader=Depends(get_config_loader_dep),
):
    """Run pending migrations."""
    from ..config.migration import create_migrator

    config_dir = loader.get_config_dir()
    migrator = create_migrator(config_dir)

    pending_before = migrator.get_pending_migrations()
    pending_versions = [m.version for m in pending_before]

    success = migrator.migrate(target_version=request.target_version, dry_run=request.dry_run)

    applied = []
    if success and not request.dry_run:
        pending_after = migrator.get_pending_migrations()
        applied = [v for v in pending_versions if v not in [m.version for m in pending_after]]

    return MigrationRunResponse(
        success=success,
        message="Migrations completed successfully" if success else "Migration failed",
        applied=applied,
    )


@router.post("/migrations/rollback", response_model=MigrationRunResponse)
async def rollback_migrations(
    request: MigrationRunRequest,
    loader=Depends(get_config_loader_dep),
):
    """Rollback migrations to a target version."""
    from ..config.migration import create_migrator

    if not request.target_version:
        raise HTTPException(status_code=400, detail="target_version required for rollback")

    config_dir = loader.get_config_dir()
    migrator = create_migrator(config_dir)

    success = migrator.rollback(target_version=request.target_version, dry_run=request.dry_run)

    return MigrationRunResponse(
        success=success,
        message=f"Rollback to {request.target_version} completed" if success else "Rollback failed",
    )


@router.get("/migrations/history")
async def get_migration_history(loader=Depends(get_config_loader_dep)):
    """Get migration history."""
    from ..config.migration import create_migrator

    config_dir = loader.get_config_dir()
    migrator = create_migrator(config_dir)

    history = migrator.get_history()
    return {
        "history": [
            {
                "version": r.version,
                "name": r.name,
                "status": r.status.value,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "error": r.error,
                "backup_path": r.backup_path,
            }
            for r in history
        ]
    }


# =============================================================================
# Secrets Endpoints (Admin only - protected by policy engine)
# =============================================================================

class SecretSetRequest(BaseModel):
    key: str
    value: str


class SecretResponse(BaseModel):
    key: str
    value: Optional[str] = None
    exists: bool


@router.get("/secrets")
async def list_secrets():
    """List all secret keys (not values)."""
    from ..config.secrets import get_secret_manager
    manager = get_secret_manager()
    return {"secrets": manager.list_secrets()}


@router.get("/secrets/{key}", response_model=SecretResponse)
async def get_secret(key: str):
    """Get a secret value (requires appropriate permissions)."""
    from ..config.secrets import get_secret
    value = get_secret(key)
    return SecretResponse(key=key, value=value, exists=value is not None)


@router.post("/secrets", response_model=SecretResponse)
async def set_secret(request: SecretSetRequest):
    """Set a secret value (requires appropriate permissions)."""
    from ..config.secrets import set_secret
    success = set_secret(request.key, request.value)
    return SecretResponse(key=request.key, value=request.value if success else None, exists=success)


@router.delete("/secrets/{key}")
async def delete_secret(key: str):
    """Delete a secret (requires appropriate permissions)."""
    from ..config.secrets import delete_secret
    success = delete_secret(key)
    if not success:
        raise HTTPException(status_code=404, detail=f"Secret '{key}' not found")
    return {"message": f"Secret '{key}' deleted"}