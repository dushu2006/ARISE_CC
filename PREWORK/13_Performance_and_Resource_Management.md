# ARISE — Performance & Resource Management

## Overview

This document specifies the performance architecture, resource budgets, optimization strategies, and operational targets for ARISE. The system must maintain responsiveness for voice interactions (<500ms), handle concurrent multi-agent tasks, and operate within reasonable resource envelopes on consumer hardware.

---

## 1. Performance Targets (SLOs)

### 1.1 Latency Budgets

| Operation | Target (P50) | Target (P95) | Target (P99) | Criticality |
|-----------|--------------|--------------|--------------|-------------|
| **Voice wake-word detection** | <50ms | <100ms | <200ms | CRITICAL |
| **Voice VAD/ASR (local)** | <200ms | <500ms | <1000ms | CRITICAL |
| **Voice VAD/ASR (cloud)** | <500ms | <1500ms | <3000ms | HIGH |
| **Voice TTS (local)** | <100ms | <300ms | <500ms | HIGH |
| **Voice TTS (cloud)** | <300ms | <800ms | <1500ms | MEDIUM |
| **Intent classification** | <50ms | <100ms | <200ms | CRITICAL |
| **Policy evaluation** | <10ms | <25ms | <50ms | CRITICAL |
| **Task creation** | <100ms | <200ms | <500ms | HIGH |
| **Model inference (local)** | <2000ms | <5000ms | <10000ms | MEDIUM |
| **Model inference (cloud)** | <1000ms | <3000ms | <8000ms | HIGH |
| **UIA element query** | <20ms | <50ms | <100ms | HIGH |
| **Playwright action** | <100ms | <500ms | <2000ms | HIGH |
| **Memory query (semantic)** | <50ms | <150ms | <300ms | HIGH |
| **Memory consolidation (batch)** | <30s | <60s | <120s | LOW (async) |
| **File search (indexed)** | <100ms | <300ms | <500ms | MEDIUM |
| **Screenshot capture** | <50ms | <150ms | <300ms | HIGH |

### 1.2 Throughput Targets

| Metric | Target |
|--------|--------|
| Concurrent tasks | 10 active, 50 queued |
| Voice commands/minute | 30 sustained |
| Model requests/minute | 60 (mixed providers) |
| UIA queries/second | 100 |
| Playwright actions/second | 10 |
| Memory queries/second | 50 |
| Audit log writes/second | 1000 |
| WebSocket messages/second | 500 |

### 1.3 Resource Budgets

| Component | CPU (avg) | CPU (peak) | Memory (avg) | Memory (peak) | Disk (steady) | Network |
|-----------|-----------|------------|--------------|---------------|---------------|---------|
| **Tauri Frontend** | 2% | 10% | 150MB | 300MB | 50MB | - |
| **Python Backend** | 5% | 30% | 500MB | 2GB | 1GB | - |
| **Model Router** | 2% | 20% | 200MB | 500MB | 100MB | 10Mbps |
| **Voice Pipeline** | 10% | 50% | 300MB | 1GB | 200MB | 5Mbps |
| **UIA Adapter** | 1% | 5% | 50MB | 100MB | 10MB | - |
| **Playwright** | 5% | 25% | 200MB | 500MB | 50MB | - |
| **Memory System** | 2% | 15% | 300MB | 1GB | 2GB | - |
| **Agents (idle)** | 0% | - | 50MB | - | - | - |
| **Agents (active ×5)** | 15% | 50% | 500MB | 2GB | 100MB | 5Mbps |
| **Total (typical)** | 15% | 80% | 2GB | 5GB | 3.5GB | 20Mbps |

---

## 2. Resource Management Architecture

### 2.1 Resource Governor

