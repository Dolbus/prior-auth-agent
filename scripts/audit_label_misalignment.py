#!/usr/bin/env python3
"""
Exp 7 — Read-only label mismatch audit.

Primary: LangSmith dataset reference `outputs.pa_decision` vs experiment run actual
          (same source as `exact_match` in scripts/evaluate.py).

Secondary: LangSmith reference vs data/patients.json `expected_outcome` (drift check).

Does not modify patients.json or LangSmith labels.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

# ---------------------------------------------------------------------------
# Pure helpers (used by tests and live audit)
# ---------------------------------------------------------------------------


def normalize_label(value: str | None) -> str:
    """strip + upper; empty/None → empty string (canonical empty bucket)."""
    if value is None:
        return ""
    s = str(value).strip()
    return s.upper()


def label_for_pattern(value: str | None) -> str:
    """Human-readable bucket for pattern keys (empty → EMPTY)."""
    if value is None or str(value).strip() == "":
        return "EMPTY"
    return str(value).strip().upper()


def pattern_key(reference: str | None, actual: str | None) -> str:
    return f"{label_for_pattern(reference)} → {label_for_pattern(actual)}"


def extract_patient_id(inputs: dict[str, Any] | None) -> str | None:
    if not inputs:
        return None
    pd = inputs.get("patient_data")
    if isinstance(pd, dict) and pd.get("id"):
        return str(pd["id"]).strip()
    return None


def load_patients_expected(path: Path) -> dict[str, str]:
    """Map patient id → raw expected_outcome string."""
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    if not isinstance(data, list):
        return out
    for row in data:
        if not isinstance(row, dict):
            continue
        pid = row.get("id")
        if pid is None:
            continue
        exp = row.get("expected_outcome")
        out[str(pid).strip()] = "" if exp is None else str(exp)
    return out


@dataclass
class AuditSummary:
    total_examples: int = 0
    aligned: int = 0
    mismatched: int = 0
    empty_actual: int = 0
    missing_patient_id: int = 0
    missing_actual_run: int = 0
    reference_vs_json_aligned: int = 0
    reference_vs_json_drift: int = 0


@dataclass
class MismatchRow:
    patient_id: str
    current_reference: str
    actual_prediction: str
    json_expected: str
    pattern: str
    proposed_reference: str = ""
    reason: str = ""
    review_status: str = "PENDING"


@dataclass
class AuditResult:
    summary: AuditSummary
    mismatch_rows: list[MismatchRow] = field(default_factory=list)
    pattern_to_ids: dict[str, list[str]] = field(default_factory=dict)
    ref_json_drift_ids: list[str] = field(default_factory=list)


def compare_ref_actual(reference: str | None, actual: str | None) -> bool:
    return normalize_label(reference) == normalize_label(actual)


def compare_ref_json(reference: str | None, json_expected: str | None) -> bool:
    return normalize_label(reference) == normalize_label(json_expected)


def iter_example_dicts(
    examples_with_runs: Iterable[Any],
) -> Iterator[dict[str, Any]]:
    """Normalize LangSmith ExampleWithRuns objects to plain dicts."""
    for ex in examples_with_runs:
        inputs = getattr(ex, "inputs", None) or {}
        outputs = getattr(ex, "outputs", None) or {}
        runs = getattr(ex, "runs", None) or []
        yield {"inputs": inputs, "outputs": outputs, "runs": runs}


def actual_from_runs(runs: list[Any]) -> str | None:
    """First run with pa_decision in outputs."""
    for run in runs:
        outs = getattr(run, "outputs", None) or {}
        if isinstance(outs, dict) and "pa_decision" in outs:
            v = outs.get("pa_decision")
            return None if v is None else str(v)
    return None


def run_audit_core(
    examples: Iterable[dict[str, Any]],
    patients_expected: dict[str, str],
) -> AuditResult:
    """
    Core audit over normalized example dicts:
    each item: {inputs, outputs, runs} where runs have .outputs with pa_decision.
    """
    summary = AuditSummary()
    mismatch_rows: list[MismatchRow] = []
    pattern_to_ids: dict[str, list[str]] = defaultdict(list)
    ref_json_drift_ids: list[str] = []

    for raw in examples:
        inputs = raw.get("inputs") or {}
        outputs = raw.get("outputs") or {}
        runs = raw.get("runs") or []

        pid = extract_patient_id(inputs)
        reference = outputs.get("pa_decision")
        ref_str = "" if reference is None else str(reference)

        if not pid:
            summary.missing_patient_id += 1
            continue

        actual_raw = actual_from_runs(runs)
        if actual_raw is None:
            summary.missing_actual_run += 1
            actual_raw = ""

        summary.total_examples += 1

        json_exp = patients_expected.get(pid, "")
        is_ref_json_drift = False
        if pid in patients_expected:
            if compare_ref_json(reference, json_exp):
                summary.reference_vs_json_aligned += 1
            else:
                summary.reference_vs_json_drift += 1
                is_ref_json_drift = True
                ref_json_drift_ids.append(pid)

        act_norm = normalize_label(actual_raw)
        if act_norm == "":
            summary.empty_actual += 1

        if compare_ref_actual(reference, actual_raw):
            summary.aligned += 1
        else:
            summary.mismatched += 1
            pat = pattern_key(reference, actual_raw)
            pattern_to_ids[pat].append(pid)
            reason_parts = [
                "LangSmith reference pa_decision differs from experiment run output.",
            ]
            if is_ref_json_drift:
                reason_parts.append(
                    "Note: LangSmith reference also differs from patients.json expected_outcome (drift)."
                )
            mismatch_rows.append(
                MismatchRow(
                    patient_id=pid,
                    current_reference=ref_str,
                    actual_prediction=actual_raw,
                    json_expected=json_exp,
                    pattern=pat,
                    proposed_reference="",
                    reason=" ".join(reason_parts),
                    review_status="PENDING",
                )
            )

    sorted_patterns = dict(
        sorted(pattern_to_ids.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    )
    return AuditResult(
        summary=summary,
        mismatch_rows=mismatch_rows,
        pattern_to_ids=sorted_patterns,
        ref_json_drift_ids=sorted(set(ref_json_drift_ids)),
    )


def fetch_audit_from_langsmith(
    experiment_name: str,
    patients_path: Path,
) -> AuditResult:
    from langsmith import Client

    client = Client()
    res = client.get_experiment_results(name=experiment_name)
    patients = load_patients_expected(patients_path)
    examples = list(iter_example_dicts(res["examples_with_runs"]))
    return run_audit_core(examples, patients)


def write_relabel_csv(path: Path, rows: list[MismatchRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "patient_id",
        "current_reference",
        "actual_prediction",
        "json_expected",
        "pattern",
        "proposed_reference",
        "reason",
        "review_status",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    "patient_id": r.patient_id,
                    "current_reference": r.current_reference,
                    "actual_prediction": r.actual_prediction,
                    "json_expected": r.json_expected,
                    "pattern": r.pattern,
                    "proposed_reference": r.proposed_reference,
                    "reason": r.reason,
                    "review_status": r.review_status,
                }
            )


def write_relabel_notes(path: Path, experiment_name: str, result: AuditResult) -> None:
    notes: dict[str, Any] = {
        "experiment": experiment_name,
        "purpose": (
            "Read-only audit: LangSmith dataset reference vs experiment actual; "
            "secondary drift check vs patients.json. No labels were modified."
        ),
        "summary": {
            "total_examples": result.summary.total_examples,
            "aligned": result.summary.aligned,
            "mismatched": result.summary.mismatched,
            "empty_actual": result.summary.empty_actual,
            "missing_patient_id": result.summary.missing_patient_id,
            "missing_actual_run": result.summary.missing_actual_run,
            "reference_vs_json_aligned": result.summary.reference_vs_json_aligned,
            "reference_vs_json_drift": result.summary.reference_vs_json_drift,
        },
        "patterns": {
            k: {"count": len(v), "patient_ids": v}
            for k, v in result.pattern_to_ids.items()
        },
        "reference_vs_json_drift_patient_ids": result.ref_json_drift_ids,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(notes, indent=2), encoding="utf-8")


def print_report(result: AuditResult, top_n: int = 5) -> None:
    s = result.summary
    print("--- Exp 7 label audit ---")
    print(f"Examples (with patient_id): {s.total_examples}")
    print(f"Aligned (ref == actual):   {s.aligned}")
    print(f"Mismatched:                {s.mismatched}")
    print(f"Empty actual:              {s.empty_actual}")
    print(f"Missing patient_id:        {s.missing_patient_id}")
    print(f"Missing actual in runs:    {s.missing_actual_run}")
    print(
        f"Reference vs patients.json: aligned={s.reference_vs_json_aligned} "
        f"drift={s.reference_vs_json_drift}"
    )
    print()
    print(f"Top {top_n} mismatch patterns (by count):")
    for i, (pat, ids) in enumerate(result.pattern_to_ids.items()):
        if i >= top_n:
            break
        preview = ids[:8]
        suffix = "..." if len(ids) > 8 else ""
        print(f"  {pat}: {len(ids)}  e.g. {preview}{suffix}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Exp 7 read-only label mismatch audit.")
    parser.add_argument(
        "--experiment",
        default="exp06d1-final-fix-e6db96c2",
        help="LangSmith experiment session name",
    )
    parser.add_argument(
        "--patients",
        type=Path,
        default=Path("data/patients.json"),
        help="Path to patients.json for expected_outcome drift check",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts"),
        help="Directory for relabel_candidates.csv and relabel_notes.json",
    )
    args = parser.parse_args()

    result = fetch_audit_from_langsmith(args.experiment, args.patients)
    out_csv = args.output_dir / "relabel_candidates.csv"
    out_notes = args.output_dir / "relabel_notes.json"
    write_relabel_csv(out_csv, result.mismatch_rows)
    write_relabel_notes(out_notes, args.experiment, result)
    print_report(result, top_n=5)
    print()
    print(f"Wrote {out_csv} ({len(result.mismatch_rows)} mismatch rows)")
    print(f"Wrote {out_notes}")


if __name__ == "__main__":
    main()
