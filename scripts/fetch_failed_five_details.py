import os
import json
from dotenv import load_dotenv
from langsmith import Client

load_dotenv('.env')
client = Client()

project_name = "exp04-rules-strict-adherence-6467e501"
failed_five_ids = ["PA-069", "PA-059", "PA-068", "PA-026", "PA-119"]

def get_failed_five_details():
    print(f"Fetching trace details for Failed Five in {project_name}...")
    
    results = {}
    
    # List all runs but filter manually for efficiency or just iterate
    # Actually client.list_runs(project_name=project_name) is better
    runs = list(client.list_runs(project_name=project_name, is_root=True))
    
    for r in runs:
        p_id = "UNKNOWN"
        try:
            # Check inputs for the patient ID
            p_id = r.inputs['patient_data']['id']
        except:
            continue
            
        if p_id in failed_five_ids:
            print(f"Found trace for {p_id}...")
            
            # Get expected from inputs/data
            expected = r.inputs['patient_data'].get('expected_outcome', 'N/A')
            actual = r.outputs.get('pa_decision', 'UNKNOWN') if r.outputs else 'UNKNOWN'
            
            # Fetch all child runs for this trace
            child_runs = list(client.list_runs(trace_id=r.trace_id))
            rules_checker_output = "NOT FOUND"
            supervisor_reasoning = "NOT FOUND"
            
            # Find the Rules Checker run and the Supervisor evaluation run
            for cr in child_runs:
                name = (cr.name or "").lower()
                if "rules checker" in name and "supervisor" not in name:
                    rules_checker_output = cr.outputs.get("rules_output", "Output Empty") if cr.outputs else "No Outputs"
                if "supervisor_eval_rules checker" in name:
                    supervisor_reasoning = cr.outputs.get("output", "Empty") if cr.outputs else "No reasoning"
            
            results[p_id] = {
                "expected": expected,
                "actual": actual,
                "rules_checker_output": rules_checker_output,
                "supervisor_eval_reasoning": supervisor_reasoning
            }
            
    return results

if __name__ == "__main__":
    details = get_failed_five_details()
    with open("failed_five_results.json", "w") as f:
        json.dump(details, f, indent=2)
    print("Results saved to failed_five_results.json")
