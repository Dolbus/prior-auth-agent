"""
Writer Agent — drafts a structured Prior Authorization letter/form
combining the Research Agent's clinical summary and the Rules Checker's
determination.
"""

from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from config.settings import settings
from metrics import collector

SYSTEM_PROMPT = """\
You are a medical documentation specialist who drafts Prior Authorization
request forms and determination letters.

You will receive:
1. A clinical research summary about the patient
2. A rules evaluation with the PA determination

Your job is to draft a COMPLETE, PROFESSIONAL Prior Authorization document.

Your output MUST follow this exact structure:

═══════════════════════════════════════════════════
PRIOR AUTHORIZATION REQUEST — [DETERMINATION]
═══════════════════════════════════════════════════

DATE: [today's date]
REFERENCE #: [patient ID]-PA

SECTION 1: PATIENT INFORMATION
- Full name, DOB, age, gender
- Insurance provider, plan, member ID, group number
- Referring provider name, NPI, specialty

SECTION 2: CLINICAL SUMMARY
- Primary diagnosis with ICD-10 code
- Disease severity and onset
- Current treatment regimen and response
- Relevant lab results

SECTION 3: REQUESTED TREATMENT
- Treatment name (brand and generic)
- Dosage and administration
- Clinical rationale for the request

SECTION 4: MEDICAL NECESSITY JUSTIFICATION
- Why the requested treatment is medically necessary
- Prior therapies tried and their outcomes
- Supporting clinical evidence

SECTION 5: INSURER CRITERIA EVALUATION
- Step therapy compliance status
- Each criterion: MET / NOT MET / INSUFFICIENT DATA
- Safety screening results (if applicable)

SECTION 6: DETERMINATION
- APPROVED / DENIED / NEEDS_MORE_INFO
- Detailed reasoning
- If DENIED: specific unmet criteria
- If NEEDS_MORE_INFO: specific information required
- Next steps for the provider

═══════════════════════════════════════════════════

Write professionally and precisely. Include all clinical details.
Do NOT fabricate any information not in the source materials.
"""


def writer_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: drafts the PA form from research + rules outputs.

    Reads research_output and rules_output from state, uses GPT-4o mini
    to generate a structured PA document, and returns writer_output.
    """
    updates = collector.start_agent(state, "writer")
    state = {**state, **updates}

    research = state.get("research_output", "")
    rules = state.get("rules_output", "")
    patient = state.get("patient_data", {})

    if not research or not rules:
        m = collector.end_agent(state, "writer")
        return {
            **m,
            "writer_output": "",
            "error": "Missing research or rules output for writer.",
            "supervisor_notes": ["[Writer] ERROR: Missing input data."],
        }

    human_msg = (
        f"Draft a Prior Authorization document for the following case.\n\n"
        f"PATIENT ID: {state.get('patient_id', 'N/A')}\n"
        f"PATIENT NAME: {patient.get('name', 'N/A')}\n\n"
        f"CLINICAL RESEARCH SUMMARY:\n{research}\n\n"
        f"RULES EVALUATION & DETERMINATION:\n{rules}\n\n"
        f"Please produce the complete PA document following the required structure."
    )

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
                "run_name": f"Writer Agent — {patient.get('name', 'N/A')}",
                "tags": ["writer", "prior-auth", state.get("patient_id", "")],
                "metadata": {
                    "agent": "writer",
                    "patient_id": state.get("patient_id", ""),
                    "pa_decision": state.get("pa_decision", ""),
                },
            },
        )

        usage = response.response_metadata.get("token_usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        writer_output = response.content

        m = collector.end_agent(state, "writer", prompt_tokens, completion_tokens)

        return {
            **m,
            "writer_output": writer_output,
            "current_step": "writing_complete",
            "supervisor_notes": [
                f"[Writer] PA document drafted "
                f"({prompt_tokens}p + {completion_tokens}c tokens)."
            ],
        }

    except Exception as e:
        m = collector.end_agent(state, "writer")
        return {
            **m,
            "writer_output": "",
            "error": f"Writer agent failed: {e}",
            "supervisor_notes": [f"[Writer] ERROR: {e}"],
        }
