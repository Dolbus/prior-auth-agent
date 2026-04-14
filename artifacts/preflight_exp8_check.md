# Preflight Experiment 8 — dataset + CSV audit
**Generated:** preflight script (`scripts/preflight_exp8_audit.py`)
- **LangSmith dataset:** `pa-baseline-120-apr08`
- **CSV export analyzed:** `artifacts/exp07_full_results.csv` (snapshot from Exp 7 run export — not live dataset)

## 1. Empty `reference_pa_decision`
| Source | Empty count |
|--------|-------------|
| LangSmith (live) | **0** |
| CSV export | **19** |

## 2. Duplicates
- **LangSmith:** total example rows = 120, unique example UUIDs = 120
- **Duplicate patient_ids (multiple examples per ID):** 0 — none
- **CSV duplicate patient_ids:** none

## 3. Predictions outside {{APPROVED, DENIED, NEEDS_MORE_INFO}}
- **CSV:** none (non-empty predictions only).

## 4. Confusion-style counts (CSV snapshot)
- ref **DENIED** → pred **NEEDS_MORE_INFO:** 24
- ref **APPROVED** → pred **DENIED:** 2
- ref **NEEDS_MORE_INFO** → pred **DENIED:** 1
- Empty / missing prediction (CSV): 0
- `prediction_is_null` = yes (CSV): 0

## 5. Nineteen relabeled examples (non-empty reference on LangSmith)
All **19** IDs have non-empty `outputs.pa_decision` on the live dataset.

Sample (id → reference):
- `PA-079` → `APPROVED`
- `PA-029` → `APPROVED`
- `PA-019` → `NEEDS_MORE_INFO`
- `PA-066` → `NEEDS_MORE_INFO`
- `PA-054` → `NEEDS_MORE_INFO`
- `PA-034` → `NEEDS_MORE_INFO`
- `PA-040` → `DENIED`
- `PA-044` → `NEEDS_MORE_INFO`
- … (19 total verified)

## 6. Safe to run final eval?
- **Preflight flag:** `PASS`
- **Note:** CSV still shows empty references from the Exp 7 export snapshot; LangSmith live dataset has **0** empty — safe to ignore CSV empties for GO/NO-GO.
- Live dataset: no empty references, no duplicate patient_ids / example UUIDs, 19 relabels verified; CSV structural checks OK.
