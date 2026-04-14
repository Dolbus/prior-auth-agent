import re
import os
from dotenv import load_dotenv
from langsmith import Client

load_dotenv('.env')
client = Client()

def get_unknown_ids():
    with open("batch_run_output.log", "r") as f:
        content = f.read()
    
    idx = content.rfind("BATCH SUMMARY")
    if idx == -1: return []
    
    summary_text = content[idx:]
    unknown_ids = []
    
    # regex for: ❌ [PA-024] Daniel Cooper        Decision:                  Expected: APPROVED
    for line in summary_text.split("\n"):
        m = re.search(r"\[(PA-\d{3})\]", line)
        if m:
            pid = m.group(1)
            dec_match = re.search(r"Decision:\s*(.*?)\s+Expected:", line)
            if dec_match:
                dec = dec_match.group(1).strip()
                if dec == "": # UNKNOWN!
                    unknown_ids.append(pid)
                    
    return unknown_ids

def main():
    unknown_ids = get_unknown_ids()
    print(f"Found {len(unknown_ids)} UNKNOWN cases: {unknown_ids}")
    
    # Fetch traces for just 3 of them
    target_ids = unknown_ids[:3]
    
    for pid in target_ids:
        print(f"\n==================================================")
        print(f"PATIENT_ID: {pid}")
        runs = list(client.list_runs(
            project_name='prior-auth-agent',
            filter=f'has(tags, "{pid}")',
            run_type='llm',
            limit=20,
        ))
        
        # 1. Get the latest Writer Agent output
        writer_output = ""
        writer_runs = [r for r in runs if "Writer" in (r.name or "") and "supervisor" not in (r.name or "")]
        if writer_runs:
            # First one is the latest because of order (or we can just take [0] assuming reverse chrono)
            out = writer_runs[0].outputs or {}
            try:
                writer_output = out['generations'][0][0]['text']
            except Exception:
                writer_output = str(out)
                
        print(f"WRITER OUTPUT:\n{writer_output[:400]}\n[...truncated...]\n")
        
        # 2. Get the Gate 4 supervisor evaluation
        eval_output = ""
        eval_runs = [r for r in runs if "supervisor" in (r.name or "").lower() and "writer" in (r.name or "").lower()]
        if eval_runs:
            out = eval_runs[0].outputs or {}
            try:
                eval_output = out['generations'][0][0]['text']
            except Exception:
                eval_output = str(out)
                
        print(f"GATE 4 EVALUATION:\n{eval_output}\n")
        print(f"==================================================")

if __name__ == "__main__":
    main()
