"""
showcase/app.py — Prior Authorization AgentOps Dashboard
Uber-inspired design. Numbers are the heroes.
Run: .venv/bin/streamlit run showcase/app.py
"""

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
DATA = Path(__file__).parent / "data"

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Prior Auth AI Agent — AgentOps",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background-color: #0a0a0a; }
[data-testid="stHeader"]           { display: none !important; }
[data-testid="stSidebar"]          { background-color: #111111; }
[data-testid="stToolbar"]          { display: none !important; }
#MainMenu                          { visibility: hidden; }
footer                             { visibility: hidden; }
.block-container                   { padding-top: 1rem !important; max-width: 1200px; }

.stTabs [data-baseweb="tab-list"] {
    background-color: transparent;
    gap: 0;
    border-bottom: 1px solid #1f1f1f;
}
.stTabs [data-baseweb="tab"] {
    background-color: transparent;
    color: #6b6b6b;
    padding: 12px 32px;
    font-weight: 500;
    font-size: 13px;
    letter-spacing: 0.03em;
    border-bottom: 2px solid transparent;
}
.stTabs [aria-selected="true"] {
    background-color: transparent !important;
    color: #ffffff !important;
    border-bottom: 2px solid #ffffff !important;
}
.stTabs [data-baseweb="tab-highlight"] {
    background-color: #ffffff !important;
}
.stTabs [data-baseweb="tab-border"] {
    background-color: #1f1f1f !important;
}

.card {
    background: #111111;
    border: 1px solid #1f1f1f;
    border-radius: 4px;
    padding: 24px 28px;
}
.card-green  { border-left: 3px solid #22c55e; }
.card-red    { border-left: 3px solid #ef4444; }
.card-amber  { border-left: 3px solid #f59e0b; }
.card-subtle { border-left: 3px solid #333333; }

.stat-label {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #6b6b6b;
    margin-top: 6px;
}
.stat-val {
    font-size: 28px;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: #ffffff;
    line-height: 1.1;
}
.stat-sub {
    font-size: 11px;
    color: #6b6b6b;
    margin-top: 4px;
    line-height: 1.5;
}

.badge {
    display: inline-block;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 3px 10px;
    border-radius: 2px;
    margin-bottom: 12px;
}
.badge-green  { background: rgba(34,197,94,0.12);  color: #22c55e; }
.badge-amber  { background: rgba(245,158,11,0.12); color: #f59e0b; }
.badge-subtle { background: #1f1f1f; color: #6b6b6b; }

hr { border-color: #1f1f1f; }

/* Equal-height cards in column rows */
[data-testid="stHorizontalBlock"] { align-items: stretch !important; }
[data-testid="stHorizontalBlock"] [data-testid="stVerticalBlock"] {
    display: flex; flex-direction: column;
}
[data-testid="stHorizontalBlock"] [data-testid="stVerticalBlock"] > div {
    flex: 1; display: flex; flex-direction: column;
}
[data-testid="stHorizontalBlock"] .card { flex: 1; }

/* Font smoothing */
[data-testid="stMarkdownContainer"] {
    -webkit-font-smoothing: antialiased;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, sans-serif;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADING
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data
def load_experiments():
    with open(DATA / "experiments.json") as f:
        return json.load(f)["experiments"]

@st.cache_data
def load_cases():
    with open(DATA / "cases.json") as f:
        return json.load(f)

@st.cache_data
def load_csvs():
    exp9  = pd.read_csv(ROOT / "artifacts" / "exp09_full_results.csv")
    exp10 = pd.read_csv(ROOT / "artifacts" / "exp10_full_results.csv")
    return exp9, exp10

exps              = load_experiments()
cases             = load_cases()
exp9_df, exp10_df = load_csvs()

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
PLOTLY_BASE = dict(
    template="plotly_dark",
    plot_bgcolor="#111111",
    paper_bgcolor="#0a0a0a",
    font=dict(color="#6b6b6b", size=12),
    margin=dict(l=20, r=20, t=40, b=20),
)

def grid_color():
    return "#1f1f1f"

DECISION_COLOR = {"APPROVED": "#22c55e", "DENIED": "#ef4444", "NEEDS_MORE_INFO": "#f59e0b"}
DECISION_LABEL = {"APPROVED": "APPROVED", "DENIED": "DENIED", "NEEDS_MORE_INFO": "NEEDS MORE INFO"}

STATUS_BADGE = {
    "clean":        ("✓ clean",        "#22c55e"),
    "locked":       ("⬡ locked",       "#ffffff"),
    "contaminated": ("⚠ contaminated", "#ef4444"),
    "factual":      ("~ factual acc",  "#f59e0b"),
}

# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "  The Problem  ",
    "  The Evidence  ",
    "  Case  ",
    "  What's Next  ",
    "  Source Data  ",
])


# ═════════════════════════════════════════════════════════════════════════════
# TAB 1 — THE PROBLEM
# ═════════════════════════════════════════════════════════════════════════════
with tab1:

    st.markdown("""
    <div style="padding:48px 0 40px 0;">
      <div style="font-size:11px;font-weight:600;letter-spacing:0.12em;
                  text-transform:uppercase;color:#6b6b6b;margin-bottom:16px;">
        Prior Authorization · Healthcare AI · AgentOps
      </div>
      <div style="font-size:42px;font-weight:800;letter-spacing:-0.02em;
                  color:#ffffff;line-height:1.15;max-width:680px;">
        PA approval takes 2–5 days.<br>
        I built an agent to evaluate<br>
        cases in <span style="color:#22c55e;">22 seconds.</span>
      </div>
      <div style="font-size:13px;color:#6b6b6b;margin-top:20px;max-width:560px;line-height:1.7;">
        A multi-agent LangGraph system evaluated across 10 controlled experiments
        on a locked dataset of 120 synthetic PA cases.
      </div>
    </div>
    """, unsafe_allow_html=True)

    s1, s2, s3 = st.columns(3)
    with s1:
        st.markdown("""
        <div style="padding-bottom:32px;">
          <div class="stat-val">2–5 days</div>
          <div class="stat-label">Manual PA Turnaround Time</div>
          <div class="stat-sub">AMA Prior Authorization Impact Survey, 2023</div>
        </div>""", unsafe_allow_html=True)
    with s2:
        st.markdown("""
        <div style="padding-bottom:32px;">
          <div class="stat-val" style="color:#22c55e;">22 s</div>
          <div class="stat-label">Agent Decision Time (P50)</div>
          <div class="stat-sub">LangSmith · n=120</div>
        </div>""", unsafe_allow_html=True)
    with s3:
        st.markdown("""
        <div style="padding-bottom:32px;">
          <div class="stat-val" style="color:#22c55e;">99.7%</div>
          <div class="stat-label">Processing Time Reduction</div>
          <div class="stat-sub">vs 2-hour manual minimum (gather docs + submit)</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    wf_left, wf_right = st.columns(2)

    with wf_left:
        st.markdown("""
        <div class="card" style="height:100%;">
          <div style="font-size:10px;font-weight:600;letter-spacing:0.12em;
                      text-transform:uppercase;color:#6b6b6b;margin-bottom:20px;">
            Traditional Workflow
          </div>
          <div style="display:flex;gap:0;">
            <div style="display:flex;flex-direction:column;align-items:center;
                        margin-right:14px;flex-shrink:0;">
              <div style="width:8px;height:8px;border-radius:50%;background:#333;margin-top:5px;"></div>
              <div style="width:1px;flex:1;background:#1f1f1f;min-height:32px;"></div>
              <div style="width:8px;height:8px;border-radius:50%;background:#333;"></div>
              <div style="width:1px;flex:1;background:#1f1f1f;min-height:32px;"></div>
              <div style="width:8px;height:8px;border-radius:50%;background:#333;"></div>
              <div style="width:1px;flex:1;background:#1f1f1f;min-height:32px;"></div>
              <div style="width:8px;height:8px;border-radius:50%;background:#333;"></div>
              <div style="width:1px;flex:1;background:#1f1f1f;min-height:32px;"></div>
              <div style="width:8px;height:8px;border-radius:50%;background:#333;"></div>
              <div style="width:1px;flex:1;background:#1f1f1f;min-height:32px;"></div>
              <div style="width:8px;height:8px;border-radius:50%;background:#333;"></div>
              <div style="width:1px;flex:1;background:#1f1f1f;min-height:32px;"></div>
              <div style="width:8px;height:8px;border-radius:50%;background:#ef4444;"></div>
            </div>
            <div style="flex:1;">
              <div style="margin-bottom:32px;">
                <div style="font-size:13px;color:#ffffff;font-weight:500;">Physician orders treatment</div>
              </div>
              <div style="margin-bottom:32px;">
                <div style="font-size:13px;color:#ffffff;font-weight:500;">Staff checks PA required</div>
                <div style="font-size:11px;color:#6b6b6b;margin-top:3px;">Manual lookup: insurer + drug/CPT code &nbsp;·&nbsp; <span style="color:#f59e0b;">15–30 min</span></div>
              </div>
              <div style="margin-bottom:32px;">
                <div style="font-size:13px;color:#ffffff;font-weight:500;">Staff gathers clinical docs</div>
                <div style="font-size:11px;color:#6b6b6b;margin-top:3px;">Charts, notes, labs, fax records &nbsp;·&nbsp; <span style="color:#f59e0b;">1–4 hours</span></div>
              </div>
              <div style="margin-bottom:32px;">
                <div style="font-size:13px;color:#ffffff;font-weight:500;">Submit to insurer portal</div>
                <div style="font-size:11px;color:#6b6b6b;margin-top:3px;">Fax / portal / phone entry &nbsp;·&nbsp; <span style="color:#f59e0b;">30–90 min</span></div>
              </div>
              <div style="margin-bottom:32px;">
                <div style="font-size:13px;color:#ffffff;font-weight:500;">Insurer assigns to queue</div>
                <div style="font-size:11px;color:#6b6b6b;margin-top:3px;">Payer Ops review queue &nbsp;·&nbsp; <span style="color:#f59e0b;">same day – 24 hrs</span></div>
              </div>
              <div style="margin-bottom:32px;">
                <div style="font-size:13px;color:#ffffff;font-weight:500;">Clinical reviewer decides</div>
                <div style="font-size:11px;color:#6b6b6b;margin-top:3px;">Payer-side human review &nbsp;·&nbsp; <span style="color:#f59e0b;">1–3 business days</span></div>
              </div>
              <div>
                <div style="font-size:13px;color:#ef4444;font-weight:600;">Denied → provider appeals</div>
                <div style="font-size:11px;color:#6b6b6b;margin-top:3px;">Peer-to-peer review &nbsp;·&nbsp; <span style="color:#ef4444;">5–15 business days</span><br>Patient may abandon therapy</div>
              </div>
            </div>
          </div>
          <div style="margin-top:20px;padding-top:16px;border-top:1px solid #1f1f1f;">
            <div style="font-size:12px;color:#6b6b6b;">
              <span style="color:#ffffff;font-weight:600;">Total:</span>
              2 days fastest &nbsp;·&nbsp; up to 21 days with denial + appeal
            </div>
            <div style="font-size:11px;color:#6b6b6b;margin-top:4px;font-style:italic;">
              Missing info loop adds 2–5 business days per cycle
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    with wf_right:
        st.markdown("""
        <div class="card" style="height:100%;">
          <div style="font-size:10px;font-weight:600;letter-spacing:0.12em;
                      text-transform:uppercase;color:#6b6b6b;margin-bottom:20px;">
            Agentic Workflow — LangGraph StateGraph
          </div>
          <div style="display:flex;gap:0;">
            <div style="display:flex;flex-direction:column;align-items:center;
                        margin-right:14px;flex-shrink:0;">
              <div style="width:8px;height:8px;border-radius:50%;background:#2a2a2a;margin-top:5px;"></div>
              <div style="width:1px;flex:1;background:#1f1f1f;min-height:32px;"></div>
              <div style="width:8px;height:8px;border-radius:50%;background:#2a2a2a;"></div>
              <div style="width:1px;flex:1;background:#1f1f1f;min-height:32px;"></div>
              <div style="width:8px;height:8px;border-radius:50%;background:#2a2a2a;"></div>
              <div style="width:1px;flex:1;background:#1f1f1f;min-height:32px;"></div>
              <div style="width:8px;height:8px;border-radius:50%;background:#2a2a2a;"></div>
              <div style="width:1px;flex:1;background:#1f1f1f;min-height:32px;"></div>
              <div style="width:8px;height:8px;border-radius:50%;background:#2a2a2a;"></div>
              <div style="width:1px;flex:1;background:#1f1f1f;min-height:32px;"></div>
              <div style="width:8px;height:8px;border-radius:50%;background:#2a2a2a;"></div>
              <div style="width:1px;flex:1;background:#1f1f1f;min-height:32px;"></div>
              <div style="width:8px;height:8px;border-radius:50%;background:#2a2a2a;"></div>
              <div style="width:1px;flex:1;background:#1f1f1f;min-height:32px;"></div>
              <div style="width:8px;height:8px;border-radius:50%;background:#2a2a2a;"></div>
              <div style="width:1px;flex:1;background:#1f1f1f;min-height:32px;"></div>
              <div style="width:8px;height:8px;border-radius:50%;background:#2a2a2a;"></div>
              <div style="width:1px;flex:1;background:#1f1f1f;min-height:32px;"></div>
              <div style="width:8px;height:8px;border-radius:50%;background:#22c55e;"></div>
            </div>
            <div style="flex:1;">
              <div style="margin-bottom:28px;">
                <div style="font-size:13px;color:#ffffff;font-weight:500;">Patient record loaded</div>
                <div style="font-size:11px;color:#6b6b6b;margin-top:3px;">Diagnoses · meds · labs · prior treatments</div>
              </div>
              <div style="margin-bottom:28px;">
                <div style="font-size:13px;color:#ffffff;font-weight:500;">Gate 1 — PA Eligibility
                  <span style="color:#22c55e;font-size:9px;font-weight:700;letter-spacing:0.08em;
                               margin-left:8px;background:rgba(34,197,94,0.1);
                               padding:2px 6px;border-radius:2px;">PYTHON</span></div>
                <div style="font-size:11px;color:#6b6b6b;margin-top:3px;">Drug + insurer lookup against coverage rules &nbsp;·&nbsp; <span style="color:#22c55e;">&lt; 1ms · 0 tokens</span></div>
              </div>
              <div style="margin-bottom:28px;">
                <div style="font-size:13px;color:#ffffff;font-weight:500;">Research Agent
                  <span style="color:#3b82f6;font-size:9px;font-weight:700;letter-spacing:0.08em;
                               margin-left:8px;background:rgba(59,130,246,0.1);
                               padding:2px 6px;border-radius:2px;">LLM · GPT-4o-mini</span></div>
                <div style="font-size:11px;color:#6b6b6b;margin-top:3px;">Extracts clinical fields from patient record &nbsp;·&nbsp; <span style="color:#f59e0b;">3.75s avg</span></div>
              </div>
              <div style="margin-bottom:28px;">
                <div style="font-size:13px;color:#ffffff;font-weight:500;">Gate 2 — Completeness Check
                  <span style="color:#a78bfa;font-size:9px;font-weight:700;letter-spacing:0.08em;
                               margin-left:8px;background:rgba(139,92,246,0.1);
                               padding:2px 6px;border-radius:2px;">SUPERVISOR · GPT-4o</span></div>
                <div style="font-size:11px;color:#6b6b6b;margin-top:3px;">All required fields present? Threshold ≥80% &nbsp;·&nbsp; <span style="color:#f59e0b;">1.76s avg</span></div>
              </div>
              <div style="margin-bottom:28px;">
                <div style="font-size:13px;color:#ffffff;font-weight:500;">Rules Checker
                  <span style="color:#22c55e;font-size:9px;font-weight:700;letter-spacing:0.08em;
                               margin-left:8px;background:rgba(34,197,94,0.1);
                               padding:2px 6px;border-radius:2px;">PYTHON</span></div>
                <div style="font-size:11px;color:#6b6b6b;margin-top:3px;">Contraindications · lab thresholds · step therapy &nbsp;·&nbsp; <span style="color:#22c55e;">~0ms · 0 tokens</span></div>
              </div>
              <div style="margin-bottom:28px;">
                <div style="font-size:13px;color:#ffffff;font-weight:500;">Gate 3 — Accuracy Check
                  <span style="color:#a78bfa;font-size:9px;font-weight:700;letter-spacing:0.08em;
                               margin-left:8px;background:rgba(139,92,246,0.1);
                               padding:2px 6px;border-radius:2px;">SUPERVISOR · GPT-4o</span></div>
                <div style="font-size:11px;color:#6b6b6b;margin-top:3px;">Correct rules applied? Step therapy verified? ≥90% &nbsp;·&nbsp; <span style="color:#f59e0b;">2.32s avg</span></div>
              </div>
              <div style="margin-bottom:28px;">
                <div style="font-size:13px;color:#ffffff;font-weight:500;">Writer Agent
                  <span style="color:#3b82f6;font-size:9px;font-weight:700;letter-spacing:0.08em;
                               margin-left:8px;background:rgba(59,130,246,0.1);
                               padding:2px 6px;border-radius:2px;">LLM · GPT-4o-mini</span></div>
                <div style="font-size:11px;color:#6b6b6b;margin-top:3px;">PA form + clinical justification &nbsp;·&nbsp; <span style="color:#ef4444;">10.07s avg — 46% of total</span></div>
              </div>
              <div style="margin-bottom:28px;">
                <div style="font-size:13px;color:#ffffff;font-weight:500;">Gate 4 — Confidence Check
                  <span style="color:#a78bfa;font-size:9px;font-weight:700;letter-spacing:0.08em;
                               margin-left:8px;background:rgba(139,92,246,0.1);
                               padding:2px 6px;border-radius:2px;">SUPERVISOR · GPT-4o</span></div>
                <div style="font-size:11px;color:#6b6b6b;margin-top:3px;">Output complete? Guardrails passed? ≥85% &nbsp;·&nbsp; <span style="color:#f59e0b;">3.10s avg</span></div>
              </div>
              <div style="margin-bottom:28px;">
                <div style="font-size:13px;color:#ffffff;font-weight:500;">Human Review Gate
                  <span style="color:#f59e0b;font-size:9px;font-weight:700;letter-spacing:0.08em;
                               margin-left:8px;background:rgba(245,158,11,0.1);
                               padding:2px 6px;border-radius:2px;">HITL</span></div>
                <div style="font-size:11px;color:#6b6b6b;margin-top:3px;">Clinician can override before output is finalized &nbsp;·&nbsp;
                  <span style="color:#f59e0b;">auto-approve mode in experiments</span></div>
              </div>
              <div>
                <div style="font-size:13px;color:#22c55e;font-weight:700;">Decision output</div>
                <div style="font-size:11px;color:#6b6b6b;margin-top:3px;">APPROVED / DENIED / NEEDS_MORE_INFO &nbsp;·&nbsp;
                  <span style="color:#22c55e;font-weight:700;">22.0s total (p50)</span></div>
              </div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
    st.markdown("""
    <div class="card" style="background:#0d0d0d;">
      <div style="font-size:10px;font-weight:600;letter-spacing:0.12em;
                  text-transform:uppercase;color:#6b6b6b;margin-bottom:16px;">
        Dataset &amp; Scope
      </div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:24px;">
        <div>
          <div style="font-size:11px;color:#6b6b6b;margin-bottom:4px;">Patients</div>
          <div style="font-size:13px;color:#ffffff;">120 synthetic cases · no real patient data</div>
        </div>
        <div>
          <div style="font-size:11px;color:#6b6b6b;margin-bottom:4px;">Payers</div>
          <div style="font-size:13px;color:#ffffff;">Aetna · Cigna · UnitedHealthcare · Humana</div>
        </div>
        <div>
          <div style="font-size:11px;color:#6b6b6b;margin-bottom:4px;">Drug Categories</div>
          <div style="font-size:13px;color:#ffffff;">GLP-1 · PCSK9 · Biologics · Oncology · Imaging · Mental Health</div>
          <div style="font-size:11px;color:#6b6b6b;margin-top:4px;line-height:1.5;">Selected for high PA burden, rule complexity, and publicly available coverage criteria</div>
        </div>
        <div>
          <div style="font-size:11px;color:#6b6b6b;margin-bottom:4px;">Ground Truth Split</div>
          <div style="font-size:13px;color:#ffffff;">72 DENIED · 36 APPROVED · 12 VALID_ESCALATION</div>
        </div>
        <div>
          <div style="font-size:11px;color:#6b6b6b;margin-bottom:4px;">Payer Rules</div>
          <div style="font-size:13px;color:#ffffff;">Manually authored from publicly available coverage criteria</div>
        </div>
        <div>
          <div style="font-size:11px;color:#6b6b6b;margin-bottom:4px;">Eval Platform</div>
          <div style="font-size:13px;color:#ffffff;">LangSmith · 10 experiments</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — THE EVIDENCE
# ═════════════════════════════════════════════════════════════════════════════
with tab2:
    obs_tab, eval_tab, opt_tab = st.tabs([
        "  Observability  ",
        "  Evaluation  ",
        "  Optimization  ",
    ])

    # ── OBS ──────────────────────────────────────────────────────────────────
    with obs_tab:
        st.markdown("""
        <div style="padding:24px 0 8px 0;">
          <div style="font-size:10px;font-weight:600;letter-spacing:0.12em;
                      text-transform:uppercase;color:#6b6b6b;">
            Inside the black box — latency, cost, and handoff overhead across 120 LangSmith traces
          </div>
        </div>
        """, unsafe_allow_html=True)

        k1, k2, k3, k4 = st.columns(4)
        for col, val, val_color, label, sub in [
            (k1, "21.44s", "#ffffff", "Authorization TAT (P50)", "p95: 28.89s · min: 16.23s · max: 35.42s"),
            (k2, "$0.012", "#22c55e", "Cost Per Authorization",  "vs $8–12 manual · 99.9% cost reduction"),
            (k3, "5,154",  "#ffffff", "Tokens Per Case (Avg)",   "3,572 input · 1,582 output · ratio 2.26:1"),
            (k4, "< 3ms",  "#22c55e", "Agent-to-Agent Handoff",  "max 2.6ms · framework is not the bottleneck"),
        ]:
            with col:
                st.markdown(f"""
                <div class="card">
                  <div style="font-size:32px;font-weight:800;letter-spacing:-0.02em;
                              color:{val_color};line-height:1;">{val}</div>
                  <div class="stat-label" style="margin-top:8px;">{label}</div>
                  <div class="stat-sub">{sub}</div>
                </div>""", unsafe_allow_html=True)

        st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

        # ── FULL-WIDTH HORIZONTAL BAR CHART ──────────────────────────────────
        bar_labels = ["Rules Checker", "Research Validation", "Rules Validation",
                      "Final Validation", "Research Agent", "Writer Agent"]
        bar_durs   = [0.95, 1.76, 2.32, 3.10, 3.75, 10.07]
        bar_colors = ["#22c55e",
                      "rgba(255,255,255,0.30)", "rgba(255,255,255,0.30)",
                      "rgba(255,255,255,0.30)", "rgba(255,255,255,0.50)",
                      "#ef4444"]
        bar_annots = ["Python gate · median 0ms", "1.76s", "2.32s",
                      "3.10s", "3.75s", "10.07s · 46% of TAT"]

        fig_nodes = go.Figure(go.Bar(
            y=bar_labels, x=bar_durs, orientation="h",
            marker_color=bar_colors,
            marker_line_width=0,
            text=bar_annots,
            textposition="outside",
            textfont=dict(color="#6b6b6b", size=11),
            hovertemplate="<b>%{y}</b><br>Mean: %{x}s<extra></extra>",
            cliponaxis=False,
        ))
        fig_nodes.update_traces(
            textfont_color=["#22c55e", "#6b6b6b", "#6b6b6b",
                            "#6b6b6b", "#6b6b6b", "#ef4444"]
        )
        fig_nodes.update_layout(
            **PLOTLY_BASE,
            title=dict(
                text="Where does 22 seconds go? — Node-level breakdown (mean, n=120)",
                font=dict(color="#ffffff", size=13)
            ),
            xaxis=dict(
                title="seconds", gridcolor=grid_color(),
                color="#6b6b6b", range=[0, 17],
                tickvals=[0, 2, 4, 6, 8, 10],
            ),
            yaxis=dict(color="#ffffff", tickfont=dict(size=12)),
            showlegend=False,
            height=300,
        )
        fig_nodes.update_layout(margin=dict(l=20, r=20, t=48, b=20))
        st.plotly_chart(fig_nodes, use_container_width=True)

        st.markdown("""
        <div style="font-size:11px;color:#6b6b6b;margin-top:-8px;margin-bottom:24px;
                    padding-left:4px;">
          Agent-to-agent handoff overhead (max 2.6ms) is not visible at this scale —
          LLM inference is the bottleneck, not the orchestration framework.
        </div>
        """, unsafe_allow_html=True)

        # ── BOTTOM ROW: TAT DISTRIBUTION (CSS) + A2A TABLE ───────────────────
        tat_col, a2a_col = st.columns([3, 2])

        with tat_col:
            tat_html = (
                '<div class="card" style="background:#0d0d0d;padding:24px 28px 20px;">'
                '<div style="font-size:10px;font-weight:600;letter-spacing:0.12em;'
                'text-transform:uppercase;color:#6b6b6b;margin-bottom:40px;">TAT Distribution — n=120</div>'
                '<div style="position:relative;height:72px;margin:0 20px;overflow:visible;">'
                '<div style="position:absolute;top:20px;left:0%;width:27.2%;height:2px;background:#333;"></div>'
                '<div style="position:absolute;top:20px;left:27.2%;width:38.8%;height:2px;background:#555;"></div>'
                '<div style="position:absolute;top:20px;left:66%;width:34%;height:2px;background:rgba(245,158,11,0.45);"></div>'
                '<div style="position:absolute;top:14px;left:0%;width:12px;height:12px;border-radius:50%;background:#555;transform:translateX(-50%);"></div>'
                '<div style="position:absolute;top:32px;left:0%;transform:translateX(-50%);text-align:center;white-space:nowrap;">'
                '<div style="font-size:12px;font-weight:600;color:#6b6b6b;">16.23s</div>'
                '<div style="font-size:9px;letter-spacing:0.1em;color:#555;text-transform:uppercase;margin-top:2px;">Min</div>'
                '</div>'
                '<div style="position:absolute;top:12px;left:27.2%;width:16px;height:16px;border-radius:50%;background:#ffffff;transform:translateX(-50%);"></div>'
                '<div style="position:absolute;top:-22px;left:27.2%;transform:translateX(-50%);text-align:center;white-space:nowrap;">'
                '<div style="font-size:12px;font-weight:700;color:#ffffff;">21.44s</div>'
                '<div style="font-size:9px;letter-spacing:0.1em;color:#6b6b6b;text-transform:uppercase;margin-top:2px;">P50</div>'
                '</div>'
                '<div style="position:absolute;top:12px;left:30.1%;width:16px;height:16px;border-radius:50%;background:#22c55e;transform:translateX(-50%);"></div>'
                '<div style="position:absolute;top:32px;left:30.1%;transform:translateX(-50%);text-align:center;white-space:nowrap;">'
                '<div style="font-size:12px;font-weight:700;color:#22c55e;">22.0s</div>'
                '<div style="font-size:9px;letter-spacing:0.1em;color:#6b6b6b;text-transform:uppercase;margin-top:2px;">Mean</div>'
                '</div>'
                '<div style="position:absolute;top:13px;left:66%;width:14px;height:14px;border-radius:50%;background:#f59e0b;transform:translateX(-50%);"></div>'
                '<div style="position:absolute;top:-22px;left:66%;transform:translateX(-50%);text-align:center;white-space:nowrap;">'
                '<div style="font-size:12px;font-weight:700;color:#f59e0b;">28.89s</div>'
                '<div style="font-size:9px;letter-spacing:0.1em;color:#6b6b6b;text-transform:uppercase;margin-top:2px;">P95</div>'
                '</div>'
                '<div style="position:absolute;top:14px;left:100%;width:12px;height:12px;border-radius:50%;background:#555;transform:translateX(-50%);"></div>'
                '<div style="position:absolute;top:32px;left:100%;transform:translateX(-50%);text-align:center;white-space:nowrap;">'
                '<div style="font-size:12px;font-weight:600;color:#6b6b6b;">35.42s</div>'
                '<div style="font-size:9px;letter-spacing:0.1em;color:#555;text-transform:uppercase;margin-top:2px;">Max</div>'
                '</div>'
                '</div>'
                '<div style="font-size:11px;color:#6b6b6b;margin-top:28px;padding-top:16px;border-top:1px solid #1f1f1f;">'
                'P95 at 28.89s — complex step-therapy cases pull the tail right. Writer node accounts for the variance.'
                '</div>'
                '</div>'
            )
            st.markdown(tat_html, unsafe_allow_html=True)

        with a2a_col:
            st.markdown("""
            <div class="card" style="height:100%;">
              <div style="font-size:10px;font-weight:600;letter-spacing:0.12em;
                          text-transform:uppercase;color:#6b6b6b;margin-bottom:20px;">
                Agent-to-Agent Handoff Latency
              </div>
              <div style="display:flex;flex-direction:column;gap:0;">
                <div style="display:flex;justify-content:space-between;
                            padding:10px 0;border-bottom:1px solid #1f1f1f;">
                  <span style="font-size:12px;color:#6b6b6b;">Research → Research Validation</span>
                  <span style="font-size:12px;color:#ffffff;font-weight:600;">1.8 ms</span>
                </div>
                <div style="display:flex;justify-content:space-between;
                            padding:10px 0;border-bottom:1px solid #1f1f1f;">
                  <span style="font-size:12px;color:#6b6b6b;">Research Validation → Rules Checker</span>
                  <span style="font-size:12px;color:#ffffff;font-weight:600;">1.2 ms</span>
                </div>
                <div style="display:flex;justify-content:space-between;
                            padding:10px 0;border-bottom:1px solid #1f1f1f;">
                  <span style="font-size:12px;color:#6b6b6b;">Rules Checker → Rules Validation</span>
                  <span style="font-size:12px;color:#ffffff;font-weight:600;">0.9 ms</span>
                </div>
                <div style="display:flex;justify-content:space-between;
                            padding:10px 0;border-bottom:1px solid #1f1f1f;">
                  <span style="font-size:12px;color:#6b6b6b;">Rules Validation → Writer</span>
                  <span style="font-size:12px;color:#ffffff;font-weight:600;">1.1 ms</span>
                </div>
                <div style="display:flex;justify-content:space-between;
                            padding:10px 0;">
                  <span style="font-size:12px;color:#6b6b6b;">Writer → Final Validation</span>
                  <span style="font-size:12px;color:#ffffff;font-weight:600;">2.6 ms</span>
                </div>
              </div>
              <div style="margin-top:16px;padding-top:12px;border-top:1px solid #1f1f1f;
                          font-size:11px;color:#22c55e;line-height:1.6;">
                Every transition &lt; 3ms. LangGraph orchestration overhead
                is effectively zero.
              </div>
            </div>
            """, unsafe_allow_html=True)

    # ── EVAL ─────────────────────────────────────────────────────────────────
    with eval_tab:
        st.markdown("""
        <div style="padding:24px 0 8px 0;">
          <div style="font-size:10px;font-weight:600;letter-spacing:0.12em;
                      text-transform:uppercase;color:#6b6b6b;">
            Did the agent get the decision right? — 10 experiments · 120-case locked dataset
          </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div style="text-align:center;padding:40px 0 32px 0;">
          <div style="font-size:10px;font-weight:600;letter-spacing:0.12em;
                      text-transform:uppercase;color:#6b6b6b;margin-bottom:8px;">
            PA Decision Accuracy — Exact Match
          </div>
          <div style="font-size:80px;font-weight:800;letter-spacing:-0.03em;
                      color:#22c55e;line-height:1;">70.0%</div>
        </div>
        """, unsafe_allow_html=True)

        q1, q2 = st.columns(2)
        with q1:
            st.markdown("""
            <div class="card card-green">
              <div style="font-size:36px;font-weight:800;letter-spacing:-0.02em;color:#22c55e;">
                0% → 100%
              </div>
              <div class="stat-label" style="margin-top:8px;">Task Completion Rate</div>
              <div class="stat-sub">35 pipeline failures (Baseline) → 0 failures (Exp 3+).
              All 120 cases now produce structured output.</div>
            </div>""", unsafe_allow_html=True)
        with q2:
            st.markdown("""
            <div class="card">
              <div style="font-size:36px;font-weight:800;letter-spacing:-0.02em;color:#ffffff;">
                +8.7pp
              </div>
              <div class="stat-label" style="margin-top:8px;">Avg Accuracy Gain Per Promoted Experiment</div>
              <div class="stat-sub">Only changes that beat the locked baseline were promoted.
              10 experiments run · 6 promoted to next iteration.</div>
            </div>""", unsafe_allow_html=True)

        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

        em_exps = [e for e in exps if e.get("score_em") is not None and e["id"] != "exp10"]
        x_main  = [e["label"] for e in em_exps]
        y_main  = [e["score_em"] for e in em_exps]

        fig_line = go.Figure()
        fig_line.add_trace(go.Scatter(
            x=x_main, y=y_main,
            fill="tozeroy", fillcolor="rgba(255,255,255,0.03)",
            line=dict(width=0), showlegend=False, hoverinfo="skip",
        ))
        fig_line.add_trace(go.Scatter(
            x=x_main, y=y_main,
            mode="lines+markers",
            name="PA Decision Accuracy",
            line=dict(color="#ffffff", width=2),
            marker=dict(size=8, color="#ffffff", line=dict(color="#0a0a0a", width=1.5)),
            hovertemplate="<b>%{x}</b><br>Accuracy: %{y:.2f}%<extra></extra>",
        ))
        fig_line.add_hline(
            y=70.0, line_dash="dot", line_color="#22c55e", opacity=0.4,
            annotation_text="70.0% locked benchmark (Exp 9)",
            annotation_font=dict(color="#22c55e", size=10),
            annotation_position="right",
        )
        fig_line.update_layout(
            **PLOTLY_BASE,
            title=dict(text="PA Decision Accuracy — 10 experiments · n=120 locked dataset",
                       font=dict(color="#ffffff", size=13)),
            yaxis=dict(title="Accuracy %", ticksuffix="%", range=[0, 83],
                       gridcolor=grid_color(), color="#6b6b6b", zeroline=False),
            xaxis=dict(gridcolor=grid_color(), color="#6b6b6b"),
            legend=dict(bgcolor="#111111", bordercolor="#1f1f1f",
                        font=dict(color="#6b6b6b", size=11), x=0.01, y=0.99),
            height=360,
            annotations=[
                dict(x="Exp 5",    y=11.7,  text="Gate 3 over-indexed", showarrow=True,
                     arrowhead=2, ax=55, ay=40, font=dict(size=10, color="#f59e0b"),
                     arrowcolor="#f59e0b", bgcolor="#0a0a0a"),
                dict(x="Exp 6d.1", y=30.8,  text="Python gate", showarrow=True,
                     arrowhead=2, ax=-50, ay=-38, font=dict(size=10, color="#22c55e"),
                     arrowcolor="#22c55e", bgcolor="#0a0a0a"),
                dict(x="Exp 7",    y=46.67, text="32 relabels", showarrow=True,
                     arrowhead=2, ax=50, ay=-30, font=dict(size=10, color="#6b6b6b"),
                     arrowcolor="#6b6b6b", bgcolor="#0a0a0a"),
                dict(x="Exp 9",    y=70.0,  text="locked ✓", showarrow=True,
                     arrowhead=2, ax=45, ay=-30, font=dict(size=10, color="#22c55e"),
                     arrowcolor="#22c55e", bgcolor="#0a0a0a"),
            ],
        )
        st.plotly_chart(fig_line, use_container_width=True)


        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

        mis_col, txt_col = st.columns([2, 3])
        with mis_col:
            fig_d = go.Figure(go.Pie(
                labels=["Pattern A — Zero steps→NMI (18)",
                        "Pattern B — Gold label error (4)",
                        "Pattern C — Diagnosis mismatch (2)"],
                values=[18, 4, 2],
                hole=0.58,
                marker=dict(
                    colors=["#22c55e","rgba(255,255,255,0.45)","#333333"],
                    line=dict(color="#0a0a0a", width=2),
                ),
                textinfo="percent",
                textfont=dict(size=11, color="#ffffff"),
                hovertemplate="<b>%{label}</b><br>%{value} cases<extra></extra>",
            ))
            fig_d.add_annotation(
                text="24<br><span style='font-size:11px'>cases</span>",
                x=0.5, y=0.5, font=dict(size=20, color="#ffffff"), showarrow=False,
            )
            fig_d.update_layout(
                **PLOTLY_BASE,
                title=dict(text="Misclassification Pattern Analysis",
                           font=dict(color="#ffffff", size=13)),
                showlegend=True,
                legend=dict(bgcolor="#111111", bordercolor="#1f1f1f",
                            font=dict(color="#6b6b6b", size=10),
                            orientation="v", x=0.5, y=-0.25, xanchor="center"),
                height=300,
            )
            fig_d.update_layout(margin=dict(l=10, r=10, t=48, b=70))
            st.plotly_chart(fig_d, use_container_width=True)

        with txt_col:
            st.markdown("""
            <div style="padding-top:48px;">
              <div style="font-size:13px;color:#ffffff;font-weight:600;margin-bottom:16px;">
                24 DENIED→NMI errors after Exp 9
              </div>
              <div style="font-size:13px;color:#6b6b6b;line-height:1.8;">
                <span style="color:#22c55e;font-weight:600;">Pattern A (75%)</span> —
                empty prior_treatments treated as missing data → NMI instead of DENIED.
                Fixed in Exp 10. 18/18 cases confirmed at row level.<br>
                <span style="color:rgba(255,255,255,0.5);font-weight:600;">Pattern B (17%)</span> —
                gold label errors. Model was correct; benchmark was wrong.<br>
                <span style="color:#6b6b6b;font-weight:600;">Pattern C (8%)</span> —
                diagnosis code mismatch. Exp 11 target.
              </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
        st.markdown("""
        <div class="card card-amber">
          <div style="font-size:10px;font-weight:600;letter-spacing:0.12em;
                      text-transform:uppercase;color:#f59e0b;margin-bottom:12px;">
            Metrics Not Yet Measured in This Evaluation
          </div>
          <div style="font-size:12px;color:#6b6b6b;line-height:1.8;">
            · <strong style="color:#ffffff;">Field Extraction Accuracy</strong> —
              lab values and ICD-10 codes not validated against source record (Exp 11 target)<br>
            · <strong style="color:#ffffff;">False Denial Rate / False Approval Rate</strong> —
              requires clinical appropriateness ground truth beyond binary label matching<br>
            · <strong style="color:#ffffff;">Hallucination Rate on PA Form</strong> —
              clinical facts in writer output not yet verified against source patient record
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ── OPT ──────────────────────────────────────────────────────────────────
    with opt_tab:
        st.markdown("""
        <div style="padding:32px 0 24px 0;">
          <div class="stat-label">Primary Latency Bottleneck</div>
          <div style="font-size:64px;font-weight:800;color:#ef4444;
                      letter-spacing:-0.03em;line-height:1;margin-top:4px;">46%</div>
          <div style="font-size:13px;color:#6b6b6b;margin-top:10px;
                      max-width:560px;line-height:1.7;">
            Writer agent consumes 10.07s of the 22.0s total authorization TAT.
            Structured output generation (OpenAI function calling) is the primary fix.
          </div>
        </div>
        """, unsafe_allow_html=True)

        o1, o2, o3 = st.columns(3)
        for col, border, badge_txt, title, metric_txt, metric_color, action, impact in [
            (o1, "#f59e0b", "EXP 11 TARGET", "Drug Synonym Resolution",
             "Brand/generic mismatch unresolved", "#f59e0b",
             "RxNorm API integration in Research Agent (e.g. Zocor → simvastatin)",
             "+2–4% PA Decision Accuracy"),
            (o2, "#ef4444", "EXP 12 TARGET", "Writer Node Latency",
             "10.07s → ~4s target", "#ef4444",
             "Replace free-form generation with OpenAI structured outputs / function calling",
             "~27% TAT reduction · ~$0.004/case cost saving"),
            (o3, "#f59e0b", "EXP 13 TARGET", "Token Efficiency",
             "5,154 → ~3,500 tokens/case", "#f59e0b",
             "Research agent context compression · supervisor gate prompt optimization",
             "~30% cost reduction per authorization"),
        ]:
            with col:
                st.markdown(f"""
                <div class="card" style="border-left:3px solid {border};height:100%;">
                  <span class="badge badge-subtle">{badge_txt}</span>
                  <div style="font-size:15px;font-weight:700;color:#ffffff;margin-bottom:8px;">{title}</div>
                  <div style="font-size:13px;color:{metric_color};font-weight:600;margin-bottom:10px;">{metric_txt}</div>
                  <div style="font-size:12px;color:#6b6b6b;line-height:1.6;margin-bottom:10px;">{action}</div>
                  <div style="font-size:12px;color:#ffffff;font-weight:500;">{impact}</div>
                </div>""", unsafe_allow_html=True)

        st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

        exp_labels = ["Exp 1","Exp 2","Exp 3b","Exp 4","Exp 5",
                      "Exp 6d.1","Exp 7","Exp 8","Exp 9","Exp 10*"]
        exp_costs  = [0.20, 0.21, 1.44, 0.72, 1.53, 1.12, 1.48, 1.50, 1.48, 1.21]
        bar_colors = ["rgba(255,255,255,0.35)","rgba(255,255,255,0.35)","#ef4444",
                      "rgba(255,255,255,0.35)","rgba(255,255,255,0.35)",
                      "rgba(255,255,255,0.35)","rgba(255,255,255,0.35)",
                      "rgba(255,255,255,0.35)","rgba(255,255,255,0.35)","#f59e0b"]

        fig_cost = go.Figure(go.Bar(
            x=exp_labels, y=exp_costs,
            marker_color=bar_colors,
            text=[f"${c:.2f}" for c in exp_costs],
            textposition="outside",
            textfont=dict(color="#ffffff", size=10),
            hovertemplate="<b>%{x}</b><br>$%{y:.2f}<extra></extra>",
        ))
        fig_cost.add_annotation(
            x="Exp 3b", y=1.44, text="7× spike<br>GPT-4o upgrade",
            showarrow=True, arrowhead=2, ax=0, ay=-48,
            font=dict(color="#ef4444", size=10),
            arrowcolor="#ef4444", bgcolor="#0a0a0a",
        )
        fig_cost.add_annotation(
            x="Exp 10*", y=1.21, text="partial run<br>95/120 cases",
            showarrow=True, arrowhead=2, ax=0, ay=-48,
            font=dict(color="#f59e0b", size=10),
            arrowcolor="#f59e0b", bgcolor="#0a0a0a",
        )
        fig_cost.update_layout(
            **PLOTLY_BASE,
            title=dict(text="Cost Per Experiment Run (120 cases)",
                       font=dict(color="#ffffff", size=13)),
            yaxis=dict(title="USD", gridcolor=grid_color(), color="#6b6b6b", tickprefix="$"),
            xaxis=dict(gridcolor=grid_color(), color="#6b6b6b"),
            showlegend=False, height=300,
        )
        fig_cost.update_layout(margin=dict(l=20, r=20, t=48, b=20))
        st.plotly_chart(fig_cost, use_container_width=True)

        st.markdown("""
        <div style="font-size:11px;color:#6b6b6b;margin-top:-8px;">
          Total eval spend: ~$11 across 10 experiments. Average cost per 120-case run: $1.19.
          Post Exp 6d.1, Python gate reduced per-case token spend on clear-cut cases to zero.
        </div>
        """, unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 3 — CASE
# ═════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("""
    <div style="padding:48px 0 40px 0;">
      <div style="font-size:10px;font-weight:600;letter-spacing:0.12em;
                  text-transform:uppercase;color:#6b6b6b;margin-bottom:16px;">
        Case · PA-057 · alirocumab (Praluent) · Humana
      </div>
      <div style="font-size:42px;font-weight:800;letter-spacing:-0.02em;
                  color:#ffffff;line-height:1.15;max-width:700px;">
        18 wrong decisions.<br>
        Traced to one code path.<br>
        Fixed in <span style="color:#22c55e;">2 lines.</span>
      </div>
      <div style="font-size:13px;color:#6b6b6b;margin-top:20px;max-width:560px;line-height:1.7;">
        Not a model problem. A logic problem. The rules checker was misclassifying
        empty step-therapy history as missing data — instead of a clear denial criterion.
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── BEAT 1: THE DIAGNOSIS ─────────────────────────────────────────────────
    st.markdown("""
    <div style="font-size:10px;font-weight:600;letter-spacing:0.12em;
                text-transform:uppercase;color:#6b6b6b;margin:24px 0 16px 0;">
      01 — The Diagnosis
    </div>
    """, unsafe_allow_html=True)

    d1, d2 = st.columns(2)
    with d1:
        st.markdown("""
        <div class="card">
          <div style="font-size:10px;font-weight:600;color:#6b6b6b;
                      letter-spacing:0.12em;text-transform:uppercase;margin-bottom:16px;">
            What the agent saw
          </div>
          <div style="font-family:monospace;font-size:12px;color:#ffffff;line-height:2.2;">
            <span style="color:#6b6b6b;">patient:          </span>PA-057<br>
            <span style="color:#6b6b6b;">drug:             </span>alirocumab (Praluent)<br>
            <span style="color:#6b6b6b;">insurer:          </span>Humana<br>
            <span style="color:#6b6b6b;">prior_treatments: </span>[] &nbsp;<span style="color:#f59e0b;font-size:11px;">← empty, not missing</span><br>
            <span style="color:#6b6b6b;">step_therapy req: </span>ezetimibe + simvastatin<br>
            <span style="color:#6b6b6b;">ground truth:     </span><span style="color:#ef4444;font-weight:700;">DENIED</span>
          </div>
        </div>
        """, unsafe_allow_html=True)
    with d2:
        st.markdown("""
        <div class="card card-red">
          <div style="font-size:10px;font-weight:600;color:#6b6b6b;
                      letter-spacing:0.12em;text-transform:uppercase;margin-bottom:16px;">
            What the code was doing wrong
          </div>
          <div style="font-size:13px;color:#ffffff;line-height:1.9;">
            Empty <span style="font-family:monospace;color:#f59e0b;">prior_treatments: []</span>
            was being treated as <em>missing data</em> — triggering
            <span style="font-family:monospace;color:#ef4444;">UNKNOWN</span> instead of
            <span style="font-family:monospace;color:#22c55e;">NOT MET</span>.
          </div>
          <div style="margin-top:16px;font-size:13px;color:#6b6b6b;line-height:1.9;">
            An empty list means the patient has <strong style="color:#ffffff;">done no prior therapy</strong>
            — step therapy requirement is clearly not met.
            The agent was asking for more information
            when the answer was already in the data.
          </div>
          <div style="margin-top:16px;font-family:monospace;font-size:12px;">
            <span style="background:#2a0f0f;color:#ef4444;padding:3px 12px;border-radius:2px;font-weight:700;">
              NEEDS_MORE_INFO
            </span>
            <span style="color:#6b6b6b;margin:0 10px;">→ should be →</span>
            <span style="background:#0f2a1a;color:#22c55e;padding:3px 12px;border-radius:2px;font-weight:700;">
              DENIED
            </span>
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ── BEAT 2: THE FIX ───────────────────────────────────────────────────────
    st.markdown("""
    <div style="font-size:10px;font-weight:600;letter-spacing:0.12em;
                text-transform:uppercase;color:#6b6b6b;margin:32px 0 16px 0;">
      02 — The Fix
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="background:#111111;border:1px solid #1f1f1f;border-radius:4px;padding:20px 24px;">
      <div style="font-size:11px;color:#6b6b6b;margin-bottom:16px;font-family:monospace;">
        agents/rules_checker.py — 2 lines changed
      </div>
      <div style="font-family:monospace;font-size:12px;line-height:2.4;">
        <span style="color:#6b6b6b;"># line ~533 — criteria label</span><br>
        <span style="background:#2a0f0f;color:#ef4444;padding:3px 10px;border-radius:2px;display:inline-block;margin:2px 0;">
          - f"- `{'{key}'}`: UNKNOWN — no required steps documented in prior_treatments"
        </span><br>
        <span style="background:#0f2a1a;color:#22c55e;padding:3px 10px;border-radius:2px;display:inline-block;margin:2px 0;">
          + f"- `{'{key}'}`: NOT MET — no required steps documented in prior_treatments"
        </span><br><br>
        <span style="color:#6b6b6b;"># line ~586 — determination output</span><br>
        <span style="background:#2a0f0f;color:#ef4444;padding:3px 10px;border-radius:2px;display:inline-block;margin:2px 0;">
          - return _format_deterministic_denial(determination="NEEDS_MORE_INFO", ...)
        </span><br>
        <span style="background:#0f2a1a;color:#22c55e;padding:3px 10px;border-radius:2px;display:inline-block;margin:2px 0;">
          + return _format_deterministic_denial(determination="DENIED", ...)
        </span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── BEAT 3: THE PROOF ─────────────────────────────────────────────────────
    st.markdown("""
    <div style="font-size:10px;font-weight:600;letter-spacing:0.12em;
                text-transform:uppercase;color:#6b6b6b;margin:32px 0 16px 0;">
      03 — The Proof
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="background:#0f2a1a;border:1px solid #22c55e;border-radius:4px;padding:20px 24px;">
      <div style="display:flex;align-items:center;gap:16px;margin-bottom:16px;">
        <div style="font-size:36px;font-weight:800;color:#22c55e;letter-spacing:-0.02em;line-height:1;">18/18</div>
        <div>
          <div style="font-size:14px;font-weight:600;color:#ffffff;">Target cases confirmed fixed at row level</div>
          <div style="font-size:11px;color:#6b6b6b;margin-top:4px;">
            exp10_full_results.csv vs exp09_full_results.csv
            &nbsp;·&nbsp; all 18 flipped NEEDS_MORE_INFO → DENIED &nbsp;·&nbsp; match=1 ✓
          </div>
        </div>
      </div>
      <div style="font-family:monospace;font-size:11px;color:#6b6b6b;
                  padding-top:14px;border-top:1px solid rgba(34,197,94,0.2);line-height:2.0;">
        PA-002 &nbsp; PA-007 &nbsp; PA-012 &nbsp; PA-017 &nbsp; PA-022 &nbsp; PA-027 &nbsp;
        PA-042 &nbsp; PA-047 &nbsp; PA-052 &nbsp; PA-057 &nbsp; PA-067 &nbsp; PA-077 &nbsp;
        PA-082 &nbsp; PA-087 &nbsp; PA-092 &nbsp; PA-097 &nbsp; PA-102 &nbsp; PA-107
      </div>
    </div>
    """, unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 4 — WHAT'S NEXT
# ═════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown("""
    <div style="padding:48px 0 32px 0;">
      <div style="font-size:11px;font-weight:600;letter-spacing:0.12em;
                  text-transform:uppercase;color:#6b6b6b;margin-bottom:16px;">
        Production Readiness Roadmap
      </div>
      <div style="font-size:42px;font-weight:800;letter-spacing:-0.02em;
                  color:#ffffff;line-height:1.15;max-width:640px;">
        70% accuracy on synthetic data.<br>
        Here's what production looks like.
      </div>
    </div>
    """, unsafe_allow_html=True)

    row1_l, row1_r = st.columns(2)
    row2_l, row2_r = st.columns(2)

    card_data = [
        (row1_l, "#22c55e", "badge-green", "IN PROGRESS", "Decision Quality", [
            "Exp 10b: clean rerun — 78–82% projected",
            "Exp 11: RxNorm drug synonyms · field-level NLP eval (lab values, ICD-10 codes)",
            "Exp 12: fix 4 over-deny regressions → 80%+ clean",
        ]),
        (row1_r, "#f59e0b", "badge-amber", "PLANNED", "Reliability Engineering", [
            "Async pipeline: 82 → ~400 cases/hr throughput",
            "Structured output enforcement (OpenAI function calling) — eliminates schema hallucinations",
        ]),
        (row2_l, "#f59e0b", "badge-amber", "PLANNED", "Clinical Safety", [
            "Clinical safety guardrail: oncology/urgent cases → mandatory HITL",
            "PHI de-identification pipeline (HIPAA requirement)",
            "Hallucination detection: verify PA form facts trace back to source patient record",
        ]),
        (row2_r, "#333333", "badge-subtle", "FUTURE", "Scale & Compliance", [
            "Multi-payer: 4 synthetic → 50+ real payers",
            "HL7 FHIR compatibility (CMS-0057-F requirement for PA data exchange)",
            "Real patient data pipeline (de-identified EHR integration)",
        ]),
    ]

    for col, border_color, badge_cls, badge_txt, title, bullets in card_data:
        bullet_html = "".join(
            f'<div style="font-size:12px;color:#6b6b6b;line-height:1.7;'
            f'padding-left:12px;border-left:1px solid #1f1f1f;margin-bottom:8px;">{b}</div>'
            for b in bullets
        )
        with col:
            st.markdown(f"""
            <div class="card" style="border-left:3px solid {border_color};margin-bottom:16px;">
              <span class="{badge_cls} badge">{badge_txt}</span>
              <div style="font-size:14px;font-weight:700;color:#ffffff;margin-bottom:16px;letter-spacing:-0.01em;">
                {title}
              </div>
              {bullet_html}
            </div>
            """, unsafe_allow_html=True)

    st.markdown("""
    <div class="card card-amber" style="background:#0d0d0d;">
      <div style="font-size:10px;font-weight:600;letter-spacing:0.12em;
                  text-transform:uppercase;color:#f59e0b;margin-bottom:12px;">
        Current Evaluation Scope
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;">
        <div style="font-size:12px;color:#6b6b6b;line-height:1.8;">
          120 synthetic cases · 4 payers · 6 drug categories · no real patient data.
          Results reflect controlled prototype performance, not production system accuracy.
        </div>
        <div style="font-size:12px;color:#6b6b6b;line-height:1.8;">
          False Denial Rate and False Approval Rate not yet measured —
          require clinical appropriateness ground truth beyond binary label matching.
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 5 — SOURCE DATA
# ═════════════════════════════════════════════════════════════════════════════
with tab5:

    st.markdown("""
    <style>
    /* Source data download buttons — small, minimal */
    [data-testid="stDownloadButton"] button {
        background: transparent !important;
        border: 1px solid #2a2a2a !important;
        color: #6b6b6b !important;
        font-size: 11px !important;
        font-weight: 600 !important;
        letter-spacing: 0.06em !important;
        padding: 6px 14px !important;
        border-radius: 2px !important;
        transition: border-color 0.15s, color 0.15s !important;
    }
    [data-testid="stDownloadButton"] button:hover {
        border-color: #ffffff !important;
        color: #ffffff !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="padding:48px 0 32px 0;">
      <div style="font-size:32px;font-weight:800;letter-spacing:-0.02em;
                  color:#ffffff;line-height:1.2;max-width:560px;">
        Raw files behind the evaluation.
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Row 1: Patient Data ───────────────────────────────────────────────────
    r1_text, r1_btn = st.columns([9, 1])
    with r1_text:
        st.markdown("""
        <div style="padding:20px 0 18px 0;border-top:1px solid #1f1f1f;">
          <div style="font-size:13px;font-weight:600;color:#ffffff;margin-bottom:5px;">
            Patient Data
          </div>
          <div style="font-size:11px;color:#6b6b6b;line-height:1.6;">
            120 synthetic cases · diagnoses, medications, lab values, prior treatment history · no real patient data
          </div>
        </div>
        """, unsafe_allow_html=True)
    with r1_btn:
        st.markdown('<div style="padding-top:22px;"></div>', unsafe_allow_html=True)
        with open(ROOT / "data" / "patients.json", "rb") as f:
            st.download_button(
                label="↓",
                data=f.read(),
                file_name="patients.json",
                mime="application/json",
                key="dl_patients",
            )

    # ── Row 2: Insurer Rules ──────────────────────────────────────────────────
    r2_text, r2_btn = st.columns([9, 1])
    with r2_text:
        st.markdown("""
        <div style="padding:20px 0 18px 0;border-top:1px solid #1f1f1f;">
          <div style="font-size:13px;font-weight:600;color:#ffffff;margin-bottom:5px;">
            Insurer Rules
          </div>
          <div style="font-size:11px;color:#6b6b6b;line-height:1.6;">
            Manually authored payer coverage criteria · Aetna, Cigna, UnitedHealthcare, Humana · used across all 10 experiments
          </div>
        </div>
        """, unsafe_allow_html=True)
    with r2_btn:
        st.markdown('<div style="padding-top:22px;"></div>', unsafe_allow_html=True)
        with open(ROOT / "config" / "insurer_rules.json", "rb") as f:
            st.download_button(
                label="↓",
                data=f.read(),
                file_name="insurer_rules.json",
                mime="application/json",
                key="dl_insurer",
            )

    st.markdown('<div style="border-top:1px solid #1f1f1f;"></div>', unsafe_allow_html=True)

