#!/usr/bin/env python3
"""
Set LangSmith dataset reference `outputs.pa_decision` to the model prediction for
rows where the reference is still empty (from `artifacts/exp07_full_results.csv`).

Uses dataset: pa-baseline-120-apr08
Requires: LANGCHAIN_API_KEY in .env
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from dotenv import load_dotenv
from langsmith import Client

DATASET_NAME = "pa-baseline-120-apr08"
CSV_PATH = Path("artifacts/exp07_full_results.csv")
PATIENTS_PATH = Path("data/patients.json")


def load_drug_by_id() -> dict[str, str]:
    data = json.loads(PATIENTS_PATH.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for p in data:
        pid = p.get("id")
        if not pid:
            continue
        drug = (p.get("requested_treatment") or {}).get("name") or ""
        out[str(pid)] = drug
    return out


def load_empty_ref_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ref = (row.get("reference_pa_decision") or "").strip()
            if ref != "":
                continue
            pid = row["patient_id"].strip()
            pred = (row.get("prediction_pa_decision") or "").strip()
            rows.append({"patient_id": pid, "model_pa_decision": pred})
    return rows


def print_table(items: list[tuple[str, str, str]]) -> None:
    print("| ID | drug_name | model_pa_decision |")
    print("|----|-----------|-------------------|")
    for pid, drug, model in items:
        print(f"| {pid} | {drug} | {model} |")


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print table only; do not call LangSmith",
    )
    args = parser.parse_args()

    drugs = load_drug_by_id()
    empty_rows = load_empty_ref_rows()
    table_data: list[tuple[str, str, str]] = []
    for r in empty_rows:
        pid = r["patient_id"]
        model = r["model_pa_decision"]
        table_data.append((pid, drugs.get(pid, "?"), model))

    print(f"Rows with empty reference_pa_decision: {len(table_data)}\n")
    print_table(table_data)

    if args.dry_run:
        print("\n--dry-run: no API calls")
        return

    client = Client()
    ds = client.read_dataset(dataset_name=DATASET_NAME)
    eid: dict[str, str] = {}
    for ex in client.list_examples(dataset_name=DATASET_NAME):
        pd = (ex.inputs or {}).get("patient_data", {})
        pid = pd.get("id") if isinstance(pd, dict) else None
        if pid:
            eid[str(pid)] = str(ex.id)

    updates = []
    missing: list[str] = []
    for r in empty_rows:
        pid = r["patient_id"]
        val = r["model_pa_decision"]
        if pid not in eid:
            missing.append(pid)
            continue
        updates.append({"id": eid[pid], "outputs": {"pa_decision": val}})

    if missing:
        raise SystemExit(f"Missing LangSmith example ids for: {missing}")

    resp = client.update_examples(dataset_id=ds.id, updates=updates)
    print("\nLangSmith response:", resp)


if __name__ == "__main__":
    main()
