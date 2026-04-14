import os
import json
from supabase import create_client
from dotenv import load_dotenv
from typing import List, Dict

load_dotenv('.env')
sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])

def fetch_gate4_failures():
    res = sb.table("case_results").select("patient_id, writer_output, supervisor_notes, pa_decision").limit(1000).execute()
    data = res.data

    unknowns = [row for row in data if not row.get("pa_decision") or row.get("pa_decision") == ""]
    
    results = []
    
    for row in unknowns:
        pid = row["patient_id"]
        writer_out = row.get("writer_output")
        notes = row.get("supervisor_notes", [])
        
        gate4_note = [n for n in notes if "writer" in n.lower() or "draft" in n.lower()]
        
        results.append({
            "patient_id": pid,
            "writer_output": writer_out,
            "gate4_notes": gate4_note
        })
        
    print(f"Total Unknown cases: {len(unknowns)}")
    print("\n--- 3 Representative Examples ---\n")
    for r in results[:3]:
        print(f"==================================================")
        print(f"PATIENT_ID: {r['patient_id']}")
        print(f"GATE 4 NOTES: {r['gate4_notes']}")
        print(f"==================================================\n")

if __name__ == "__main__":
    fetch_gate4_failures()
