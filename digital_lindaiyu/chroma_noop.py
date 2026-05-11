"""Chroma product telemetry no-op implementation."""

from __future__ import annotations

from chromadb.config import System
from chromadb.telemetry.product import ProductTelemetryClient, ProductTelemetryEvent
from overrides import override


class NoopTelemetry(ProductTelemetryClient):
    """Drop Chroma telemetry events locally."""

    def __init__(self, system: System) -> None:
        super().__init__(system)

    @override
    def capture(self, event: ProductTelemetryEvent) -> None:
        return None
