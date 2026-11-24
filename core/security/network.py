"""
Network Egress Control.

Controls outbound network connections with allowlist/denylist,
DNS blocking, and proxy interception.
"""

from __future__ import annotations
import asyncio
import ipaddress
import logging
import socket
import ssl
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

from core.config import load_config
from core.config.models import SecurityConfig, NetworkConfig
from core.structured_logging import get_logger, log_structured

logger = get_logger(__name__)


@dataclass
class NetworkRule:
    """Network access rule."""
    name: str
    action: str  # allow, deny, log
    direction: str  # inbound, outbound
    protocol: str  # tcp, udp, icmp
    port: Optional[int] = None
    destination: str = ""  # IP, CIDR, or domain
    description: str = ""
    is_active: bool = True
    priority: int = 0


@dataclass
class ConnectionRequest:
    """A connection request to evaluate."""
    destination: str
    port: int
    protocol: str = "tcp"
    source_ip: Optional[str] = None
    capability: Optional[str] = None
    task_id: Optional[str] = None


@dataclass
class ConnectionDecision:
    """Decision for a connection request."""
    allowed: bool
    rule_name: Optional[str] = None
    reason: str = ""
    action: str = "deny"  # allow, deny, log


class DNSResolver:
    """Custom DNS resolver with blocking capability."""

    def __init__(self, blocked_domains: Set[str]):
        self.blocked_domains = blocked_domains
        self._cache: Dict[str, List[str]] = {}
        self._blocked_cache: Set[str] = set()

    def is_blocked(self, domain: str) -> bool:
        """Check if a domain is blocked."""
        domain_lower = domain.lower().rstrip('.')

        # Check exact match
        if domain_lower in self.blocked_domains:
            return True

        # Check parent domains
        parts = domain_lower.split('.')
        for i in range(len(parts)):
            parent = '.'.join(parts[i:])
            if parent in self.blocked_domains:
                return True

        return False

    async def resolve(self, host: str) -> List[str]:
        """Resolve host to IP addresses, with blocking."""
        if self.is_blocked(host):
            log_structured(logger, logging.WARNING, "DNS resolution blocked", host=host)
            raise ConnectionError(f"DNS resolution blocked for {host}")

        # Check cache
        if host in self._cache:
            return self._cache[host]

        try:
            # Use getaddrinfo for resolution
            loop = asyncio.get_event_loop()
            addrs = await loop.getaddrinfo(host, None, family=socket.AF_INET, type=socket.SOCK_STREAM)
            ips = list(set(addr[4][0] for addr in addrs))
            self._cache[host] = ips
            return ips
        except Exception as e:
            log_structured(logger, logging.ERROR, "DNS resolution failed", host=host, error=str(e))
            raise


