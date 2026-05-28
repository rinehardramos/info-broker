"""Sentinel module — holds the process-wide UsageEmitter instance."""
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from platform_monitoring.usage.emitter import UsageEmitter
_emitter: "UsageEmitter | None" = None
