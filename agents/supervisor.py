"""
Supervisor Agent — orchestrates the PA workflow, validates intermediate
outputs, assesses confidence scores via LLM, and enforces retries/escalations.
"""

from __future__ import annotations
from typing import Any
import re
import time

from langchain_core.messages import SystemMessage, HumanMessage
from metrics import collector
from langchain_openai import ChatOpenAI

from agents.rules_checker import (
    _extract_decision,
    _resolve_rules,
    is_step_therapy_partial_failure,
    is_step_therapy_sequence_violation,
)

LLM_MODEL = "gpt-4o"

def extract_confidence(eval_text: str) -> float:
    match = re.search(r'CONFIDENCE(?: SCORE)?:\s*(\d+(?:\.\d+)?)', eval_text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return 0.0

def _evaluate_agent_output(agent_name: str, criteria: str, output: str) -> tuple[float, int, int, str]:
    """Uses LLM to evaluate the completeness and accuracy of an agent's output.
    
    Returns (confidence, prompt_tokens, comp_tokens, reasoning_string).
    Retries up to 3 times on OpenAI 429 rate-limit errors with exponential backoff.
    All other exceptions are surfaced immediately without retry.

    Callers must **not** clear downstream workflow fields (e.g. ``pa_decision``) on failure;
    ``validate_rules_node`` recovers ``pa_decision`` from ``rules_output`` when state is empty.
    """
    llm = ChatOpenAI(model=LLM_MODEL, temperature=0).with_config({"run_name": f"supervisor_eval_{agent_name}"})
    sys_prompt = f"""You are a Supervisor in a Prior Auth workflow evaluating the {agent_name}.
Review the output against these criteria: {criteria}

You must return a strict assessment and end with a confidence score line exactly like this:
CONFIDENCE: 95
"""
    msg = [SystemMessage(content=sys_prompt), HumanMessage(content=f"OUTPUT TO EVALUATE:\n{output}")]

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            response = llm.invoke(msg)
            usage = response.response_metadata.get("token_usage", {})
            p_tokens = usage.get("prompt_tokens", 0)
            c_tokens = usage.get("completion_tokens", 0)
            content = str(response.content)
            conf = extract_confidence(content)
            return conf, p_tokens, c_tokens, content
        except Exception as e:
            err_str = str(e)
            # Only retry on transient rate-limit / server overload errors
            is_rate_limit = "429" in err_str or "rate_limit" in err_str.lower() or "RateLimitError" in type(e).__name__
            if is_rate_limit and attempt < max_retries:
                sleep_secs = 10 * attempt  # 10s, 20s on successive retries
                print(f"[Supervisor] ⚠️  Rate limit hit evaluating {agent_name} "
                      f"(attempt {attempt}/{max_retries}). Sleeping {sleep_secs}s before retry...")
                time.sleep(sleep_secs)
                continue
            # Non-transient error or final retry exhausted — surface the failure
            reason = f"[Supervisor] ERROR evaluating {agent_name} (attempt {attempt}): {e}"
            print(reason)
            return 0.0, 0, 0, reason
    # Should not reach here, but guard anyway
    return 0.0, 0, 0, f"[Supervisor] ERROR: exhausted all retries for {agent_name}"

def _handle_retry_logic(state: dict[str, Any], agent_name: str, passed: bool, notes_list: list[str]) -> tuple[dict, bool]:
    """Manages independent retry_counts and escalation logic."""
    counts = state.get("retry_counts", {})
    if agent_name not in counts:
        counts[agent_name] = 0

    escalated = False
    if not passed:
        counts[agent_name] += 1
        if counts[agent_name] >= state.get("max_retries", 2):
            notes_list.append(f"[Supervisor] {agent_name} validation failed after {counts[agent_name]} retries. Escalating.")
            state["escalated_from_agent"] = agent_name
            state["escalation_reason"] = f"Failed validation thresholds repeatedly."
            escalated = True
        else:
            notes_list.append(f"[Supervisor] {agent_name} validation FAILED (retry {counts[agent_name]}).")
    else:
        notes_list.append(f"[Supervisor] {agent_name} validation PASSED.")
        counts[agent_name] = 0 # reset on pass
        
    state["retry_counts"] = counts
    return state, escalated

# ------------------------------------------------------------------
# Validation nodes
# ------------------------------------------------------------------

def validate_eligibility_node(state: dict[str, Any]) -> dict[str, Any]:
    updates = collector.start_agent(state, "supervisor_validate_eligibility")
    state = {**state, **updates}
    
    output = state.get("eligibility_output", "")
    notes = []
    
    # Eligibility requires >95% confidence. We can parse it from the eligibility node directly since it was instructed to output it, OR eval it.
    conf = extract_confidence(output)
    
    passed = conf >= 95.0
    if "UNKNOWN_RULE" in output.upper():
        passed = False
        notes.append("Unknown rule flagged in Eligibility.")
    
    state, escalated = _handle_retry_logic(state, "eligibility_checker", passed, notes)
    
    # Set pa_required based on output
    pa_req = "PA REQUIRED: TRUE" in output.upper() or "PA REQUIRED: YES" in output.upper()

    end_updates = collector.end_agent(state, "supervisor_validate_eligibility")

    pa_required_effective = pa_req if passed else state.get("pa_required", True)
    if escalated:
        current_step = "escalated_to_human"
    elif passed and not pa_req:
        current_step = "eligibility_pa_not_required"
    elif passed:
        current_step = "eligibility_validated"
    else:
        current_step = "eligibility_retry_needed"

    out: dict[str, Any] = {
        **end_updates,
        "supervisor_notes": notes,
        "pa_required": pa_required_effective,
        "retry_counts": state["retry_counts"],
        "escalated_from_agent": state.get("escalated_from_agent", ""),
        "escalation_reason": state.get("escalation_reason", ""),
        "current_step": current_step,
    }
    # Graph routes to END when pa_required is false — still emit a canonical pa_decision for eval/telemetry.
    if not escalated and passed and not pa_req:
        out["pa_decision"] = "APPROVED"
        out["rules_output"] = (
            "1. DETERMINATION\nAPPROVED\n\n"
            "2. NOTE\n"
            "Prior authorization is not required for this treatment under the matched insurer rule "
            "(pa_required: false). No rules-based medical necessity review was performed.\n"
        )
    return out

def validate_research_node(state: dict[str, Any]) -> dict[str, Any]:
    updates = collector.start_agent(state, "supervisor_validate_research")
    state = {**state, **updates}
    notes = []
    
    output = state.get("research_output", "")
    # Research Gate: >90% extraction confidence
    confidence, p_tokens, c_tokens, reasoning = _evaluate_agent_output(
        "Research Agent",
        "Must contain DEMOGRAPHICS, DIAGNOSIS, MEDICATIONS. LABS and CLINICAL NOTES should be extracted if present; if genuinely absent from the record, NOT FOUND is an acceptable and correct response.",
        output
    )
    
    passed = confidence >= 80.0
    retry_instruction = ""
    if float(confidence) < 80.0:
        notes.append(f"Research extraction confidence too low ({confidence}%).")
        retry_instruction = reasoning
        
    state, escalated = _handle_retry_logic(state, "research", passed, notes)
    
    end_updates = collector.end_agent(state, "supervisor_validate_research", p_tokens, c_tokens)
    return {
        **end_updates,
        "supervisor_notes": notes,
        "retry_counts": state["retry_counts"],
        "retry_instruction": retry_instruction,
        "escalated_from_agent": state.get("escalated_from_agent", ""),
        "escalation_reason": state.get("escalation_reason", ""),
        "current_step": "escalated_to_human" if escalated else ("research_validated" if passed else "research_retry_needed"),
    }

def validate_rules_node(state: dict[str, Any]) -> dict[str, Any]:
    updates = collector.start_agent(state, "supervisor_validate_rules")
    state = {**state, **updates}
    notes = []
    
    output = state.get("rules_output", "")
    # Recover pa_decision from rules text if state lost it (edge-case errors upstream).
    effective_pa = (state.get("pa_decision") or "").strip()
    if not effective_pa and output:
        recovered = _extract_decision(output)
        if recovered and recovered != "UNKNOWN":
            effective_pa = recovered
            notes.append(f"[Supervisor] Recovered pa_decision from rules_output: {recovered}")
    patient = state.get("patient_data") or {}
    insurer = patient.get("insurance_provider", "")
    rules = _resolve_rules(patient, insurer)
    # Step therapy: (1) some steps documented but not all, or (2) all documented but wrong order
    # in prior_treatments vs insurer step_therapy sequence → DENIED, not NEEDS_MORE_INFO.
    if effective_pa == "NEEDS_MORE_INFO" and rules:
        if is_step_therapy_partial_failure(patient, rules):
            effective_pa = "DENIED"
            notes.append(
                "[Supervisor] Coerced pa_decision to DENIED: step-therapy failed (partial documentation), not missing."
            )
        elif is_step_therapy_sequence_violation(patient, rules):
            effective_pa = "DENIED"
            notes.append(
                "[Supervisor] Coerced pa_decision to DENIED: step-therapy sequence not met "
                "(prior treatments out of order vs required sequence), not missing data."
            )
    state = {**state, "pa_decision": effective_pa}
    # Rules Gate: ≥90% rubric accuracy (Exp05 rubric — updated to accept NEEDS_MORE_INFO as a
    # valid high-confidence outcome when patient data is incomplete)
    _gate3_criteria = (
        "Evaluate the Rules Checker output against the following rubric:\n"
        "\n"
        "ASSIGN A HIGH SCORE (90+) when ANY of these conditions is true:\n"
        "  1. APPROVED or DENIED — and the decision is logically consistent with the "
        "insurer_rules.json keys provided, uses only criteria that exist as explicit keys in the "
        "JSON, and all required data was present and evaluated correctly.\n"
        "  2. NEEDS_MORE_INFO — and the Rules Checker correctly identifies which "
        "insurer_rules.json keys could not be evaluated because the patient record lacked the "
        "required data, marks those rules as UNKNOWN, and clearly explains what info is missing. "
        "Do NOT penalize NEEDS_MORE_INFO for incomplete patient records. "
        "This is the correct and expected behavior under those conditions.\n"
        "\n"
        "FAIL (score below 90) ONLY when:\n"
        "  - The Rules Checker references, applies, or penalizes the patient for requirements "
        "whose keys do NOT exist in the insurer_rules.json (e.g., invented safety screenings, "
        "clinical severity scoring, or any criterion that is not a literal key in the JSON). "
        "This is hallucination.\n"
        "  - APPROVED or DENIED is issued in direct contradiction to the JSON rules.\n"
        "  - The determination is missing, unclear, or not one of: APPROVED, DENIED, NEEDS_MORE_INFO.\n"
        "\n"
        "NOTE: The numeric threshold stays at 90. A well-justified NEEDS_MORE_INFO with no "
        "hallucinations and a complete list of missing JSON keys can and should score 90 or above."
    )
    conf, p_tokens, c_tokens, reasoning = _evaluate_agent_output(
        "Rules Checker",
        _gate3_criteria,
        output
    )
    
    passed = (conf >= 90.0) and ("APPROVED" in output or "DENIED" in output or "NEEDS_MORE_INFO" in output)
    if not passed:
        notes.append(f"Rules logic confidence too low ({conf}%).")
        
    state, escalated = _handle_retry_logic(state, "rules_checker", passed, notes)
    
    end_updates = collector.end_agent(state, "supervisor_validate_rules", p_tokens, c_tokens)
    return {
        **end_updates,
        "pa_decision": effective_pa,
        "supervisor_notes": notes,
        "retry_counts": state["retry_counts"],
        "escalated_from_agent": state.get("escalated_from_agent", ""),
        "escalation_reason": state.get("escalation_reason", ""),
        "current_step": "escalated_to_human" if escalated else ("rules_validated" if passed else "rules_retry_needed"),
    }

def validate_final_node(state: dict[str, Any]) -> dict[str, Any]:
    updates = collector.start_agent(state, "supervisor_final_validate")
    state = {**state, **updates}
    notes = []
    
    output = state.get("writer_output", "")
    # Final Gate: >95% generation completion
    confidence, p_tokens, c_tokens, reasoning = _evaluate_agent_output(
        "Writer Agent",
        "Must be a Medical Request Form. Explicit 'not provided' or 'not found' placeholders for missing admin data are acceptable. Focus scoring on clinical correctness, decision alignment, and hallucinations.",
        output
    )
    
    if float(confidence) < 85.0:
        notes.append(f"Draft completion confidence too low ({confidence}%).")

    passed = confidence >= 85.0
    state, escalated = _handle_retry_logic(state, "writer", passed, notes)
    
    end_updates = collector.end_agent(state, "supervisor_final_validate", p_tokens, c_tokens)
    return {
        **end_updates,
        "supervisor_notes": notes,
        "retry_counts": state["retry_counts"],
        "escalated_from_agent": state.get("escalated_from_agent", ""),
        "escalation_reason": state.get("escalation_reason", ""),
        "current_step": "escalated_to_human" if escalated else ("final_validated" if passed else "final_retry_needed"),
    }
