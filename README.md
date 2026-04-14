# Prior Authorization AI Agent — AgentOps Demo

A four-agent Prior Authorization system built to showcase the **AgentOps framework** (Observability, Evaluation, Optimization).

**Stack:** LangGraph · LangSmith · Supabase · OpenAI GPT-4o mini (free tiers only)

---

## Architecture

```
┌──────────────┐
│  Supervisor  │ ◄── Orchestrates, validates, enforces guardrails
└──────┬───────┘
       │
  ┌────▼────┐    ┌─────────────┐    ┌──────────┐    ┌────────┐
  │ Research │───►│ Rules Check │───►│ HITL     │───►│ Writer │
  │  Agent   │    │   Agent     │    │ Review   │    │ Agent  │
  └──────────┘    └─────────────┘    └──────────┘    └────────┘
       │                │                                │
   patients.json   insurer_rules.py                 PA Document
```

**LangGraph Flow:**
```
START → Research → Validate → Rules Checker → Validate → HITL → Writer → Validate → END
                     ↺ retry                    ↺ retry                      ↺ retry
```

---

## Quick Start

### 1. Clone & Set Up Environment

```bash
cd prior-auth-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables

```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

**Required for Phase 1:**
| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Your OpenAI API key |

**Required for Phase 2 (LangSmith):**
| Variable | Description |
|----------|-------------|
| `LANGCHAIN_TRACING_V2` | Set to `true` |
| `LANGCHAIN_API_KEY` | Your LangSmith API key |
| `LANGCHAIN_PROJECT` | Project name (default: `prior-auth-agent`) |

**Required for Phase 3 (Supabase):**
| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_KEY` | Your Supabase anon key |

### 3. Run

```bash
# Interactive patient selection
python main.py

# Specific patient
python main.py --patient PA-001

# All patients (auto-approve HITL)
python main.py --all

# Skip HITL pause
python main.py --patient PA-001 --no-hitl
```

### 4. Run Tests

```bash
pytest tests/ -v
```

---

## Mock Patients

| ID | Patient | Treatment | Expected Outcome |
|----|---------|-----------|------------------|
| PA-001 | Maria Santos | Humira (RA) | ✅ APPROVED |
| PA-002 | James Chen | Ozempic (Weight) | ❌ DENIED |
| PA-003 | Aisha Washington | MRI Lumbar | ⏳ NEEDS_MORE_INFO |
| PA-004 | Robert Kim | Dupixent (Atopic Dermatitis) | ✅ APPROVED |
| PA-005 | Sarah Nielsen | Humira (Crohn's) | ❌ DENIED |

---

## AgentOps Metrics

| Metric | Description |
|--------|-------------|
| End-to-End Duration | Wall-clock time from start to final output |
| Handoff Latency | Time gap between consecutive agent transitions |
| Cost per Case | Token usage × GPT-4o mini pricing |
| Task Completion Rate | % of runs reaching final output |
| Guardrail Violation Rate | Supervisor failures / total checks |
| Factual Accuracy | Decision match vs expected outcome |
| Prompt Token Efficiency | Output tokens / input tokens ratio |
| Handoff Success Rate | Successful agent transitions / total transitions |

---

## Supabase Tables (Phase 3)

### `case_results`
```sql
CREATE TABLE case_results (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    patient_id TEXT NOT NULL,
    patient_name TEXT NOT NULL,
    pa_decision TEXT NOT NULL,
    expected_outcome TEXT,
    factual_accuracy FLOAT,
    duration_sec FLOAT,
    total_tokens INTEGER,
    cost_usd FLOAT,
    guardrail_violation_rate FLOAT,
    handoff_success_rate FLOAT,
    writer_output TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

### `audit_log`
```sql
CREATE TABLE audit_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    case_id UUID REFERENCES case_results(id),
    agent_name TEXT NOT NULL,
    step_type TEXT NOT NULL,
    duration_sec FLOAT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    guardrail_passed BOOLEAN,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

---

## Project Structure

```
prior-auth-agent/
├── main.py              # CLI entry point
├── config/              # Settings + insurer rules
├── agents/              # 4 LangGraph agent nodes
├── graph/               # StateGraph definition
├── metrics/             # Collector + evaluator
├── persistence/         # Supabase client (Phase 3)
├── dashboard/           # Streamlit app (Phase 4)
├── data/                # Mock patient JSON
└── tests/               # pytest suite
```

---

## Build Phases

- **Phase 1:** LangGraph workflow in terminal ← *current*
- **Phase 2:** LangSmith tracing integration
- **Phase 3:** Supabase persistence (case results + audit log)
- **Phase 4:** Streamlit dashboard with Plotly charts
