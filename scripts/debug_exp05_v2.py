import os, json
from dotenv import load_dotenv
from langsmith import Client

load_dotenv(".env")
client = Client()
# Using the v2 project which is currently running or just finished
project_name = "exp05-supervisor-gate3-v2-db9789d3"

def debug_failures():
    print(f"Inspecting failures in {project_name}...")
    runs = list(client.list_runs(project_name=project_name, is_root=True, limit=5))
    
    for r in runs:
        pid = r.inputs.get("patient_data", {}).get("id")
        name = r.inputs.get("patient_data", {}).get("name")
        print(f"\n===== PATIENT: {name} ({pid}) =====")
        
        children = list(client.list_runs(trace_id=r.trace_id))
        for c in children:
            c_name = c.name or "Unnamed"
            # Look for Research Agent output
            if "Research Agent —" in c_name and "supervisor" not in c_name.lower():
                out = c.outputs.get("research_output", "EMPTY") if c.outputs else "NO OUTPUTS"
                print(f"[Research Agent] Output Length: {len(str(out))}")
                
            # Look for Supervisor Evaluation
            if "supervisor_eval_Research Agent" in c_name:
                outs = c.outputs or {}
                # Check for standard content in LangSmith response
                # Usually outputs['generations'][0][0]['text'] or similar
                print(f"[Supervisor Eval] ID: {c.id}")
                if "generations" in outs:
                    text = outs["generations"][0][0].get("text", "NO TEXT FIELD")
                    print(f"REASONING:\n{text}")
                else:
                    print(f"RAW OUTPUTS: {json.dumps(outs, indent=2)}")

if __name__ == "__main__":
    debug_failures()
