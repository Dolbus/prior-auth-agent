import time
import os
import json
from dotenv import load_dotenv
from langsmith import Client
import numpy as np

load_dotenv('.env')
client = Client()

def get_metrics():
    project_name = "exp04-rules-strict-adherence-1818de29"
    
    print(f"Fetching runs in {project_name}...")
    # Get only root runs
    root_runs = list(client.list_runs(project_name=project_name, is_root=True))
    print(f"Run completed. Found {len(root_runs)} root runs. Calculating metrics...")
    
    # We also need the feedback (accuracy)
    accuracy_sum = 0
    accuracy_count = 0
    
    decisions = {"APPROVED": 0, "DENIED": 0, "NEEDS_MORE_INFO": 0, "UNKNOWN": 0, "ESCALATED": 0}
    
    latencies = []
    
    total_tokens = 0
    prompt_tokens = 0
    comp_tokens = 0
    
    total_cost = 0.0
    prompt_cost = 0.0
    comp_cost = 0.0
    
    for r in root_runs:
        # feedback
        feedbacks = client.list_feedback(run_ids=[r.id])
        for f in feedbacks:
            if f.key == "factual_accuracy" and f.score is not None:
                accuracy_sum += f.score
                accuracy_count += 1
                
        # output decisions
        outs = r.outputs or {}
        dec = outs.get("pa_decision") or "UNKNOWN"
        if dec == "": dec = "UNKNOWN"
        # Since expected output format usually sets pa_decision to empty if escalated, checking writer escalation
        # If the metric is mapped, we can just do:
        if "escalated" in str(outs).lower() or outs.get("escalated") is True:
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
        t_stats = r.total_tokens or 0
        p_stats = r.prompt_tokens or 0
        c_stats = r.completion_tokens or 0
        
        cost = r.total_cost or 0.0
        
        total_tokens += t_stats
        prompt_tokens += p_stats
        comp_tokens += c_stats
        
        # We don't have separate prompt/completion cost directly on the root sometimes, but we estimate or use available
        total_cost += float(cost)
        # cost split can be estimated for gpt-4o-mini if not available:
        
    # fallback cost estimation if 0 (sometimes langsmith aggregates are slow):
    if total_cost == 0 and total_tokens > 0:
        prompt_cost = (prompt_tokens / 1000000.0) * 0.150
        comp_cost = (comp_tokens / 1000000.0) * 0.600
        total_cost = prompt_cost + comp_cost
    else:
        # Langsmith usually logs total_cost. Splitting by ratio:
        if total_tokens > 0:
            prompt_cost = total_cost * (prompt_tokens / total_tokens)
            comp_cost = total_cost * (comp_tokens / total_tokens)
            
    final_accuracy = (accuracy_sum / accuracy_count) * 100 if accuracy_count > 0 else 0
    
    lat_p50 = np.percentile(latencies, 50) if latencies else 0
    lat_p95 = np.percentile(latencies, 95) if latencies else 0
    
    metrics = {
        "final_accuracy": f"{final_accuracy:.1f}%",
        "decisions_count": {
            "UNKNOWN": decisions["UNKNOWN"],
            "ESCALATED": decisions["ESCALATED"],
            "APPROVED": decisions["APPROVED"],
            "DENIED": decisions["DENIED"],
            "NEEDS_MORE_INFO": decisions["NEEDS_MORE_INFO"]
        },
        "latency": {
            "p50_seconds": round(lat_p50, 2),
            "p95_seconds": round(lat_p95, 2)
        },
        "tokens": {
            "total": total_tokens,
            "prompt": prompt_tokens,
            "completion": comp_tokens
        },
        "cost": {
            "total_usd": round(total_cost, 4),
            "prompt_usd": round(prompt_cost, 4),
            "completion_usd": round(comp_cost, 4)
        }
    }
    
    print(json.dumps(metrics, indent=2))

if __name__ == "__main__":
    get_metrics()
