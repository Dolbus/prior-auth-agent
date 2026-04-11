"""
Rules Checker Agent — evaluates the patient's treatment request against
the hardcoded insurer rules dictionary and produces a structured
determination (APPROVED / DENIED / NEEDS_MORE_INFO).
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config.insurer_rules import get_rules_for_treatment
from config.settings import settings
from metrics import collector

SYSTEM_PROMPT = """\
You are operating in STRICT ADHERENCE MODE as a prior authorization contract engine.

Your ONLY source of truth is the insurer_rules.json object provided in this request.
You are NOT a clinician. You are a rule-evaluation engine. General medical knowledge is NEVER a \
valid basis for any criterion — not for safety, not for labs, not for dosing, not for anything.

═══════════════════════════════════════════
STRICT RULES — each violation is a critical error
═══════════════════════════════════════════

RULE 1 — JSON-only evaluation:
  Evaluate ONLY the criteria that appear as explicit keys in the provided insurer_rules.json.
  If a concept (safety screening, lab threshold, severity scale, contraindication, step therapy, etc.) does not
  appear as a key in the JSON, it does NOT exist as a requirement. Ignore it completely.

RULE 2 — Mandatory full key enumeration:
  You MUST list EVERY key from the insurer_rules.json object in your CRITERIA EVALUATION section.
  Use the exact key name as it appears in the JSON (e.g., `BMI_min`, `A1C_min`, `step_therapy_required`,
  `diagnosis_required`). Omitting any JSON key from your evaluation is a critical error.

RULE 3 — No invented requirements:
  You may not add, infer, or invent requirements from medical guidelines, drug labels, clinical best
  practices, or any source outside the provided JSON. Doing so is always an error.

RULE 3A — Step therapy is presence-only unless the JSON says otherwise:
  If the JSON contains a `step_therapy` list, evaluate ONLY whether each listed therapy string appears in
  the patient's `prior_treatments` list (presence/substring match against the literal strings).
  Do NOT require duration, outcomes, failure, response, intolerance, dates, severity, or any other
  detail unless those appear as separate explicit JSON keys.
  If `step_therapy_presence_hints` shows every required step with `present: true`, then `step_therapy` is MET.
  Do not ask for duration, outcomes, or failure documentation in that situation.
  Presence in `prior_treatments` is sufficient evidence unless the JSON rule contains explicit duration or
  outcome keys (separate top-level keys), in which case only those keys may add requirements.
  If a step-therapy item itself literally contains duration text (for example, "physical therapy 6 weeks"
  or "oral antidepressants 4 weeks"), treat that exact string as the full requirement. Do NOT split it
  into additional inferred sub-requirements.
  If `step_therapy` is an empty list, that means there is no step-therapy requirement and the key passes.
  When `step_therapy_presence_hints` is present in STRUCTURED PATIENT FACTS, treat those booleans as authoritative
  for presence-only compliance (do not contradict them using the research narrative).

RULE 3B — Empty lab_thresholds means no lab requirement:
  If `lab_thresholds` is an empty object `{}`, there is NO lab requirement for this rule and the key passes.
  Only evaluate labs when `lab_thresholds` contains one or more explicit keys.
  Do NOT mark an empty `lab_thresholds` object as NOT MET or UNKNOWN.

RULE 4 — Missing data MUST yield NEEDS_MORE_INFO (with carve-outs):
  If a required rule key is present in the JSON but the patient record does not contain sufficient
  information to confirm or deny it, you MUST mark that rule as UNKNOWN.
  An overall determination of NEEDS_MORE_INFO is REQUIRED whenever ANY rule is marked UNKNOWN.
  You may NOT issue a DENIED determination for a rule that is merely unknown or unconfirmed — except where a
  deterministic pre-check already resolved contraindications or lab thresholds against structured patient facts
  (those rows are final; do not downgrade them to UNKNOWN because the research summary is incomplete).
  Carve-out: for `step_therapy`, do not mark UNKNOWN for missing duration/outcomes when presence-only evaluation
  is sufficient and `step_therapy_presence_hints` is provided.

RULE 4A — NEEDS_MORE_INFO vs DENIED (semantic boundary):
  NEEDS_MORE_INFO is ONLY when required clinical data is ABSENT or a JSON-backed criterion is UNKNOWN so you
  cannot evaluate it.
  DENIED is when the patient record is PRESENT and sufficient to evaluate the criterion, but the criterion is
  NOT MET (e.g. step therapy incomplete with some steps documented, lab threshold failed, contraindication matched).
  Do NOT use NEEDS_MORE_INFO when structured facts show an explicit failure of a documented requirement.