```python
# src/arise/performance/resource_governor.py
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from enum import Enum
import asyncio
import psutil
import time

class ResourcePool(Enum):
    CPU = "cpu"
    MEMORY = "memory"
    GPU = "gpu"
    NETWORK = "network"
    DISK_IO = "disk_io"
    MODEL_CONCURRENCY = "model_concurrency"
    BROWSER_CONCURRENCY = "browser_concurrency"
    AGENT_CONCURRENCY = "agent_concurrency"

@dataclass
class ResourceLimit:
    pool: ResourcePool
    soft_limit: float      # Warning threshold
    hard_limit: float      # Hard enforcement
    unit: str              # "percent", "mb", "count", "mbps"
    window_seconds: int = 60

@dataclass
class ResourceUsage:
    pool: ResourcePool
    current: float
    peak: float
    timestamp: float

class ResourceGovernor:
    """Central resource governance with admission control"""
    
    def __init__(self, runtime: "AppRuntime"):
        self.runtime = runtime
        self.limits: Dict[ResourcePool, ResourceLimit] = {}
        self.usage: Dict[ResourcePool, ResourceUsage] = {}
        self._reservations: Dict[str, Dict[ResourcePool, float]] = {}  # task_id -> resources
        self._waiters: Dict[ResourcePool, List[asyncio.Future]] = {}
        self._monitor_task: Optional[asyncio.Task] = None
        self._init_default_limits()
    
    def _init_default_limits(self):
        # System-wide limits (configurable via settings)
        self.limits = {
            ResourcePool.CPU: ResourceLimit(ResourcePool.CPU, 70.0, 85.0, "percent"),
            ResourcePool.MEMORY: ResourceLimit(ResourcePool.MEMORY, 4096, 6144, "mb"),
            ResourcePool.GPU: ResourceLimit(ResourcePool.GPU, 80.0, 95.0, "percent"),
            ResourcePool.NETWORK: ResourceLimit(ResourcePool.NETWORK, 50, 100, "mbps"),
            ResourcePool.DISK_IO: ResourceLimit(ResourcePool.DISK_IO, 100, 200, "mbps"),
            ResourcePool.MODEL_CONCURRENCY: ResourceLimit(ResourcePool.MODEL_CONCURRENCY, 3, 5, "count"),
            ResourcePool.BROWSER_CONCURRENCY: ResourceLimit(ResourcePool.BROWSER_CONCURRENCY, 2, 3, "count"),
            ResourcePool.AGENT_CONCURRENCY: ResourceLimit(ResourcePool.AGENT_CONCURRENCY, 5, 8, "count"),
        }
    
    async def start(self):
        self._monitor_task = asyncio.create_task(self._monitor_loop())
    
    async def stop(self):
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
    
    async def _monitor_loop(self):
        while True:
            try:
                await self._collect_metrics()
                await self._check_limits()
                await asyncio.sleep(5)  # 5-second monitoring interval
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Resource monitor error: {e}")
                await asyncio.sleep(10)
    
    async def _collect_metrics(self):
        # System metrics
        process = psutil.Process()
        
        # CPU
        cpu_percent = process.cpu_percent(interval=0.1)
        self.usage[ResourcePool.CPU] = ResourceUsage(
            ResourcePool.CPU, cpu_percent, 
            max(cpu_percent, self.usage.get(ResourcePool.CPU, ResourceUsage(ResourcePool.CPU, 0, 0, 0)).peak),
            time.time()
        )
        
        # Memory
        mem_info = process.memory_info()
        mem_mb = mem_info.rss / (1024 * 1024)
        self.usage[ResourcePool.MEMORY] = ResourceUsage(
            ResourcePool.MEMORY, mem_mb,
            max(mem_mb, self.usage.get(ResourcePool.MEMORY, ResourceUsage(ResourcePool.MEMORY, 0, 0, 0)).peak),
            time.time()
        )
        
        # GPU (if available)
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            gpu_info = pynvml.nvmlDeviceGetUtilizationRates(handle)
            self.usage[ResourcePool.GPU] = ResourceUsage(
                ResourcePool.GPU, gpu_info.gpu, gpu_info.gpu, time.time()
            )
        except Exception:
            pass
        
        # Network (simplified)
        net_io = psutil.net_io_counters()
        if hasattr(self, '_last_net_io'):
            elapsed = 5  # seconds
            mbps = ((net_io.bytes_sent + net_io.bytes_recv) - 
                    (self._last_net_io.bytes_sent + self._last_net_io.bytes_recv)) / (1024*1024) / elapsed * 8
            self.usage[ResourcePool.NETWORK] = ResourceUsage(
                ResourcePool.NETWORK, mbps, mbps, time.time()
            )
        self._last_net_io = net_io
        
        # Active reservations
        for pool in [ResourcePool.MODEL_CONCURRENCY, ResourcePool.BROWSER_CONCURRENCY, ResourcePool.AGENT_CONCURRENCY]:
            current = sum(r.get(pool, 0) for r in self._reservations.values())
            self.usage[pool] = ResourceUsage(pool, current, current, time.time())
    
    async def _check_limits(self):
        for pool, usage in self.usage.items():
            limit = self.limits.get(pool)
            if not limit:
                continue
            
            if usage.current >= limit.hard_limit:
                await self._handle_hard_limit(pool, usage)
            elif usage.current >= limit.soft_limit:
                await self._handle_soft_limit(pool, usage)
    
    async def _handle_soft_limit(self, pool: ResourcePool, usage: ResourceUsage):
        logger.warning(f"Resource soft limit reached: {pool.value} = {usage.current} {self.limits[pool].unit}")
        await self.runtime.events.emit("resource.soft_limit", {
            "pool": pool.value,
            "current": usage.current,
            "limit": self.limits[pool].soft_limit,
            "unit": self.limits[pool].unit,
        })
    
    async def _handle_hard_limit(self, pool: ResourcePool, usage: ResourceUsage):
        logger.error(f"Resource hard limit reached: {pool.value} = {usage.current} {self.limits[pool].unit}")
        
        # Emit event for adaptive behavior
        await self.runtime.events.emit("resource.hard_limit", {
            "pool": pool.value,
            "current": usage.current,
            "limit": self.limits[pool].hard_limit,
            "unit": self.limits[pool].unit,
        })
        
        # Take action based on pool
        if pool == ResourcePool.MEMORY:
            await self.runtime.memory_system.force_consolidation()
            await self._evict_caches()
        elif pool == ResourcePool.MODEL_CONCURRENCY:
            # Queue incoming model requests
            pass
        elif pool == ResourcePool.AGENT_CONCURRENCY:
            # Pause task scheduling
            await self.runtime.task_engine.pause_scheduling()
    
    async def reserve(self, task_id: str, requirements: Dict[ResourcePool, float]) -> bool:
        """Attempt to reserve resources for a task"""
        # Check if reservation would exceed limits
        for pool, amount in requirements.items():
            limit = self.limits.get(pool)
            if not limit:
                continue
            
            current = self.usage.get(pool, ResourceUsage(pool, 0, 0, 0)).current
            reserved = sum(r.get(pool, 0) for r in self._reservations.values())
            
            if current + reserved + amount > limit.hard_limit:
                return False
        
        # Reserve
        self._reservations[task_id] = requirements
        return True
    
    async def release(self, task_id: str):
        """Release task reservations"""
        self._reservations.pop(task_id, None)
        
        # Notify waiters
        for pool, waiters in self._waiters.items():
            for future in waiters:
                if not future.done():
                    future.set_result(True)
            waiters.clear()
    
    async def wait_for_capacity(self, pool: ResourcePool, timeout: float = 30.0) -> bool:
        """Wait until capacity is available"""
        limit = self.limits.get(pool)
        if not limit:
            return True
        
        current = self.usage.get(pool, ResourceUsage(pool, 0, 0, 0)).current
        reserved = sum(r.get(pool, 0) for r in self._reservations.values())
        
        if current + reserved < limit.soft_limit:
            return True
        
        future = asyncio.get_event_loop().create_future()
        self._waiters.setdefault(pool, []).append(future)
        
        try:
            await asyncio.wait_for(future, timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
```

### 2.2 Adaptive Concurrency Control

