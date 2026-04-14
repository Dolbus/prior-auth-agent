"""
Unit tests for individual agent logic.

These tests use mock LLM responses to verify that each agent:
  1. Handles valid input correctly
  2. Handles missing input gracefully
  3. Updates metrics via the collector
  4. Returns the expected state keys
"""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest

# Load a test patient
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_test_patient(patient_id: str = "PA-001") -> dict:
    patients = json.loads((DATA_DIR / "patients.json").read_text())
    return next(p for p in patients if p["id"] == patient_id)


def _make_mock_response(content: str, prompt_tokens: int = 100, completion_tokens: int = 200):
    """Create a mock LangChain ChatOpenAI response."""
    resp = MagicMock()
    resp.content = content
    resp.response_metadata = {
        "token_usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }
    }
    return resp


def _base_state(patient_id: str = "PA-001") -> dict:
    patient = _load_test_patient(patient_id)
    return {
        "patient_id": patient["id"],
        "patient_data": patient,
        "research_output": "",
        "rules_output": "",
        "pa_decision": "",
        "writer_output": "",
        "supervisor_notes": [],
        "guardrail_violations": [],
        "current_step": "initialized",
        "retry_count": 0,
        "max_retries": 2,
        "hitl_approved": False,
        "expected_outcome": patient.get("expected_outcome", ""),
        "metrics": {},
        "error": "",
    }


# ==================================================================
# Research Agent Tests
# ==================================================================

class TestResearchAgent:

    @patch("agents.research.ChatOpenAI")
    def test_research_produces_output(self, mock_llm_class):
        from agents.research import research_node

        mock_response = _make_mock_response(
            "## PATIENT DEMOGRAPHICS\nMaria Santos, 51, Female\n"
            "## DIAGNOSIS\nRheumatoid Arthritis M05.79\n"
            "## CURRENT MEDICATIONS\nMethotrexate 15mg\n"
            "## REQUESTED TREATMENT\nHumira adalimumab\n"
            "## RELEVANT LABS\nRF Positive\n"
            "## CLINICAL NOTES SUMMARY\nBilateral joint swelling\n"
            "## STEP THERAPY HISTORY\nMethotrexate 52 weeks inadequate"
        )
        mock_llm_class.return_value.invoke.return_value = mock_response

        state = _base_state("PA-001")
        result = research_node(state)

        assert result["research_output"] != ""
        assert "research_complete" == result["current_step"]
        assert any("Research" in n for n in result["supervisor_notes"])

    @patch("agents.research.ChatOpenAI")
    def test_research_handles_empty_patient(self, mock_llm_class):
        from agents.research import research_node

        state = _base_state()
        state["patient_data"] = {}

        result = research_node(state)

        assert result["research_output"] == ""
        assert "error" in result or result.get("error")


# ==================================================================
# Rules Checker Tests
# ==================================================================