RULE 5 — DENIED requires explicit evidence (with carve-outs):
  DENIED is only valid when there is an explicit, documented contraindication or a confirmed,
  evidenced failure/outcomes mismatch for a required criterion already present in the patient record — OR when
  a deterministic rule engine would deny on documented contraindication intersection or documented lab threshold
  failure against structured labs (without inferring from free text alone).

RULE 6 — No standalone Safety Screening section:
  Do NOT produce a dedicated "Safety Screening" section unless the JSON rules contain an explicit
  safety-related key. All evaluation must derive from JSON keys only.

═══════════════════════════════════════════
OUTPUT FORMAT — all six sections are required
═══════════════════════════════════════════

1. DETERMINATION
   Exactly one of: APPROVED | DENIED | NEEDS_MORE_INFO

2. CRITERIA EVALUATION
   List EVERY key that appears in the insurer_rules.json. For each key:
     - Exact JSON key name (e.g., `BMI_min`)
     - Status: MET | NOT MET | UNKNOWN
     - Evidence: the specific patient fact that supports this status, or
       "Insufficient data in patient record" if information is absent.
   Special handling:
     - `step_therapy`: presence-only against `prior_treatments` (see STRUCTURED PATIENT FACTS
       `step_therapy_presence_hints` when present)
     - `lab_thresholds: {}`: MET, because no lab requirement exists
     - empty patient `contraindications: []`: treat as no contraindications documented/present

3. STEP THERAPY COMPLIANCE
   List each required prior therapy from the JSON and whether the patient has completed it.
   If no step therapy key exists in the JSON, state: "No step therapy requirement in rules."

4. REASONING
   Explain the determination using ONLY the JSON rule evaluations from Section 2.
   Do not reference any criterion not present in the JSON.

5. MISSING INFORMATION
   Required only when determination is NEEDS_MORE_INFO.
   List exactly what patient data is needed, tied to the specific JSON key that is UNKNOWN.

6. RULES SOURCE CONFIRMATION
   State: (a) the exact number of rule keys evaluated, (b) confirm no criteria beyond the JSON
   were applied, and (c) if any key was marked UNKNOWN, confirm that drove a NEEDS_MORE_INFO decision.