```python
# src/arise/performance/concurrency_controller.py
import asyncio
from dataclasses import dataclass
from typing import Dict, Callable, Any
import time

class ConcurrencyController:
    """Adaptive concurrency control using AIMD (Additive Increase Multiplicative Decrease)"""
    
    def __init__(self, initial_concurrency: int = 3, min_concurrency: int = 1, max_concurrency: int = 10):
        self.current = initial_concurrency
        self.min_concurrency = min_concurrency
        self.max_concurrency = max_concurrency
        self.semaphore = asyncio.Semaphore(initial_concurrency)
        
        # AIMD parameters
        self.increase_step = 1
        self.decrease_factor = 0.5
        
        # Metrics
        self.latencies: list = []
        self.errors: int = 0
        self.requests: int = 0
        self.last_adjustment = time.time()
        self.adjustment_interval = 10  # seconds
    
    async def execute(self, coro_factory: Callable[[], Any]) -> Any:
        """Execute with concurrency control"""
        async with self.semaphore:
            start = time.time()
            self.requests += 1
            try:
                result = await coro_factory()
                latency = time.time() - start
                self.latencies.append(latency)
                if len(self.latencies) > 100:
                    self.latencies.pop(0)
                return result
            except Exception as e:
                self.errors += 1
                raise
            finally:
                await self._maybe_adjust()
    
    async def _maybe_adjust(self):
        now = time.time()
        if now - self.last_adjustment < self.adjustment_interval:
            return
        
        if self.requests < 10:  # Not enough data
            return
        
        avg_latency = sum(self.latencies) / len(self.latencies) if self.latencies else 0
        error_rate = self.errors / self.requests if self.requests > 0 else 0
        
        # Adjust based on latency and error rate
        if error_rate > 0.1 or avg_latency > 5.0:  # High latency or errors
            new_concurrency = max(self.min_concurrency, int(self.current * self.decrease_factor))
            if new_concurrency < self.current:
                self.current = new_concurrency
                self.semaphore = asyncio.Semaphore(self.current)
                logger.info(f"Decreased concurrency to {self.current} (error_rate={error_rate:.2f}, latency={avg_latency:.2f}s)")
        elif error_rate < 0.01 and avg_latency < 1.0:  # Healthy
            new_concurrency = min(self.max_concurrency, self.current + self.increase_step)
            if new_concurrency > self.current:
                self.current = new_concurrency
                self.semaphore = asyncio.Semaphore(self.current)
                logger.info(f"Increased concurrency to {self.current}")
        
        # Reset metrics
        self.latencies.clear()
        self.errors = 0
        self.requests = 0
        self.last_adjustment = now

# Per-subsystem controllers
class SubsystemConcurrency:
    def __init__(self, runtime: "AppRuntime"):
        self.runtime = runtime
        self.controllers = {
            "model_inference": ConcurrencyController(3, 1, 5),
            "browser_automation": ConcurrencyController(2, 1, 3),
            "voice_processing": ConcurrencyController(1, 1, 2),  # Serial for audio
            "file_operations": ConcurrencyController(5, 2, 10),
            "agent_execution": ConcurrencyController(5, 2, 8),
        }
    
    async def run(self, subsystem: str, coro_factory: Callable[[], Any]) -> Any:
        controller = self.controllers.get(subsystem)
        if not controller:
            return await coro_factory()
        return await controller.execute(coro_factory)
```

---

## 3. Caching Strategy

### 3.1 Multi-Level Cache Architecture

```python
# src/arise/performance/cache.py
from dataclasses import dataclass
from typing import Any, Optional, Dict, Callable
from enum import Enum
import asyncio
import time
import hashlib
import json

class CacheLevel(Enum):
    L1_MEMORY = "l1_memory"      # In-process, fastest
    L2_DISK = "l2_disk"          # SQLite/Redis, persistent
    L3_DISTRIBUTED = "l3_distributed"  # Not used in local-first

@dataclass
class CacheConfig:
    max_size: int                # Max entries
    ttl_seconds: int             # Time to live
    level: CacheLevel
    eviction: str = "lru"        # lru, lfu, fifo

class MultiLevelCache:
    """Multi-level cache with write-through and read-through"""
    
    def __init__(self, name: str, config: Dict[CacheLevel, CacheConfig]):
        self.name = name
        self.config = config
        self.l1: Dict[str, CacheEntry] = {}
        self.l1_order: list = []  # For LRU
        self.l2_db = None  # SQLite connection
        self.stats = CacheStats()
    
    async def get(self, key: str, loader: Callable[[], Any] = None) -> Optional[Any]:
        # L1 check
        entry = self.l1.get(key)
        if entry and not entry.is_expired():
            self._touch_l1(key)
            self.stats.hits += 1
            return entry.value
        
        # L2 check
        if CacheLevel.L2_DISK in self.config:
            entry = await self._l2_get(key)
            if entry and not entry.is_expired():
                self._l1_put(key, entry)
                self.stats.hits += 1
                return entry.value
        
        self.stats.misses += 1
        
        # Load if loader provided
        if loader:
            value = await loader() if asyncio.iscoroutinefunction(loader) else loader()
            await self.set(key, value)
            return value
        
        return None
    
    async def set(self, key: str, value: Any, ttl: int = None):
        entry = CacheEntry(value, ttl or self.config.get(CacheLevel.L1_MEMORY, CacheConfig(0, 3600, CacheLevel.L1_MEMORY)).ttl_seconds)
        self._l1_put(key, entry)
        
        # Write-through to L2
        if CacheLevel.L2_DISK in self.config:
            await self._l2_put(key, entry)
    
    def _l1_put(self, key: str, entry: "CacheEntry"):
        # Evict if at capacity
        max_size = self.config[CacheLevel.L1_MEMORY].max_size
        while len(self.l1) >= max_size and self.l1_order:
            oldest = self.l1_order.pop(0)
            self.l1.pop(oldest, None)
            self.stats.evictions += 1
        
        self.l1[key] = entry
        self.l1_order.append(key)
    
    def _touch_l1(self, key: str):
        if key in self.l1_order:
            self.l1_order.remove(key)
            self.l1_order.append(key)
    
    async def _l2_get(self, key: str) -> Optional["CacheEntry"]:
        # SQLite implementation
        pass
    
    async def _l2_put(self, key: str, entry: "CacheEntry"):
        # SQLite implementation
        pass

@dataclass
class CacheEntry:
    value: Any
    expires_at: float
    created_at: float = field(default_factory=time.time)
    
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    
    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

# Cache instances per subsystem
CACHE_CONFIGS = {
    "model_responses": {
        CacheLevel.L1_MEMORY: CacheConfig(100, 300, CacheLevel.L1_MEMORY),  # 5 min
        CacheLevel.L2_DISK: CacheConfig(1000, 3600, CacheLevel.L2_DISK),    # 1 hour
    },
    "web_search": {
        CacheLevel.L1_MEMORY: CacheConfig(50, 600, CacheLevel.L1_MEMORY),    # 10 min
        CacheLevel.L2_DISK: CacheConfig(500, 86400, CacheLevel.L2_DISK),     # 24 hours
    },
    "file_index": {
        CacheLevel.L1_MEMORY: CacheConfig(200, 300, CacheLevel.L1_MEMORY),
        CacheLevel.L2_DISK: CacheConfig(5000, 86400, CacheLevel.L2_DISK),
    },
    "ui_elements": {
        CacheLevel.L1_MEMORY: CacheConfig(100, 60, CacheLevel.L1_MEMORY),    # 1 min (volatile)
    },
    "memory_embeddings": {
        CacheLevel.L1_MEMORY: CacheConfig(500, 1800, CacheLevel.L1_MEMORY),  # 30 min
        CacheLevel.L2_DISK: CacheConfig(10000, 604800, CacheLevel.L2_DISK),  # 1 week
    },
}
```