class TestRulesCheckerAgent:

    @patch("agents.rules_checker.ChatOpenAI")
    def test_rules_checker_produces_determination(self, mock_llm_class):
        from agents.rules_checker import rules_checker_node

        mock_response = _make_mock_response(
            "## DETERMINATION: APPROVED\n\n"
            "## CRITERIA EVALUATION\n"
            "Step therapy: MET - methotrexate 52 weeks\n"
            "Safety screening: MET\n\n"
            "## REASONING\nPatient meets all criteria."
        )
        mock_llm_class.return_value.invoke.return_value = mock_response

        state = _base_state("PA-001")
        state["research_output"] = "Clinical summary for Maria Santos..."

        result = rules_checker_node(state)

        assert result["pa_decision"] == "APPROVED"
        assert result["rules_output"] != ""

    @patch("agents.rules_checker.ChatOpenAI")
    def test_rules_checker_denied(self, mock_llm_class):
        from agents.rules_checker import rules_checker_node

        state = _base_state("PA-030")
        state["research_output"] = "Clinical summary for Dupixent request."

        result = rules_checker_node(state)

        assert result["pa_decision"] == "DENIED"
        assert "helminth" in result["rules_output"].lower() or "contraindication" in result["rules_output"].lower()
        mock_llm_class.return_value.invoke.assert_not_called()

    def test_rules_checker_no_research(self):
        from agents.rules_checker import rules_checker_node

        state = _base_state()
        state["research_output"] = ""

        result = rules_checker_node(state)

        assert result["pa_decision"] == "NEEDS_MORE_INFO"
        assert "NEEDS_MORE_INFO" in result["rules_output"]
        assert result["error"]

    @patch("agents.rules_checker.ChatOpenAI")
    def test_rules_checker_deterministic_contraindication_skips_llm(self, mock_llm_class):
        """Bug 1: matching insurer + patient contraindications yields DENIED without LLM."""
        from agents.rules_checker import rules_checker_node

        state = _base_state("PA-065")
        state["research_output"] = "Summary for oncology case."

        result = rules_checker_node(state)

        assert result["pa_decision"] == "DENIED"
        assert "autoimmune" in result["rules_output"].lower()
        mock_llm_class.return_value.invoke.assert_not_called()

    @patch("agents.rules_checker.ChatOpenAI")
    def test_rules_checker_deterministic_lab_below_threshold_skips_llm(self, mock_llm_class):
        """Bug 2: documented lab below numeric threshold yields DENIED without LLM."""
        from agents.rules_checker import rules_checker_node

        state = _base_state("PA-043")
        state["research_output"] = "LDL and statin history noted."

        result = rules_checker_node(state)

        assert result["pa_decision"] == "DENIED"
        assert "LDL" in result["rules_output"] or "ldl" in result["rules_output"].lower()
        mock_llm_class.return_value.invoke.assert_not_called()

    @patch("agents.rules_checker.ChatOpenAI")
    def test_rules_checker_deterministic_lab_percent_key_skips_llm(self, mock_llm_class):
        """Numeric *_percent / PD_L1_min_percent below threshold short-circuits like *_min."""
        from agents.rules_checker import rules_checker_node

        state = _base_state("PA-063")
        state["research_output"] = "PD-L1 staining reported."

        result = rules_checker_node(state)

        assert result["pa_decision"] == "DENIED"
        assert "PD_L1" in result["rules_output"] or "pd_l1" in result["rules_output"].lower()
        mock_llm_class.return_value.invoke.assert_not_called()

    @patch("agents.rules_checker.ChatOpenAI")
    def test_rules_checker_deterministic_body_surface_area_percent_skips_llm(self, mock_llm_class):
        from agents.rules_checker import rules_checker_node

        state = _base_state("PA-033")
        state["research_output"] = "BSA and prior biologics noted."

        result = rules_checker_node(state)

        assert result["pa_decision"] == "DENIED"
        ro = result["rules_output"].lower()
        assert "body_surface_area" in ro or "bsa" in ro or "9.9" in result["rules_output"]
        mock_llm_class.return_value.invoke.assert_not_called()

    @patch("agents.rules_checker.ChatOpenAI")
    def test_rules_checker_missing_labs_does_not_short_circuit_lab_denial(self, mock_llm_class):
        """Empty labs: _lab_value_missing keeps deterministic lab DENIED off; LLM still runs."""
        from agents.rules_checker import rules_checker_node

        mock_llm_class.return_value.invoke.return_value = _make_mock_response(
            "1. DETERMINATION\nNEEDS_MORE_INFO\n\n2. CRITERIA EVALUATION\n...\n"
        )

        state = _base_state("PA-044")
        state["research_output"] = "LDL not in chart."

        result = rules_checker_node(state)

        mock_llm_class.return_value.invoke.assert_called_once()
        assert result["rules_output"] != ""

    @patch("agents.rules_checker.ChatOpenAI")
    def test_rules_checker_deterministic_step_therapy_all_present(self, mock_llm_class):
        from agents.rules_checker import rules_checker_node

        state = _base_state("PA-101")
        state["research_output"] = "Narrative that might otherwise demand duration or outcome documentation."

        result = rules_checker_node(state)

        assert result["pa_decision"] == "APPROVED"
        assert "deterministic step therapy" in result["supervisor_notes"][0].lower()
        mock_llm_class.return_value.invoke.assert_not_called()

    @patch("agents.rules_checker.ChatOpenAI")
    def test_rules_checker_deterministic_step_therapy_partial_missing(self, mock_llm_class):
        from agents.rules_checker import rules_checker_node

        state = _base_state("PA-101")
        pd = dict(state["patient_data"])
        pd["prior_treatments"] = ["SSRI", "SNRI"]
        state["patient_data"] = pd
        state["research_output"] = "Clinical summary."

        result = rules_checker_node(state)

        assert result["pa_decision"] == "DENIED"
        assert "incomplete" in result["supervisor_notes"][0].lower()
        mock_llm_class.return_value.invoke.assert_not_called()

    @patch("agents.rules_checker.ChatOpenAI")
    def test_rules_checker_deterministic_step_therapy_all_missing(self, mock_llm_class):
        from agents.rules_checker import rules_checker_node

        state = _base_state("PA-102")
        state["research_output"] = "Clinical summary."

        result = rules_checker_node(state)

        assert result["pa_decision"] == "NEEDS_MORE_INFO"
        assert "none documented" in result["supervisor_notes"][0].lower()
        mock_llm_class.return_value.invoke.assert_not_called()


