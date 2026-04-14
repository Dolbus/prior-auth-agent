"""
Research Agent — reads patient data from JSON and uses GPT-4o mini
to extract and summarize the clinical context needed for PA evaluation.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from config.settings import settings
from metrics import collector

SYSTEM_PROMPT = """\
You are a clinical research assistant specializing in Prior Authorization.
Your job is to review a patient's medical record and produce a structured
clinical summary that will be used to evaluate whether a treatment request
meets insurer requirements.

You MUST include ALL of the following sections in your output:

1. PATIENT DEMOGRAPHICS — name, age, gender, insurance details
2. DIAGNOSIS — primary diagnosis, ICD-10 code, severity, onset
3. CURRENT MEDICATIONS — list every current med with dose, duration, and response
4. REQUESTED TREATMENT — what is being requested and why  
5. RELEVANT LABS — key lab values that support or contradict the request
6. CLINICAL NOTES SUMMARY — key findings from the clinical notes
7. STEP THERAPY HISTORY — which prior therapies have been tried, for how long, and outcomes

Be factual. Do NOT add information not present in the patient record.
Do NOT make treatment recommendations — that is for the Rules Checker.
"""


def research_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: extracts clinical context from patient data.

    Reads patient_data from state, sends it to GPT-4o mini with a
    structured extraction prompt, and returns the research_output.
    """
    # Start timing
    updates = collector.start_agent(state, "research")
    state = {**state, **updates}

    patient = state.get("patient_data", {})
    if not patient:
        m = collector.end_agent(state, "research")
        return {
            **m,
            "research_output": "",
            "error": "No patient data found in state.",
            "supervisor_notes": ["[Research] ERROR: No patient data in state."],
        }

    # Build the prompt
    patient_json = json.dumps(patient, indent=2, default=str)
    base_msg = (
        f"Please review the following patient record and produce a structured "
        f"clinical summary for Prior Authorization evaluation.\n\n"
        f"PATIENT RECORD:\n```json\n{patient_json}\n```"
    )
    
    retry_instruction = state.get("retry_instruction", "")
    if retry_instruction:
        human_msg = base_msg + (
            f"\n\nIMPORTANT RETRY INSTRUCTION: The supervisor rejected your previous extraction for the following reason:\n"
            f"{retry_instruction}\n\n"
            f"Re-evaluate the patient JSON specifically looking for this missing data. If the data is genuinely not present in the record, clearly state 'NOT FOUND' instead of hallucinating."
        )
    else:
        human_msg = base_msg

    try:
        llm = ChatOpenAI(
            model=settings.openai_model,
            temperature=settings.openai_temperature,
            max_tokens=settings.openai_max_tokens,
            api_key=settings.openai_api_key,
        )

        response = llm.invoke(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=human_msg),
            ],
            config={
                "run_name": f"Research Agent — {patient.get('name', 'unknown')}",
                "tags": ["research", "prior-auth", patient.get("id", "")],
                "metadata": {
                    "agent": "research",
                    "patient_id": patient.get("id", ""),
                    "patient_name": patient.get("name", ""),
                    "treatment": patient.get("requested_treatment", {}).get("name", ""),
                },
            },
        )

        # Extract token usage from response metadata
        usage = response.response_metadata.get("token_usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        research_output = response.content

        # End timing
        m = collector.end_agent(state, "research", prompt_tokens, completion_tokens)

        return {
            **m,
            "research_output": research_output,
            "current_step": "research_complete",
            "supervisor_notes": [
                f"[Research] Extracted clinical summary for patient "
                f"{patient.get('name', 'unknown')} "
                f"({prompt_tokens}p + {completion_tokens}c tokens)."
            ],
        }

    except Exception as e:
        m = collector.end_agent(state, "research")
        return {
            **m,
            "research_output": "",
            "error": f"Research agent failed: {e}",
            "supervisor_notes": [f"[Research] ERROR: {e}"],
        }
