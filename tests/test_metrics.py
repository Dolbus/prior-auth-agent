"""
Tests for the metrics collector and evaluator modules.

Verifies that:
  - Timing data is captured correctly
  - Token counts accumulate
  - Guardrail and handoff counters work
  - compute_final_metrics returns all 8 AgentOps KPIs
  - Evaluator scores accuracy correctly
"""

from __future__ import annotations

import time

import pytest

from metrics import collector
from metrics.evaluator import evaluate_accuracy, _normalize_decision


class TestMetricsCollector:

    def test_start_and_end_run(self):
        state = {}
        result = collector.start_run(state)
        assert result["metrics"]["run_start"] > 0

        state = {**state, **result}
        result = collector.end_run(state, completed=True)
        assert result["metrics"]["run_end"] >= result["metrics"]["run_start"]
        assert result["metrics"]["completed"] is True

    def test_agent_timing(self):
        state = {}
        state = {**state, **collector.start_run(state)}

        # Start an agent
        state = {**state, **collector.start_agent(state, "test_agent")}
        time.sleep(0.01)  # Small delay
        state = {**state, **collector.end_agent(state, "test_agent", 100, 50)}

        timings = state["metrics"]["agent_timings"]["test_agent"]
        assert timings["start"] > 0
        assert timings["end"] >= timings["start"]
        assert timings["prompt_tokens"] == 100
        assert timings["completion_tokens"] == 50

    def test_token_accumulation(self):
        state = {}
        state = {**state, **collector.start_run(state)}

        state = {**state, **collector.start_agent(state, "agent1")}
        state = {**state, **collector.end_agent(state, "agent1", 100, 50)}

        state = {**state, **collector.start_agent(state, "agent2")}
        state = {**state, **collector.end_agent(state, "agent2", 200, 100)}

        assert state["metrics"]["total_prompt_tokens"] == 300
        assert state["metrics"]["total_completion_tokens"] == 150
        assert state["metrics"]["total_tokens"] == 450

    def test_guardrail_check_counting(self):
        state = {}
        state = {**state, **collector.start_run(state)}

        state = {**state, **collector.record_guardrail_check(state, passed=True)}
        state = {**state, **collector.record_guardrail_check(state, passed=True)}
        state = {**state, **collector.record_guardrail_check(state, passed=False)}

        assert state["metrics"]["guardrail_checks_total"] == 3
        assert state["metrics"]["guardrail_violations_total"] == 1

    def test_handoff_counting(self):
        state = {}
        state = {**state, **collector.start_run(state)}

        state = {**state, **collector.record_handoff(state, success=True)}
        state = {**state, **collector.record_handoff(state, success=True)}
        state = {**state, **collector.record_handoff(state, success=False)}

        assert state["metrics"]["handoff_attempts"] == 3
        assert state["metrics"]["handoff_successes"] == 2

    def test_compute_final_metrics_has_all_kpis(self):
        state = {}
        state = {**state, **collector.start_run(state)}

        state = {**state, **collector.start_agent(state, "a1")}
        state = {**state, **collector.end_agent(state, "a1", 100, 50)}

        state = {**state, **collector.start_agent(state, "a2")}
        state = {**state, **collector.end_agent(state, "a2", 200, 100)}

        state = {**state, **collector.record_guardrail_check(state, passed=True)}
        state = {**state, **collector.record_guardrail_check(state, passed=False)}
        state = {**state, **collector.record_handoff(state, success=True)}
        state = {**state, **collector.record_handoff(state, success=False)}

        state = {**state, **collector.end_run(state, completed=True)}

        metrics = collector.compute_final_metrics(state)

        # All 8 KPIs should be present
        assert "end_to_end_duration_sec" in metrics
        assert "handoff_latencies" in metrics
        assert "cost_usd" in metrics
        assert "task_completed" in metrics
        assert "guardrail_violation_rate" in metrics
        assert "prompt_token_efficiency" in metrics
        assert "handoff_success_rate" in metrics
        assert "agent_timings" in metrics

        # Verify computed values
        assert metrics["end_to_end_duration_sec"] >= 0
        assert metrics["cost_usd"] >= 0
        assert metrics["task_completed"] is True
        assert metrics["guardrail_violation_rate"] == 0.5  # 1/2
        assert metrics["handoff_success_rate"] == 0.5  # 1/2
        assert metrics["total_tokens"] == 450

    def test_compute_final_metrics_zero_division(self):
        """Should handle zero-division cases gracefully."""
        state = {}
        state = {**state, **collector.start_run(state)}
        state = {**state, **collector.end_run(state)}

        metrics = collector.compute_final_metrics(state)

        assert metrics["guardrail_violation_rate"] == 0.0
        assert metrics["prompt_token_efficiency"] == 0.0
        assert metrics["handoff_success_rate"] == 0.0


class TestEvaluator:

    def test_exact_match(self):
        state = {"pa_decision": "APPROVED", "expected_outcome": "APPROVED"}
        result = evaluate_accuracy(state)
        assert result["match"] is True
        assert result["factual_accuracy"] == 1.0

    def test_mismatch(self):
        state = {"pa_decision": "APPROVED", "expected_outcome": "DENIED"}
        result = evaluate_accuracy(state)
        assert result["match"] is False
        assert result["factual_accuracy"] == 0.0

    def test_normalize_variants(self):
        assert _normalize_decision("APPROVE") == "APPROVED"
        assert _normalize_decision("DENY") == "DENIED"
        assert _normalize_decision("NEEDS MORE INFO") == "NEEDS_MORE_INFO"
        assert _normalize_decision("PENDING") == "NEEDS_MORE_INFO"
        assert _normalize_decision("REJECTED") == "DENIED"
        assert _normalize_decision("YES") == "APPROVED"
        assert _normalize_decision("NO") == "DENIED"

    def test_case_insensitive(self):
        state = {"pa_decision": "approved", "expected_outcome": "APPROVED"}
        result = evaluate_accuracy(state)
        assert result["match"] is True
