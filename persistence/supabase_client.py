"""
Supabase persistence client — writes case results and audit log rows.

Reads SUPABASE_URL and SUPABASE_KEY from environment (via settings).
All writes are best-effort: failures are logged but do not break the
PA workflow.
"""

from __future__ import annotations

import traceback
from datetime import datetime, timezone
from typing import Any

from config.settings import settings


def _get_client():
    """Lazily create and return the Supabase client."""
    if not settings.supabase_enabled:
        return None
    try:
        from supabase import create_client
        return create_client(settings.supabase_url, settings.supabase_key)
    except Exception as e:
        print(f"  ⚠️  Supabase client init failed: {e}")
        return None


def write_case_result(result: dict[str, Any]) -> str | None:
    """Insert a case result row into Supabase.

    Args:
        result: The result dict from run_single_patient() containing
                patient_id, patient_name, pa_decision, metrics, etc.

    Returns:
        The UUID of the inserted row, or None on failure.
    """
    client = _get_client()
    if client is None:
        return None

    metrics = result.get("metrics", {})
    patient_data = result.get("patient_data", {})
    treatment = patient_data.get("requested_treatment", {})
    diagnosis = patient_data.get("diagnosis", {})
    insurance = patient_data.get("insurance", {})

    row = {
        "patient_id": result.get("patient_id", ""),
        "patient_name": result.get("patient_name", ""),
        "treatment": treatment.get("name", ""),
        "diagnosis": diagnosis.get("primary", ""),
        "insurance_provider": insurance.get("provider", ""),
        "pa_decision": result.get("pa_decision", ""),
        "expected_outcome": result.get("expected_outcome", ""),
        "factual_accuracy": result.get("accuracy", {}).get("factual_accuracy", 0.0),
        "duration_sec": metrics.get("end_to_end_duration_sec", 0.0),
        "total_prompt_tokens": metrics.get("total_prompt_tokens", 0),
        "total_completion_tokens": metrics.get("total_completion_tokens", 0),
        "total_tokens": metrics.get("total_tokens", 0),
        "cost_usd": metrics.get("cost_usd", 0.0),
        "guardrail_violation_rate": metrics.get("guardrail_violation_rate", 0.0),
        "guardrail_checks_total": metrics.get("guardrail_checks_total", 0),
        "guardrail_violations_total": metrics.get("guardrail_violations_total", 0),
        "handoff_success_rate": metrics.get("handoff_success_rate", 0.0),
        "handoff_attempts": metrics.get("handoff_attempts", 0),
        "handoff_successes": metrics.get("handoff_successes", 0),
        "prompt_token_efficiency": metrics.get("prompt_token_efficiency", 0.0),
        "writer_output": result.get("writer_output", ""),
        "supervisor_notes": result.get("supervisor_notes", []),
        "guardrail_violations": result.get("guardrail_violations", []),
        "pa_required": result.get("pa_required", True),
        "escalated": result.get("escalated", False),
        "payer_feedback": result.get("payer_feedback", ""),
    }

    try:
        response = client.table("case_results").insert(row).execute()
        case_id = response.data[0]["id"] if response.data else None
        print(f"  📦 Supabase: case_results row written (ID: {case_id})")
        return case_id
    except Exception as e:
        print(f"  ⚠️  Supabase case_results write failed: {e}")
        traceback.print_exc()
        return None


def write_audit_log(case_id: str, metrics: dict[str, Any], supervisor_notes: list[str]) -> int:
    """Insert audit log rows for each agent step in a case run.

    Args:
        case_id: The UUID of the parent case_results row.
        metrics: The final_metrics dict with agent_timings.
        supervisor_notes: List of supervisor log messages.

    Returns:
        Number of audit rows successfully written.
    """
    client = _get_client()
    if client is None or not case_id:
        return 0

    agent_timings = metrics.get("agent_timings", {})
    rows_written = 0

    # Build a lookup from supervisor notes
    notes_by_agent: dict[str, list[str]] = {}
    for note in supervisor_notes:
        # Notes are formatted like "[AgentName] message"
        for agent_name in agent_timings:
            agent_label = agent_name.replace("_", " ").title()
            if f"[{agent_label}]" in note or f"[{agent_name}]" in note:
                notes_by_agent.setdefault(agent_name, []).append(note)
                break
        else:
            # Supervisor or HITL notes
            if "[Supervisor]" in note:
                notes_by_agent.setdefault("supervisor", []).append(note)
            elif "[HITL]" in note:
                notes_by_agent.setdefault("human_review", []).append(note)

    for agent_name, timing in agent_timings.items():
        # Determine step type
        if "validate" in agent_name or "supervisor" in agent_name:
            step_type = "validation"
        elif agent_name == "human_review":
            step_type = "hitl"
        else:
            step_type = "agent"

        # Determine if this was a guardrail check
        is_validation = step_type == "validation"

        row = {
            "case_id": case_id,
            "agent_name": agent_name,
            "step_type": step_type,
            "duration_sec": timing.get("duration_sec", 0.0),
            "prompt_tokens": timing.get("prompt_tokens", 0),
            "completion_tokens": timing.get("completion_tokens", 0),
            "total_tokens": timing.get("prompt_tokens", 0) + timing.get("completion_tokens", 0),
            "guardrail_checks": 1 if is_validation else 0,
            "guardrail_violations": 0,  # Individual violations tracked in case_results
            "handoff_attempted": is_validation,
            "handoff_succeeded": is_validation,  # If we got past validation, handoff succeeded
            "notes": " | ".join(notes_by_agent.get(agent_name, [])) or None,
            "escalated_from": metrics.get("escalation_details", {}).get("agent", "") if step_type == "hitl" else None,
            "retry_count": timing.get("retries", 0),
        }

        try:
            client.table("audit_log").insert(row).execute()
            rows_written += 1
        except Exception as e:
            print(f"  ⚠️  Supabase audit_log write failed for {agent_name}: {e}")

    if rows_written > 0:
        print(f"  📦 Supabase: {rows_written} audit_log rows written")

    return rows_written


def read_case_results(limit: int = 100) -> list[dict]:
    """Read case results from Supabase (for dashboard).

    Returns a list of dicts, newest first.
    """
    client = _get_client()
    if client is None:
        return []

    try:
        response = (
            client.table("case_results")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data or []
    except Exception as e:
        print(f"  ⚠️  Supabase read case_results failed: {e}")
        return []


def read_audit_log(case_id: str | None = None, limit: int = 500) -> list[dict]:
    """Read audit log rows from Supabase (for dashboard).

    Args:
        case_id: Optional — filter to a specific case.
        limit: Max rows to return.

    Returns a list of dicts, newest first.
    """
    client = _get_client()
    if client is None:
        return []

    try:
        query = client.table("audit_log").select("*").order("created_at", desc=True).limit(limit)
        if case_id:
            query = query.eq("case_id", case_id)
        response = query.execute()
        return response.data or []
    except Exception as e:
        print(f"  ⚠️  Supabase read audit_log failed: {e}")
        return []
