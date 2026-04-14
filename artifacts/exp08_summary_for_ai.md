# Experiment 8 — summary for downstream AI

**Purpose:** One-page context so another model or session can continue without re-reading traces.

## What was run

- **LangSmith experiment (session):** `exp08-final-supervisor-fix-6a126636`
- **Reference dataset:** `pa-baseline-120-apr08` (120 examples), loaded via LangSmith API at eval time — **not** the local Exp 7 CSV export.
- **Dataset version fingerprint:** `2026-04-11T01:47:20.702988+00:00` (max `modified_at` on examples; same value stored on the experiment as `dataset_version`).

## Headline metrics

| Metric | Value |
|--------|--------|
| Mean `exact_match` | **63.33%** (76 / 120) |
| vs Exp 7 post-relabel | **+16.7 pp** (Exp 7 was **46.67%**) |
| DENIED (ref) → NEEDS_MORE_INFO (pred) | **23** (Exp 7 CSV snapshot had **24**) |
| APPROVED (ref) → DENIED (pred) | **2** |
| NEEDS_MORE_INFO (ref) → DENIED (pred) | **1** |
| Empty reference in dataset | **0** |
| Null/empty model `pa_decision` | **0** |
| Total cost (session) | **~$1.50** |
| Latency p50 / p99 | **~22.1 s** / **~33.7 s** |
| Total tokens | **619,932** |

## Code / product context (Exp 8)

- **Rules:** RULE 4A — NEEDS_MORE_INFO only when clinical data missing/UNKNOWN; DENIED when criteria not met with data present.
- **Supervisor:** `validate_rules_node` coerces NEEDS_MORE_INFO → DENIED when `is_step_therapy_partial_failure`; recovers `pa_decision` from `rules_output` when state is empty.
- **Row-level file:** [`exp08_full_results.csv`](exp08_full_results.csv) — columns include `reference_pa_decision`, `prediction_pa_decision`, `exact_match_row`, `denied_ref_nmi_actual`.

## Human changelog

See repository [`CHANGELOG.md`](../CHANGELOG.md) — section **Experiment 8: Final Supervisor + Prompt Fix**.
