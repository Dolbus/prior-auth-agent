import os
from dotenv import load_dotenv
from langsmith import Client

load_dotenv(".env")
client = Client()

# Pull runs tagged "research" for our known escalated patients
target_ids = ["PA-021", "PA-028", "PA-066"]

count = 0
for pid in target_ids:
    runs = list(client.list_runs(
        project_name="prior-auth-agent",
        filter=f'has(tags, "{pid}")',
        run_type="llm",
        limit=10,
    ))
    
    # find the research run (not supervisor_eval)
    for r in runs:
        name = r.name or ""
        if "Research Agent" in name and "supervisor" not in name.lower():
            print(f"\n{'='*70}")
            print(f"PATIENT: {pid} | Run: {name}")
            print(f"{'='*70}")
            out = r.outputs or {}
            # LangSmith stores chat model outputs under generations
            text = ""
            try:
                gens = out.get("generations", [])
                if gens:
                    text = gens[0].get("text", "") or gens[0].get("message", {}).get("kwargs", {}).get("content", "")
            except Exception:
                pass
            if not text:
                text = str(out)
            print(text[:3000])
            count += 1
            break
    
    if count == 0:
        print(f"\n[{pid}] No research run found — may have been deduplicated or missing in LangSmith.")