### 3.2 Cache Invalidation

```python
class CacheInvalidator:
    """Coordinated cache invalidation across subsystems"""
    
    def __init__(self, runtime: "AppRuntime"):
        self.runtime = runtime
        self.caches: Dict[str, MultiLevelCache] = {}
        self.invalidation_rules: Dict[str, List[str]] = {}  # event -> cache keys
    
    def register_cache(self, name: str, cache: MultiLevelCache):
        self.caches[name] = cache
    
    def register_rule(self, event_type: str, cache_keys: List[str]):
        self.invalidation_rules.setdefault(event_type, []).extend(cache_keys)
    
    async def invalidate(self, event_type: str, context: Dict = None):
        """Invalidate caches based on event"""
        keys = self.invalidation_rules.get(event_type, [])
        
        for key in keys:
            for cache in self.caches.values():
                await cache.delete(key)
        
        # Pattern-based invalidation
        if context:
            await self._invalidate_patterns(event_type, context)
    
    async def _invalidate_patterns(self, event_type: str, context: Dict):
        patterns = {
            "file_written": ["file_index:*", "memory_embeddings:file:*"],
            "memory_consolidated": ["memory_embeddings:*", "memory_queries:*"],
            "policy_changed": ["policy_cache:*"],
            "credential_changed": ["model_responses:*"],
        }
        
        for pattern in patterns.get(event_type, []):
            prefix = pattern.replace("*", "")
            for cache in self.caches.values():
                await cache.delete_prefix(prefix)
```

---

## 4. Memory Management

### 4.1 Python Memory Optimization

```python
# src/arise/performance/memory_optimizer.py
import gc
import sys
import weakref
from typing import Dict, Any
import tracemalloc

class MemoryOptimizer:
    """Python memory optimization and monitoring"""
    
    def __init__(self, runtime: "AppRuntime"):
        self.runtime = runtime
        self.tracemalloc_started = False
        self.snapshots: list = []
        self.weak_refs: Dict[str, weakref.ref] = {}
    
    def start_tracking(self):
        if not self.tracemalloc_started:
            tracemalloc.start(25)  # Track 25 frames
            self.tracemalloc_started = True
    
    def take_snapshot(self, label: str = ""):
        if self.tracemalloc_started:
            snapshot = tracemalloc.take_snapshot()
            self.snapshots.append((label, snapshot, time.time()))
            if len(self.snapshots) > 10:
                self.snapshots.pop(0)
    
    def get_top_allocations(self, limit: int = 20) -> list:
        if not self.tracemalloc_started or len(self.snapshots) < 2:
            return []
        
        current = self.snapshots[-1][1]
        previous = self.snapshots[-2][1]
        
        stats = current.compare_to(previous, 'lineno')
        return [
            {
                "file": str(s.traceback[0].filename) if s.traceback else "unknown",
                "line": s.traceback[0].lineno if s.traceback else 0,
                "size_diff_mb": s.size_diff / (1024 * 1024),
                "count_diff": s.count_diff,
            }
            for s in stats[:limit]
        ]
    
    def force_gc(self, generation: int = 2):
        """Force garbage collection"""
        collected = gc.collect(generation)
        logger.info(f"GC gen={generation} collected {collected} objects")
        return collected
    
    def get_memory_stats(self) -> Dict[str, Any]:
        process = psutil.Process()
        mem = process.memory_info()
        
        return {
            "rss_mb": mem.rss / (1024 * 1024),
            "vms_mb": mem.vms / (1024 * 1024),
            "percent": process.memory_percent(),
            "gc_counts": gc.get_count(),
            "gc_thresholds": gc.get_threshold(),
            "tracemalloc_traced": self.tracemalloc_started,
        }
    
    def register_weak_ref(self, name: str, obj: Any):
        """Register object for weak reference tracking"""
        self.weak_refs[name] = weakref.ref(obj)
    
    def check_leaks(self) -> Dict[str, bool]:
        """Check if registered objects are still alive"""
        return {name: ref() is not None for name, ref in self.weak_refs.items()}
```

### 4.2 Object Pooling

