# Continuous Optimization Strategy

This document outlines how the Auto Marketer project self-improves over time through an Agentic Feedback Loop.

## 1. The Data Flywheel
- **Collection:** The `research_agent.py` script conducts OSINT research and saves the state to Postgres.
- **Validation:** The human user grades the research (1-5) via the CLI and provides text feedback.
- **Correction (Short-Term):** Feedback is injected into future prompts via Dynamic Few-Shot Prompting and Episodic Memory (Qdrant). This ensures the agent stops making the same logical errors immediately.
- **Verification:** The `evaluate_grading.py` script and the `pytest` suite track the alignment between the System's Confidence and the Human's Ground Truth over time.
- **Training (Long-Term):** Highly graded data is exported to JSONL to fine-tune a smaller, faster local LLM, reducing latency and cost.

## 2. Agent Handoff Protocol
- Agents must document their findings in `docs/lessons-learned.md`.
- Agents must respect the locks in `tasks/agent-collab.md`.
- Complex decisions requiring architectural shifts must be validated by the user before implementation.
- Tests MUST be written or updated when modifying the grading, ingestion, or research logic.
