"""
Post Decision simulated actions based on simulated payer responses.
"""
from typing import Any
from metrics import collector

def payer_approved_node(state: dict[str, Any]) -> dict[str, Any]:
    updates = collector.start_agent(state, "payer_approved")
    m = {**state, **updates}
    
    msg = "[Payer Response] PA Request APPROVED. Notifying provider and patient."
    print("\n  " + msg)
    
    end_updates = collector.end_agent(m, "payer_approved")
    return {
        **end_updates,
        "payer_feedback": "APPROVED",
        "supervisor_notes": [msg]
    }

def payer_denied_node(state: dict[str, Any]) -> dict[str, Any]:
    updates = collector.start_agent(state, "payer_denied")
    m = {**state, **updates}
    
    msg = "[Payer Response] PA Request DENIED. Flagged for internal appeal drafting."
    print("\n  " + msg)
    
    end_updates = collector.end_agent(m, "payer_denied")
    return {
        **end_updates,
        "payer_feedback": "DENIED",
        "supervisor_notes": [msg]
    }

def payer_needs_more_info_node(state: dict[str, Any]) -> dict[str, Any]:
    updates = collector.start_agent(state, "payer_needs_more_info")
    m = {**state, **updates}
    
    msg = "[Payer Response] NEEDS MORE INFO. Routing back to provider for missing documents."
    print("\n  " + msg)
    
    end_updates = collector.end_agent(m, "payer_needs_more_info")
    return {
        **end_updates,
        "payer_feedback": "NEEDS_MORE_INFO",
        "supervisor_notes": [msg]
    }

def submit_to_payer_node(state: dict[str, Any]) -> dict[str, Any]:
    """Simulates sending the PA form to the payer API and receiving a response.
    Here we fake the response based on the 'expected_outcome' or 'pa_decision'.
    Ideally, if the rule checker said APPROVED, the simulated payer approves.
    """
    updates = collector.start_agent(state, "submit_to_payer")
    m = {**state, **updates}
    
    decision = state.get("pa_decision", "APPROVED").upper()
    print(f"\n  [System] Submitting Drafted PA to Payer API... Awaiting response.")
    
    end_updates = collector.end_agent(m, "submit_to_payer")
    return {
        **end_updates,
        # We pass it along, graph routing decides the next node based on state["pa_decision"]
    }
