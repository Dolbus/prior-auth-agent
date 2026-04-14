import os
import json
from dotenv import load_dotenv
from langsmith import Client

load_dotenv('.env')
client = Client()

project_name = "exp03b-model-swap-supervisors-gpt4o-7807f610"

print("Fetching root runs to identify failed exact matches...")
runs = list(client.list_runs(project_name=project_name, is_root=True))

failed_runs = []
for r in runs:
    feedbacks = list(client.list_feedback(run_ids=[r.id]))
    # check for exact_match or factual_accuracy == 0
    is_failed = False
    for f in feedbacks:
        if (f.key == "exact_match" or f.key == "factual_accuracy") and f.score == 0:
            is_failed = True
            break
            
    if is_failed:
        failed_runs.append(r)
    if len(failed_runs) >= 5:
        break

print(f"Found {len(failed_runs)} failed traces for analysis.\n")

for i, r in enumerate(failed_runs):
    # LangSmith evaluate runner usually puts reference in r.outputs if we passed it, but evaluate.py checks it.
    # We can get inputs directly
    try:
        pid = r.inputs.get("patient_id", r.name)
    except:
        pid = "UNKNOWN"
        
    outputs = r.outputs or {}
    actual = outputs.get("pa_decision", "N/A")
    
    # Expected is harder to grab if it's strictly in the evaluator trace, but we'll try r.reference.
    expected = "N/A"
    
    child_runs = list(client.list_runs(trace_id=r.trace_id))
    
    # RAG/Model layers
    research_out = ""
    rules_out = ""
    
    for cr in child_runs:
        cname = (cr.name or "").lower()
        if "research" in cname and "supervisor" not in cname:
            outs = cr.outputs or {}
            if "generations" in outs:
                research_out = outs["generations"][0][0].get("text", "")
            else:
                research_out = str(outs)
        if "rules checker" in cname and "supervisor" not in cname:
            outs = cr.outputs or {}
            if "generations" in outs:
                rules_out = outs["generations"][0][0].get("text", "")
            else:
                rules_out = str(outs)
                
    print(f"==================================================")
    print(f"TRACE {i+1}: Patient {pid}")
    print(f"Actual Decision: {actual}")
    print(f"--- RESEARCH AGENT LOGIC ---")
    print(f"{str(research_out).strip()}")
    print(f"\n--- RULES CHECKER LOGIC ---")
    print(f"{str(rules_out).strip()}")
    print(f"==================================================\n")
