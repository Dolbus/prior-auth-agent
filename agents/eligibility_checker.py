"""
Eligibility Checker Agent — Determines if PA is required.
"""
from typing import Any
import json
import os
from langchain_core.messages import SystemMessage, HumanMessage
from config.settings import settings
from metrics import collector
from langchain_openai import ChatOpenAI
from config.insurer_rules import get_rules_for_treatment

def get_rules_string() -> str:
    path = os.path.join(os.path.dirname(__file__), "../config/insurer_rules.json")
    if not os.path.exists(path):
        return "[]"
    with open(path, "r") as f:
        return f.read()

SYSTEM_PROMPT = """You are an Eligibility Checker Agent for a Prior Authorization system.
Your job is to read the patient's demographics, insurance provider, and requested treatment.
Then, look at the provided Insurer Rules JSON.

Determine:
1. Is the Insurer and Requested Drug present in the Rules?
2. If YES, what is the 'pa_required' status?
3. If NO (unknown insurer or drug), you MUST default to "PA REQUIRED: TRUE" and clearly state "FLAG: UNKNOWN_RULE".

Your output MUST include:
- INSURER RECOGNIZED: Yes/No
- DRUG RECOGNIZED: Yes/No
- PA REQUIRED: True/False
- FLAG: UNKNOWN_RULE (only if not found)
- CONFIDENCE SCORE: (0-100%) - Give 100% if exact match, 50% if unknown rule fallback.
"""

NORMALIZATION_MAP = {
    "UHC": "UnitedHealthcare",
    "UNITED": "UnitedHealthcare",
    "UNITED HEALTHCARE": "UnitedHealthcare"
}

def _normalize_name(name: str) -> str:
    name_upper = name.strip().upper()
    return NORMALIZATION_MAP.get(name_upper, name.strip())

def eligibility_checker_node(state: dict[str, Any]) -> dict[str, Any]:
    """Check if PA is required based on rules lookup."""
    updates = collector.start_agent(state, "eligibility_checker")
    state = {**state, **updates}
    
    patient_data = state.get("patient_data", {})
    
    treatment = patient_data.get("requested_treatment", {})
    treatment_name = treatment.get("name", "")
    insurer = patient_data.get("insurance_provider", "")
    
    normalized_insurer = _normalize_name(insurer)
    rules = get_rules_for_treatment(treatment_name, normalized_insurer)
    
    if rules is None:
        rules = get_rules_for_treatment(treatment.get("generic_name", ""), normalized_insurer)
        
    if rules is None:
        rules = get_rules_for_treatment(treatment.get("cpt_code", ""), normalized_insurer)
    
    if rules is not None:
        pa_req_str = "True" if rules.get('pa_required', True) else "False"
        content = f"- INSURER RECOGNIZED: Yes\n- DRUG RECOGNIZED: Yes\n- PA REQUIRED: {pa_req_str}\n- FLAG: \n- CONFIDENCE SCORE: 100"
        end_updates = collector.end_agent(state, "eligibility_checker", 0, 0)
        return {
            **end_updates,
            "eligibility_output": content,
        }

    # Layer 2 Fallback to LLM
    patient_str = json.dumps(patient_data, indent=2)
    rules_str = get_rules_string()
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0).with_config({
        "run_name": "eligibility_checker",
        "tags": ["agent", "eligibility"],
    })
    
    messages = [
        SystemMessage(content=SYSTEM_PROMPT + "\n\nRULES DB:\n" + rules_str),
        HumanMessage(content=f"Patient Data:\n{patient_str}")
    ]
    
    response = llm.invoke(messages)
    content = str(response.content)
    
    usage = response.response_metadata.get("token_usage", {})
    end_updates = collector.end_agent(
        state, 
        "eligibility_checker", 
        usage.get("prompt_tokens", 0),
        usage.get("completion_tokens", 0)
    )
    
    return {
        **end_updates,
        "eligibility_output": content,
    }