"""


def _normalize_contra(text: str) -> str:
    """Normalize a contraindication string for fuzzy comparison."""
    return " ".join(str(text).lower().split())


def _contraindication_match(
    patient_contraindications: list[Any],
    rule_contraindications: list[Any],
) -> list[str]:
    """Return rule-side contraindication strings that intersect the patient list (substring match)."""
    if not rule_contraindications:
        return []
    p_norm = [_normalize_contra(str(x)) for x in patient_contraindications if str(x).strip()]
    hits: list[str] = []
    for r in rule_contraindications:
        rn = _normalize_contra(str(r))
        if not rn:
            continue
        for pn in p_norm:
            if rn in pn or pn in rn or rn == pn:
                hits.append(str(r))
                break
    return hits


def _prior_treatment_has_step(required_step: str, prior_treatments: list[Any]) -> bool:
    """Return True if required_step is present in prior_treatments (substring, normalized)."""
    req = _normalize_contra(required_step)
    if not req:
        return False
    for p in prior_treatments:
        pv = _normalize_contra(str(p))
        if not pv:
            continue
        if req in pv or pv in req:
            return True
    return False


def _build_step_therapy_presence_hints(
    step_therapy_rules: list[Any],
    prior_treatments: list[Any],
) -> list[dict[str, Any]]:
    """Build machine-readable presence hints for each required step-therapy string."""
    out: list[dict[str, Any]] = []
    for step in step_therapy_rules:
        s = str(step)
        out.append(
            {
                "required_step": s,
                "present": _prior_treatment_has_step(s, prior_treatments),
            }
        )
    return out


def _coerce_float(val: Any) -> float | None:
    try:
        if val is None or val == "":
            return None
        return float(val)
    except (TypeError, ValueError):
        return None


def _patient_bmi(labs: dict[str, Any]) -> float | None:
    """Best-effort BMI from labs (supports synthetic keys that mirror rule names)."""
    for k in ("BMI", "bmi", "BMI_min", "BMI_with_comorbidity"):
        v = _coerce_float(labs.get(k))
        if v is not None:
            return v
    return None


def _patient_has_weight_related_comorbidity(patient: dict[str, Any]) -> bool | None:
    """Return True if diagnoses suggest a weight-related comorbidity; None if unclear."""
    diags = patient.get("diagnoses") or []
    blob = " ".join(str(d).lower() for d in diags)
    # Common ICD / text hints for T2D, HTN, dyslipidemia, etc.
    hints = (
        "e10", "e11", "e12", "e13",  # diabetes
        "i10", "i11", "i12", "i13",  # hypertension
        "e78",  # dyslipidemia
        "n18", "n19",  # CKD
        "g47.33",  # sleep apnea (example)
        "k76.0",  # NAFLD
        "i25",  # ASCVD
    )
    for h in hints:
        if h in blob:
            return True
    # Non-ICD keywords if ever present in string diagnoses
    text_hints = ("diabetes", "hypertension", "hyperlipidemia", "dyslipidemia", "sleep apnea")
    for h in text_hints:
        if h in blob:
            return True
    if not blob.strip():
        return None
    return False


def _lab_value_for_threshold_key(labs: dict[str, Any], threshold_key: str) -> Any:
    """Resolve a patient lab value for a given insurer rule threshold key."""
    if threshold_key in labs and labs[threshold_key] is not None and labs[threshold_key] != "":
        return labs[threshold_key]
    aliases: dict[str, list[str]] = {
        "A1C_min": ["A1C", "a1c", "HbA1c", "hba1c"],
        "BMI_min": ["BMI", "bmi"],
        "BMI_with_comorbidity": ["BMI", "bmi"],
        "LDL_min": ["LDL", "ldl"],
        "PD_L1_min_percent": ["PD_L1", "PDL1", "pd_l1"],
        "body_surface_area_min_percent": ["BSA", "bsa", "body_surface_area"],
    }
    for alt in aliases.get(threshold_key, []):
        if alt in labs and labs[alt] is not None and labs[alt] != "":
            return labs[alt]
    return None


def _lab_value_missing(rules: dict[str, Any], patient: dict[str, Any]) -> bool:
    """True if structured labs lack data needed to evaluate any lab_thresholds key."""
    labs = patient.get("labs") or {}
    if not isinstance(labs, dict):
        labs = {}
    thresholds = rules.get("lab_thresholds") or {}
    if not isinstance(thresholds, dict) or not thresholds:
        return False

    keys = list(thresholds.keys())
    # Wegovy-style dual BMI: need one BMI + comorbidity clarity in the border band
    if "BMI_min" in thresholds and "BMI_with_comorbidity" in thresholds:
        bmi = _patient_bmi(labs)
        if bmi is None:
            return True
        bmin = _coerce_float(thresholds.get("BMI_min"))
        bwc = _coerce_float(thresholds.get("BMI_with_comorbidity"))
        if bmin is None or bwc is None:
            return False
        if bwc <= bmi < bmin:
            cm = _patient_has_weight_related_comorbidity(patient)
            if cm is None:
                return True
        return False

    for tkey, _expected in thresholds.items():
        if _lab_value_for_threshold_key(labs, str(tkey)) is None:
            return True
    return False


def _check_lab_thresholds_fail(rules: dict[str, Any], patient: dict[str, Any]) -> tuple[bool, str]:
    """Return (failed, reason).

    For Wegovy-style dual BMI keys (`BMI_min` + `BMI_with_comorbidity`), approval uses OR logic across the two
    documented pathways: failing to meet BOTH pathways (not compound AND of passing rows) means DENIED — i.e.
    failing ANY applicable pathway when values are documented is a denial driver; do not require every JSON key
    to fail independently before denying.
    """
    thresholds = rules.get("lab_thresholds") or {}
    if not isinstance(thresholds, dict) or not thresholds:
        return False, ""

    labs = patient.get("labs") or {}
    if not isinstance(labs, dict):
        labs = {}

    # Dual BMI OR-path (Wegovy)
    if "BMI_min" in thresholds and "BMI_with_comorbidity" in thresholds:
        bmi = _patient_bmi(labs)
        if bmi is None:
            return False, ""
        bmin = _coerce_float(thresholds.get("BMI_min"))
        bwc = _coerce_float(thresholds.get("BMI_with_comorbidity"))
        if bmin is None or bwc is None:
            return False, ""
        if bmi >= bmin:
            return False, ""
        comorb = _patient_has_weight_related_comorbidity(patient)
        if bmi >= bwc and comorb is True:
            return False, ""
        if bwc <= bmi < bmin and comorb is False:
            return True, (
                f"BMI {bmi} is below `BMI_min` ({bmin}) and no qualifying weight-related comorbidity documented "
                f"to use `BMI_with_comorbidity` ({bwc})."
            )
        if bmi < bwc:
            return True, f"BMI {bmi} is below `BMI_with_comorbidity` ({bwc})."
        # bmi between bwc and bmin with unknown comorbidity: not a deterministic fail here
        return False, ""

    failed_reasons: list[str] = []
    # Non–dual-BMI keys: failing ANY present numeric/string threshold ⇒ DENIED (not a compound AND across all rule keys).
    for tkey, expected in thresholds.items():
        raw = _lab_value_for_threshold_key(labs, str(tkey))
        if raw is None:
            continue
        tk = str(tkey)
        # Any numeric rule threshold (including *_min, *_min_percent, body_surface_area_min_percent, etc.)
        if isinstance(expected, (int, float)) and not isinstance(expected, bool):
            val = _coerce_float(raw)
            if val is None:
                continue
            if val < float(expected):
                failed_reasons.append(f"`{tk}` requires >= {expected}; observed {val}.")
        else:
            exp = _normalize_contra(str(expected))
            got = _normalize_contra(str(raw))
            if got != exp and exp not in got and got not in exp:
                failed_reasons.append(f"`{tk}` requires {expected!r}; observed {raw!r}.")

    if failed_reasons:
        return True, " ".join(failed_reasons)
    return False, ""


def _criteria_lines_deterministic(
    rules: dict[str, Any],
    *,
    mode: str,
    extra: dict[str, Any],
) -> str:
    """Build CRITERIA EVALUATION lines for deterministic denials."""
    lines: list[str] = []
    for key in rules:
        if mode == "contraindication" and key == "contraindications":
            matches = extra.get("matches") or []
            lines.append(
                f"- `{key}`: NOT MET — patient record intersects insurer contraindications: {matches}"
            )
            continue
        if mode == "lab" and key == "lab_thresholds":
            lines.append(f"- `{key}`: NOT MET — {extra.get('reason', '')}")
            continue
        if key == "lab_thresholds" and not (rules.get("lab_thresholds") or {}):
            lines.append(f"- `{key}`: MET — empty object implies no lab requirement")
            continue
        if key == "step_therapy":
            st = rules.get("step_therapy") or []
            hints = extra.get("step_hints") or []
            lines.append(f"- `{key}`: evaluated via presence-only — items: {st!r}; hints: {hints!r}")
            continue
        lines.append(f"- `{key}`: informational / not used for this deterministic branch — see JSON")
    return "\n".join(lines)


def _format_deterministic_denial(
    *,
    determination: str,
    criteria_block: str,
    step_block: str,
    reasoning: str,
    rules_key_count: int,
    missing_section: str | None = None,
) -> str:
    if missing_section is not None:
        missing = missing_section
    elif determination == "NEEDS_MORE_INFO":
        missing = (
            "\n5. MISSING INFORMATION\n"
            "Structured evaluation could not be completed deterministically; see criteria.\n"
        )
    elif determination == "APPROVED":
        missing = "\n5. MISSING INFORMATION\nN/A (deterministic approval).\n"
    else:
        missing = "\n5. MISSING INFORMATION\nN/A (deterministic denial).\n"

    return (
        f"1. DETERMINATION\n{determination}\n\n"
        f"2. CRITERIA EVALUATION\n{criteria_block}\n\n"
        f"3. STEP THERAPY COMPLIANCE\n{step_block}\n\n"
        f"4. REASONING\n{reasoning}\n"
        f"{missing}"
        f"6. RULES SOURCE CONFIRMATION\n"
        f"(a) Evaluated {rules_key_count} top-level JSON keys from insurer_rules.json match. "
        f"(b) No criteria beyond JSON were applied. "
        f"(c) UNKNOWN-driven information-gap determination: {'yes' if determination == 'NEEDS_MORE_INFO' else 'no'}.\n"
    )


def _deterministic_contraindication_output(
    rules: dict[str, Any],
    patient: dict[str, Any],
    matches: list[str],
    structured_facts: dict[str, Any],
) -> str:
    st = rules.get("step_therapy") or []
    hints = structured_facts.get("step_therapy_presence_hints") or []
    if isinstance(st, list) and st and not hints:
        hints = _build_step_therapy_presence_hints(st, structured_facts.get("prior_treatments") or [])

    step_lines: list[str] = []
    for h in hints:
        step_lines.append(
            f"- {h.get('required_step')!r}: {'MET (present)' if h.get('present') else 'NOT MET (absent)'}"
        )
    step_block = (
        "\n".join(step_lines)
        if step_lines
        else "No step therapy requirement in rules."
    )

    criteria = _criteria_lines_deterministic(
        rules,
        mode="contraindication",
        extra={"matches": matches, "step_hints": hints},
    )
    reasoning = (
        "DENIED because patient contraindications intersect insurer rule contraindications "
        f"({matches}) under strict JSON-only evaluation."
    )
    return _format_deterministic_denial(
        determination="DENIED",
        criteria_block=criteria,
        step_block=step_block,
        reasoning=reasoning,
        rules_key_count=len(rules),
    )


def _deterministic_lab_failure_output(
    rules: dict[str, Any],
    patient: dict[str, Any],
    reason: str,
    structured_facts: dict[str, Any],
) -> str:
    st = rules.get("step_therapy") or []
    hints = structured_facts.get("step_therapy_presence_hints") or []
    if isinstance(st, list) and st and not hints:
        hints = _build_step_therapy_presence_hints(st, structured_facts.get("prior_treatments") or [])

    step_lines: list[str] = []
    for h in hints:
        step_lines.append(
            f"- {h.get('required_step')!r}: {'MET (present)' if h.get('present') else 'NOT MET (absent)'}"
        )
    step_block = (
        "\n".join(step_lines)
        if step_lines
        else "No step therapy requirement in rules."
    )

    criteria = _criteria_lines_deterministic(
        rules,
        mode="lab",
        extra={"reason": reason, "step_hints": hints},
    )
    reasoning = f"DENIED because structured labs fail insurer `lab_thresholds` requirements: {reason}"
    return _format_deterministic_denial(
        determination="DENIED",
        criteria_block=criteria,
        step_block=step_block,
        reasoning=reasoning,
        rules_key_count=len(rules),
    )


def _step_therapy_step_block(hints: list[dict[str, Any]]) -> str:
    if not hints:
        return "No step therapy requirement in rules."
    lines = []
    for h in hints:
        lines.append(
            f"- {h.get('required_step')!r}: {'MET (present)' if h.get('present') else 'NOT MET (absent)'}"
        )
    return "\n".join(lines)


def _criteria_lines_step_therapy_deterministic(
    rules: dict[str, Any],
    *,
    variant: str,
    hints: list[dict[str, Any]],
) -> str:
    """Criteria section for deterministic step-therapy outcomes (approve / partial deny / all missing)."""
    lines: list[str] = []
    for key in rules:
        if variant == "approve":
            if key == "step_therapy":
                lines.append(f"- `{key}`: MET — all required prior therapies present; hints: {hints!r}")
            elif key == "contraindications":
                lines.append(
                    "- `contraindications`: MET — no intersection between patient and insurer contraindication lists"
                )
            elif key == "lab_thresholds":
                th = rules.get("lab_thresholds") or {}
                if not th:
                    lines.append("- `lab_thresholds`: MET — empty object implies no lab requirement")
                else:
                    lines.append(
                        "- `lab_thresholds`: MET — structured labs satisfy thresholds (deterministic numeric check)"
                    )
            else:
                lines.append(
                    f"- `{key}`: informational — no additional deterministic gate for this step-therapy approval path"
                )
        elif variant == "partial":
            if key == "step_therapy":
                lines.append(f"- `{key}`: NOT MET — incomplete prior therapies; hints: {hints!r}")
            elif key == "lab_thresholds" and not (rules.get("lab_thresholds") or {}):
                lines.append("- `lab_thresholds`: MET — empty object implies no lab requirement")
            else:
                lines.append(
                    f"- `{key}`: informational — deterministic branch driven by incomplete step therapy"
                )
        else:  # all_missing → DENIED (zero prior treatments documented = step therapy not completed)
            if key == "step_therapy":
                lines.append(
                    f"- `{key}`: NOT MET — no required steps documented in prior_treatments; hints: {hints!r}"
                )
            elif key == "lab_thresholds" and not (rules.get("lab_thresholds") or {}):
                lines.append("- `lab_thresholds`: MET — empty object implies no lab requirement")
            else:
                lines.append(
                    f"- `{key}`: informational — deterministic branch driven by zero step therapy documentation"
                )
    return "\n".join(lines)


def _deterministic_step_therapy_approved_output(
    rules: dict[str, Any],
    hints: list[dict[str, Any]],
) -> str:
    step_block = _step_therapy_step_block(hints)
    criteria = _criteria_lines_step_therapy_deterministic(rules, variant="approve", hints=hints)
    reasoning = (
        "APPROVED because all `step_therapy` strings appear in `prior_treatments` (normalized substring / "
        "presence-only), structured contraindications do not intersect insurer rules, and structured labs do "
        "not fail `lab_thresholds`."
    )
    return _format_deterministic_denial(
        determination="APPROVED",
        criteria_block=criteria,
        step_block=step_block,
        reasoning=reasoning,
        rules_key_count=len(rules),
    )


def _deterministic_step_therapy_partial_denial_output(
    rules: dict[str, Any],
    hints: list[dict[str, Any]],
) -> str:
    step_block = _step_therapy_step_block(hints)
    criteria = _criteria_lines_step_therapy_deterministic(rules, variant="partial", hints=hints)
    reasoning = (
        "DENIED because not all required `step_therapy` items are documented in `prior_treatments` under "
        "strict presence-only matching."
    )
    return _format_deterministic_denial(
        determination="DENIED",
        criteria_block=criteria,
        step_block=step_block,
        reasoning=reasoning,
        rules_key_count=len(rules),
    )


def _deterministic_step_therapy_all_missing_output(
    rules: dict[str, Any],
    hints: list[dict[str, Any]],
) -> str:
    # Exp 10 fix: zero prior treatments documented → DENIED (step therapy not completed).
    # Prior behavior was NEEDS_MORE_INFO, which was wrong: absence of required step therapy
    # is a hard denial condition, not a request for more information.
    step_block = _step_therapy_step_block(hints)
    criteria = _criteria_lines_step_therapy_deterministic(rules, variant="all_missing", hints=hints)
    reasoning = (
        "DENIED because no required step-therapy items are documented in `prior_treatments`. "
        "Absence of required prior therapy is a hard denial condition under strict JSON-only evaluation."
    )
    return _format_deterministic_denial(
        determination="DENIED",
        criteria_block=criteria,
        step_block=step_block,
        reasoning=reasoning,
        rules_key_count=len(rules),
    )


def is_step_therapy_partial_failure(patient: dict[str, Any], rules: dict[str, Any] | None) -> bool:
    """True when some required step-therapy items are documented but not all (failed), not all-missing."""
    if not rules:
        return False
    st_steps = rules.get("step_therapy")
    if not isinstance(st_steps, list) or not st_steps:
        return False
    prior = patient.get("prior_treatments") or []
    if not isinstance(prior, list):
        prior = []
    st_hints = _build_step_therapy_presence_hints(st_steps, prior)
    present_flags = [bool(h.get("present")) for h in st_hints]
    if not present_flags:
        return False
    any_present = any(present_flags)
    all_present = all(present_flags)
    return any_present and not all_present


def _first_prior_index_for_step(required_step: str, prior_treatments: list[Any]) -> int | None:
    """Index of the first prior entry that matches ``required_step`` (substring match)."""
    for i, p in enumerate(prior_treatments):
        if _prior_treatment_has_step(required_step, [p]):
            return i
    return None


def is_step_therapy_sequence_violation(patient: dict[str, Any], rules: dict[str, Any] | None) -> bool:
    """True when all required steps appear in prior_treatments but not in insurer list order.

    ``step_therapy`` order is treated as the required sequence; ``prior_treatments`` order is
    chronological. If a later required step is documented before an earlier one, that is a
    failure (DENIED), not NEEDS_MORE_INFO for missing sequence.
    """
    if not rules:
        return False
    st_steps = rules.get("step_therapy")
    if not isinstance(st_steps, list) or len(st_steps) < 2:
        return False
    prior = patient.get("prior_treatments") or []
    if not isinstance(prior, list) or not prior:
        return False
    indices: list[int] = []
    for step in st_steps:
        idx = _first_prior_index_for_step(str(step), prior)
        if idx is None:
            return False
        indices.append(idx)
    for a, b in zip(indices, indices[1:]):
        if a >= b:
            return True
    return False


def _build_structured_patient_facts(
    patient: dict[str, Any],
    rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    treatment = patient.get("requested_treatment", {}) or {}
    diagnoses = patient.get("diagnoses", [])
    prior_treatments = patient.get("prior_treatments", [])
    labs = patient.get("labs", {})
    contraindications = patient.get("contraindications", [])

    facts: dict[str, Any] = {
        "patient_id": patient.get("id", ""),
        "insurer": patient.get("insurance_provider", ""),
        "requested_treatment": {
            "name": treatment.get("name", ""),
            "generic_name": treatment.get("generic_name", "") or treatment.get("generic", ""),
            "generic": treatment.get("generic", ""),
            "dosage": treatment.get("dosage", ""),
        },
        "diagnoses": diagnoses if isinstance(diagnoses, list) else [],
        "prior_treatments": prior_treatments if isinstance(prior_treatments, list) else [],
        "labs": labs if isinstance(labs, dict) else {},
        "contraindications": contraindications if isinstance(contraindications, list) else [],
    }

    cpt_code = treatment.get("cpt_code")
    if cpt_code:
        facts["requested_treatment"]["cpt_code"] = cpt_code

    if rules:
        st = rules.get("step_therapy")
        if isinstance(st, list) and st:
            facts["step_therapy_presence_hints"] = _build_step_therapy_presence_hints(
                st,
                facts["prior_treatments"],
            )

    return facts


def _build_rule_interpretation(rules: dict[str, Any] | None) -> dict[str, Any]:
    rules = rules or {}

    step_therapy_items = rules.get("step_therapy", [])
    if not isinstance(step_therapy_items, list):
        step_therapy_items = []

    lab_thresholds = rules.get("lab_thresholds", {})
    if not isinstance(lab_thresholds, dict):
        lab_thresholds = {}

    contraindications = rules.get("contraindications", [])
    if not isinstance(contraindications, list):
        contraindications = []

    return {
        "step_therapy_mode": "no_requirement" if not step_therapy_items else "presence_only",
        "required_step_therapy_items": step_therapy_items,
        "lab_threshold_mode": "no_requirement" if not lab_thresholds else "evaluate_named_thresholds_only",
        "lab_threshold_keys": list(lab_thresholds.keys()),
        "contraindication_list": contraindications,
    }


def _resolve_rules(patient: dict[str, Any], insurer: str) -> dict[str, Any] | None:
    """Resolve insurer rules: brand name, then generic_name OR generic, then cpt_code."""
    treatment = patient.get("requested_treatment", {}) or {}
    brand = treatment.get("name", "") or ""
    generic = (treatment.get("generic_name") or treatment.get("generic") or "") or ""
    cpt = treatment.get("cpt_code") or ""

    r = get_rules_for_treatment(brand, insurer) if brand else None
    if r is None and generic:
        r = get_rules_for_treatment(generic, insurer)
    if r is None and cpt:
        r = get_rules_for_treatment(str(cpt), insurer)
    return r


def rules_checker_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: evaluates patient data against insurer rules.

    Reads research_output and patient_data from state, looks up the
    applicable insurer rules, and uses GPT-4o mini to produce a
    structured determination.
    """
    updates = collector.start_agent(state, "rules_checker")
    state = {**state, **updates}

    patient = state.get("patient_data", {})
    research = state.get("research_output", "")

    if not research:
        m = collector.end_agent(state, "rules_checker")
        stub_rules = (
            "1. DETERMINATION\nNEEDS_MORE_INFO\n\n"
            "2. CRITERIA EVALUATION\n"
            "Cannot evaluate insurer rules without a structured clinical research summary.\n"
        )
        return {
            **m,
            "rules_output": stub_rules,
            "pa_decision": "NEEDS_MORE_INFO",
            "error": "No research output available for rules checking.",
            "supervisor_notes": ["[Rules Checker] ERROR: No research output in state."],
        }

    treatment = patient.get("requested_treatment", {}) or {}
    treatment_name = treatment.get("name", "")
    insurer = patient.get("insurance_provider", "")

    rules = _resolve_rules(patient, insurer)

    structured_patient_facts = _build_structured_patient_facts(patient, rules)

    if rules:
        p_contras = patient.get("contraindications") or []
        r_contras = rules.get("contraindications") or []
        if isinstance(r_contras, list) and r_contras:
            matches = _contraindication_match(
                p_contras if isinstance(p_contras, list) else [],
                r_contras,
            )
            if matches:
                rules_output = _deterministic_contraindication_output(
                    rules,
                    patient,
                    matches,
                    structured_patient_facts,
                )
                m = collector.end_agent(state, "rules_checker", 0, 0)
                return {
                    **m,
                    "rules_output": rules_output,
                    "pa_decision": _extract_decision(rules_output),
                    "current_step": "rules_check_complete",
                    "supervisor_notes": [
                        f"[Rules Checker] Determination: DENIED (deterministic contraindications) for "
                        f"{treatment_name} (0p + 0c tokens)."
                    ],
                }

        if not _lab_value_missing(rules, patient):
            fail, reason = _check_lab_thresholds_fail(rules, patient)
            if fail and reason:
                rules_output = _deterministic_lab_failure_output(
                    rules,
                    patient,
                    reason,
                    structured_patient_facts,
                )
                m = collector.end_agent(state, "rules_checker", 0, 0)
                return {
                    **m,
                    "rules_output": rules_output,
                    "pa_decision": _extract_decision(rules_output),
                    "current_step": "rules_check_complete",
                    "supervisor_notes": [
                        f"[Rules Checker] Determination: DENIED (deterministic labs) for "
                        f"{treatment_name} (0p + 0c tokens)."
                    ],
                }

        st_steps = rules.get("step_therapy")
        if isinstance(st_steps, list) and st_steps:
            prior = patient.get("prior_treatments") or []
            if not isinstance(prior, list):
                prior = []
            st_hints = _build_step_therapy_presence_hints(st_steps, prior)
            present_flags = [bool(h.get("present")) for h in st_hints]
            all_present = bool(present_flags) and all(present_flags)
            any_present = any(present_flags)

            if not any_present:
                rules_output = _deterministic_step_therapy_all_missing_output(rules, st_hints)
                m = collector.end_agent(state, "rules_checker", 0, 0)
                return {
                    **m,
                    "rules_output": rules_output,
                    "pa_decision": _extract_decision(rules_output),
                    "current_step": "rules_check_complete",
                    "supervisor_notes": [
                        f"[Rules Checker] Determination: NEEDS_MORE_INFO (deterministic step therapy — none documented) "
                        f"for {treatment_name} (0p + 0c tokens)."
                    ],
                }
            if any_present and not all_present:
                rules_output = _deterministic_step_therapy_partial_denial_output(rules, st_hints)
                m = collector.end_agent(state, "rules_checker", 0, 0)
                return {
                    **m,
                    "rules_output": rules_output,
                    "pa_decision": _extract_decision(rules_output),
                    "current_step": "rules_check_complete",
                    "supervisor_notes": [
                        f"[Rules Checker] Determination: DENIED (deterministic step therapy — incomplete) for "
                        f"{treatment_name} (0p + 0c tokens)."
                    ],
                }
            if all_present:
                if not _lab_value_missing(rules, patient):
                    fail_lab, _reason = _check_lab_thresholds_fail(rules, patient)
                    if not fail_lab:
                        rules_output = _deterministic_step_therapy_approved_output(rules, st_hints)
                        m = collector.end_agent(state, "rules_checker", 0, 0)
                        return {
                            **m,
                            "rules_output": rules_output,
                            "pa_decision": _extract_decision(rules_output),
                            "current_step": "rules_check_complete",
                            "supervisor_notes": [
                                f"[Rules Checker] Determination: APPROVED (deterministic step therapy) for "
                                f"{treatment_name} (0p + 0c tokens)."
                            ],
                        }

    rules_json = json.dumps(rules, indent=2, default=str) if rules else "No specific rules found for this treatment."
    structured_patient_facts_json = json.dumps(structured_patient_facts, indent=2, default=str)
    rule_interpretation = _build_rule_interpretation(rules)
    rule_interpretation_json = json.dumps(rule_interpretation, indent=2, default=str)

    human_msg = (
        f"Please evaluate the following Prior Authorization request.\n\n"
        f"STRUCTURED PATIENT FACTS (authoritative raw data from patient_data):\n"
        f"```json\n{structured_patient_facts_json}\n```\n\n"
        f"RULE INTERPRETATION DIRECTIVES (derived directly from insurer_rules.json):\n"
        f"```json\n{rule_interpretation_json}\n```\n\n"
        f"CLINICAL RESEARCH SUMMARY:\n{research}\n\n"
        f"INSURER RULES FOR '{treatment_name}':\n```json\n{rules_json}\n```\n\n"
        f"Use STRUCTURED PATIENT FACTS as the source of truth for diagnoses, prior_treatments, labs, "
        f"contraindications, insurer, and requested treatment. Use the CLINICAL RESEARCH SUMMARY only as "
        f"supporting context. If the summary suggests a requirement that is not an explicit JSON key, ignore it.\n\n"
        f"Evaluate each criterion and provide your structured determination."
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
                "run_name": f"Rules Checker — {treatment_name}",
                "tags": ["rules_checker", "prior-auth", patient.get("id", "")],
                "metadata": {
                    "agent": "rules_checker",
                    "patient_id": patient.get("id", ""),
                    "treatment": treatment_name,
                    "diagnosis": patient.get("diagnosis", {}).get("primary", ""),
                },
            },
        )

        usage = response.response_metadata.get("token_usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        rules_output = response.content

        # Extract the determination from the LLM output
        pa_decision = _extract_decision(rules_output)

        m = collector.end_agent(state, "rules_checker", prompt_tokens, completion_tokens)

        return {
            **m,
            "rules_output": rules_output,
            "pa_decision": pa_decision,
            "current_step": "rules_check_complete",
            "supervisor_notes": [
                f"[Rules Checker] Determination: {pa_decision} for "
                f"{treatment_name} ({prompt_tokens}p + {completion_tokens}c tokens)."
            ],
        }

    except Exception as e:
        m = collector.end_agent(state, "rules_checker")
        return {
            **m,
            "rules_output": "",
            "pa_decision": "",
            "error": f"Rules checker failed: {e}",
            "supervisor_notes": [f"[Rules Checker] ERROR: {e}"],
        }


def _extract_decision(output: str) -> str:
    """Parse the LLM output to find the determination.

    Looks for explicit DETERMINATION lines, then falls back to scanning
    for keywords.
    """
    output_upper = output.upper()

    # Look for explicit determination patterns
    for line in output.split("\n"):
        line_upper = line.upper().strip()
        if "DETERMINATION" in line_upper:
            if "NEEDS_MORE_INFO" in line_upper or "NEEDS MORE INFO" in line_upper:
                return "NEEDS_MORE_INFO"
            if "APPROVED" in line_upper or "APPROVE" in line_upper:
                return "APPROVED"
            if "DENIED" in line_upper or "DENY" in line_upper:
                return "DENIED"

    # Fallback: scan the whole output
    if "NEEDS_MORE_INFO" in output_upper or "NEEDS MORE INFO" in output_upper:
        return "NEEDS_MORE_INFO"
    if "DENIED" in output_upper or "DENIAL" in output_upper:
        return "DENIED"
    if "APPROVED" in output_upper or "APPROVAL" in output_upper:
        return "APPROVED"

    return "UNKNOWN"