```python
# src/arise/performance/object_pool.py
import asyncio
from typing import TypeVar, Callable, Generic, List
from dataclasses import dataclass

T = TypeVar('T')

@dataclass
class PoolConfig:
    min_size: int = 2
    max_size: int = 10
    acquire_timeout: float = 5.0
    idle_timeout: float = 300.0  # 5 minutes
    factory: Callable[[], T] = None
    reset: Callable[[T], None] = None
    validator: Callable[[T], bool] = None

class ObjectPool(Generic[T]):
    """Async object pool for expensive resources"""
    
    def __init__(self, config: PoolConfig):
        self.config = config
        self._available: asyncio.Queue = asyncio.Queue()
        self._in_use: set = set()
        self._created = 0
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task = None
    
    async def start(self):
        # Pre-create minimum objects
        for _ in range(self.config.min_size):
            obj = self.config.factory()
            await self._available.put(obj)
            self._created += 1
        
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def stop(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
        while not self._available.empty():
            obj = await self._available.get()
            await self._destroy(obj)
    
    async def acquire(self) -> T:
        async with self._lock:
            # Try to get from pool
            try:
                obj = self._available.get_nowait()
                if self.config.validator and not self.config.validator(obj):
                    await self._destroy(obj)
                    obj = await self._create_new()
                self._in_use.add(id(obj))
                return obj
            except asyncio.QueueEmpty:
                pass
            
            # Create new if under max
            if self._created < self.config.max_size:
                obj = await self._create_new()
                self._in_use.add(id(obj))
                return obj
            
            # Wait for available
            try:
                obj = await asyncio.wait_for(self._available.get(), timeout=self.config.acquire_timeout)
                if self.config.validator and not self.config.validator(obj):
                    await self._destroy(obj)
                    return await self.acquire()  # Retry
                self._in_use.add(id(obj))
                return obj
            except asyncio.TimeoutError:
                raise PoolExhaustedError("Pool exhausted and timeout reached")
    
    async def release(self, obj: T):
        obj_id = id(obj)
        if obj_id not in self._in_use:
            return  # Already released or not from this pool
        
        self._in_use.remove(obj_id)
        
        # Reset if configured
        if self.config.reset:
            try:
                self.config.reset(obj)
            except Exception:
                await self._destroy(obj)
                return
        
        # Validate
        if self.config.validator and not self.config.validator(obj):
            await self._destroy(obj)
            return
        
        await self._available.put(obj)
    
    async def _create_new(self) -> T:
        obj = self.config.factory()
        self._created += 1
        return obj
    
    async def _destroy(self, obj: T):
        self._created -= 1
        # Call destructor if exists
        if hasattr(obj, 'close'):
            await obj.close() if asyncio.iscoroutinefunction(obj.close) else obj.close()
        elif hasattr(obj, '__aexit__'):
            await obj.__aexit__(None, None, None)
    
    async def _cleanup_loop(self):
        while True:
            await asyncio.sleep(60)  # Check every minute
            await self._cleanup_idle()
    
    async def _cleanup_idle(self):
        async with self._lock:
            now = time.time()
            to_keep = []
            
            while not self._available.empty():
                obj = await self._available.get()
                # Check last access time (would need tracking)
                # For now, just keep min_size
                if len(to_keep) < self.config.min_size:
                    to_keep.append(obj)
                else:
                    await self._destroy(obj)
            
            for obj in to_keep:
                await self._available.put(obj)

# Pool instances
POOLS = {
    "playwright_browser": ObjectPool(PoolConfig(
        min_size=1, max_size=3,
        factory=lambda: PlaywrightBrowser(),
        reset=lambda b: b.close_all_pages(),
        validator=lambda b: b.is_connected(),
    )),
    "http_client": ObjectPool(PoolConfig(
        min_size=2, max_size=10,
        factory=lambda: aiohttp.ClientSession(),
        reset=lambda s: None,
        validator=lambda s: not s.closed,
    )),
    "sqlite_connection": ObjectPool(PoolConfig(
        min_size=3, max_size=10,
        factory=lambda: sqlite3.connect("data/arise.db"),
        reset=lambda c: c.rollback(),
        validator=lambda c: True,
    )),
}
```

---

## 5. Startup & Shutdown Performance

### 5.1 Startup Optimization

```python
# src/arise/performance/startup.py
import asyncio
from dataclasses import dataclass
from typing import List, Dict, Callable, Awaitable
import time

@dataclass
class StartupPhase:
    name: str
    dependencies: List[str] = field(default_factory=list)
    critical: bool = True
    timeout: float = 30.0

class StartupOrchestrator:
    """Parallel startup with dependency resolution"""
    
    def __init__(self):
        self.phases: Dict[str, StartupPhase] = {}
        self.tasks: Dict[str, Callable[[], Awaitable]] = {}
        self.results: Dict[str, Any] = {}
        self.timings: Dict[str, float] = {}
    
    def register(self, phase: StartupPhase, task: Callable[[], Awaitable]):
        self.phases[phase.name] = phase
        self.tasks[phase.name] = task
    
    async def run(self) -> Dict[str, Any]:
        start_total = time.time()
        completed = set()
        running = {}
        
        while len(completed) < len(self.phases):
            # Find ready phases
            ready = []
            for name, phase in self.phases.items():
                if name in completed or name in running:
                    continue
                if all(dep in completed for dep in phase.dependencies):
                    ready.append(name)
            
            # Start ready phases
            for name in ready:
                phase = self.phases[name]
                task = self.tasks[name]
                running[name] = asyncio.create_task(self._run_with_timeout(name, task, phase.timeout))
            
            if not running:
                # Circular dependency or all blocked
                remaining = set(self.phases.keys()) - completed
                raise StartupError(f"Deadlock: {remaining}")
            
            # Wait for at least one to complete
            done, pending = await asyncio.wait(
                running.values(), 
                return_when=asyncio.FIRST_COMPLETED
            )
            
            for task in done:
                # Find which phase
                for name, t in running.items():
                    if t is task:
                        phase_name = name
                        break
                
                try:
                    result = await task
                    self.results[phase_name] = result
                    completed.add(phase_name)
                except Exception as e:
                    phase = self.phases[phase_name]
                    if phase.critical:
                        raise StartupError(f"Critical phase {phase_name} failed: {e}") from e
                    else:
                        logger.warning(f"Non-critical phase {phase_name} failed: {e}")
                        self.results[phase_name] = {"error": str(e)}
                        completed.add(phase_name)
                
                del running[phase_name]
        
        self.timings["total"] = time.time() - start_total
        return self.results
    
    async def _run_with_timeout(self, name: str, task: Callable, timeout: float):
        phase_start = time.time()
        try:
            result = await asyncio.wait_for(task(), timeout=timeout)
            self.timings[name] = time.time() - phase_start
            return result
        except asyncio.TimeoutError:
            self.timings[name] = time.time() - phase_start
            raise StartupError(f"Phase {name} timed out after {timeout}s")
```

### 5.2 Startup Phases