class EgressController:
    """
    Network egress controller with allowlist/denylist,
    per-capability permissions, DNS blocking, and proxy interception.
    """

    def __init__(self, config: Optional[NetworkConfig] = None):
        self.config = config or load_config().security.network
        self._rules: List[NetworkRule] = []
        self._dns_resolver: Optional[DNSResolver] = None
        self._initialized = False
        self._default_socket_create = socket.socket
        self._default_getaddrinfo = socket.getaddrinfo

    async def initialize(self) -> None:
        """Initialize egress controller."""
        log_structured(logger, logging.INFO, "Initializing Egress Controller")

        # Build rules from config
        self._build_rules()

        # Initialize DNS resolver
        if self.config.dns_blocking_enabled:
            self._dns_resolver = DNSResolver(set(self.config.denylist))

        # Patch socket if proxy interception enabled
        if self.config.proxy_interception_enabled:
            self._patch_socket()

        self._initialized = True
        log_structured(logger, logging.INFO, "Egress Controller initialized",
                      rules=len(self._rules), dns_blocking=self.config.dns_blocking_enabled)

    def _build_rules(self) -> None:
        """Build network rules from configuration."""
        self._rules = []

        # Add allowlist rules (high priority)
        for domain in self.config.allowlist:
            self._rules.append(NetworkRule(
                name=f"allowlist-{domain}",
                action="allow",
                direction="outbound",
                protocol="tcp",
                destination=domain,
                description=f"Allowlist: {domain}",
                priority=100,
            ))

        # Add denylist rules (highest priority - deny wins)
        for domain in self.config.denylist:
            self._rules.append(NetworkRule(
                name=f"denylist-{domain}",
                action="deny",
                direction="outbound",
                protocol="tcp",
                destination=domain,
                description=f"Denylist: {domain}",
                priority=200,
            ))

        # Sort by priority (higher first)
        self._rules.sort(key=lambda r: -r.priority)

    def _patch_socket(self) -> None:
        """Patch socket to intercept connections."""
        original_create_connection = socket.create_connection

        def intercepted_create_connection(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None, *, all_errors=False):
            host, port = address[0], address[1]

            # Check if allowed
            decision = self.check_connection(ConnectionRequest(
                destination=host,
                port=port,
            ))

            if not decision.allowed:
                log_structured(logger, logging.WARNING, "Connection blocked by egress controller",
                              host=host, port=port, reason=decision.reason)
                raise ConnectionError(f"Connection blocked: {decision.reason}")

            if decision.action == "log":
                log_structured(logger, logging.INFO, "Connection allowed (logged)",
                              host=host, port=port, rule=decision.rule_name)

            return original_create_connection(address, timeout, source_address, all_errors=all_errors)

        socket.create_connection = intercepted_create_connection

        # Also patch getaddrinfo for DNS blocking
        if self._dns_resolver:
            original_getaddrinfo = socket.getaddrinfo

            def intercepted_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
                if self._dns_resolver and self._dns_resolver.is_blocked(host):
                    log_structured(logger, logging.WARNING, "DNS lookup blocked", host=host)
                    raise socket.gaierror(f"DNS lookup blocked for {host}")
                return original_getaddrinfo(host, port, family, type, proto, flags)

            socket.getaddrinfo = intercepted_getaddrinfo

    def _unpatch_socket(self) -> None:
        """Restore original socket functions."""
        socket.create_connection = self._default_socket_create
        socket.getaddrinfo = self._default_getaddrinfo

    def check_connection(self, request: ConnectionRequest) -> ConnectionDecision:
        """
        Check if a connection is allowed.

        Args:
            request: Connection request to evaluate

        Returns:
            ConnectionDecision with allowance and reason
        """
        if not self.config.egress_control_enabled:
            return ConnectionDecision(allowed=True, reason="Egress control disabled")

        # Normalize destination
        dest = request.destination.lower()

        # Check if IP address
        try:
            dest_ip = ipaddress.ip_address(dest)
            is_ip = True
        except ValueError:
            is_ip = False

        # Evaluate rules in priority order
        for rule in self._rules:
            if not rule.is_active or rule.direction != "outbound":
                continue

            if rule.protocol != "any" and rule.protocol != request.protocol:
                continue

            if rule.port and rule.port != request.port:
                continue

            # Check destination match
            if self._match_destination(dest, rule.destination, is_ip):
                if rule.action == "allow":
                    return ConnectionDecision(allowed=True, rule_name=rule.name, reason=f"Allowed by rule: {rule.name}", action="allow")
                elif rule.action == "deny":
                    return ConnectionDecision(allowed=False, rule_name=rule.name, reason=f"Denied by rule: {rule.name}", action="deny")
                elif rule.action == "log":
                    return ConnectionDecision(allowed=True, rule_name=rule.name, reason=f"Logged by rule: {rule.name}", action="log")

        # Default policy
        if self.config.default_policy == "allow":
            return ConnectionDecision(allowed=True, reason="Default policy: allow", action="allow")
        else:
            return ConnectionDecision(allowed=False, reason="Default policy: deny", action="deny")

    def _match_destination(self, dest: str, pattern: str, is_ip: bool) -> bool:
        """Check if destination matches pattern."""
        pattern = pattern.lower()

        # Exact match
        if dest == pattern:
            return True

        # CIDR match (if dest is IP)
        if is_ip and '/' in pattern:
            try:
                network = ipaddress.ip_network(pattern, strict=False)
                return ipaddress.ip_address(dest) in network
            except ValueError:
                pass

        # Domain suffix match (e.g., ".example.com" matches "api.example.com")
        if pattern.startswith('.'):
            return dest.endswith(pattern) or dest == pattern[1:]

        # Wildcard match
        if '*' in pattern:
            import fnmatch
            return fnmatch.fnmatch(dest, pattern)

        return False

    async def check_url(self, url: str, capability: Optional[str] = None, task_id: Optional[str] = None) -> ConnectionDecision:
        """
        Check if a URL is allowed.

        Args:
            url: URL to check
            capability: Capability making the request
            task_id: Task ID for context

        Returns:
            ConnectionDecision
        """
        parsed = urlparse(url)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        request = ConnectionRequest(
            destination=host,
            port=port,
            protocol="tcp",
            capability=capability,
            task_id=task_id,
        )

        return self.check_connection(request)

    async def resolve_host(self, host: str) -> List[str]:
        """Resolve host using custom DNS resolver."""
        if self._dns_resolver:
            return await self._dns_resolver.resolve(host)
        # Fallback to system resolver
        loop = asyncio.get_event_loop()
        addrs = await loop.getaddrinfo(host, None, family=socket.AF_INET, type=socket.SOCK_STREAM)
        return list(set(addr[4][0] for addr in addrs))

    def add_rule(self, rule: NetworkRule) -> None:
        """Add a custom network rule."""
        self._rules.append(rule)
        self._rules.sort(key=lambda r: -r.priority)

    def remove_rule(self, name: str) -> bool:
        """Remove a network rule by name."""
        for i, rule in enumerate(self._rules):
            if rule.name == name:
                self._rules.pop(i)
                return True
        return False

    def get_rules(self) -> List[NetworkRule]:
        """Get all network rules."""
        return self._rules.copy()

    async def shutdown(self) -> None:
        """Shutdown egress controller."""
        self._unpatch_socket()
        self._initialized = False
        log_structured(logger, logging.INFO, "Egress Controller shutdown")

    def is_initialized(self) -> bool:
        return self._initialized


# Global egress controller instance
_egress_controller: Optional[EgressController] = None


async def get_egress_controller() -> Optional[EgressController]:
    """Get the global egress controller instance."""
    return _egress_controller


async def init_egress_controller(config: Optional[NetworkConfig] = None) -> EgressController:
    """Initialize the global egress controller."""
    global _egress_controller
    _egress_controller = EgressController(config)
    await _egress_controller.initialize()
    return _egress_controller


async def shutdown_egress_controller() -> None:
    """Shutdown the global egress controller."""
    global _egress_controller
    if _egress_controller:
        await _egress_controller.shutdown()
        _egress_controller = None


__all__ = [
    "EgressController",
    "NetworkRule",
    "ConnectionRequest",
    "ConnectionDecision",
    "DNSResolver",
    "get_egress_controller",
    "init_egress_controller",
    "shutdown_egress_controller",
]