"""Tests for scripts/audit_label_misalignment.py — no live LangSmith."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.audit_label_misalignment import (
    actual_from_runs,
    compare_ref_actual,
    extract_patient_id,
    load_patients_expected,
    normalize_label,
    pattern_key,
    run_audit_core,
    write_relabel_csv,
)


def test_normalize_label() -> None:
    assert normalize_label(None) == ""
    assert normalize_label("") == ""
    assert normalize_label("  approved  ") == "APPROVED"
    assert normalize_label("needs_more_info") == "NEEDS_MORE_INFO"


def test_pattern_key_empty_and_standard() -> None:
    assert pattern_key("APPROVED", "") == "APPROVED → EMPTY"
    assert pattern_key(None, "denied") == "EMPTY → DENIED"
    assert pattern_key("VALID_ESCALATION", "APPROVED") == "VALID_ESCALATION → APPROVED"


def test_extract_patient_id() -> None:
    assert extract_patient_id({"patient_data": {"id": "PA-001"}}) == "PA-001"
    assert extract_patient_id({}) is None
    assert extract_patient_id(None) is None


def test_compare_ref_actual_case_insensitive() -> None:
    assert compare_ref_actual("approved", "APPROVED")
    assert not compare_ref_actual("APPROVED", "DENIED")


def test_actual_from_runs_simple_namespace() -> None:
    runs = [
        SimpleNamespace(outputs={"pa_decision": "DENIED"}),
    ]
    assert actual_from_runs(runs) == "DENIED"


def test_actual_from_runs_first_with_key_wins() -> None:
    runs = [
        SimpleNamespace(outputs={"other": 1}),
        SimpleNamespace(outputs={"pa_decision": "APPROVED"}),
    ]
    assert actual_from_runs(runs) == "APPROVED"


def test_actual_from_runs_missing() -> None:
    assert actual_from_runs([]) is None
    assert actual_from_runs([SimpleNamespace(outputs={})]) is None


def test_load_patients_expected(tmp_path: Path) -> None:
    p = tmp_path / "p.json"
    p.write_text(
        json.dumps(
            [
                {"id": "PA-001", "expected_outcome": "APPROVED"},
                {"id": "PA-002", "expected_outcome": None},
            ]
        ),
        encoding="utf-8",
    )
    m = load_patients_expected(p)
    assert m["PA-001"] == "APPROVED"
    assert m["PA-002"] == ""


def test_run_audit_core_aligned_and_mismatch() -> None:
    patients = {"PA-001": "APPROVED", "PA-002": "DENIED"}
    examples = [
        {
            "inputs": {"patient_data": {"id": "PA-001"}},
            "outputs": {"pa_decision": "APPROVED"},
            "runs": [SimpleNamespace(outputs={"pa_decision": "APPROVED"})],
        },
        {
            "inputs": {"patient_data": {"id": "PA-002"}},
            "outputs": {"pa_decision": "DENIED"},
            "runs": [SimpleNamespace(outputs={"pa_decision": "APPROVED"})],
        },
    ]
    r = run_audit_core(examples, patients)
    assert r.summary.total_examples == 2
    assert r.summary.aligned == 1
    assert r.summary.mismatched == 1
    assert r.summary.empty_actual == 0
    assert len(r.mismatch_rows) == 1
    assert r.mismatch_rows[0].patient_id == "PA-002"
    assert r.mismatch_rows[0].pattern == "DENIED → APPROVED"
    assert "DENIED → APPROVED" in r.pattern_to_ids


def test_run_audit_core_empty_actual() -> None:
    patients = {"PA-003": "APPROVED"}
    examples = [
        {
            "inputs": {"patient_data": {"id": "PA-003"}},
            "outputs": {"pa_decision": "APPROVED"},
            "runs": [SimpleNamespace(outputs={"pa_decision": ""})],
        },
    ]
    r = run_audit_core(examples, patients)
    assert r.summary.empty_actual == 1
    assert r.summary.mismatched == 1
    assert r.summary.aligned == 0
    assert r.mismatch_rows[0].pattern == "APPROVED → EMPTY"

    examples_aligned_empty = [
        {
            "inputs": {"patient_data": {"id": "PA-004"}},
            "outputs": {"pa_decision": ""},
            "runs": [SimpleNamespace(outputs={"pa_decision": ""})],
        },
    ]
    r2 = run_audit_core(examples_aligned_empty, {"PA-004": ""})
    assert r2.summary.empty_actual == 1
    assert r2.summary.aligned == 1


def test_run_audit_core_ref_json_drift() -> None:
    patients = {"PA-001": "DENIED"}
    examples = [
        {
            "inputs": {"patient_data": {"id": "PA-001"}},
            "outputs": {"pa_decision": "APPROVED"},
            "runs": [SimpleNamespace(outputs={"pa_decision": "APPROVED"})],
        },
    ]
    r = run_audit_core(examples, patients)
    assert r.summary.reference_vs_json_drift == 1
    assert r.summary.reference_vs_json_aligned == 0
    assert "PA-001" in r.ref_json_drift_ids
    assert len(r.mismatch_rows) == 0


def test_write_relabel_csv(tmp_path: Path) -> None:
    from scripts.audit_label_misalignment import MismatchRow

    rows = [
        MismatchRow(
            patient_id="PA-001",
            current_reference="X",
            actual_prediction="Y",
            json_expected="Z",
            pattern="X → Y",
            proposed_reference="",
            reason="test",
            review_status="PENDING",
        )
    ]
    out = tmp_path / "out.csv"
    write_relabel_csv(out, rows)
    text = out.read_text(encoding="utf-8")
    assert "proposed_reference" in text
    assert ",,test,PENDING" in text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
