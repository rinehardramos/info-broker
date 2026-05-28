"""Sentinel module — holds the process-wide PricingResolver instance."""
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.observability.pricing import PricingResolver
_resolver: "PricingResolver | None" = None
