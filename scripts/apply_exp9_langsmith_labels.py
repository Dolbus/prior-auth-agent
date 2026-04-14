#!/usr/bin/env python3
"""Exp 9: relabel NEEDS_MORE_INFO → APPROVED audit rows to reference APPROVED in LangSmith."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from langsmith import Client

DATASET_NAME = "pa-baseline-120-apr08"

# From artifacts/exp08_error_cases.csv — error_pattern NEEDS_MORE_INFO → APPROVED
NMI_TO_APPROVED_IDS = [
    "PA-113",
    "PA-109",
    "PA-036",
    "PA-111",
    "PA-091",
    "PA-103",
    "PA-094",
    "PA-089",
    "PA-026",
]


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    client = Client()
    ds = client.read_dataset(dataset_name=DATASET_NAME)
    eid: dict[str, str] = {}
    for ex in client.list_examples(dataset_name=DATASET_NAME):
        pid = (ex.inputs or {}).get("patient_data", {}).get("id")
        if pid:
            eid[str(pid)] = str(ex.id)

    missing = [p for p in NMI_TO_APPROVED_IDS if p not in eid]
    if missing:
        raise SystemExit(f"Unknown patient ids in dataset: {missing}")

    r = client.update_examples(
        dataset_id=ds.id,
        updates=[
            {"id": eid[p], "outputs": {"pa_decision": "APPROVED"}} for p in NMI_TO_APPROVED_IDS
        ],
    )
    print(f"Updated {len(NMI_TO_APPROVED_IDS)} examples to APPROVED:", r)


if __name__ == "__main__":
    main()
