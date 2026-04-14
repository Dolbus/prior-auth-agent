"""Tests for step-therapy helpers used by supervisor."""

from agents.rules_checker import (
    is_step_therapy_partial_failure,
    is_step_therapy_sequence_violation,
)


def test_partial_failure_some_steps_present() -> None:
    rules = {"step_therapy": ["metformin", "insulin"]}
    patient = {"prior_treatments": ["metformin"]}
    assert is_step_therapy_partial_failure(patient, rules) is True


def test_partial_failure_none_present() -> None:
    rules = {"step_therapy": ["metformin"]}
    patient = {"prior_treatments": []}
    assert is_step_therapy_partial_failure(patient, rules) is False


def test_partial_failure_all_present() -> None:
    rules = {"step_therapy": ["metformin"]}
    patient = {"prior_treatments": ["metformin"]}
    assert is_step_therapy_partial_failure(patient, rules) is False


def test_no_step_therapy_rule() -> None:
    assert is_step_therapy_partial_failure({"prior_treatments": []}, {}) is False


def test_sequence_violation_wrong_order() -> None:
    rules = {"step_therapy": ["metformin", "sulfonylurea"]}
    patient = {"prior_treatments": ["sulfonylurea", "metformin"]}
    assert is_step_therapy_sequence_violation(patient, rules) is True


def test_sequence_ok() -> None:
    rules = {"step_therapy": ["metformin", "sulfonylurea"]}
    patient = {"prior_treatments": ["metformin", "sulfonylurea"]}
    assert is_step_therapy_sequence_violation(patient, rules) is False


def test_sequence_single_step_not_applicable() -> None:
    rules = {"step_therapy": ["metformin"]}
    patient = {"prior_treatments": ["metformin"]}
    assert is_step_therapy_sequence_violation(patient, rules) is False


def test_sequence_missing_step_not_sequence_flag() -> None:
    rules = {"step_therapy": ["metformin", "insulin"]}
    patient = {"prior_treatments": ["metformin"]}
    assert is_step_therapy_sequence_violation(patient, rules) is False