```python
# Startup phase definitions (in order)

STARTUP_PHASES = [
    StartupPhase("config_load", [], critical=True, timeout=5.0),
    StartupPhase("logging_init", ["config_load"], critical=True, timeout=2.0),
    StartupPhase("credential_manager", ["config_load"], critical=True, timeout=3.0),
    StartupPhase("database_init", ["config_load"], critical=True, timeout=5.0),
    StartupPhase("audit_log", ["database_init"], critical=True, timeout=2.0),
    StartupPhase("policy_engine", ["database_init", "credential_manager"], critical=True, timeout=3.0),
    StartupPhase("model_router", ["config_load", "credential_manager"], critical=True, timeout=10.0),
    StartupPhase("memory_system", ["database_init", "model_router"], critical=True, timeout=5.0),
    StartupPhase("voice_pipeline", ["config_load", "model_router"], critical=False, timeout=10.0),
    StartupPhase("adapters_init", ["config_load"], critical=True, timeout=5.0),
    StartupPhase("task_engine", ["policy_engine", "model_router", "adapters_init"], critical=True, timeout=3.0),
    StartupPhase("agent_coordinator", ["task_engine", "memory_system", "model_router"], critical=True, timeout=3.0),
    StartupPhase("event_bus", ["config_load"], critical=True, timeout=1.0),
    StartupPhase("frontend_bridge", ["event_bus", "task_engine"], critical=True, timeout=3.0),
    StartupPhase("scheduler", ["task_engine", "agent_coordinator"], critical=False, timeout=2.0),
    StartupPhase("recovery", ["task_engine", "audit_log"], critical=False, timeout=5.0),
]
```

---

## 6. Performance Monitoring

### 6.1 Metrics Collection

```python
# src/arise/performance/metrics.py
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from collections import defaultdict
import time
import asyncio

@dataclass
class MetricPoint:
    name: str
    value: float
    timestamp: float
    tags: Dict[str, str] = field(default_factory=dict)

class MetricsCollector:
    """Prometheus-compatible metrics collector"""
    
    def __init__(self):
        self.counters: Dict[str, float] = defaultdict(float)
        self.gauges: Dict[str, float] = {}
        self.histograms: Dict[str, List[float]] = defaultdict(list)
        self.summaries: Dict[str, List[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    def increment(self, name: str, value: float = 1.0, tags: Dict[str, str] = None):
        key = self._make_key(name, tags)
        self.counters[key] += value
    
    def gauge(self, name: str, value: float, tags: Dict[str, str] = None):
        key = self._make_key(name, tags)
        self.gauges[key] = value
    
    def histogram(self, name: str, value: float, tags: Dict[str, str] = None):
        key = self._make_key(name, tags)
        self.histograms[key].append(value)
        # Keep last 1000 values
        if len(self.histograms[key]) > 1000:
            self.histograms[key] = self.histograms[key][-1000:]
    
    def timing(self, name: str, value: float, tags: Dict[str, str] = None):
        self.histogram(f"{name}_duration_seconds", value, tags)
    
    def _make_key(self, name: str, tags: Dict[str, str] = None) -> str:
        if not tags:
            return name
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}{{{tag_str}}}"
    
    def get_prometheus_format(self) -> str:
        """Export in Prometheus text format"""
        lines = []
        
        for key, value in self.counters.items():
            lines.append(f"# TYPE {key.split('{')[0]} counter")
            lines.append(f"{key} {value}")
        
        for key, value in self.gauges.items():
            lines.append(f"# TYPE {key.split('{')[0]} gauge")
            lines.append(f"{key} {value}")
        
        for key, values in self.histograms.items():
            if not values:
                continue
            base_name = key.split('{')[0]
            lines.append(f"# TYPE {base_name} histogram")
            # Buckets
            buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
            for bucket in buckets:
                count = sum(1 for v in values if v <= bucket)
                lines.append(f"{key}_bucket{{le=\"{bucket}\"}} {count}")
            lines.append(f"{key}_bucket{{le=\"+Inf\"}} {len(values)}")
            lines.append(f"{key}_sum {sum(values)}")
            lines.append(f"{key}_count {len(values)}")
        
        return "\n".join(lines)

# Global metrics instance
metrics = MetricsCollector()

# Convenience decorators
def timed(name: str, tags: Dict[str, str] = None):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start = time.time()
            try:
                return await func(*args, **kwargs)
            finally:
                metrics.timing(name, time.time() - start, tags)
        return wrapper
    return decorator

def counted(name: str, tags: Dict[str, str] = None):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            finally:
                metrics.increment(name, 1.0, tags)
        return wrapper
    return decorator
```

### 6.2 Health Checks

```python
# src/arise/performance/health.py
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Callable, Awaitable
import asyncio

class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

@dataclass
class HealthCheck:
    name: str
    check: Callable[[], Awaitable[bool]]
    critical: bool = True
    timeout: float = 5.0
    interval: float = 30.0

class HealthMonitor:
    """System health monitoring"""
    
    def __init__(self, runtime: "AppRuntime"):
        self.runtime = runtime
        self.checks: Dict[str, HealthCheck] = {}
        self.status: Dict[str, HealthStatus] = {}
        self.last_check: Dict[str, float] = {}
        self._monitor_task: asyncio.Task = None
    
    def register(self, check: HealthCheck):
        self.checks[check.name] = check
        self.status[check.name] = HealthStatus.HEALTHY
    
    async def start(self):
        self._monitor_task = asyncio.create_task(self._monitor_loop())
    
    async def stop(self):
        if self._monitor_task:
            self._monitor_task.cancel()
    
    async def _monitor_loop(self):
        while True:
            await asyncio.sleep(10)
            for name, check in self.checks.items():
                if time.time() - self.last_check.get(name, 0) >= check.interval:
                    asyncio.create_task(self._run_check(name, check))
    
    async def _run_check(self, name: str, check: HealthCheck):
        try:
            result = await asyncio.wait_for(check.check(), timeout=check.timeout)
            self.status[name] = HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY
        except Exception:
            self.status[name] = HealthStatus.UNHEALTHY
        self.last_check[name] = time.time()
    
    def get_overall_status(self) -> HealthStatus:
        if any(s == HealthStatus.UNHEALTHY for s in self.status.values()):
            return HealthStatus.UNHEALTHY
        if any(s == HealthStatus.DEGRADED for s in self.status.values()):
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY
    
    async def check_all(self) -> Dict[str, HealthStatus]:
        for name, check in self.checks.items():
            await self._run_check(name, check)
        return self.status.copy()

# Standard health checks
def create_standard_checks(runtime: "AppRuntime") -> List[HealthCheck]:
    return [
        HealthCheck("database", lambda: runtime.db.health_check(), critical=True),
        HealthCheck("credential_manager", lambda: runtime.credential_manager.health_check(), critical=True),
        HealthCheck("model_router", lambda: runtime.model_router.health_check(), critical=True),
        HealthCheck("voice_pipeline", lambda: runtime.voice_pipeline.health_check(), critical=False),
        HealthCheck("audit_log", lambda: runtime.audit_log.verify_integrity(), critical=True),
        HealthCheck("memory_system", lambda: runtime.memory_system.health_check(), critical=True),
        HealthCheck("task_engine", lambda: runtime.task_engine.health_check(), critical=True),
        HealthCheck("resource_governor", lambda: runtime.resource_governor.health_check(), critical=True),
    ]
```

