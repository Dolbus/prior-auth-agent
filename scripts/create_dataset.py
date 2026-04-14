import os
import json
from supabase import create_client
from dotenv import load_dotenv
from langsmith import Client

def main():
    load_dotenv(".env")
    sb = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))
    ls_client = Client()

    # Load local patient data map
    with open("data/patients.json", "r") as f:
        patients_raw = json.load(f)
    patient_map = {p["id"]: p for p in patients_raw}

    # Fetch rows from supabase
    print("Fetching from Supabase case_results...")
    res = sb.table("case_results").select("*").execute()
    data = res.data
    print(f"Fetched {len(data)} completed cases.")

    dataset_name = "pa-baseline-120-apr08"
    
    try:
        ls_client.read_dataset(dataset_name=dataset_name)
        print(f"Dataset {dataset_name} already exists. Deleting it to start fresh.")
        ls_client.delete_dataset(dataset_name=dataset_name)
    except Exception:
        pass

    dataset = ls_client.create_dataset(
        dataset_name=dataset_name,
        description="Official baseline dataset containing 120 synthetic cases from Phase 3 with verified decisions."
    )

    inputs = []
    outputs = []

    for row in data:
        pid = row.get("patient_id")
        pdata = patient_map.get(pid, {})
        inp = {
            "patient_id": pid,
            "insurer": row.get("insurance_provider"),
            "treatment": row.get("treatment"),
            "patient_data": pdata
        }
        outp = {
            "pa_decision": row.get("pa_decision")
        }
        inputs.append(inp)
        outputs.append(outp)

    print(f"Creating examples in LangSmith dataset '{dataset_name}'...")
    ls_client.create_examples(
        inputs=inputs,
        outputs=outputs,
        dataset_id=dataset.id
    )
    print("Done!")

if __name__ == "__main__":
    main()
