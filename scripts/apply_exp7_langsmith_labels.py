#!/usr/bin/env python3
"""One-shot: apply Exp 7 dataset label updates via LangSmith API. Loads .env."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from langsmith import Client

DATASET_NAME = "pa-baseline-120-apr08"


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    client = Client()
    ds = client.read_dataset(dataset_name=DATASET_NAME)

    eid: dict[str, str] = {}
    for ex in client.list_examples(dataset_name=DATASET_NAME):
        pid = (ex.inputs or {}).get("patient_data", {}).get("id")
        if pid:
            eid[str(pid)] = str(ex.id)

    # 1. EMPTY → APPROVED (13)
    approved_ids = [
        "PA-024", "PA-076", "PA-098", "PA-108", "PA-078", "PA-028", "PA-088",
        "PA-106", "PA-021", "PA-093", "PA-023", "PA-086", "PA-119",
    ]
    r1 = client.update_examples(
        dataset_id=ds.id,
        updates=[{"id": eid[p], "outputs": {"pa_decision": "APPROVED"}} for p in approved_ids],
    )
    print("Batch 1 (EMPTY→APPROVED):", r1)

    # 2. DENIED → NMI pattern rows — user requested reference DENIED (full list from audit)
    denied_nmi_ids = [
        "PA-073", "PA-052", "PA-097", "PA-074", "PA-022", "PA-047", "PA-071",
        "PA-077", "PA-017", "PA-082", "PA-092", "PA-002", "PA-102", "PA-012",
        "PA-027", "PA-072",
    ]
    r2 = client.update_examples(
        dataset_id=ds.id,
        updates=[{"id": eid[p], "outputs": {"pa_decision": "DENIED"}} for p in denied_nmi_ids],
    )
    print("Batch 2 (DENIED→NMI list → DENIED):", r2)

    # 3. EMPTY → DENIED (3)
    empty_denied_ids = ["PA-110", "PA-080", "PA-025"]
    r3 = client.update_examples(
        dataset_id=ds.id,
        updates=[{"id": eid[p], "outputs": {"pa_decision": "DENIED"}} for p in empty_denied_ids],
    )
    print("Batch 3 (EMPTY→DENIED):", r3)


if __name__ == "__main__":
    main()
