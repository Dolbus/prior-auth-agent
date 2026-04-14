"""
LangGraph StateGraph — defines the complete upgraded Prior Authorization workflow.
Includes independent retry loops, human escalations, and post-decision simulation.
"""

from __future__ import annotations
import json
from typing import Any

from langgraph.graph import StateGraph, END, START

from agents.state import PAState
from agents.eligibility_checker import eligibility_checker_node
from agents.research import research_node
from agents.rules_checker import rules_checker_node
from agents.writer import writer_node
from agents.supervisor import (
    validate_eligibility_node,
    validate_research_node,
    validate_rules_node,
    validate_final_node,
)
from agents.post_decision import (
    submit_to_payer_node,
    payer_approved_node,
    payer_denied_node,
    payer_needs_more_info_node,
)
from metrics import collector
from config.settings import settings


# ------------------------------------------------------------------
# HITL / Escalation node
# ------------------------------------------------------------------

def human_review_node(state: dict[str, Any]) -> dict[str, Any]:
    """Human-in-the-loop pause. Acts as an escalation gate and final approval gate."""
    updates = collector.start_agent(state, "human_review")
    state = {**state, **updates}

    patient = state.get("patient_data", {})
    pa_decision = state.get("pa_decision", "UNKNOWN")
    escalated = state.get("current_step") == "escalated_to_human" or state.get("escalated_from_agent")

    print("\n" + "=" * 60)
    print("  🔍  HUMAN-IN-THE-LOOP REVIEW / ESCALATION GATE")
    print("=" * 60)
    print(f"  Patient:    {patient.get('name', 'N/A')}")
    print(f"  Treatment:  {patient.get('requested_treatment', {}).get('name', 'N/A')}")

    if escalated:
        print(f"  ⚠️ ESCALATION ALERT ⚠️")
        print(f"  Failed Agent:  {state.get('escalated_from_agent')}")
        print(f"  Reason:        {state.get('escalation_reason')}")
    else:
        print(f"  PA Decision: {pa_decision}")

    if settings.hitl_enabled:
        try:
            response = input("\n  ➤  Approve/Resolve this case? (yes/no): ").strip().lower()
            approved = response in ("yes", "y", "")
        except (EOFError, KeyboardInterrupt):
            approved = True
    else:
        approved = True
        print("  [HITL disabled — auto-approving/resolving]")

    status = "✅ RESOLVED/APPROVED" if approved else "❌ REJECTED"
    print(f"\n  Human review: {status}")
    print("=" * 60 + "\n")

    end_updates = collector.end_agent(state, "human_review")
    # Clean up escalation flags since human handled it
    return {
        **end_updates,
        "hitl_approved": approved,
        "current_step": "hitl_complete",
        "supervisor_notes": [f"[HITL] Review status: {'APPROVED' if approved else 'REJECTED'}."],
    }


# ------------------------------------------------------------------
# Routing functions
# ------------------------------------------------------------------

def route_after_eligibility(state: dict[str, Any]) -> str:
    step = state.get("current_step")
    if step == "escalated_to_human": return "human_review"
    if step == "eligibility_retry_needed": return "eligibility_checker"
    if not state.get("pa_required", True): return END # fast track exit
    return "research"

def route_after_research(state: dict[str, Any]) -> str:
    step = state.get("current_step")
    if step == "escalated_to_human": return "human_review"
    if step == "research_retry_needed": return "research"
    return "rules_checker"

def route_after_rules(state: dict[str, Any]) -> str:
    step = state.get("current_step")
    if step == "escalated_to_human": return "human_review"
    if step == "rules_retry_needed": return "rules_checker"
    return "writer"

def route_after_writer(state: dict[str, Any]) -> str:
    step = state.get("current_step")
    if step == "escalated_to_human": return "human_review"
    if step == "final_retry_needed": return "writer"
    return "human_review"