---

## 7. Profiling & Optimization

### 7.1 Continuous Profiling

```python
# src/arise/performance/profiler.py
import cProfile
import pstats
import io
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Optional

@dataclass
class ProfileResult:
    function: str
    calls: int
    total_time: float
    cumulative_time: float
    per_call: float

class ContinuousProfiler:
    """On-demand and continuous profiling"""
    
    def __init__(self):
        self.profiler: Optional[cProfile.Profile] = None
        self.enabled = False
        self.output_dir = Path("data/profiles")
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    @asynccontextmanager
    async def profile(self, name: str = "profile"):
        """Context manager for profiling a block"""
        if not self.enabled:
            yield
            return
        
        self.profiler = cProfile.Profile()
        self.profiler.enable()
        
        try:
            yield
        finally:
            self.profiler.disable()
            await self._save_profile(name)
    
    async def _save_profile(self, name: str):
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filepath = self.output_dir / f"{name}_{timestamp}.prof"
        
        self.profiler.dump_stats(str(filepath))
        
        # Generate summary
        s = io.StringIO()
        ps = pstats.Stats(self.profiler, stream=s).sort_stats('cumulative')
        ps.print_stats(50)
        
        summary_path = self.output_dir / f"{name}_{timestamp}.txt"
        summary_path.write_text(s.getvalue())
        
        logger.info(f"Profile saved to {filepath}")
    
    def start_continuous(self, interval: int = 60):
        """Start continuous profiling (samples every interval)"""
        self.enabled = True
        asyncio.create_task(self._continuous_loop(interval))
    
    async def _continuous_loop(self, interval: int):
        while self.enabled:
            await asyncio.sleep(interval)
            if self.enabled:
                async with self.profile(f"continuous_{datetime.utcnow().strftime('%H%M%S')}"):
                    await asyncio.sleep(0.1)  # Brief sample
    
    def stop_continuous(self):
        self.enabled = False
    
    def get_top_functions(self, limit: int = 20) -> List[ProfileResult]:
        if not self.profiler:
            return []
        
        s = io.StringIO()
        ps = pstats.Stats(self.profiler, stream=s).sort_stats('cumulative')
        ps.print_stats(limit)
        
        # Parse output
        lines = s.getvalue().split('\n')
        results = []
        for line in lines[5:]:  # Skip header
            parts = line.split()
            if len(parts) >= 6:
                try:
                    results.append(ProfileResult(
                        function=' '.join(parts[5:]),
                        calls=int(parts[0]),
                        total_time=float(parts[1]),
                        cumulative_time=float(parts[3]),
                        per_call=float(parts[2]),
                    ))
                except (ValueError, IndexError):
                    pass
        return results
```

### 7.2 Optimization Checklist

| Area | Optimization | Impact | Effort |
|------|--------------|--------|--------|
| **Model Router** | Request batching, connection pooling | High | Medium |
| **Voice** | Local VAD/ASR, streaming TTS | High | High |
| **UIA** | Element caching, lazy tree traversal | Medium | Medium |
| **Playwright** | Browser reuse, CDP session pooling | High | Medium |
| **Memory** | Embedding cache, incremental indexing | High | Medium |
| **Database** | WAL mode, connection pooling, indexes | Medium | Low |
| **Serialization** | msgpack instead of JSON for internal | Medium | Low |
| **Async** | Proper async/await, avoid sync in async | High | Medium |
| **Imports** | Lazy imports for heavy modules | Medium | Low |

---

## 8. Capacity Planning

### 8.1 Scaling Guidelines

| User Load | CPU Cores | RAM | GPU | Storage | Notes |
|-----------|-----------|-----|-----|---------|-------|
| Light (1-5 tasks/day) | 4 | 8GB | Optional | 50GB | Baseline |
| Moderate (20 tasks/day) | 8 | 16GB | Recommended | 100GB | Voice + agents |
| Heavy (100+ tasks/day) | 16 | 32GB | Required | 256GB | Multi-agent, video |
| Power (continuous) | 24+ | 64GB | Required (24GB+) | 500GB+ | Local LLM, training |

### 8.2 Resource Alerting

```python
ALERT_THRESHOLDS = {
    "cpu_percent": {"warning": 70, "critical": 85},
    "memory_percent": {"warning": 75, "critical": 90},
    "disk_percent": {"warning": 80, "critical": 95},
    "gpu_memory_percent": {"warning": 80, "critical": 95},
    "task_queue_depth": {"warning": 20, "critical": 50},
    "model_queue_depth": {"warning": 5, "critical": 10},
    "error_rate_5m": {"warning": 0.05, "critical": 0.15},
    "p99_latency": {"warning": 10.0, "critical": 30.0},
}
```

---

## 9. Configuration

