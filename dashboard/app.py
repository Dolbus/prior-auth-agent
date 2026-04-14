import streamlit as st
import pandas as pd
import json
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
import os
import sys

# Add parent directory to path so we can import from our modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from persistence.supabase_client import read_case_results, read_audit_log

# Page Config
st.set_page_config(
    page_title="AgentOps: Prior Auth Dashboard",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
def load_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
        }
        
        /* Main Container */
        .main .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }

        /* Metric Cards */
        div[data-testid="metric-container"] {
            background-color: #1e1e24;
            border: 1px solid #2d2d3a;
            padding: 1.25rem 1rem;
            border-radius: 0.75rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            transition: transform 0.2s ease-in-out, box-shadow 0.2s ease-in-out;
        }
        div[data-testid="metric-container"]:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
            border-color: #4f4f6a;
        }
        div[data-testid="metric-container"] > div > div > div > div > p {
            font-size: 1.6rem !important;
            font-weight: 700 !important;
            color: #f8f9fa !important;
        }
        div[data-testid="metric-container"] > div > div[data-testid="stMetricLabel"] > div > p {
            font-size: 0.85rem !important;
            font-weight: 600 !important;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #aeb1b5 !important;
        }

        /* Status Pills */
        .status-pill {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.8rem;
            font-weight: 600;
            text-align: center;
        }
        .status-approved { background-color: rgba(16, 185, 129, 0.1); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.2); }
        .status-denied { background-color: rgba(239, 68, 68, 0.1); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.2); }
        .status-info { background-color: rgba(245, 158, 11, 0.1); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.2); }
        
        /* Agent Timeline formatting */
        .timeline-agent {
            background-color: #1a1a24;
            border-left: 3px solid #6366f1;
            padding: 10px 15px;
            margin-bottom: 10px;
            border-radius: 4px;
        }
        
        /* DataFrame custom styling */
        .stDataFrame {
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
        }
        
        /* Headers */
        h1, h2, h3 {
            color: #f3f4f6;
            font-weight: 700;
            letter-spacing: -0.025em;
        }
        h1 { font-size: 2.25rem; margin-bottom: 0.5rem; }
        
        .gradient-text {
            background-clip: text;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-image: linear-gradient(90deg, #8b5cf6, #3b82f6);
        }
        </style>
    """, unsafe_allow_html=True)

# Fetch Data
@st.cache_data(ttl=5) # Refresh every 5 seconds 
def get_data():
    cases = read_case_results(limit=500)
    
    # If no cases are present yet
    if not cases:
        return pd.DataFrame(), pd.DataFrame()
        
    df_cases = pd.DataFrame(cases)
    
    # Format created_at to proper datetime
    if 'created_at' in df_cases.columns:
        df_cases['created_at'] = pd.to_datetime(df_cases['created_at'])
        
    # Get audit logs for the cases
    all_audits = []
    # (In a real app, you'd fetch audits efficiently. Here we fetch the latest general audits and join)
    audits = read_audit_log(limit=1000)
    df_audits = pd.DataFrame(audits) if audits else pd.DataFrame()
    if not df_audits.empty and 'created_at' in df_audits.columns:
        df_audits['created_at'] = pd.to_datetime(df_audits['created_at'])
        
    return df_cases, df_audits

# Helpers
def get_status_html(status):
    if status.upper() == "APPROVED":
        return f'<span class="status-pill status-approved">APPROVED</span>'
    elif status.upper() == "DENIED":
        return f'<span class="status-pill status-denied">DENIED</span>'
    else:
        return f'<span class="status-pill status-info">NEEDS MORE INFO</span>'

def render_dashboard():
    # Load custom CSS
    load_css()
    
    st.markdown('<h1 style="margin-bottom:0;">AgentOps <span class="gradient-text">Prior Auth Intelligence</span> Dashboard</h1>', unsafe_allow_html=True)
    st.markdown('<p style="color: #9ca3af; margin-bottom: 2rem;">Real-time observability, evaluation, and operational metrics for the multi-agent Prior Authorization workflow.</p>', unsafe_allow_html=True)

    df_cases, df_audits = get_data()

    if df_cases.empty:
        st.info("No cases have been processed yet. Run `python main.py` to generate data.")
        return

    # --- TOP LEVEL KPIs ---
    st.markdown("### Top-Level Operations Metrics")
    kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)
    
    total_cases = len(df_cases)
    avg_duration = df_cases['duration_sec'].mean()
    total_cost = df_cases['cost_usd'].sum()
    avg_accuracy = df_cases['factual_accuracy'].mean() * 100
    approval_rate = (len(df_cases[df_cases['pa_decision'] == 'APPROVED']) / total_cases) * 100 if total_cases else 0
    exit_rate = (len(df_cases[df_cases['pa_required'] == False]) / total_cases) * 100 if 'pa_required' in df_cases and total_cases else 0

    kpi1.metric("Total Cases Processed", f"{total_cases}")
    kpi2.metric("Eligibility Exit Rate", f"{exit_rate:.1f}%")
    kpi3.metric("Avg Workflow Duration", f"{avg_duration:.1f}s")
    kpi4.metric("Total API Cost", f"${total_cost:.4f}")
    kpi5.metric("Agent Factual Accuracy", f"{avg_accuracy:.1f}%")
    kpi6.metric("Auth Approval Rate", f"{approval_rate:.1f}%")
    
    st.markdown("<br>", unsafe_allow_html=True)

    # --- OBSERVABILITY CHARTS ---
    col1, col2 = st.columns([1, 1], gap="large")
    
    with col1:
        st.markdown("### Agent Latency Distribution")
        if not df_audits.empty:
            # Filter just the generating agents (not validators)
            active_agents = df_audits[df_audits['step_type'] == 'agent']
            if not active_agents.empty:
                hover_data = ["retry_count"] if "retry_count" in active_agents.columns else []
                fig = px.box(active_agents, x="agent_name", y="duration_sec", 
                             color="agent_name", color_discrete_sequence=px.colors.qualitative.Pastel,
                             hover_data=hover_data)
                fig.update_layout(
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    font_color='#e5e7eb',
                    margin=dict(l=0, r=0, t=10, b=0),
                    showlegend=False
                )
                fig.update_yaxes(title="Seconds", showgrid=True, gridcolor='#374151')
                fig.update_xaxes(title="")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Insufficient agent logs for latency chart.")
    
    with col2:
        st.markdown("### Token Cost per Case")
        fig2 = px.bar(df_cases.sort_values('created_at'), x=df_cases.index, y='cost_usd',
                      color='pa_decision',
                      color_discrete_map={'APPROVED': '#10b981', 'DENIED': '#ef4444', 'NEEDS_MORE_INFO': '#f59e0b'})
        fig2.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font_color='#e5e7eb',
            margin=dict(l=0, r=0, t=10, b=0),
            legend_title="Decision",
            xaxis_title="Case ID",
            yaxis_title="Cost ($ USD)"
        )
        st.plotly_chart(fig2, use_container_width=True)

    # --- CASE LOGS ---
    st.markdown("### Recent Submissions")
    
    # Create an interactive table using st.dataframe with formatting
    cols = ['id', 'created_at', 'patient_name', 'treatment', 'pa_decision', 'duration_sec', 'cost_usd']
    if 'escalated' in df_cases.columns: cols.append('escalated')
    if 'payer_feedback' in df_cases.columns: cols.append('payer_feedback')
    
    display_df = df_cases[cols].copy()
    display_df['created_at'] = display_df['created_at'].dt.strftime('%Y-%m-%d %H:%M:%S')
    display_df['duration_sec'] = display_df['duration_sec'].apply(lambda x: f"{x:.1f}s")
    display_df['cost_usd'] = display_df['cost_usd'].apply(lambda x: f"${x:.4f}")
    if 'escalated' in display_df.columns:
        display_df['escalated'] = display_df['escalated'].apply(lambda x: "🚨 YES" if x else "NO")
    display_df = display_df.sort_values('created_at', ascending=False)
    
    # Display table
    config = {
        "id": st.column_config.TextColumn("Case ID", width="medium"),
        "created_at": "Timestamp",
        "patient_name": "Patient",
        "treatment": "Treatment",
        "pa_decision": "Decision",
        "duration_sec": "Latency",
        "cost_usd": "Token Cost",
    }
    if 'escalated' in display_df.columns: config['escalated'] = "Escalated"
    if 'payer_feedback' in display_df.columns: config['payer_feedback'] = "Payer Feedback"

    st.dataframe(
        display_df,
        column_config=config,
        hide_index=True,
        use_container_width=True
    )

    # --- DRILL DOWN ---
    st.markdown("---")
    st.markdown("## 🔎 Case Deep Dive & Tracing")
    
    case_options = {f"{row['patient_name']} - {row['treatment']} ({str(row['id']).split('-')[0]})": row['id'] 
                    for idx, row in df_cases.iterrows()}
    
    selected_label = st.selectbox("Select a case to inspect workflow execution:", list(case_options.keys()))
    selected_case_id = case_options[selected_label]
    
    case_data = df_cases[df_cases['id'] == selected_case_id].iloc[0]
    case_audits = df_audits[df_audits['case_id'] == selected_case_id].sort_values('created_at') if not df_audits.empty else pd.DataFrame()
    
    detail_col1, detail_col2 = st.columns([1, 1], gap="large")
    
    with detail_col1:
        st.markdown(f"### Supervisor Audit Log")
        st.markdown(f"Status: {get_status_html(case_data['pa_decision'])}", unsafe_allow_html=True)
        st.markdown(f"**Patient:** {case_data['patient_name']} &nbsp;|&nbsp; **Duration:** {case_data['duration_sec']:.1f}s")
        st.markdown("<br>", unsafe_allow_html=True)
        
        if not case_audits.empty:
            for _, audit in case_audits.iterrows():
                agent = audit['agent_name'].replace('_', ' ').title()
                emoji_map = {
                    "Research": "🔍", "Rules Checker": "📋", "Writer": "📝", 
                    "Supervisor Validate Research": "🛡️", "Supervisor Validate Rules": "🛡️", 
                    "Human Review": "🧑‍⚕️", "Supervisor Final Validate": "✅"
                }
                emoji = emoji_map.get(agent, "🤖")
                notes = audit['notes'] if pd.notna(audit['notes']) else "Completed execution."
                
                st.markdown(f"""
                <div class="timeline-agent">
                    <div style="font-weight:600; color:#e2e8f0; margin-bottom:4px;">{emoji} {agent} <span style="float:right; font-weight:400; color:#9ca3af; font-size:0.85em;">{audit['duration_sec']:.2f}s</span></div>
                    <div style="font-size:0.9em; color:#cbd5e1;">{notes}</div>
                    <div style="font-size:0.8em; color:#6b7280; margin-top:6px;">Tokens: {audit['prompt_tokens']}P / {audit['completion_tokens']}C</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.warning("No audit logs found for this case.")
            
    with detail_col2:
        st.markdown("### Generated PA Document")
        writer_output = case_data.get('writer_output', "No PA document generated.")
        if pd.notna(writer_output) and writer_output:
            st.text_area("Form Draft", value=writer_output, height=600, disabled=True)
        else:
            st.info("No writer output available.")

if __name__ == "__main__":
    render_dashboard()
