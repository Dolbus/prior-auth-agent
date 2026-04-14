import argparse
from dotenv import load_dotenv
from langsmith.evaluation import evaluate
from graph.workflow import build_graph, create_initial_state

load_dotenv(".env")

# Build graph once
graph = build_graph()

def process_patient(inputs: dict) -> dict:
    patient_data = inputs.get("patient_data")
    if not patient_data:
        raise ValueError("Missing patient_data in inputs")
    
    state = create_initial_state(patient_data)
    
    from config.settings import settings
    object.__setattr__(settings, "hitl_enabled", False)
    
    langsmith_config = {
        "run_name": f"PA Case — {patient_data.get('name', 'unknown')} ({patient_data['id']})",
        "tags": ["prior-auth", patient_data["id"]],
        "metadata": {
            "patient_id": patient_data["id"],
            "patient_name": patient_data.get("name", ""),
            "treatment": patient_data.get("requested_treatment", {}).get("name", "")
        },
    }
    
    final_state = graph.invoke(state, config=langsmith_config)

    # Coerce None so LangSmith JSON outputs never serialize pa_decision as null.
    pa_decision = final_state.get("pa_decision") or ""

    return {
        "pa_decision": pa_decision,
    }

def exact_match_evaluator(run, example) -> dict:
    """Evaluates if the predicted decision matches the expected decision."""
    actual = (run.outputs or {}).get("pa_decision") or ""
    expected = (example.outputs or {}).get("pa_decision") or ""
    score = 1 if actual.upper() == expected.upper() else 0
    return {"key": "exact_match", "score": score}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", required=True, help="Experiment prefix name")
    parser.add_argument("--dataset", default="pa-baseline-120-apr08", help="Dataset name")
    parser.add_argument("--concurrency", type=int, default=1, help="Max concurrency for evaluation")
    args = parser.parse_args()

    print(f"Running LangSmith evaluation on '{args.dataset}' with prefix '{args.prefix}' and concurrency {args.concurrency}...")
    
    from config.settings import settings
    object.__setattr__(settings, "hitl_enabled", False)
    
    results = evaluate(
        process_patient,
        data=args.dataset,
        evaluators=[exact_match_evaluator],
        experiment_prefix=args.prefix,
        max_concurrency=args.concurrency
    )
    print("Evaluation completed.")

if __name__ == "__main__":
    main()
