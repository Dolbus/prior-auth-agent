"""
Metrics Collector — captures all 8 AgentOps metrics in the PAState.

Provides helper functions that agent nodes call to record timing, token
usage, guardrail checks, and handoff results.  All raw data is stored
in state["metrics"]; derived KPIs are computed at the end via
`compute_final_metrics()`.
"""

from __future__ import annotations

import time
from copy import deepcopy
from typing import Any

from config.settings import settings


def _ensure_metrics(state: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of the metrics dict, creating it if absent."""
    return deepcopy(state.get("metrics") or {
        "run_start": 0.0,
        "run_end": 0.0,
        "agent_timings": {},
        "guardrail_checks_total": 0,
        "guardrail_violations_total": 0,
        "handoff_attempts": 0,
        "handoff_successes": 0,
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "total_tokens": 0,
        "completed": False,
    })


# ------------------------------------------------------------------
# Run-level helpers
# ------------------------------------------------------------------

def start_run(state: dict[str, Any]) -> dict[str, Any]:
    """Mark the beginning of the full pipeline run."""
    m = _ensure_metrics(state)
    m["run_start"] = time.time()
    return {"metrics": m}


def end_run(state: dict[str, Any], completed: bool = True) -> dict[str, Any]:
    """Mark the end of the full pipeline run."""
    m = _ensure_metrics(state)
    m["run_end"] = time.time()
    m["completed"] = completed
    return {"metrics": m}


# ------------------------------------------------------------------
# Agent-level helpers
# ------------------------------------------------------------------

def start_agent(state: dict[str, Any], agent_name: str) -> dict[str, Any]:
    """Record the start time for a named agent."""
    m = _ensure_metrics(state)
    m["agent_timings"].setdefault(agent_name, {})
    m["agent_timings"][agent_name]["start"] = time.time()
    return {"metrics": m}


def end_agent(
    state: dict[str, Any],
    agent_name: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> dict[str, Any]:
    """Record end time and token usage for a named agent."""
    m = _ensure_metrics(state)
    timing = m["agent_timings"].setdefault(agent_name, {})
    timing["end"] = time.time()
    timing["prompt_tokens"] = prompt_tokens
    timing["completion_tokens"] = completion_tokens
    timing["total_tokens"] = prompt_tokens + completion_tokens

    # Accumulate totals
    m["total_prompt_tokens"] += prompt_tokens
    m["total_completion_tokens"] += completion_tokens
    m["total_tokens"] += prompt_tokens + completion_tokens
    return {"metrics": m}


# ------------------------------------------------------------------
# Guardrail & handoff helpers
# ------------------------------------------------------------------

def record_guardrail_check(
    state: dict[str, Any], passed: bool
) -> dict[str, Any]:
    """Increment guardrail check counters."""
    m = _ensure_metrics(state)
    m["guardrail_checks_total"] += 1
    if not passed:
        m["guardrail_violations_total"] += 1
    return {"metrics": m}


def record_handoff(
    state: dict[str, Any], success: bool
) -> dict[str, Any]:
    """Increment handoff counters."""
    m = _ensure_metrics(state)
    m["handoff_attempts"] += 1
    if success:
        m["handoff_successes"] += 1
    return {"metrics": m}


# ------------------------------------------------------------------
# Final metric computation
# ------------------------------------------------------------------

def compute_final_metrics(state: dict[str, Any]) -> dict[str, Any]:
    """Derive all 8 AgentOps KPIs from raw collected data.

    Returns a summary dict with:
      1. end_to_end_duration_sec
      2. handoff_latencies  (per transition)
      3. cost_usd
      4. task_completed
      5. guardrail_violation_rate
      6. prompt_token_efficiency
      7. handoff_success_rate
      8. factual_accuracy  (placeholder — filled by evaluator)
    """
    m = _ensure_metrics(state)

    # 1. End-to-end duration
    duration = m["run_end"] - m["run_start"] if m["run_end"] else 0.0

    # 2. Handoff latencies
    ordered_agents = sorted(
        m["agent_timings"].items(),
        key=lambda x: x[1].get("start", 0),
    )
    handoff_latencies: dict[str, float] = {}
    for i in range(1, len(ordered_agents)):
        prev_name, prev_t = ordered_agents[i - 1]
        curr_name, curr_t = ordered_agents[i]
        prev_end = prev_t.get("end", 0)
        curr_start = curr_t.get("start", 0)
        key = f"{prev_name} → {curr_name}"
        handoff_latencies[key] = round(curr_start - prev_end, 4)

    # 3. Cost (GPT-4o mini pricing)
    input_cost = (m["total_prompt_tokens"] / 1_000_000) * settings.input_cost_per_million
    output_cost = (m["total_completion_tokens"] / 1_000_000) * settings.output_cost_per_million
    total_cost = round(input_cost + output_cost, 6)

    # 4. Task completion
    task_completed = m.get("completed", False)

    # 5. Guardrail violation rate
    gc = m["guardrail_checks_total"]
    gv_rate = round(m["guardrail_violations_total"] / gc, 4) if gc > 0 else 0.0

    # 6. Prompt token efficiency (output / input ratio)
    pt = m["total_prompt_tokens"]
    efficiency = round(m["total_completion_tokens"] / pt, 4) if pt > 0 else 0.0

    # 7. Handoff success rate
    ha = m["handoff_attempts"]
    hs_rate = round(m["handoff_successes"] / ha, 4) if ha > 0 else 0.0

    return {
        "end_to_end_duration_sec": round(duration, 3),
        "handoff_latencies": handoff_latencies,
        "cost_usd": total_cost,
        "total_prompt_tokens": m["total_prompt_tokens"],
        "total_completion_tokens": m["total_completion_tokens"],
        "total_tokens": m["total_tokens"],
        "task_completed": task_completed,
        "guardrail_violation_rate": gv_rate,
        "guardrail_checks_total": gc,
        "guardrail_violations_total": m["guardrail_violations_total"],
        "prompt_token_efficiency": efficiency,
        "handoff_success_rate": hs_rate,
        "handoff_attempts": m["handoff_attempts"],
        "handoff_successes": m["handoff_successes"],
        "agent_timings": {
            name: {
                "duration_sec": round(t.get("end", 0) - t.get("start", 0), 3),
                "prompt_tokens": t.get("prompt_tokens", 0),
                "completion_tokens": t.get("completion_tokens", 0),
            }
            for name, t in m["agent_timings"].items()
        },
    }
