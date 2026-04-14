"""
Evaluator — compares agent outputs to expected outcomes for factual
accuracy scoring.

Used after the graph completes to measure how well the agents did
against the ground-truth labels in the mock patient data.
"""

from __future__ import annotations

from typing import Any


def evaluate_accuracy(state: dict[str, Any]) -> dict[str, Any]:
    """Score the PA decision against the expected outcome.

    Returns a dict with:
      - factual_accuracy: 1.0 if decision matches expected, else 0.0
      - decision: the agent's PA decision
      - expected: the expected outcome from mock data
      - match: bool
      - notes: explanation
    """
    decision = (state.get("pa_decision") or "").strip().upper()
    if not decision and state.get("escalated_from_agent"):
        decision = "ESCALATED"
        
    expected = (state.get("expected_outcome") or "").strip().upper()

    # Normalize common variants
    decision_normalized = _normalize_decision(decision)
    expected_normalized = _normalize_decision(expected)

    match = decision_normalized == expected_normalized

    notes = (
        f"Decision '{decision}' matches expected '{expected}'."
        if match
        else f"MISMATCH: Agent decided '{decision}' but expected '{expected}'."
    )

    return {
        "factual_accuracy": 1.0 if match else 0.0,
        "decision": decision,
        "expected": expected,
        "match": match,
        "notes": notes,
    }


def _normalize_decision(raw: str) -> str:
    """Map various decision strings to canonical form."""
    raw = raw.strip().upper().replace(" ", "_").replace("-", "_")
    approved_variants = {"APPROVED", "APPROVE", "YES", "AUTHORIZED"}
    denied_variants = {"DENIED", "DENY", "NO", "REJECTED", "REJECT"}
    pending_variants = {"NEEDS_MORE_INFO", "PENDING", "NEEDS_INFO", "INCOMPLETE", "MORE_INFO_NEEDED"}
    escalated_variants = {"ESCALATED", "ESCALATION", "VALID_ESCALATION"}

    if raw in approved_variants:
        return "APPROVED"
    if raw in denied_variants:
        return "DENIED"
    if raw in pending_variants:
        return "NEEDS_MORE_INFO"
    if raw in escalated_variants:
        return "ESCALATED"
    return raw


def generate_evaluation_report(
    state: dict[str, Any],
    accuracy_result: dict[str, Any],
    final_metrics: dict[str, Any],
) -> str:
    """Produce a human-readable evaluation report combining accuracy + metrics."""
    patient = state.get("patient_data", {})
    lines = [
        "=" * 60,
        "  AGENTOPS EVALUATION REPORT",
        "=" * 60,
        "",
        f"  Patient:   {patient.get('name', 'N/A')} ({state.get('patient_id', 'N/A')})",
        f"  Treatment: {patient.get('requested_treatment', {}).get('name', 'N/A')}",
        "",
        "─" * 60,
        "  ACCURACY",
        "─" * 60,
        f"  Decision:          {accuracy_result['decision']}",
        f"  Expected:          {accuracy_result['expected']}",
        f"  Match:             {'✅ YES' if accuracy_result['match'] else '❌ NO'}",
        f"  Factual Accuracy:  {accuracy_result['factual_accuracy']:.0%}",
        "",
        "─" * 60,
        "  PERFORMANCE METRICS",
        "─" * 60,
        f"  End-to-End Duration:     {final_metrics['end_to_end_duration_sec']:.2f}s",
        f"  Total Tokens:            {final_metrics['total_tokens']:,}",
        f"  Cost (USD):              ${final_metrics['cost_usd']:.6f}",
        f"  Task Completed:          {'✅' if final_metrics['task_completed'] else '❌'}",
        f"  Guardrail Violation Rate: {final_metrics['guardrail_violation_rate']:.1%}",
        f"  Prompt Token Efficiency:  {final_metrics['prompt_token_efficiency']:.3f}",
        f"  Handoff Success Rate:     {final_metrics['handoff_success_rate']:.1%}",
        "",
        "─" * 60,
        "  AGENT TIMINGS",
        "─" * 60,
    ]

    for agent_name, timing in final_metrics.get("agent_timings", {}).items():
        lines.append(
            f"  {agent_name:<30} "
            f"{timing['duration_sec']:>6.2f}s  "
            f"{timing['prompt_tokens']:>5}p  "
            f"{timing['completion_tokens']:>5}c tokens"
        )

    lines.append("")
    lines.append("─" * 60)
    lines.append("  HANDOFF LATENCIES")
    lines.append("─" * 60)
    for transition, latency in final_metrics.get("handoff_latencies", {}).items():
        lines.append(f"  {transition:<40} {latency:>8.4f}s")

    lines.extend(["", "=" * 60])
    return "\n".join(lines)