def route_after_hitl(state: dict[str, Any]) -> str:
    if state.get("hitl_approved", False):
        return "submit_to_payer"
    return END

def route_post_payer(state: dict[str, Any]) -> str:
    decision = state.get("pa_decision", "APPROVED").upper()
    if "DENIED" in decision:
        return "payer_denied"
    elif "NEEDS_MORE_INFO" in decision or "NEEDS" in decision:
        return "payer_needs_more_info"
    return "payer_approved"


# ------------------------------------------------------------------
# Graph builder
# ------------------------------------------------------------------

def build_graph() -> StateGraph:
    builder = StateGraph(PAState)

    builder.add_node("eligibility_checker", eligibility_checker_node)
    builder.add_node("validate_eligibility", validate_eligibility_node)
    builder.add_node("research", research_node)
    builder.add_node("validate_research", validate_research_node)
    builder.add_node("rules_checker", rules_checker_node)
    builder.add_node("validate_rules", validate_rules_node)
    builder.add_node("writer", writer_node)
    builder.add_node("validate_final", validate_final_node)
    builder.add_node("human_review", human_review_node)
    
    # Post-Decision Payer Nodes
    builder.add_node("submit_to_payer", submit_to_payer_node)
    builder.add_node("payer_approved", payer_approved_node)
    builder.add_node("payer_denied", payer_denied_node)
    builder.add_node("payer_needs_more_info", payer_needs_more_info_node)

    # Linear core edges
    builder.add_edge(START, "eligibility_checker")
    builder.add_edge("eligibility_checker", "validate_eligibility")
    builder.add_edge("research", "validate_research")
    builder.add_edge("rules_checker", "validate_rules")
    builder.add_edge("writer", "validate_final")
    
    # Terminal edges for Post-Decision paths
    builder.add_edge("payer_approved", END)
    builder.add_edge("payer_denied", END)
    builder.add_edge("payer_needs_more_info", END)

    # Conditional Routers
    builder.add_conditional_edges(
        "validate_eligibility", route_after_eligibility,
        {"eligibility_checker": "eligibility_checker", "research": "research", "human_review": "human_review", END: END}
    )
    builder.add_conditional_edges(
        "validate_research", route_after_research,
        {"research": "research", "rules_checker": "rules_checker", "human_review": "human_review"}
    )
    builder.add_conditional_edges(
        "validate_rules", route_after_rules,
        {"rules_checker": "rules_checker", "writer": "writer", "human_review": "human_review"}
    )
    builder.add_conditional_edges(
        "validate_final", route_after_writer,
        {"writer": "writer", "human_review": "human_review"}
    )
    builder.add_conditional_edges(
        "human_review", route_after_hitl,
        {"submit_to_payer": "submit_to_payer", END: END}
    )
    builder.add_conditional_edges(
        "submit_to_payer", route_post_payer,
        {"payer_approved": "payer_approved", "payer_denied": "payer_denied", "payer_needs_more_info": "payer_needs_more_info"}
    )

    return builder.compile()


def load_patients() -> list[dict]:
    patients_path = settings.patients_file
    if not patients_path.exists():
        raise FileNotFoundError(f"Patients file not found: {patients_path}")
    return json.loads(patients_path.read_text())

def create_initial_state(patient: dict) -> dict[str, Any]:
    return {
        "patient_id": patient["id"],
        "patient_data": patient,
        "eligibility_output": "",
        "pa_required": True,
        "research_output": "",
        "rules_output": "",
        "pa_decision": "",
        "writer_output": "",
        "supervisor_notes": [],
        "guardrail_violations": [],
        "current_step": "initialized",
        "retry_counts": {},
        "max_retries": settings.max_retries,
        "escalated_from_agent": "",
        "escalation_reason": "",
        "hitl_approved": False,
        "payer_feedback": "",
        "expected_outcome": patient.get("expected_outcome", ""),
        "expected_reasoning": patient.get("expected_reasoning", ""),
        "metrics": {},
        "error": "",
    }
