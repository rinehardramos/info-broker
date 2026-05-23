"""Constants for the catalogs subsystem.

See spec 2026-05-23-research-skeleton-tactic-completion-design.md.
"""
from __future__ import annotations


# The unified phase taxonomy. Every PhaseSpec.id must be one of these.
# Legacy phase ids (signal_extraction, broaden, red_team, rank_verify) were
# retired in spec 2026-05-23.
LEGAL_PHASE_IDS: frozenset[str] = frozenset({
    "extract",
    "gather",
    "disconfirm",
    "synthesize",
})