# ==================================================================
# Writer Agent Tests
# ==================================================================

class TestWriterAgent:

    @patch("agents.writer.ChatOpenAI")
    def test_writer_produces_document(self, mock_llm_class):
        from agents.writer import writer_node

        mock_response = _make_mock_response(
            "═══════════════════════════════════════════════════\n"
            "PRIOR AUTHORIZATION REQUEST — APPROVED\n"
            "═══════════════════════════════════════════════════\n\n"
            "SECTION 1: PATIENT INFORMATION\nMaria Santos\n\n"
            "SECTION 2: CLINICAL SUMMARY\nRA, moderate-to-severe\n\n"
            "SECTION 3: REQUESTED TREATMENT\nHumira\n\n"
            "SECTION 4: MEDICAL NECESSITY JUSTIFICATION\n...\n\n"
            "SECTION 5: INSURER CRITERIA EVALUATION\n...\n\n"
            "SECTION 6: DETERMINATION\nAPPROVED\n"
        )
        mock_llm_class.return_value.invoke.return_value = mock_response

        state = _base_state("PA-001")
        state["research_output"] = "Research summary..."
        state["rules_output"] = "Rules determination..."

        result = writer_node(state)

        assert result["writer_output"] != ""
        assert "writing_complete" == result["current_step"]

    def test_writer_missing_inputs(self):
        from agents.writer import writer_node

        state = _base_state()
        result = writer_node(state)

        assert result["writer_output"] == ""
        assert result["error"]


class TestSupervisorAgent:

    @patch("agents.supervisor._evaluate_agent_output")
    def test_validate_research_passes(self, mock_eval):
        mock_eval.return_value = (95.0, 10, 10, "Looks good")
        from agents.supervisor import validate_research_node

        state = _base_state("PA-001")
        state["research_output"] = "Some good output"

        result = validate_research_node(state)

        assert result["current_step"] == "research_validated"
        assert len(result["supervisor_notes"]) > 0

    @patch("agents.supervisor._evaluate_agent_output")
    def test_validate_research_fails_empty(self, mock_eval):
        mock_eval.return_value = (50.0, 10, 10, "Too short")
        from agents.supervisor import validate_research_node

        state = _base_state()
        state["research_output"] = ""

        result = validate_research_node(state)

        assert result["current_step"] == "research_retry_needed"
        assert len(result["supervisor_notes"]) > 0

    @patch("agents.supervisor._evaluate_agent_output")
    def test_validate_rules_passes(self, mock_eval):
        mock_eval.return_value = (95.0, 10, 10, "Excellent reasoning")
        from agents.supervisor import validate_rules_node

        state = _base_state()
        state["rules_output"] = "DETERMINATION: APPROVED\nCRITERIA met."
        state["pa_decision"] = "APPROVED"

        result = validate_rules_node(state)

        assert result["current_step"] == "rules_validated"

    @patch("agents.supervisor._evaluate_agent_output")
    def test_validate_rules_invalid_decision(self, mock_eval):
        mock_eval.return_value = (80.0, 10, 10, "Bad decision")
        from agents.supervisor import validate_rules_node

        state = _base_state()
        state["rules_output"] = "Some output"
        state["pa_decision"] = "MAYBE"

        result = validate_rules_node(state)

        assert result["current_step"] == "rules_retry_needed"
        assert len(result["supervisor_notes"]) > 0

    @patch("agents.supervisor._handle_retry_logic")
    @patch("agents.supervisor.collector.end_agent")
    @patch("agents.supervisor.collector.start_agent")
    def test_validate_eligibility_pa_not_required_sets_pa_decision(self, mock_start, mock_end, mock_retry):
        """Fast-track when PA not required: canonical APPROVED + rules_output before graph END."""
        from agents.supervisor import validate_eligibility_node

        mock_start.return_value = {}
        mock_end.return_value = {"metrics": {}}
        mock_retry.side_effect = lambda s, a, p, n: (s, False)

        state = _base_state("PA-001")
        state["eligibility_output"] = (
            "- INSURER RECOGNIZED: Yes\n- DRUG RECOGNIZED: Yes\n- PA REQUIRED: False\n"
            "- CONFIDENCE SCORE: 100\n"
        )
        state["retry_counts"] = {"eligibility_checker": 0}
        state["max_retries"] = 2

        result = validate_eligibility_node(state)

        assert result["pa_decision"] == "APPROVED"
        assert result["pa_required"] is False
        assert result["current_step"] == "eligibility_pa_not_required"
        assert "pa_required: false" in result["rules_output"].lower()
