import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv(".env")
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

res = sb.table("case_results").select("patient_id, treatment, pa_decision, supervisor_notes, writer_output").execute()

count = 0
for r in res.data:
    dec = r.get("pa_decision")
    if not dec or dec == "UNKNOWN":
        print("==========")
        print(f"ID: {r.get('patient_id')} | Treatment: {r.get('treatment')}")
        print(f"Decision: '{dec}'")
        notes = r.get("supervisor_notes", [])
        if notes:
            for note in notes:
                print(f"Note: {note}")
        count += 1
        if count >= 3:
            break
