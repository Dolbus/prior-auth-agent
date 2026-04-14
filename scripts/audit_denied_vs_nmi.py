#!/usr/bin/env python3
"""
Offline audit: DENIED (reference) vs NEEDS_MORE_INFO (prediction) from exp07 CSV.
No API calls. Joins patients.json for drug_name and expected_reasoning.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

CSV_IN = Path("artifacts/exp07_full_results.csv")
PATIENTS = Path("data/patients.json")
OUT = Path("artifacts/denied_vs_nmi_audit.csv")


def main() -> None:
    patients = json.loads(PATIENTS.read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in patients if isinstance(p, dict) and p.get("id")}

    rows_out: list[dict[str, str]] = []
    with CSV_IN.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ref = (row.get("reference_pa_decision") or "").strip().upper()
            pred = (row.get("prediction_pa_decision") or "").strip().upper()
            if ref != "DENIED" or pred != "NEEDS_MORE_INFO":
                continue
            pid = row["patient_id"].strip()
            p = by_id.get(pid, {})
            drug = (p.get("requested_treatment") or {}).get("name", "")
            reasoning = p.get("expected_reasoning") or ""
            rows_out.append(
                {
                    "patient_id": pid,
                    "drug_name": drug,
                    "reference_pa_decision": row.get("reference_pa_decision", ""),
                    "prediction_pa_decision": row.get("prediction_pa_decision", ""),
                    "expected_reasoning_dataset": reasoning,
                    "note": "Full rules_checker narrative is in LangSmith trace (offline audit).",
                }
            )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not rows_out:
        print("No DENIED vs NEEDS_MORE_INFO rows found.")
        return

    fieldnames = list(rows_out[0].keys())
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows_out)

    print(f"Wrote {OUT} ({len(rows_out)} rows)\n")
    print("| patient_id | drug_name | prediction | expected_reasoning (dataset) |")
    print("|------------|-----------|------------|------------------------------|")
    for r in rows_out:
        er = (r["expected_reasoning_dataset"] or "")[:80]
        if len(r["expected_reasoning_dataset"] or "") > 80:
            er += "…"
        print(f"| {r['patient_id']} | {r['drug_name']} | {r['prediction_pa_decision']} | {er} |")


if __name__ == "__main__":
    main()
