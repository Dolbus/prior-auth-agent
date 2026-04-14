import os, json
from dotenv import load_dotenv
from langsmith import Client

load_dotenv(".env")
client = Client()
project = "exp05-supervisor-gate3-needs-more-info-fd3f1676"

runs = list(client.list_runs(project_name=project, is_root=True))
if runs:
    r = runs[0]
    print(f"--- Trace for {r.id} ---")
    # All state updates are often in the trace outputs or metadata
    # But let's check the human_review run which shows the escalated state
    children = list(client.list_runs(trace_id=r.trace_id))
    for c in children:
        if "human_review" in (c.name or ""):
            print("HUMAN REVIEW INPUTS:")
            print(json.dumps(c.inputs, indent=2))
        if "supervisor_eval_Research Agent" in (c.name or ""):
            print(f"SUPERVISOR EVAL OUTPUTS ({c.name}):")
            print(json.dumps(c.outputs, indent=2))
