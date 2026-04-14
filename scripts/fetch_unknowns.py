import os
from dotenv import load_dotenv
from langsmith import Client

load_dotenv(".env")
client = Client()

runs = client.list_runs(
    project_name="prior-auth-agent",
    filter='has(tags, "rules_checker")',
    limit=100
)

count = 0
for r in runs:
    out = r.outputs
    if not out: continue
    
    content = ""
    try:
        # standard extraction for ChatOpenAI response
        if 'generations' in out and out['generations']:
            content = out['generations'][0].get('message', {}).get('kwargs', {}).get('content', '')
            if not content:
                content = out['generations'][0].get('text', '')
        elif 'output' in out:
            content = out['output'].get('content', '')
    except Exception:
        pass
        
    if not content:
        content = str(out)
        
    # Check if this raw output failed to contain the canonical determinators
    has_app = "APPROVED" in content
    has_den = "DENIED" in content
    has_nmi = "NEEDS_MORE_INFO" in content
    
    if not has_app and not has_den and not has_nmi:
        print(f"--- EXAMPLE {count+1} ---")
        print(content)
        print("\n")
        count += 1
        if count >= 3:
            break
