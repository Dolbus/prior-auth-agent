import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv(".env")
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

res = sb.table("case_results").select(
    "patient_id, treatment, pa_decision, expected_outcome, supervisor_notes, escalated"
).execute()

# Tally all distinct pa_decision values
from collections import Counter
decisions = Counter()
for r in res.data:
    dec = repr(r.get("pa_decision", "NONE"))
    decisions[dec] += 1

print("=== ALL DISTINCT pa_decision VALUES (repr) ===")
for val, count in decisions.most_common():
    print(f"  {val!s:40s} count={count}")

print("\n=== CASES WITH pa_decision NOT IN APPROVED/DENIED/NEEDS_MORE_INFO ===")
count = 0
for r in res.data:
    dec = r.get("pa_decision", "")
    if dec not in ("APPROVED", "DENIED", "NEEDS_MORE_INFO"):
        print(f"patient_id={r['patient_id']:8s} | treatment={r['treatment']:20s} | pa_decision={repr(dec):20s} | escalated={r.get('escalated')} | expected={r.get('expected_outcome')}")
        count += 1
print(f"\nTotal: {count}")