```toml
# config/performance.toml

[resource_limits]
cpu_percent_soft = 70.0
cpu_percent_hard = 85.0
memory_mb_soft = 4096
memory_mb_hard = 6144
gpu_percent_soft = 80.0
gpu_percent_hard = 95.0
network_mbps_soft = 50
network_mbps_hard = 100
model_concurrency_soft = 3
model_concurrency_hard = 5
browser_concurrency_soft = 2
browser_concurrency_hard = 3
agent_concurrency_soft = 5
agent_concurrency_hard = 8

[concurrency]
model_inference_initial = 3
model_inference_min = 1
model_inference_max = 5
browser_automation_initial = 2
browser_automation_min = 1
browser_automation_max = 3
voice_processing_initial = 1
voice_processing_min = 1
voice_processing_max = 2
file_operations_initial = 5
file_operations_min = 2
file_operations_max = 10
agent_execution_initial = 5
agent_execution_min = 2
agent_execution_max = 8

[caching]
model_responses_l1_size = 100
model_responses_l1_ttl = 300
model_responses_l2_size = 1000
model_responses_l2_ttl = 3600
web_search_l1_size = 50
web_search_l1_ttl = 600
web_search_l2_size = 500
web_search_l2_ttl = 86400
file_index_l1_size = 200
file_index_l1_ttl = 300
file_index_l2_size = 5000
file_index_l2_ttl = 86400
ui_elements_l1_size = 100
ui_elements_l1_ttl = 60
memory_embeddings_l1_size = 500
memory_embeddings_l1_ttl = 1800
memory_embeddings_l2_size = 10000
memory_embeddings_l2_ttl = 604800

[pools]
playwright_browser_min = 1
playwright_browser_max = 3
playwright_browser_acquire_timeout = 5.0
playwright_browser_idle_timeout = 300.0
http_client_min = 2
http_client_max = 10
http_client_acquire_timeout = 3.0
http_client_idle_timeout = 60.0
sqlite_connection_min = 3
sqlite_connection_max = 10
sqlite_connection_acquire_timeout = 2.0

[startup]
parallel_init = true
phase_timeout_default = 30.0
critical_phase_timeout = 60.0

[monitoring]
metrics_interval = 10
health_check_interval = 30
profile_enabled = false
profile_interval = 300
prometheus_port = 9090

[alerts]
cpu_warning = 70
cpu_critical = 85
memory_warning = 75
memory_critical = 90
disk_warning = 80
disk_critical = 95
task_queue_warning = 20
task_queue_critical = 50
error_rate_warning = 0.05
error_rate_critical = 0.15
```

---

## 10. Testing Performance

### 10.1 Benchmark Suite

```python
# tests/performance/benchmarks.py
import pytest
import asyncio
import time
from dataclasses import dataclass

@dataclass
class BenchmarkResult:
    name: str
    iterations: int
    total_time: float
    avg_time: float
    p50: float
    p95: float
    p99: float
    throughput: float  # ops/sec

class PerformanceBenchmark:
    def __init__(self, runtime: "AppRuntime"):
        self.runtime = runtime
    
    async def run_all(self) -> List[BenchmarkResult]:
        results = []
        
        results.append(await self._benchmark("intent_classification", 
            lambda: self.runtime.intent_classifier.classify("test"), 100))
        
        results.append(await self._benchmark("policy_evaluation",
            lambda: self.runtime.policy.assess_risk("test task", None), 1000))
        
        results.append(await self._benchmark("task_creation",
            lambda: self.runtime.task_engine.create_task("test", {}), 100))
        
        results.append(await self._benchmark("memory_query",
            lambda: self.runtime.memory.query("test query", k=10), 50))
        
        results.append(await self._benchmark("uia_element_find",
            lambda: self.runtime.uia_adapter.find_element("Chrome", "address bar"), 50))
        
        results.append(await self._benchmark("playwright_navigate",
            lambda: self.runtime.playwright_adapter.navigate("https://example.com"), 10))
        
        results.append(await self._benchmark("model_inference_local",
            lambda: self.runtime.model_router.complete("fast", "Hello"), 20))
        
        results.append(await self._benchmark("voice_wake_word",
            lambda: self.runtime.voice.detect_wake_word(audio_chunk), 1000))
        
        return results
    
    async def _benchmark(self, name: str, func: Callable, iterations: int) -> BenchmarkResult:
        times = []
        
        # Warmup
        for _ in range(min(10, iterations // 10)):
            await func()
        
        # Benchmark
        for _ in range(iterations):
            start = time.perf_counter()
            await func()
            times.append(time.perf_counter() - start)
        
        times.sort()
        
        return BenchmarkResult(
            name=name,
            iterations=iterations,
            total_time=sum(times),
            avg_time=sum(times) / len(times),
            p50=times[len(times) // 2],
            p95=times[int(len(times) * 0.95)],
            p99=times[int(len(times) * 0.99)],
            throughput=iterations / sum(times),
        )

# CI thresholds
PERFORMANCE_THRESHOLDS = {
    "intent_classification": {"p99": 0.2, "throughput": 50},
    "policy_evaluation": {"p99": 0.05, "throughput": 1000},
    "task_creation": {"p99": 0.5, "throughput": 50},
    "memory_query": {"p99": 0.3, "throughput": 20},
    "uia_element_find": {"p99": 0.1, "throughput": 30},
    "playwright_navigate": {"p99": 5.0, "throughput": 2},
    "model_inference_local": {"p99": 10.0, "throughput": 2},
    "voice_wake_word": {"p99": 0.1, "throughput": 100},
}
```

---

## 11. Open Performance Decisions

| Decision | Options | Considerations |
|----------|---------|----------------|
| Local LLM inference | llama.cpp / ollama / vLLM / TGI | llama.cpp: lowest resource; vLLM: highest throughput |
| Embedding model | all-MiniLM-L6-v2 / bge-small / nomic-embed | Size vs quality tradeoff |
| Vector DB | ChromaDB / Qdrant / LanceDB / SQLite-vec | Chroma: simple; Qdrant: scalable; LanceDB: columnar |
| Cache backend | In-memory / SQLite / Redis / DiskCache | In-memory: fastest; SQLite: persistent; Redis: distributed |
| Metrics export | Prometheus / StatsD / OTLP / Custom | Prometheus: standard; OTLP: vendor-neutral |
| Profiling | cProfile / py-spy / Austin / Scalene | py-spy: no code changes; Scalene: GPU + memory |
| Browser pool | Playwright / Selenium / CDP direct | Playwright: best API; CDP: most control |