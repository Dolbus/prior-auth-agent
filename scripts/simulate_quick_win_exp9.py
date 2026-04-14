#!/usr/bin/env python3
"""
Simulate Exp9-style quick wins on Exp8 row export:
1. Relabel NEEDS_MORE_INFO → APPROVED errors: reference → APPROVED (agree with model).
2. Sample 10 DENIED → NEEDS_MORE_INFO: set prediction → DENIED (simulated model fix).

Reads artifacts/exp08_full_results.csv; writes artifacts/quick_win_exp9.csv.
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "artifacts" / "exp08_full_results.csv"
ERR = REPO / "artifacts" / "exp08_error_cases.csv"
OUT = REPO / "artifacts" / "quick_win_exp9.csv"


def norm(s: str) -> str:
    return (s or "").strip().upper()


def main() -> None:
    rows = list(csv.DictReader(SRC.open(encoding="utf-8")))
    assert len(rows) == 120, f"expected 120 rows, got {len(rows)}"

    if ERR.exists():
        ec = list(csv.DictReader(ERR.open(encoding="utf-8")))
        nmi_ap = [r for r in ec if r.get("error_pattern") == "NEEDS_MORE_INFO → APPROVED"]
        dnmi = [r for r in ec if r.get("error_pattern") == "DENIED → NEEDS_MORE_INFO"]
        assert len(nmi_ap) == 9, f"error_cases: expected 9 NMI→APPROVED, got {len(nmi_ap)}"
        assert len(dnmi) == 23, f"error_cases: expected 23 DENIED→NMI, got {len(dnmi)}"

    # Collect DENIED → NEEDS_MORE_INFO for sampling
    denied_nmi_pids = [
        r["patient_id"]
        for r in rows
        if norm(r["reference_pa_decision"]) == "DENIED"
        and norm(r["prediction_pa_decision"]) == "NEEDS_MORE_INFO"
    ]
    assert len(denied_nmi_pids) == 23, f"expected 23 DENIED→NMI, got {len(denied_nmi_pids)}"

    random.seed(42)
    sample_10 = sorted(random.sample(denied_nmi_pids, 10))

    out_rows: list[dict] = []
    nmi_to_appr = 0
    denied_nmi_overridden = 0

    for r in rows:
        pid = r["patient_id"]
        ref = norm(r["reference_pa_decision"])
        pred = norm(r["prediction_pa_decision"])

        sim_ref = r["reference_pa_decision"]
        sim_pred = r["prediction_pa_decision"]
        notes: list[str] = []

        # 1) Relabel: NEEDS_MORE_INFO → APPROVED → reference := APPROVED
        if ref == "NEEDS_MORE_INFO" and pred == "APPROVED":
            sim_ref = "APPROVED"
            notes.append("relabel_ref_APPROVED(NMI→APPROVED)")
            nmi_to_appr += 1

        # 2) Sample 10: DENIED → NEEDS_MORE_INFO → prediction := DENIED
        if (
            norm(sim_ref) == "DENIED"
            and norm(sim_pred) == "NEEDS_MORE_INFO"
            and pid in sample_10
        ):
            sim_pred = "DENIED"
            notes.append("sim_pred_DENIED(DENIED→NMI sample)")
            denied_nmi_overridden += 1

        sr = norm(sim_ref)
        sp = norm(sim_pred)
        match = 1 if sr == sp else 0

        out_rows.append(
            {
                **r,
                "sim_reference_pa_decision": sim_ref,
                "sim_prediction_pa_decision": sim_pred,
                "sim_exact_match_row": match,
                "simulation_notes": "; ".join(notes) if notes else "",
            }
        )

    assert nmi_to_appr == 9, f"expected 9 NMI→APPROVED relabels, got {nmi_to_appr}"
    assert denied_nmi_overridden == 10

    total_match = sum(r["sim_exact_match_row"] for r in out_rows)
    pct = 100.0 * total_match / len(out_rows)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fn = list(out_rows[0].keys())
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fn)
        w.writeheader()
        w.writerows(out_rows)

    print("Simulation: Exp9 quick-win (offline)")
    print(f"  Source: {SRC.name}")
    print(f"  1) Relabel NEEDS_MORE_INFO→APPROVED rows: reference → APPROVED (n={nmi_to_appr})")
    print(f"  2) Sample 10 DENIED→NEEDS_MORE_INFO: prediction → DENIED")
    print(f"     sampled patient_ids: {', '.join(sample_10)}")
    print(f"  New exact_match: {total_match}/120 = {pct:.2f}%")
    print(f"  Baseline (Exp8): 76/120 = 63.33%")
    print(f"  Wrote {OUT}")


if __name__ == "__main__":
    main()
