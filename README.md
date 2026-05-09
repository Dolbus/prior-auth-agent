# Prior Authorization AI Agent

Multi-agent prior-auth system built around evaluation discipline. Hybrid deterministic + LLM rules engine, per-gate supervisor validation, and ten controlled experiments improving exact-match accuracy from a 46.7% relabel baseline to **70.0% (84/120)** on a locked 120-case eval set.

**Live dashboard:** [pa-agentops.streamlit.app](https://pa-agentops.streamlit.app)
**Stack:** LangGraph · LangSmith · Supabase · OpenAI (`gpt-4o-mini` + `gpt-4o`) · Streamlit

---

## What it does

- Ingests a patient record and an insurer rule set, produces an `APPROVED` / `DENIED` / `NEEDS_MORE_INFO` determination, and emits a generated PA form with structured reasoning per criterion.
- Each agent step is graded by an LLM-as-judge supervisor with a per-agent confidence threshold and an independent retry counter; three failures escalate to a human-in-the-loop gate.
- Contraindication, lab-threshold, and step-therapy checks run as deterministic Python before any LLM call. The LLM is the fallback path, not the primary one — see [agents/rules_checker.py](agents/rules_checker.py).
- Every run emits cost, latency, token, and gate-pass metrics traced via LangSmith and persisted to Supabase. Two Streamlit dashboards consume that data: a runtime view and a static showcase view.
- Reproducible: all accuracy claims reference one LangSmith dataset (`pa-baseline-120-apr08`, n=120) version-pinned by timestamp. Each experiment in [CHANGELOG.md](CHANGELOG.md) cites its session ID and a row-level CSV.

---

## Architecture

```
                         ┌─────────────────────────┐
                         │   eligibility_checker   │  drug+insurer combo: PA needed?
                         └────────────┬────────────┘
                                      ▼
                         ┌─────────────────────────┐    retry≤2
                         │  validate_eligibility   │ ─────────────┐
                         │   (≥95% confidence)     │              │
                         └────────────┬────────────┘              │
                                      ▼                           │
                         ┌─────────────────────────┐              │
                         │        research         │  ◄───────────┘
                         │  extract DX / meds /    │
                         │  labs / prior treatment │
                         └────────────┬────────────┘
                                      ▼
                         ┌─────────────────────────┐    retry≤2
                         │   validate_research     │ ─────────────┐
                         │   (≥80% confidence)     │              │
                         └────────────┬────────────┘              │
                                      ▼                           │
                         ┌─────────────────────────┐              │
                         │     rules_checker       │  ◄───────────┘
                         │  ┌───────────────────┐  │   contraindication / lab /
                         │  │ deterministic     │  │   step-therapy gates run
                         │  │ Python branches   │  │   FIRST (added in v2 after
                         │  └───────────────────┘  │   Exp 5 surfaced JSON-key
                         │  ┌───────────────────┐  │   hallucinations)
                         │  │ LLM fallback      │  │
                         │  │ (gpt-4o-mini,     │  │
                         │  │ STRICT ADHERENCE) │  │
                         │  └───────────────────┘  │
                         └────────────┬────────────┘
                                      ▼
                         ┌─────────────────────────┐    retry≤2
                         │     validate_rules      │ ─────────────┐
                         │     (≥90% rubric)       │              │
                         └────────────┬────────────┘              │
                                      ▼                           │
                         ┌─────────────────────────┐              │
                         │         writer          │  ◄───────────┘
                         │   generate PA form      │
                         └────────────┬────────────┘
                                      ▼
                         ┌─────────────────────────┐    retry≤2
                         │     validate_final      │ ─────────────┐
                         │   (≥85% completeness)   │              │
                         └────────────┬────────────┘              │
                                      ▼                           │
                         ┌─────────────────────────┐              │
                         │      human_review       │  ◄── escalation gate
                         │     (HITL approval)     │      (any agent → 3
                         └────────────┬────────────┘       retries → here)
                                      ▼
                         ┌─────────────────────────┐
                         │     submit_to_payer     │
                         └────────────┬────────────┘
                                      │
                         ┌────────────┼────────────┐
                         ▼            ▼            ▼
                     APPROVED     DENIED    NEEDS_MORE_INFO
```

Thirteen-node `StateGraph` with conditional routing — see [graph/workflow.py](graph/workflow.py).

---

## Tech stack

| Layer | Tool | Notes |
|---|---|---|
| Orchestration | LangGraph | 13-node `StateGraph`, conditional routers, per-agent retry counters |
| LLM | `gpt-4o-mini` (research, rules, writer), `gpt-4o` (supervisor) | OpenAI chat completions |
| Tracing | LangSmith | `run_name`, `tags`, `metadata` per agent call; locked dataset versioning |
| Persistence | Supabase (Postgres) | `case_results` (1 row / run), `audit_log` (1 row / agent step) — see [sql/setup.sql](sql/setup.sql) |
| Dashboard | Streamlit + Plotly | `showcase/app.py` (live), `dashboard/app.py` (Supabase-backed runtime view) |
| Eval | LangSmith experiments | Locked 120-case dataset, exact-match scoring |
| Tests | pytest | Workflow, agent, rules-engine, evaluator, audit coverage |

---

## Engineering highlights

- **Hybrid deterministic + LLM rules engine.** Contraindications, lab thresholds (incl. dual-BMI OR-logic for Wegovy-style rules), and step-therapy presence checks run as Python code before the LLM is invoked. The LLM only runs when deterministic gates cannot resolve. Implemented across [agents/rules_checker.py](agents/rules_checker.py) `_deterministic_*` functions; the change was made in v2 after Exp 5 isolated JSON-key hallucinations as the dominant failure mode.

- **Per-gate supervisor validation with independent retries.** Each agent's output is graded by an LLM-as-judge against a per-agent rubric, with separate confidence thresholds chosen empirically per gate role: 95% (eligibility), 80% (research), 90% (rules), 85% (writer). Each agent has its own retry counter; three failures escalate to HITL. See `validate_*_node` and `_handle_retry_logic` in [agents/supervisor.py](agents/supervisor.py).

- **Anti-hallucination prompt contract.** The rules-checker system prompt is six numbered RULES + carve-outs that pin the model to evaluating only keys present in `insurer_rules.json`, distinguish UNKNOWN from NOT-MET (RULE 4A), and disallow inferred safety screenings (RULE 6). See `SYSTEM_PROMPT` in [agents/rules_checker.py](agents/rules_checker.py).

- **Locked-set evaluation discipline.** All accuracy claims reference one LangSmith dataset (`pa-baseline-120-apr08`, n=120), version-pinned by timestamp. Each experiment in [CHANGELOG.md](CHANGELOG.md) cites its session ID, the dataset fingerprint, the row-level outcome, and any contamination disclosures (Exp 10's quota exhaustion is documented rather than hidden).

- **Layered triage as a debugging method.** The Exp 9→10 work used a 4-layer funnel — threshold sensitivity → deterministic-path gaps → LLM reasoning failures → gold-label audits — to classify and retire 24 bugs systematically rather than case-by-case prompt edits. Documented in the Experiment 10 entry of [CHANGELOG.md](CHANGELOG.md).

---

## Results

| Experiment | Exact-match | Δ | Change |
|---|---|---|---|
| Exp 7 (post-relabel) | 46.67% (56/120) | baseline | After dataset relabeling correction |
| Exp 8 | 63.33% (76/120) | +16.7 pp | RULE 4A semantic boundary + supervisor coercion of step-therapy partial failures to DENIED |
| **Exp 9** | **70.00% (84/120)** | +6.7 pp | Final clean benchmark |
| Exp 10 | 62.50% (75/120) | — | **Contaminated** by OpenAI quota exhaustion at case ~95; row-level CSV confirms target hypothesis (18/18 cases flipped correctly). Re-run pending. |

Total tracked eval spend: **~$10.89**. Exp 8 latency p50/p99: **22.1s / 33.7s**.

---

## Repo structure

```
prior-auth-agent/
├── main.py                 CLI entry point
├── agents/                 LangGraph nodes
│   ├── eligibility_checker.py
│   ├── research.py
│   ├── rules_checker.py    deterministic Python branches + LLM fallback
│   ├── supervisor.py       per-gate LLM-as-judge validation
│   ├── writer.py           PA form generator
│   └── post_decision.py    payer-side simulation (APPROVED / DENIED / NMI)
├── graph/workflow.py       13-node StateGraph + routing functions
├── config/
│   ├── insurer_rules.json  drug × insurer rule set
│   └── settings.py         typed env-driven settings
├── data/
│   ├── patients.json       synthetic patients (NPI prefix `9` = synthetic)
│   └── ground_truth.csv    expected determinations for the eval set
├── metrics/                token / latency / cost collector + evaluator
├── persistence/            Supabase REST client
├── showcase/app.py         AgentOps dashboard (deployed at the link above)
├── dashboard/app.py        Supabase-backed runtime dashboard
├── scripts/
│   ├── evaluate.py         LangSmith experiment runner
│   ├── create_dataset.py   build the 120-case eval set
│   └── generate_*.py       synthetic patient + rules generation
├── sql/setup.sql           Supabase schema (case_results, audit_log)
├── tests/                  pytest (workflow, agents, rules, evaluator, audit)
└── CHANGELOG.md            experiment-by-experiment history with session IDs
```

---

## Local development

```bash
git clone https://github.com/Dolbus/prior-auth-agent.git
cd prior-auth-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # add OPENAI_API_KEY (LangSmith / Supabase keys optional)

# Single case end-to-end
python main.py --patient PA-001

# Full eval set, auto-approve HITL
python main.py --all --no-hitl

# Tests
pytest tests/ -v
```

Required env: `OPENAI_API_KEY`. Optional: `LANGCHAIN_TRACING_V2` + `LANGCHAIN_API_KEY` (tracing), `SUPABASE_URL` + `SUPABASE_KEY` (persistence).

---

## What's intentionally not in v1

- **No real EHR integration.** All cases are synthetic JSON modeled on real clinical structure; NPIs are synthetic (`9`-prefixed) and patient identifiers are generated.
- **HITL is a CLI prompt**, not a UI workflow with role-based routing.
- **Insurer rules are a static JSON file**, not a live policy feed.
- **No PHI handling.** This is an architecture and evaluation demo; production deployment would need HIPAA controls, BAA-covered infrastructure, and audited data flows.
- **Single-payer simulation.** The post-decision branch simulates payer responses rather than integrating with a clearinghouse.

---

## License

MIT.
