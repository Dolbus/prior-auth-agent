#!/usr/bin/env python3
"""
Fetch LangSmith evaluation metrics for a completed experiment session and
optionally write row-level results to CSV.

Example:
  PYTHONPATH=. python scripts/extract_exp7_metrics.py \\
    --experiment exp07-post-relabel-902d698a \\
    --csv artifacts/exp07_full_results.csv
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from dotenv import load_dotenv
from langsmith import Client


def normalize(s: str | None) -> str:
    if s is None:
        return ""
    return str(s).strip().upper()


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--experiment",
        default="exp07-post-relabel-902d698a",
        help="LangSmith experiment session name",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("artifacts/exp07_full_results.csv"),
        help="Write full row-by-row results to this path",
    )
    args = parser.parse_args()

    client = Client()
    res = client.get_experiment_results(name=args.experiment)

    fb = res["feedback_stats"].get("exact_match", {})
    rs = res["run_stats"]

    denied_ref_nmi_out = 0
    approved_ref_denied_pred = 0
    nmi_ref_denied_pred = 0
    empty_or_null_out = 0
    ref_empty_count = 0
    rows: list[dict] = []

    for ex in res["examples_with_runs"]:
        pid = (ex.inputs or {}).get("patient_data", {}).get("id", "")
        ref = (ex.outputs or {}).get("pa_decision")
        ref_s = "" if ref is None else str(ref)

        actual_raw: str | None = None
        for run in ex.runs or []:
            outs = getattr(run, "outputs", None) or {}
            if isinstance(outs, dict) and "pa_decision" in outs:
                v = outs.get("pa_decision")
                actual_raw = None if v is None else str(v)
                break

        act_s = "" if actual_raw is None else str(actual_raw).strip()
        rn = normalize(ref_s)
        an = normalize(act_s)

        if rn == "":
            ref_empty_count += 1
        if actual_raw is None or act_s == "":
            empty_or_null_out += 1
        if rn == "DENIED" and an == "NEEDS_MORE_INFO":
            denied_ref_nmi_out += 1
        if rn == "APPROVED" and an == "DENIED":
            approved_ref_denied_pred += 1
        if rn == "NEEDS_MORE_INFO" and an == "DENIED":
            nmi_ref_denied_pred += 1

        row_match = 1 if rn == an else 0
        rows.append(
            {
                "patient_id": pid,
                "reference_pa_decision": ref_s,
                "prediction_pa_decision": act_s,
                "prediction_is_null": "yes" if actual_raw is None else "no",
                "exact_match_row": row_match,
                "denied_ref_nmi_actual": 1 if (rn == "DENIED" and an == "NEEDS_MORE_INFO") else 0,
            }
        )

    em_avg = fb.get("avg")
    em_pct = round((em_avg or 0) * 100, 2) if em_avg is not None else None

    p50 = rs.get("latency_p50")
    p50_s = p50.total_seconds() if p50 is not None else None

    total_cost = rs.get("total_cost")
    if total_cost is not None:
        total_cost_f = float(total_cost)
    else:
        total_cost_f = None

    print("---", args.experiment, "---")
    print(f"exact_match (session avg): {em_avg}  ({em_pct}%)")
    print(f"n: {fb.get('n')}")
    print(f"total_cost_usd: {total_cost_f}")
    print(f"latency_p50_seconds: {p50_s}")
    print(f"latency_p99: {rs.get('latency_p99')}")
    print(f"total_tokens: {rs.get('total_tokens')}")
    print(f"count_reference_denied_prediction_needs_more_info: {denied_ref_nmi_out}")
    print(f"count_reference_approved_prediction_denied: {approved_ref_denied_pred}")
    print(f"count_reference_needs_more_info_prediction_denied: {nmi_ref_denied_pred}")
    print(f"count_prediction_null_or_empty: {empty_or_null_out}")
    print(f"count_reference_empty_string: {ref_empty_count}")

    args.csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with args.csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {args.csv} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
