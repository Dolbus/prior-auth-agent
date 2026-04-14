"""Tests for scripts/evaluate.py output shape (LangSmith-safe)."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def minimal_patient() -> dict:
    return {
        "id": "PA-TEST",
        "name": "Test Patient",
        "insurance_provider": "Aetna",
        "requested_treatment": {"name": "Ozempic", "generic": "semaglutide"},
        "diagnoses": ["E11"],
        "prior_treatments": [],
        "labs": {},
        "contraindications": [],
    }


def test_process_patient_coerces_none_pa_decision_to_empty_string(minimal_patient):
    """If graph leaves pa_decision as None, outputs must be str (never JSON null)."""
    import importlib

    ev = importlib.import_module("scripts.evaluate")
    importlib.reload(ev)

    fake_state = {"pa_decision": None, "metrics": {}}
    with patch.object(ev.graph, "invoke", return_value=fake_state):
        out = ev.process_patient({"patient_data": minimal_patient})
    assert out["pa_decision"] == ""
    assert isinstance(out["pa_decision"], str)
