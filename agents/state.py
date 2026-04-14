"""
LangGraph shared state schema for the Prior Authorization workflow.

Every node in the graph reads from and writes to this TypedDict.
List fields use Annotated[list, operator.add] so that partial updates
from nodes are *appended* rather than overwriting previous entries.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class AgentTiming(TypedDict, total=False):
    """Timing and token data for a single agent invocation."""
    start: float
    end: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class PAState(TypedDict, total=False):
    """
    Complete state flowing through the Prior Authorization LangGraph.

    Sections
    --------
    Patient context   — patient_id, patient_data
    Agent outputs     — research_output, rules_output, pa_decision, writer_output
    Supervisor        — supervisor_notes, guardrail_violations, current_step, retry_count
    HITL              — hitl_approved
    Evaluation        — expected_outcome, expected_reasoning
    Metrics           — metrics (nested dict of timings/tokens/counters)
    Error handling    — error
    """

    # ---- Patient Context ----
    patient_id: str
    patient_data: dict[str, Any]

    # ---- Agent Outputs ----
    eligibility_output: str
    pa_required: bool
    research_output: str
    rules_output: str
    pa_decision: str          # APPROVED | DENIED | NEEDS_MORE_INFO
    writer_output: str

    # ---- Supervisor ----
    supervisor_notes: Annotated[list[str], operator.add]
    guardrail_violations: Annotated[list[str], operator.add]
    current_step: str
    retry_counts: dict[str, int]
    max_retries: int
    escalated_from_agent: str
    escalation_reason: str
    retry_instruction: str

    # ---- Human-in-the-Loop & Payer ----
    hitl_approved: bool
    payer_feedback: str

    # ---- Evaluation ----
    expected_outcome: str
    expected_reasoning: str

    # ---- Metrics (mutable dict replaced on each update) ----
    metrics: dict[str, Any]

    # ---- Error ----
    error: str
