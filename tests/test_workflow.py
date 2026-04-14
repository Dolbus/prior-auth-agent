"""
Integration test — runs the full LangGraph workflow with mocked LLM,
verifying that the graph compiles, routes correctly, and produces
expected state at the end.
"""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest

from graph.workflow import build_graph, load_patients, create_initial_state
from metrics import collector


def _make_mock_response(content: str, prompt_tokens: int = 80, completion_tokens: int = 150):
    resp = MagicMock()
    resp.content = content
    resp.response_metadata = {
        "token_usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }
    }
    return resp


class TestWorkflowIntegration:

    def test_graph_compiles(self):
        """Graph should compile without errors."""
        graph = build_graph()
        assert graph is not None

    def test_load_patients(self):
        """Should load all mock patients."""
        patients = load_patients()
        assert len(patients) == 120
        assert all("id" in p for p in patients)

    def test_create_initial_state(self):
        """Initial state should have all required keys."""
        patients = load_patients()
        state = create_initial_state(patients[0])

        required_keys = [
            "patient_id", "patient_data", "research_output",
            "rules_output", "pa_decision", "writer_output",
            "supervisor_notes", "guardrail_violations",
            "current_step", "retry_counts", "max_retries",
            "hitl_approved", "expected_outcome", "metrics", "error",
        ]
        for key in required_keys:
            assert key in state, f"Missing key: {key}"

    @patch("agents.supervisor._evaluate_agent_output")
    @patch("agents.writer.ChatOpenAI")
    @patch("agents.rules_checker.ChatOpenAI")
    @patch("agents.research.ChatOpenAI")
    def test_full_workflow_approved(self, mock_research_llm, mock_rules_llm, mock_writer_llm, mock_supervisor_eval):
        """Full workflow for an APPROVED case should reach completion."""
        # Ensure all supervisor gates pass with high confidence
        mock_supervisor_eval.return_value = (95.0, 10, 10, "Looks great!")
        # Mock Research Agent response
        mock_research_llm.return_value.invoke.return_value = _make_mock_response(
            "## PATIENT DEMOGRAPHICS\nMaria Santos, 51, Female\n"
            "## DIAGNOSIS\nRheumatoid Arthritis M05.79\n"
            "## CURRENT MEDICATIONS\nMethotrexate 15mg weekly for 52 weeks — inadequate\n"
            "## REQUESTED TREATMENT\nHumira adalimumab 40mg biweekly\n"
            "## RELEVANT LABS\nRF Factor: Positive, Anti-CCP: Positive\n"
            "## CLINICAL NOTES SUMMARY\nBilateral MCP joint swelling\n"
            "## STEP THERAPY HISTORY\nMethotrexate 52 weeks — inadequate response"
        )

        # Mock Rules Checker response
        mock_rules_llm.return_value.invoke.return_value = _make_mock_response(
            "## DETERMINATION: APPROVED\n\n"
            "## CRITERIA EVALUATION\n"
            "Step therapy: MET\nSafety screening: MET\n\n"
            "## REASONING\nAll criteria met for Humira."
        )

        # Mock Writer response
        mock_writer_llm.return_value.invoke.return_value = _make_mock_response(
            "PRIOR AUTHORIZATION REQUEST — APPROVED\n\n"
            "SECTION 1: PATIENT INFORMATION\nMaria Santos\n\n"
            "SECTION 2: CLINICAL SUMMARY\nRA moderate-to-severe\n\n"
            "SECTION 3: REQUESTED TREATMENT\nHumira\n\n"
            "SECTION 6: DETERMINATION\nAPPROVED\n"
        )

        # Disable HITL for testing
        from config.settings import settings
        object.__setattr__(settings, "hitl_enabled", False)

        graph = build_graph()
        patients = load_patients()
        patient = next(p for p in patients if p["id"] == "PA-001")
        initial_state = create_initial_state(patient)

        # Start metrics
        run_start = collector.start_run(initial_state)
        initial_state = {**initial_state, **run_start}

        final_state = graph.invoke(initial_state)

        # Verify outputs exist
        assert final_state.get("research_output"), "Research output should not be empty"
        assert final_state.get("rules_output"), "Rules output should not be empty"
        assert final_state.get("pa_decision") == "APPROVED"
        assert final_state.get("writer_output"), "Writer output should not be empty"

        # Verify supervisor notes were accumulated
        assert len(final_state.get("supervisor_notes", [])) > 0

        # Restore HITL
        object.__setattr__(settings, "hitl_enabled", True)
