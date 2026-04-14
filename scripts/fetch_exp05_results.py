import os
import json
from dotenv import load_dotenv
from langsmith import Client
import numpy as np

load_dotenv('.env')
client = Client()

project_name = "exp05-supervisor-gate3-needs-more-info-fd3f1676"
failed_five_ids = ["PA-069", "PA-059", "PA-068", "PA-026", "PA-119"]

def get_metrics():
    print(f"Fetching runs in {project_name}...")
    root_runs = list(client.list_runs(project_name=project_name, is_root=True))
    print(f"Found {len(root_runs)} root runs. Calculating metrics...")
    
    accuracy_sum = 0
    accuracy_count = 0
    decisions = {"APPROVED": 0, "DENIED": 0, "NEEDS_MORE_INFO": 0, "UNKNOWN": 0, "ESCALATED": 0}
    latencies = []
    total_tokens = 0
    prompt_tokens = 0
    comp_tokens = 0
    total_cost = 0.0
    
    failed_five_data = {}

    for r in root_runs:
        # feedback
        feedbacks = client.list_feedback(run_ids=[r.id])
        for f in feedbacks:
            if f.key == "exact_match" and f.score is not None:
                accuracy_sum += f.score
                accuracy_count += 1
                
        # output decisions
        outs = r.outputs or {}
        dec = outs.get("pa_decision") or "UNKNOWN"
        if dec == "": dec = "UNKNOWN"
        
        # Check for escalation
        is_escalated = False
        if "escalated" in str(outs).lower() or outs.get("escalated") is True:
            is_escalated = True

        if is_escalated:
            decisions["ESCALATED"] += 1
        elif dec in decisions:
            decisions[dec] += 1
        else:
            decisions["UNKNOWN"] += 1
            
        # latencies
        if r.end_time and r.start_time:
            lat = (r.end_time - r.start_time).total_seconds()
            latencies.append(lat)
            
        # tokens & costs
        total_tokens += (r.total_tokens or 0)
        prompt_tokens += (r.prompt_tokens or 0)
        comp_tokens += (r.completion_tokens or 0)
        total_cost += float(r.total_cost or 0.0)
        
        # Capture Failed Five
        p_id = "UNKNOWN"
        try:
            p_id = r.inputs['patient_data']['id']
        except:
            pass
            
        if p_id in failed_five_ids:
            # We need the rules checker output
            rules_out = ""
            supervisor_reasoning = ""
            child_runs = list(client.list_runs(trace_id=r.trace_id))
            for cr in child_runs:
                if "rules checker" in (cr.name or "").lower() and "supervisor" not in (cr.name or "").lower():
                    rules_out = cr.outputs.get("rules_output", "") if cr.outputs else ""
                if "supervisor_eval_Rules Checker" in (cr.name or ""):
                    supervisor_reasoning = cr.outputs.get("output", "No output") if cr.outputs else "No output"
            
            failed_five_data[p_id] = {
                "actual_decision": dec,
                "is_escalated": is_escalated,
                "rules_checker_output": rules_out,
                "supervisor_reasoning": supervisor_reasoning
            }

    # fallback cost estimation
    if total_cost == 0 and total_tokens > 0:
        total_cost = (prompt_tokens / 1000000.0) * 0.15 + (comp_tokens / 1000000.0) * 0.60
            
    final_accuracy = (accuracy_sum / accuracy_count) * 100 if accuracy_count > 0 else 0
    lat_p50 = np.percentile(latencies, 50) if latencies else 0
    lat_p95 = np.percentile(latencies, 95) if latencies else 0
    
    metrics = {
        "final_accuracy": f"{final_accuracy:.1f}%",
        "decisions_count": decisions,
        "latency": {"p50": round(lat_p50, 2), "p95": round(lat_p95, 2)},
        "tokens": {"total": total_tokens, "prompt": prompt_tokens, "completion": comp_tokens},
        "cost": {"total_usd": round(total_cost, 4)}
    }
    
    return metrics, failed_five_data

if __name__ == "__main__":
    metrics, failed_five = get_metrics()
    print("Aggregate Metrics:")
    print(json.dumps(metrics, indent=2))
    print("\nFailed Five Data:")
    for pid, data in failed_five.items():
        print(f"--- {pid} ---")
        print(f"Decision: {data['actual_decision']} (Escalated: {data['is_escalated']})")
        print(f"Supervisor Reasoning:\n{data['supervisor_reasoning']}")
        print(f"Rules Checker Output (truncated):\n{data['rules_checker_output'][:200]}...\n")
