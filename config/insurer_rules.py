import json
import os

def get_rules_for_treatment(treatment_name: str, insurer: str = "") -> dict | None:
    """Look up insurer rules by treatment name (case-insensitive) and insurer.
    
    Reads from the dynamically generated insurer_rules.json.
    """
    path = os.path.join(os.path.dirname(__file__), "insurer_rules.json")
    if not os.path.exists(path):
        return None
        
    with open(path, "r") as f:
        rules_list = json.load(f)
        
    key = treatment_name.lower().replace(" ", "")
    insurer_key = insurer.lower()
    
    for rule in rules_list:
        if rule.get("insurer", "").lower() == insurer_key:
            if key in rule.get("brand_name", "").lower().replace(" ", "") or key in rule.get("drug_name", "").lower().replace(" ", ""):
                return rule
                
    # Fallback to just treatment match if insurer wasn't exact
    for rule in rules_list:
        if key in rule.get("brand_name", "").lower().replace(" ", "") or key in rule.get("drug_name", "").lower().replace(" ", ""):
            return rule
            
    return None
