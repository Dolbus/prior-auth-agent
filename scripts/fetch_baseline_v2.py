import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv(".env")
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

def fetch_metrics():
    # Make multiple queries if paging needed? Usually we get up to 1000 items. Just do execute().
    res = sb.table("case_results").select("patient_id, treatment, pa_decision, expected_outcome, escalated, factual_accuracy").limit(1000).execute()
    data = res.data

    total = len(data)
    if total == 0:
        print("No cases found.")
        return

    decisions = {"APPROVED": 0, "DENIED": 0, "NEEDS_MORE_INFO": 0, "UNKNOWN": 0, "TOTAL": total}
    escalated = 0

    for r in data:
        decision = r.get("pa_decision") or "UNKNOWN"
        if decision == "": decision = "UNKNOWN"
        
        if decision in decisions:
            decisions[decision] += 1
        else:
            decisions["UNKNOWN"] += 1
            
        if r.get("escalated"):
            escalated += 1

    print("=== Baseline v2 Metrics ===")
    print(f"Total Cases processed: {total}")
    print(f"APPROVED:        {decisions['APPROVED']}")
    print(f"DENIED:          {decisions['DENIED']}")
    print(f"NEEDS_MORE_INFO: {decisions['NEEDS_MORE_INFO']}")
    print(f"UNKNOWN:         {decisions['UNKNOWN']}")
    print(f"\nEscalated:     {escalated} ({(escalated/total)*100:.1f}%)")
    
    accuracies = [a.get("factual_accuracy", 0) for a in data if a.get("factual_accuracy") is not None]
    if len(accuracies) > 0:
        avg_acc = (sum(accuracies) / len(accuracies)) * 100
        print(f"Avg Accuracy:  {avg_acc:.1f}%")
        
    print("\nDecision by Treatment:")
    treatment_stats = {}
    for r in data:
        t = r["treatment"]
        d = r.get("pa_decision", "UNKNOWN")
        if d == "": d = "UNKNOWN"
        if t not in treatment_stats:
            treatment_stats[t] = {"APPROVED": 0, "DENIED": 0, "NEEDS_MORE_INFO": 0, "UNKNOWN": 0, "Escalated": 0, "Total": 0}
        treatment_stats[t][d] += 1
        if r.get("escalated"):
            treatment_stats[t]["Escalated"] += 1
        treatment_stats[t]["Total"] += 1
        
    for t, s in treatment_stats.items():
        print(f"{t:15s}: Total: {s['Total']:2d} | APP: {s['APPROVED']:2d} | DEN: {s['DENIED']:2d} | NMI: {s['NEEDS_MORE_INFO']:2d} | UNK: {s['UNKNOWN']:2d} | Esc: {s['Escalated']:2d}")

if __name__ == "__main__":
    fetch_metrics()
