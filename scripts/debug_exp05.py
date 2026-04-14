import os, json
from dotenv import load_dotenv
from langsmith import Client

load_dotenv(".env")
client = Client()
project = "exp05-supervisor-gate3-needs-more-info-fd3f1676"

runs = list(client.list_runs(project_name=project, is_root=True))
print(f"Total runs: {len(runs)}")

for r in runs[:3]:
    pid = r.inputs.get("patient_data", {}).get("id")
    print(f"\n--- DEBUG {pid} ---")
    children = list(client.list_runs(trace_id=r.trace_id))
    for c in children:
        if "supervisor_eval_Research Agent" in (c.name or ""):
            print(f"AGENT: {c.name}")
            outs = c.outputs or {}
            # LangSmith JSON structure for LLM runs
            gen = outs.get("generations")
            if gen:
                text = gen[0][0].get("text", "No text field")
                print(f"REASONING:\n{text}")
            else:
                print(f"OUTPUTS:\n{json.dumps(outs, indent=2)}")
