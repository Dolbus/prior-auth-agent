#!/usr/bin/env python3
"""
Exp 8 error analysis: filter mismatches from exp08_full_results.csv, pull LangSmith
traces for rules_output + supervisor reasoning, write CSV + markdown report.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from langsmith import Client

REPO = Path(__file__).resolve().parent.parent
CSV_IN = REPO / "artifacts" / "exp08_full_results.csv"
CSV_ERR = REPO / "artifacts" / "exp08_error_cases.csv"
MD_OUT = REPO / "artifacts" / "exp08_error_analysis.md"
PATIENTS = REPO / "data" / "patients.json"
RULES = REPO / "config" / "insurer_rules.json"
PROJECT = "exp08-final-supervisor-fix-6a126636"


def load_json(path: Path) -> list | dict:
    return json.loads(path.read_text(encoding="utf-8"))


def drug_category_map(rules: list) -> dict[str, str]:
    """brand_name -> category from insurer_rules."""
    m: dict[str, str] = {}
    for r in rules:
        b = (r.get("brand_name") or "").strip()
        if b:
            m[b] = (r.get("category") or "Unknown").strip()
    return m


def patient_drug(patients: list, pid: str) -> tuple[str, str]:
    for p in patients:
        if p.get("id") == pid:
            name = (p.get("requested_treatment") or {}).get("name") or ""
            return name, (name or "").strip()
    return "", ""


def classify_rule_type(rules_text: str) -> str:
    """Theme for clustering from rules_checker narrative (not supervisor text)."""
    t = rules_text or ""
    low = t.lower()
    # Parsed determination block (prompt format: "1. DETERMINATION\\nX")
    det_m = re.search(
        r"(?:^|\n)\s*1\.\s*DETERMINATION\s*\n\s*(\w[\w_+ ]*)",
        t,
        re.IGNORECASE | re.MULTILINE,
    )
    det = (det_m.group(1) or "").strip().upper().replace(" ", "_") if det_m else ""
    if "NEEDS" in det:
        return "determination_needs_more_info"
    if "step_therapy" in low and "not met" in low:
        return "step_therapy_not_met"
    if "lab_thresholds" in low and "not met" in low:
        return "lab_thresholds_not_met"
    if "contraindication" in low and "not met" in low:
        return "contraindications_not_met"
    if "bmi" in low and "not met" in low:
        return "bmi_not_met"
    if "needs_more_info" in low or "needs more info" in low:
        return "mentions_needs_more_info"
    return "other_or_mixed"


def find_named(run, name: str):
    if (run.name or "") == name:
        return run
    for ch in getattr(run, "child_runs", None) or []:
        x = find_named(ch, name)
        if x:
            return x
    return None


def supervisor_rules_eval_text(outputs: dict | None) -> str:
    if not outputs:
        return ""
    gen = outputs.get("generations")
    if not gen or not gen[0]:
        return ""
    g0 = gen[0][0]
    if isinstance(g0, dict):
        msg = g0.get("message")
        if isinstance(msg, dict):
            kwargs = msg.get("kwargs") or {}
            c = kwargs.get("content")
            if c:
                return str(c)
        if "text" in g0:
            return str(g0["text"])
    return str(g0)


def extract_from_trace(client: Client, root_run_id: str) -> tuple[str, str]:
    full = client.read_run(root_run_id, load_child_runs=True)
    rc = find_named(full, "rules_checker")
    rules_out = ""
    if rc and rc.outputs:
        rules_out = (rc.outputs.get("rules_output") or "").strip()

    sv = find_named(full, "supervisor_eval_Rules Checker")
    agent_reasoning = supervisor_rules_eval_text(sv.outputs if sv else None)
    return agent_reasoning, rules_out


def main() -> None:
    load_dotenv(REPO / ".env")
    patients = load_json(PATIENTS)
    rules_list = load_json(RULES)
    cat_by_brand = drug_category_map(rules_list)

    rows = list(csv.DictReader(CSV_IN.open(encoding="utf-8")))
    errors = [r for r in rows if str(r.get("exact_match_row", "")).strip() == "0"]
    if not errors:
        raise SystemExit("No rows with exact_match_row == 0")

    # Basic error CSV (no traces yet)
    field_base = [
        "patient_id",
        "drug_name",
        "drug_category",
        "error_pattern",
        "reference_pa_decision",
        "prediction_pa_decision",
        "denied_ref_nmi_actual",
    ]
    err_enriched: list[dict] = []

    client = Client()
    print(f"Loading root runs from {PROJECT}...")
    roots = list(client.list_runs(project_name=PROJECT, is_root=True))
    pid_to_root = {}
    for r in roots:
        ins = r.inputs or {}
        pd = ins.get("patient_data") or {}
        pid = pd.get("id")
        if pid:
            pid_to_root[pid] = r.id
    print(f"Mapped {len(pid_to_root)} patient ids to root runs.")

    pattern_counts: Counter[str] = Counter()
    category_pattern_counts: Counter[tuple[str, str]] = Counter()
    rule_type_counts: Counter[str] = Counter()
    case_md_blocks: list[str] = []

    for i, row in enumerate(errors):
        pid = row["patient_id"]
        ref = row["reference_pa_decision"]
        pred = row["prediction_pa_decision"]
        drug_name, _ = patient_drug(patients, pid)
        category = cat_by_brand.get(drug_name.strip(), "Unknown")
        ep = f"{ref} → {pred}"
        pattern_counts[ep] += 1
        category_pattern_counts[(category, ep)] += 1

        root_id = pid_to_root.get(pid)
        agent_r = ""
        rules_out = ""
        if root_id:
            try:
                agent_r, rules_out = extract_from_trace(client, root_id)
            except Exception as e:
                agent_r = f"[fetch error: {e}]"
                rules_out = ""
        else:
            agent_r = "[no root run found for patient_id]"

        rt = classify_rule_type(rules_out)
        rule_type_counts[rt] += 1

        err_enriched.append(
            {
                "patient_id": pid,
                "drug_name": drug_name,
                "drug_category": category,
                "error_pattern": ep,
                "reference_pa_decision": ref,
                "prediction_pa_decision": pred,
                "denied_ref_nmi_actual": row.get("denied_ref_nmi_actual", ""),
                "rule_type_guess": rt,
                "agent_reasoning": agent_r,
                "rules_checker_output": rules_out,
            }
        )

        def trunc(s: str, n: int = 6000) -> str:
            s = s or ""
            return s if len(s) <= n else s[: n - 20] + "\n\n… [truncated] …"

        case_md_blocks.append(
            "\n".join(
                [
                    "---",
                    "",
                    "### %s — %s (%s)" % (pid, drug_name, category),
                    "",
                    "- **Pattern:** %s" % ep,
                    "- **Rule-type guess (from rules text):** %s" % rt,
                    "",
                    "**Supervisor evaluation (Rules Checker)**",
                    "",
                    "```",
                    trunc(agent_r, 8000),
                    "```",
                    "",
                    "**Rules checker output**",
                    "",
                    "```",
                    trunc(rules_out, 12000),
                    "```",
                    "",
                ]
            )
        )
        print(f"  [{i+1}/{len(errors)}] {pid} {ep}")

    # Write wide CSV (may be large; Excel-friendly escaping)
    CSV_ERR.parent.mkdir(parents=True, exist_ok=True)
    fnames = list(err_enriched[0].keys())
    with CSV_ERR.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fnames, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        w.writerows(err_enriched)

    top_patterns = pattern_counts.most_common(10)
    top_cat = category_pattern_counts.most_common(10)
    top_rule = rule_type_counts.most_common(10)

    summary_lines = [
        "# Experiment 8 — error analysis (n=%d)" % len(errors),
        "",
        "**Source session:** `%s`" % PROJECT,
        "**Dataset:** `pa-baseline-120-apr08` · **Traces:** LangSmith (`rules_checker` + `supervisor_eval_Rules Checker`)",
        "",
        "## Summary",
        "",
        "- **Mismatches:** %d / 120" % len(errors),
        "",
        "## Top 10 — error_pattern (reference → prediction)",
        "",
        "| Rank | error_pattern | count |",
        "|------|---------------|-------|",
    ]
    for idx, (pat, cnt) in enumerate(top_patterns, 1):
        summary_lines.append("| %d | %s | %d |" % (idx, pat, cnt))
    summary_lines.extend(
        [
            "",
            "## Top 10 — drug_category × error_pattern",
            "",
            "| Rank | drug_category | error_pattern | count |",
            "|------|---------------|---------------|-------|",
        ]
    )
    for idx, ((cat, pat), cnt) in enumerate(top_cat, 1):
        summary_lines.append("| %d | %s | %s | %d |" % (idx, cat, pat, cnt))
    summary_lines.extend(
        [
            "",
            "## Rule-type guess (keyword heuristic on rules_output)",
            "",
            "| rule_type_guess | count |",
            "|-----------------|-------|",
        ]
    )
    for rt, cnt in top_rule:
        summary_lines.append("| %s | %d |" % (rt, cnt))
    summary_lines.extend(["", "## Per-case traces", ""])
    summary_lines.extend(case_md_blocks)

    MD_OUT.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    print(f"Wrote {CSV_ERR} ({len(err_enriched)} rows)")
    print(f"Wrote {MD_OUT}")
    print("\n--- TOP error_pattern ---")
    for pat, cnt in top_patterns:
        print(f"  {cnt:2d}  {pat}")
    print("\n--- TOP drug_category × pattern ---")
    for (cat, pat), cnt in top_cat[:10]:
        print(f"  {cnt:2d}  [{cat}] {pat}")
    print("\n--- rule_type_guess ---")
    for rt, cnt in top_rule:
        print(f"  {cnt:2d}  {rt}")


if __name__ == "__main__":
    main()
