#!/usr/bin/env python3
"""
Prior Authorization Agent — CLI entry point.

Usage:
    python main.py                      # Interactive patient selection
    python main.py --patient PA-001     # Run specific patient
    python main.py --all                # Run all patients (auto-approve HITL)
    python main.py --no-hitl            # Skip human-in-the-loop pause
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from config.settings import settings
from graph.workflow import build_graph, load_patients, create_initial_state
from metrics import collector
from metrics.evaluator import evaluate_accuracy, generate_evaluation_report
from persistence.supabase_client import write_case_result, write_audit_log


def print_banner():
    """Print the application banner."""
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║     🏥  PRIOR AUTHORIZATION AI AGENT                    ║")
    print("║     AgentOps Framework Demo                             ║")
    print("║     LangGraph + LangSmith + Supabase + GPT-4o mini     ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()


def select_patient(patients: list[dict]) -> dict:
    """Interactive patient selection menu."""
    print("Available patients:")
    print("─" * 60)
    for i, p in enumerate(patients, 1):
        treatment = p.get("requested_treatment", {})
        print(
            f"  {i}. [{p['id']}] {p['name']:<20} "
            f"→ {treatment.get('name', 'N/A'):<12} "
            f"(Expected: {p.get('expected_outcome', '?')})"
        )
    print("─" * 60)

    while True:
        try:
            choice = input("\n  Select patient (1-{}): ".format(len(patients))).strip()
            idx = int(choice) - 1
            if 0 <= idx < len(patients):
                return patients[idx]
            print("  Invalid selection. Try again.")
        except (ValueError, EOFError, KeyboardInterrupt):
            print("\n  Exiting.")
            sys.exit(0)


def run_single_patient(
    graph,
    patient: dict,
    show_output: bool = True,
) -> dict[str, Any]:
    """Run the PA workflow for a single patient and return results."""
    if show_output:
        print(f"\n{'═' * 60}")
        print(f"  Processing: {patient['name']} ({patient['id']})")
        print(f"  Treatment:  {patient.get('requested_treatment', {}).get('name', 'N/A')}")
        print(f"{'═' * 60}\n")

    # Create initial state and start metrics
    initial_state = create_initial_state(patient)
    run_start_updates = collector.start_run(initial_state)
    initial_state = {**initial_state, **run_start_updates}

    # Run the graph with LangSmith tracing config
    langsmith_config = {
        "run_name": f"PA Case — {patient.get('name', 'unknown')} ({patient['id']})",
        "tags": ["prior-auth", patient["id"], patient.get("expected_outcome", "")],
        "metadata": {
            "patient_id": patient["id"],
            "patient_name": patient.get("name", ""),
            "treatment": patient.get("requested_treatment", {}).get("name", ""),
            "expected_outcome": patient.get("expected_outcome", ""),
            "insurance": patient.get("insurance", {}).get("provider", ""),
        },
    }
    try:
        final_state = graph.invoke(initial_state, config=langsmith_config)
    except Exception as e:
        print(f"\n  ❌ Graph execution failed: {e}")
        final_state = {**initial_state, "error": str(e)}

    # End metrics
    completed = bool(final_state.get("writer_output"))
    run_end_updates = collector.end_run(final_state, completed=completed)
    final_state = {**final_state, **run_end_updates}

    # Compute final metrics
    final_metrics = collector.compute_final_metrics(final_state)

    # Evaluate accuracy
    accuracy_result = evaluate_accuracy(final_state)

    # Add accuracy to metrics
    final_metrics["factual_accuracy"] = accuracy_result["factual_accuracy"]

    if show_output:
        # Print the PA document
        writer_output = final_state.get("writer_output", "")
        if writer_output:
            print("\n" + writer_output)

        # Print supervisor notes
        notes = final_state.get("supervisor_notes", [])
        if notes:
            print(f"\n{'─' * 60}")
            print("  SUPERVISOR LOG")
            print(f"{'─' * 60}")
            for note in notes:
                print(f"  {note}")

        # Print evaluation report
        report = generate_evaluation_report(final_state, accuracy_result, final_metrics)
        print(f"\n{report}")

    result = {
        "patient_id": patient["id"],
        "patient_name": patient["name"],
        "patient_data": patient,
        "pa_decision": final_state.get("pa_decision", ""),
        "expected_outcome": patient.get("expected_outcome", ""),
        "accuracy": accuracy_result,
        "metrics": final_metrics,
        "writer_output": final_state.get("writer_output", ""),
        "supervisor_notes": final_state.get("supervisor_notes", []),
        "guardrail_violations": final_state.get("guardrail_violations", []),
        "pa_required": final_state.get("pa_required", True),
        "escalated": bool(final_state.get("escalated_from_agent")),
        "payer_feedback": final_state.get("payer_feedback", ""),
    }

    final_metrics["escalation_details"] = {
        "agent": final_state.get("escalated_from_agent", ""),
        "reason": final_state.get("escalation_reason", "")
    }

    # ---- Supabase persistence (Phase 3) ----
    if settings.supabase_enabled:
        case_id = write_case_result(result)
        if case_id:
            write_audit_log(
                case_id=case_id,
                metrics=final_metrics,
                supervisor_notes=final_state.get("supervisor_notes", []),
            )

    return result


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Prior Authorization AI Agent — AgentOps Demo"
    )
    parser.add_argument(
        "--patient",
        type=str,
        help="Patient ID to process (e.g., PA-001)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all patients (auto-approves HITL)",
    )
    parser.add_argument(
        "--no-hitl",
        action="store_true",
        help="Skip human-in-the-loop pause",
    )
    args = parser.parse_args()

    print_banner()

    # Validate config
    warnings = settings.validate()
    if warnings:
        print("  ⚠️  Configuration warnings:")
        for w in warnings:
            print(f"     • {w}")
        print()
        if "OPENAI_API_KEY" in str(warnings):
            print("  Set OPENAI_API_KEY in .env to run agents.")
            print("  See .env.example for the template.\n")
            sys.exit(1)

    # Load patients
    try:
        patients = load_patients()
    except FileNotFoundError as e:
        print(f"  ❌ {e}")
        sys.exit(1)

    print(f"  Loaded {len(patients)} patients from {settings.patients_file.name}")

    # LangSmith tracing status
    if settings.tracing_enabled:
        print(f"  LangSmith tracing: ✅ ENABLED (project: {settings.langchain_project})")
    else:
        print("  LangSmith tracing: ⚠️  DISABLED (set LANGCHAIN_TRACING_V2=true and LANGCHAIN_API_KEY)")

    # Supabase persistence status
    if settings.supabase_enabled:
        print(f"  Supabase persistence: ✅ ENABLED ({settings.supabase_url})")
    else:
        print("  Supabase persistence: ⚠️  DISABLED (set SUPABASE_URL and SUPABASE_KEY)")

    # Disable HITL if requested
    if args.no_hitl or args.all:
        settings.__dict__  # Force init
        object.__setattr__(settings, "hitl_enabled", False)

    # Build graph
    graph = build_graph()
    print("  LangGraph workflow compiled successfully ✅")

    if args.all:
        # Run all patients
        print(f"\n  Running all {len(patients)} patients...\n")
        results = []
        for patient in patients:
            result = run_single_patient(graph, patient)
            results.append(result)

        # Summary
        print(f"\n{'═' * 60}")
        print("  BATCH SUMMARY")
        print(f"{'═' * 60}")
        for r in results:
            match_icon = "✅" if r["accuracy"]["match"] else "❌"
            print(
                f"  {match_icon} [{r['patient_id']}] {r['patient_name']:<20} "
                f"Decision: {r['pa_decision']:<16} "
                f"Expected: {r['expected_outcome']}"
            )

        total = len(results)
        correct = sum(1 for r in results if r["accuracy"]["match"])
        total_cost = sum(r["metrics"]["cost_usd"] for r in results)
        avg_duration = sum(r["metrics"]["end_to_end_duration_sec"] for r in results) / total

        print(f"\n  Accuracy:     {correct}/{total} ({correct/total:.0%})")
        print(f"  Total Cost:   ${total_cost:.6f}")
        print(f"  Avg Duration: {avg_duration:.2f}s")
        print(f"{'═' * 60}\n")

    elif args.patient:
        # Run specific patient
        patient = next((p for p in patients if p["id"] == args.patient), None)
        if not patient:
            print(f"  ❌ Patient '{args.patient}' not found.")
            print(f"  Available: {', '.join(p['id'] for p in patients)}")
            sys.exit(1)
        run_single_patient(graph, patient)

    else:
        # Interactive selection
        patient = select_patient(patients)
        run_single_patient(graph, patient)


if __name__ == "__main__":
    main()
