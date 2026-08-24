"""Platform collector contracts and built-in adapters."""

from server.collectors.contract import (
    CollectorCapabilities,
    CollectorCapability,
    CollectorException,
    CollectorRegistry,
    DetailRequest,
    DynamicField,
    IdentityKind,
    PlatformIdentity,
    RawResult,
    SearchRequest,
    SearchResult,
    SearchSort,
    SystemCollectorError,
)
from server.collectors.pdd import PddCollector


collector_registry = CollectorRegistry()
collector_registry.register(PddCollector())


__all__ = [
    "CollectorCapabilities",
    "CollectorCapability",
    "CollectorException",
    "CollectorRegistry",
    "DetailRequest",
    "DynamicField",
    "IdentityKind",
    "PlatformIdentity",
    "RawResult",
    "SearchRequest",
    "SearchResult",
    "SearchSort",
    "SystemCollectorError",
    "collector_registry",
]
