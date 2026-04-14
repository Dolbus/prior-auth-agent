#!/usr/bin/env python3
"""
Preflight audit before Experiment 8 final eval: LangSmith dataset + local CSV export.

Usage:
  PYTHONPATH=. python scripts/preflight_exp8_audit.py
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from langsmith import Client

DATASET_NAME = "pa-baseline-120-apr08"
CSV_EXPORT = Path("artifacts/exp07_full_results.csv")
REPORT_PATH = Path("artifacts/preflight_exp8_check.md")

# The 19 rows that were batch-updated to non-empty reference (update_empty_reference_labels.py)
RELABELED_19 = [
    "PA-079", "PA-029", "PA-019", "PA-066", "PA-054", "PA-034", "PA-040", "PA-044",
    "PA-032", "PA-112", "PA-064", "PA-037", "PA-004", "PA-117", "PA-049", "PA-070",
    "PA-068", "PA-059", "PA-069",
]

VALID = {"APPROVED", "DENIED", "NEEDS_MORE_INFO"}


def normalize(s: str | None) -> str:
    if s is None:
        return ""
    return str(s).strip().upper()


def audit_langsmith_dataset(client: Client) -> dict:
    by_pid: dict[str, list[str]] = {}
    example_ids: list[str] = []
    empty_ref = 0
    pid_to_ref: dict[str, str] = {}

    for ex in client.list_examples(dataset_name=DATASET_NAME):
        eid = str(ex.id)
        example_ids.append(eid)
        ref = (ex.outputs or {}).get("pa_decision")
        ref_s = "" if ref is None else str(ref).strip()
        if ref_s == "":
            empty_ref += 1
        pd = (ex.inputs or {}).get("patient_data", {})
        pid = pd.get("id") if isinstance(pd, dict) else None
        if pid:
            ps = str(pid).strip()
            by_pid.setdefault(ps, []).append(eid)
            pid_to_ref[ps] = ref_s

    dup_pids = {p: ids for p, ids in by_pid.items() if len(ids) > 1}
    dup_example_ids = len(example_ids) != len(set(example_ids))

    relabeled_ok: list[tuple[str, str]] = []
    relabeled_still_empty: list[str] = []
    for pid in RELABELED_19:
        rs = pid_to_ref.get(pid, "")
        if rs == "":
            relabeled_still_empty.append(pid)
        else:
            relabeled_ok.append((pid, rs))

    return {
        "total_examples": len(example_ids),
        "unique_example_ids": len(set(example_ids)),
        "duplicate_example_id_rows": dup_example_ids,
        "patient_id_count": len(by_pid),
        "duplicate_patient_ids": dup_pids,
        "empty_reference_count": empty_ref,
        "relabeled_19_ok": relabeled_ok,
        "relabeled_19_still_empty": relabeled_still_empty,
    }


def audit_csv(path: Path) -> dict:
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({k: (row.get(k) or "") for k in row})

    pids = [r["patient_id"].strip() for r in rows]
    dup_pid_csv = {p: c for p, c in Counter(pids).items() if c > 1}

    empty_ref = sum(1 for r in rows if (r.get("reference_pa_decision") or "").strip() == "")

    invalid_pred = []
    for r in rows:
        pred = normalize(r.get("prediction_pa_decision"))
        if pred == "":
            continue  # counted separately
        if pred not in VALID:
            invalid_pred.append((r["patient_id"], r.get("prediction_pa_decision", "")))

    null_pred = sum(1 for r in rows if r.get("prediction_is_null") == "yes")
    empty_pred = sum(
        1 for r in rows if (r.get("prediction_pa_decision") or "").strip() == ""
    )
    empty_or_null_pred = empty_pred

    # Confusion-style (reference x prediction), CSV snapshot
    c_denied_nmi = 0
    c_appr_den = 0
    c_nmi_den = 0
    for r in rows:
        ref = normalize(r.get("reference_pa_decision"))
        pred = normalize(r.get("prediction_pa_decision"))
        if ref == "DENIED" and pred == "NEEDS_MORE_INFO":
            c_denied_nmi += 1
        if ref == "APPROVED" and pred == "DENIED":
            c_appr_den += 1
        if ref == "NEEDS_MORE_INFO" and pred == "DENIED":
            c_nmi_den += 1

    return {
        "row_count": len(rows),
        "empty_reference_count": empty_ref,
        "duplicate_patient_ids": dup_pid_csv,
        "invalid_prediction_labels": invalid_pred,
        "empty_prediction_rows": empty_pred,
        "null_prediction_rows": null_pred,
        "empty_or_null_prediction_total": empty_or_null_pred,
        "confusion_denied_to_nmi": c_denied_nmi,
        "confusion_approved_to_denied": c_appr_den,
        "confusion_nmi_to_denied": c_nmi_den,
    }


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    client = Client()

    ls = audit_langsmith_dataset(client)
    csv_audit = audit_csv(CSV_EXPORT)

    # GO/NO-GO uses **live** LangSmith for labels; CSV may be an older export.
    safe = (
        ls["empty_reference_count"] == 0
        and not ls["duplicate_patient_ids"]
        and not ls["duplicate_example_id_rows"]
        and len(ls["relabeled_19_still_empty"]) == 0
        and not csv_audit["duplicate_patient_ids"]
        and not csv_audit["invalid_prediction_labels"]
    )
    csv_stale_empty_refs = csv_audit["empty_reference_count"] > 0

    lines: list[str] = []
    lines.append("# Preflight Experiment 8 — dataset + CSV audit\n")
    lines.append("**Generated:** preflight script (`scripts/preflight_exp8_audit.py`)\n")
    lines.append(f"- **LangSmith dataset:** `{DATASET_NAME}`\n")
    lines.append(f"- **CSV export analyzed:** `{CSV_EXPORT}` (snapshot from Exp 7 run export — not live dataset)\n")
    lines.append("\n## 1. Empty `reference_pa_decision`\n")
    lines.append(f"| Source | Empty count |\n|--------|-------------|\n")
    lines.append(f"| LangSmith (live) | **{ls['empty_reference_count']}** |\n")
    lines.append(f"| CSV export | **{csv_audit['empty_reference_count']}** |\n")

    lines.append("\n## 2. Duplicates\n")
    lines.append(f"- **LangSmith:** total example rows = {ls['total_examples']}, unique example UUIDs = {ls['unique_example_ids']}\n")
    lines.append(f"- **Duplicate patient_ids (multiple examples per ID):** {len(ls['duplicate_patient_ids'])} — ")
    lines.append(", ".join(ls["duplicate_patient_ids"].keys()) if ls["duplicate_patient_ids"] else "none\n")
    lines.append(f"- **CSV duplicate patient_ids:** {csv_audit['duplicate_patient_ids'] or 'none'}\n")

    lines.append("\n## 3. Predictions outside {{APPROVED, DENIED, NEEDS_MORE_INFO}}\n")
    if csv_audit["invalid_prediction_labels"]:
        lines.append("Non-empty predictions that are not in the valid set (CSV):\n")
        for pid, raw in csv_audit["invalid_prediction_labels"]:
            lines.append(f"- `{pid}` → `{raw}`\n")
    else:
        lines.append("- **CSV:** none (non-empty predictions only).\n")

    lines.append("\n## 4. Confusion-style counts (CSV snapshot)\n")
    lines.append(f"- ref **DENIED** → pred **NEEDS_MORE_INFO:** {csv_audit['confusion_denied_to_nmi']}\n")
    lines.append(f"- ref **APPROVED** → pred **DENIED:** {csv_audit['confusion_approved_to_denied']}\n")
    lines.append(f"- ref **NEEDS_MORE_INFO** → pred **DENIED:** {csv_audit['confusion_nmi_to_denied']}\n")
    lines.append(f"- Empty / missing prediction (CSV): {csv_audit['empty_or_null_prediction_total']}\n")
    lines.append(f"- `prediction_is_null` = yes (CSV): {csv_audit['null_prediction_rows']}\n")

    lines.append("\n## 5. Nineteen relabeled examples (non-empty reference on LangSmith)\n")
    if ls["relabeled_19_still_empty"]:
        lines.append("**Still empty:** " + ", ".join(ls["relabeled_19_still_empty"]) + "\n")
    else:
        lines.append("All **19** IDs have non-empty `outputs.pa_decision` on the live dataset.\n")
    lines.append("\nSample (id → reference):\n")
    for pid, ref in ls["relabeled_19_ok"][:8]:
        lines.append(f"- `{pid}` → `{ref}`\n")
    if len(ls["relabeled_19_ok"]) > 8:
        lines.append(f"- … ({len(ls['relabeled_19_ok'])} total verified)\n")

    lines.append("\n## 6. Safe to run final eval?\n")
    lines.append(f"- **Preflight flag:** `{'PASS' if safe else 'REVIEW NEEDED'}`\n")
    if csv_stale_empty_refs and ls["empty_reference_count"] == 0:
        lines.append(
            "- **Note:** CSV still shows empty references from the Exp 7 export snapshot; "
            "LangSmith live dataset has **0** empty — safe to ignore CSV empties for GO/NO-GO.\n"
        )
    if not safe:
        lines.append("- See issues above before running `scripts/evaluate.py`.\n")
    else:
        lines.append(
            "- Live dataset: no empty references, no duplicate patient_ids / example UUIDs, "
            "19 relabels verified; CSV structural checks OK.\n"
        )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")

    print("\n=== PREFLIGHT SUMMARY ===\n")
    print(f"LangSmith empty references: {ls['empty_reference_count']}")
    print(f"CSV empty references (stale export): {csv_audit['empty_reference_count']}")
    print(f"Duplicate patient_ids (LS): {len(ls['duplicate_patient_ids'])}")
    print(f"Duplicate patient_ids (CSV): {len(csv_audit['duplicate_patient_ids'])}")
    print(f"Invalid pred labels (CSV): {len(csv_audit['invalid_prediction_labels'])}")
    print(f"CSV DENIED→NMI / APPROVED→DENIED / NMI→DENIED: {csv_audit['confusion_denied_to_nmi']} / {csv_audit['confusion_approved_to_denied']} / {csv_audit['confusion_nmi_to_denied']}")
    print(f"19 relabels still empty on LS: {ls['relabeled_19_still_empty'] or 'none'}")
    if csv_stale_empty_refs and ls["empty_reference_count"] == 0:
        print("(CSV has stale empty refs; LangSmith live is clean.)")
    print(f"\nSafe for final eval: {'YES' if safe else 'NO — see report'}")


if __name__ == "__main__":
    main()
