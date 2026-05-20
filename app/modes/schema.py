"""
Mode schema — per-domain configuration that shapes the loop without forking it.

A Mode is loaded once at run-init and consulted by:
  - init_working_memory  (hypothesis_seeds, source_class_weights)
  - turn prompt builder  (prompt_persona, tool_weights — slice A2)
  - workflow termination (require_contradiction_resolution — slice A4)
  - synthesis renderer   (output_template — slice A3)

The bundled launch set is: general, kyc_edd, competitive_intel, lead_gen.
Users may author additional Modes; they're versioned and validated against
this schema before being persisted.
"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


SourceClass = Literal[
    "primary_official", "registry", "news", "aggregator", "social",
    "inferred", "user_attested", "negative", "training", "unknown",
]


class PhaseTuning(BaseModel):
    max_turns: int = Field(default=3, ge=1, le=10)
    tool_call_budget: int = Field(default=6, ge=1, le=20)


class ModePhases(BaseModel):
    explore: PhaseTuning = Field(default_factory=lambda: PhaseTuning(max_turns=3))
    test: PhaseTuning = Field(default_factory=lambda: PhaseTuning(max_turns=4))
    synthesize: PhaseTuning = Field(default_factory=lambda: PhaseTuning(max_turns=1, tool_call_budget=2))


class ModeTermination(BaseModel):
    require_contradiction_resolution: bool = False
    require_all_pir_satisfied: bool = False
    max_turns: int = Field(default=8, ge=2, le=16)


class Mode(BaseModel):
    # ── Identity ──
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    label: str
    version: int = 1
    description: str = ""

    # ── Loop framing ──
    prompt_persona: str = ""

    # ── Phase tuning ──
    phases: ModePhases = Field(default_factory=ModePhases)

    # ── Tool defaults ──
    preferred_tool_categories: list[str] = Field(default_factory=list)
    tool_weights: dict[str, float] = Field(default_factory=dict)

    # ── Evidence rules ──
    source_class_weights: dict[SourceClass, float] = Field(default_factory=dict)
    require_independent_corroboration: bool = False
    confidence_threshold_to_claim: float = Field(default=0.7, ge=0.0, le=1.0)
    treat_absence_as_finding: bool = False

    # ── Priors ──
    hypothesis_seeds: list[str] = Field(default_factory=list)

    # ── Termination ──
    termination: ModeTermination = Field(default_factory=ModeTermination)

    # ── Output shape ──
    output_template: str | None = None
    export_formats: list[str] = Field(default_factory=lambda: ["markdown"])
    audit_trail: Literal["none", "optional", "required"] = "none"

    # ── Open-question framing ──
    open_question_framing: Literal["internal", "strategic", "regulator_visible"] = "internal"
