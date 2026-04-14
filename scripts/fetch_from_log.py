import re

def parse_log_for_baseline():
    approved = 0
    denied = 0
    nmi = 0
    unknown = 0
    escalated = 0
    
    with open("batch_run_output.log", "r") as f:
        content = f.read()
        
    # We need to find the batch summary section at the end.
    idx = content.rfind("BATCH SUMMARY")
    if idx == -1:
        print("Could not find batch summary.")
        return
        
    summary_text = content[idx:]
    
    # regex for: Decision: DENIED           Expected: DENIED
    for line in summary_text.split("\n"):
        if "Decision:" in line:
            m = re.search(r"Decision:\s*([A-Za-z_]*)", line)
            if m:
                dec = m.group(1).strip()
                if dec == "APPROVED":
                    approved += 1
                elif dec == "DENIED":
                    denied += 1
                elif dec == "NEEDS_MORE_INFO":
                    nmi += 1
                else:  # Empty string corresponds to UNKNOWN
                    unknown += 1
                    
        # Check escalated. The batch summary has "Expected: ESCALATED", but for escalated cases the decision is empty (UNKNOWN).
        # Actually in our previous pipeline run, escalated cases output "ESCALATED" in the log? No, "Decision: " is empty.
        
    # Let's count escalated separately:
    # Look for "Escalating." in the full log or look for "escalated_from_agent"
    total_escalated = content.count("Escalating.")
    
    print(f"APPROVED: {approved}")
    print(f"DENIED: {denied}")
    print(f"NEEDS_MORE_INFO: {nmi}")
    print(f"UNKNOWN: {unknown}")
    print(f"Escalated (total): {total_escalated}")

if __name__ == "__main__":
    parse_log_for_baseline()
