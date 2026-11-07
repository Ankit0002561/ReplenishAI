"""
ReplenishAI: Autonomous Supply Chain & Inventory Procurement Agent
Interactive Streamlit Web Dashboard
Features:
1. Multi-SKU Portfolio Dashboard
2. Supply Chain Shock Simulator (Interactive 'What-If' Controls)
3. Dynamic Stock Burn-Down Chart (14-day horizon with Vendor Milestones)
4. Automated Critical Stockout Alerting Engine (Webhook + Mock Email Dispatcher)
5. Dual-Strategy Supplier Trade-off Matrix
6. One-Click Purchase Order (PO) Export Generator
"""

from datetime import datetime
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.database import init_db, get_all_products, get_suppliers_for_sku, get_sales_log_for_sku
from agent.orchestrator import ReplenishAIAgent, AuditReport, get_fleet_overview
from agent.formulas import calculate_dos, calculate_ltd, calculate_stockout_gap, calculate_roq, triage_risk
from agent.alerting import build_alert_payload, dispatch_webhook, format_escalation_email

# -----------------------------------------------------------------------------
# Page Configuration & Styling
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="ReplenishAI | Supply Chain Procurement Agent",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for modern enterprise UI
st.markdown("""
<style>
    /* Metric Card Styling */
    .metric-box {
        background-color: #0e1117;
        border: 1px solid #262730;
        border-radius: 8px;
        padding: 14px;
        text-align: center;
    }
    .metric-value {
        font-size: 24px;
        font-weight: 700;
        color: #f0f2f6;
    }
    .metric-label {
        font-size: 12px;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    /* Risk Badges */
    .badge-critical {
        background: linear-gradient(135deg, #e63946, #b7094c);
        color: white;
        padding: 10px 18px;
        border-radius: 8px;
        font-weight: 800;
        font-size: 18px;
        text-align: center;
        letter-spacing: 1px;
        box-shadow: 0 4px 14px rgba(230, 57, 70, 0.4);
    }
    .badge-atrisk {
        background: linear-gradient(135deg, #f77f00, #d62828);
        color: white;
        padding: 10px 18px;
        border-radius: 8px;
        font-weight: 800;
        font-size: 18px;
        text-align: center;
        letter-spacing: 1px;
        box-shadow: 0 4px 14px rgba(247, 127, 0, 0.3);
    }
    .badge-healthy {
        background: linear-gradient(135deg, #2a9d8f, #1b4332);
        color: white;
        padding: 10px 18px;
        border-radius: 8px;
        font-weight: 800;
        font-size: 18px;
        text-align: center;
        letter-spacing: 1px;
        box-shadow: 0 4px 14px rgba(42, 157, 143, 0.3);
    }
    /* Card containers */
    .card-container {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 18px;
        margin-bottom: 16px;
    }
    .trace-header {
        font-weight: 600;
        color: #58a6ff;
        font-size: 15px;
    }
    .trace-tool {
        background-color: #21262d;
        color: #79c0ff;
        padding: 2px 8px;
        border-radius: 4px;
        font-family: monospace;
        font-size: 12px;
    }
    /* PO Box */
    .po-container {
        background: linear-gradient(180deg, #161b22, #0d1117);
        border: 2px solid #238636;
        border-radius: 10px;
        padding: 22px;
        box-shadow: 0 6px 20px rgba(35, 134, 54, 0.15);
    }
    /* Alert Card */
    .alert-card {
        background: linear-gradient(180deg, #210d10, #161b22);
        border: 2px solid #da3633;
        border-radius: 10px;
        padding: 20px;
        box-shadow: 0 4px 18px rgba(218, 54, 51, 0.2);
    }
</style>
""", unsafe_allow_html=True)


# Initialize Database on first load
@st.cache_resource
def setup_database():
    init_db(force_reset=False)
    return True

setup_database()

# Session State for Alert History & Triggers
if "alert_history" not in st.session_state:
    st.session_state["alert_history"] = []
if "dispatched_alerts" not in st.session_state:
    st.session_state["dispatched_alerts"] = set()

# -----------------------------------------------------------------------------
# Sidebar Configuration & Parameters
# -----------------------------------------------------------------------------
with st.sidebar:
    st.image("https://img.icons8.com/isometric/100/shipping-container.png", width=64)
    st.title("ReplenishAI")
    st.caption("Autonomous Supply Chain Operations Agent")
    st.markdown("---")

    st.subheader("⚙️ Procurement Policy")
    target_coverage = st.slider(
        "Target Coverage (Days)",
        min_value=7,
        max_value=90,
        value=30,
        step=1,
        help="Target number of days of inventory buffer to order."
    )

    safety_stock = st.slider(
        "Safety Stock Buffer (Days)",
        min_value=0,
        max_value=30,
        value=7,
        step=1,
        help="Extra safety buffer to prevent stockout under demand spikes."
    )

    st.markdown("---")
    st.subheader("📚 Core Rules & Formulas")
    with st.expander("View Agent Formulation Rules", expanded=False):
        st.markdown("""
        **1. Days of Supply (DoS)**:
        `Available Stock / ADD`

        **2. Lead Time Demand (LTD)**:
        `ADD * Supplier Lead Time (Days)`

        **3. Stockout Gap**:
        `Available Stock - LTD`
        *(Negative = stockout deficit)*

        **4. Recommended Order Quantity (ROQ)**:
        `(ADD * (Target Days + Safety Days)) + max(0, -Stockout Gap)`

        **5. Risk Triage Matrix**:
        - 🔴 `CRITICAL`: DoS < Supplier Lead Time
        - 🟡 `AT RISK`: DoS <= Supplier Lead Time + Buffer Days
        - 🟢 `HEALTHY`: DoS > Supplier Lead Time + Buffer Days

        **6. Dual Strategy Trade-offs**:
        - **Strategy Alpha**: Cost-Optimized standard lead time
        - **Strategy Beta**: Expedited dispatch to avert stockout
        """)

    st.markdown("---")
    if st.button("🔄 Reset Database to Seeds", use_container_width=True):
        init_db(force_reset=True)
        st.session_state["alert_history"] = []
        st.session_state["dispatched_alerts"] = set()
        st.success("Database restored to fresh seed state.")
        st.rerun()


# -----------------------------------------------------------------------------
# Main Header
# -----------------------------------------------------------------------------
st.title("📦 ReplenishAI Autonomous Procurement Agent")
st.markdown("Autonomous multi-SKU inventory velocity tracking, shock simulations, burn-down analytics, and incident alerting.")

# -----------------------------------------------------------------------------
# MULTI-SKU PORTFOLIO DASHBOARD (Fleet Overview)
# -----------------------------------------------------------------------------
st.subheader("📊 Multi-SKU Portfolio Fleet Overview")

fleet_data = get_fleet_overview(buffer_days=3)

# Fleet KPI Cards
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
critical_count = sum(1 for item in fleet_data if item["risk_status"] == "CRITICAL")
at_risk_count = sum(1 for item in fleet_data if item["risk_status"] == "AT RISK")
healthy_count = sum(1 for item in fleet_data if item["risk_status"] == "HEALTHY")

with kpi1:
    st.metric("Total Monitored SKUs", len(fleet_data), "Enterprise Catalog")
with kpi2:
    st.metric("🔴 Critical Stockouts", critical_count, f"{critical_count} Imminent", delta_color="inverse")
with kpi3:
    st.metric("🟡 At Risk (Low Buffer)", at_risk_count, "Eroded Buffer", delta_color="off")
with kpi4:
    st.metric("🟢 Healthy Inventory", healthy_count, "Adequate Buffer", delta_color="normal")

def format_risk_badge(status: str) -> str:
    if status == "CRITICAL":
        return "🔴 CRITICAL"
    elif status == "AT RISK":
        return "🟡 AT RISK"
    else:
        return "🟢 HEALTHY"

table_rows = []
for item in fleet_data:
    table_rows.append({
        "SKU": item["sku"],
        "Product Name": item["product_name"],
        "Category": item["category"],
        "On-Hand Stock": f"{item['on_hand_stock']:g} units",
        "Daily Demand": f"{item['daily_demand']:.1f} u/day",
        "Days of Supply": f"{item['days_of_supply']:.2f} days",
        "Risk Status": format_risk_badge(item["risk_status"])
    })

df_fleet = pd.DataFrame(table_rows)

st.dataframe(
    df_fleet,
    use_container_width=True,
    hide_index=True,
    column_config={
        "SKU": st.column_config.TextColumn("SKU", width="small"),
        "Product Name": st.column_config.TextColumn("Product Name", width="medium"),
        "Category": st.column_config.TextColumn("Category", width="small"),
        "On-Hand Stock": st.column_config.TextColumn("On-Hand Stock", width="small"),
        "Daily Demand": st.column_config.TextColumn("Daily Demand", width="small"),
        "Days of Supply": st.column_config.TextColumn("Days of Supply", width="small"),
        "Risk Status": st.column_config.TextColumn("Risk Status", width="medium"),
    }
)

st.markdown("---")

# -----------------------------------------------------------------------------
# SKU Selector
# -----------------------------------------------------------------------------
st.subheader("🎯 Autonomous Deep Audit & Procurement Engine")

sku_list = [item["sku"] for item in fleet_data]
sku_label_map = {
    item["sku"]: f"{item['sku']} - {item['product_name']} (Stock: {item['on_hand_stock']:g} | {format_risk_badge(item['risk_status'])})"
    for item in fleet_data
}

col_sku_pick, col_audit_btn = st.columns([3, 1])

if "selected_sku" not in st.session_state:
    st.session_state["selected_sku"] = "SKU-101"

with col_sku_pick:
    selected_sku = st.selectbox(
        "Select Target SKU to Audit & Simulate:",
        options=sku_list,
        index=sku_list.index(st.session_state["selected_sku"]) if st.session_state["selected_sku"] in sku_list else 0,
        format_func=lambda s: sku_label_map[s],
        key="sku_selector"
    )
    st.session_state["selected_sku"] = selected_sku

with col_audit_btn:
    st.write("")
    st.write("")
    trigger_audit = st.button("⚡ Run Full Audit", type="primary", use_container_width=True)

# -----------------------------------------------------------------------------
# Run Base Audit
# -----------------------------------------------------------------------------
agent = ReplenishAIAgent(target_coverage_days=target_coverage, safety_stock_days=safety_stock)
base_report = agent.run_procurement_audit(selected_sku)

# -----------------------------------------------------------------------------
# FEATURE 1: SUPPLY CHAIN SHOCK SIMULATOR ("What-If" Controls)
# -----------------------------------------------------------------------------
st.write("")
st.subheader("⚡ Supply Chain Shock Simulator")
st.markdown("Simulate operational stress by injecting **Demand Spikes** and **Transit & Port Delays** in real time.")

shock_col1, shock_col2 = st.columns(2)

with shock_col1:
    demand_surge_mult = st.slider(
        "📈 Demand Surge Multiplier",
        min_value=1.0,
        max_value=3.0,
        value=1.0,
        step=0.1,
        format="%.1fx",
        help="Simulate unexpected surge in daily customer sales orders."
    )

with shock_col2:
    transit_delay_days = st.slider(
        "🚢 Transit & Port Delay",
        min_value=0,
        max_value=7,
        value=0,
        step=1,
        format="+%d days",
        help="Simulate freight disruption, customs delays, or port congestions."
    )

# Dynamic Re-computation under Shock Conditions
base_stock = base_report.current_stock
base_demand = base_report.average_daily_demand
effective_demand = round(base_demand * demand_surge_mult, 2)

alpha_info = base_report.strategy_alpha_analysis
beta_info = base_report.strategy_beta_analysis

base_alpha_lead = alpha_info["lead_time_days"]
base_beta_lead = beta_info["lead_time_days"]

effective_alpha_lead = base_alpha_lead + transit_delay_days
effective_beta_lead = base_beta_lead + transit_delay_days

effective_dos = calculate_dos(base_stock, effective_demand)
effective_ltd = calculate_ltd(effective_demand, effective_alpha_lead)
effective_gap = calculate_stockout_gap(base_stock, effective_ltd)
effective_risk = triage_risk(effective_dos, effective_alpha_lead, safety_stock_days=3)
effective_roq = calculate_roq(effective_demand, target_coverage, safety_stock, effective_gap)

# Shocked expedited metrics
effective_beta_ltd = calculate_ltd(effective_demand, effective_beta_lead)
effective_beta_gap = calculate_stockout_gap(base_stock, effective_beta_ltd)
effective_beta_roq = calculate_roq(effective_demand, target_coverage, safety_stock, effective_beta_gap)

# Status Pill for Active Shock
if demand_surge_mult > 1.0 or transit_delay_days > 0:
    st.warning(
        f"⚡ **Stress-Test Scenario Active**: Demand is **+{int((demand_surge_mult - 1.0)*100)}%** higher "
        f"({effective_demand:.1f} u/d vs baseline {base_demand:.1f} u/d), and freight transit is "
        f"**+{transit_delay_days} days delayed** (Standard delivery: {effective_alpha_lead}d vs {base_alpha_lead}d).",
        icon="⚠️"
    )

# Render Live Metrics Bar
m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns([1.5, 1.2, 1.2, 1.2, 1.2])

with m_col1:
    if effective_risk == "CRITICAL":
        st.markdown('<div class="badge-critical">🔴 CRITICAL RISK<br><span style="font-size:12px;font-weight:400;">STOCKOUT INEVITABLE</span></div>', unsafe_allow_html=True)
    elif effective_risk == "AT RISK":
        st.markdown('<div class="badge-atrisk">🟡 AT RISK<br><span style="font-size:12px;font-weight:400;">BUFFER ERODED</span></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="badge-healthy">🟢 HEALTHY STATUS<br><span style="font-size:12px;font-weight:400;">SUFFICIENT BUFFER</span></div>', unsafe_allow_html=True)

with m_col2:
    st.metric(
        label="Effective Demand",
        value=f"{effective_demand:.1f} u/d",
        delta=f"{demand_surge_mult:.1f}x Surge" if demand_surge_mult > 1.0 else "Baseline",
        delta_color="inverse" if demand_surge_mult > 1.0 else "off"
    )

with m_col3:
    st.metric(
        label="Standard Lead Time",
        value=f"{effective_alpha_lead} Days",
        delta=f"+{transit_delay_days}d Delay" if transit_delay_days > 0 else "On Schedule",
        delta_color="inverse" if transit_delay_days > 0 else "off"
    )

with m_col4:
    is_deficit = effective_dos < effective_alpha_lead
    st.metric(
        label="Days of Supply (DoS)",
        value=f"{effective_dos:.2f} Days",
        delta=f"{effective_dos - base_report.days_of_supply:+.2f}d vs Base" if (demand_surge_mult > 1.0 or transit_delay_days > 0) else "Standard",
        delta_color="inverse" if is_deficit else "normal"
    )

with m_col5:
    st.metric(
        label="Stockout Deficit Gap",
        value=f"{effective_gap:+.1f} Units",
        delta=f"{'Deficit' if effective_gap < 0 else 'Surplus'}",
        delta_color="inverse" if effective_gap < 0 else "normal"
    )

# -----------------------------------------------------------------------------
# FEATURE 2: DYNAMIC STOCK BURN-DOWN CHART (Plotly 14-Day Forward Horizon)
# -----------------------------------------------------------------------------
st.write("")
st.subheader("📉 Dynamic Stock Burn-Down Trajectory (14-Day Horizon)")

# Calculate trajectory points
days_horizon = np.linspace(0, 14, 141)
stockout_day = min(14.0, effective_dos)

# Projected stock and deficit
projected_stock = np.maximum(0.0, base_stock - (effective_demand * days_horizon))
backorder_deficit = np.where(days_horizon > stockout_day, -(effective_demand * (days_horizon - stockout_day)), 0.0)

# Outage Metrics
outage_duration_days = max(0.0, effective_alpha_lead - stockout_day) if stockout_day < effective_alpha_lead else 0.0
outage_hours = outage_duration_days * 24.0
lost_demand_units = max(0.0, -effective_gap)

# Render Metric Callout Banner
b1, b2, b3 = st.columns(3)
with b1:
    st.metric("🚨 Stockout Occurs At", f"Day {stockout_day:.2f}", f"In ~{stockout_day*24:.0f} Hours" if stockout_day < 14 else "No Stockout")
with b2:
    st.metric("⏳ Total Stockout Duration", f"{outage_duration_days:.1f} Days", f"{outage_hours:.0f} Total Hours of Zero Stock", delta_color="inverse" if outage_duration_days > 0 else "normal")
with b3:
    st.metric("📉 Lost Demand Exposure", f"{lost_demand_units:.1f} Units", "Unfulfilled customer orders before Standard arrival", delta_color="inverse" if lost_demand_units > 0 else "normal")

# Create Plotly Burn-Down Figure
fig = go.Figure()

# 1. On-Hand Inventory Area (Positive)
fig.add_trace(go.Scatter(
    x=days_horizon,
    y=projected_stock,
    mode='lines',
    name='Projected Available Stock (Units)',
    line=dict(color='#2ea043', width=3),
    fill='tozeroy',
    fillcolor='rgba(46, 160, 67, 0.18)',
    hovertemplate='Day %{x:.1f}: <b>%{y:.1f} units available</b><extra></extra>'
))

# 2. Backordered Cumulative Deficit (Negative)
fig.add_trace(go.Scatter(
    x=days_horizon,
    y=backorder_deficit,
    mode='lines',
    name='Cumulative Backorder Deficit (Units)',
    line=dict(color='#f85149', width=3, dash='dash'),
    fill='tozeroy',
    fillcolor='rgba(248, 81, 73, 0.22)',
    hovertemplate='Day %{x:.1f}: <b>%{y:.1f} units backordered deficit</b><extra></extra>'
))

# Zero Baseline Line
fig.add_hline(y=0, line_color="#8b949e", line_width=1.5)

# Milestone: Vendor A (Expedited) Arrival
fig.add_vline(
    x=effective_beta_lead,
    line_dash="dot",
    line_color="#e3b341",
    line_width=2.5,
    annotation_text=f"✈️ Vendor A (Expedited: Day {effective_beta_lead})",
    annotation_position="top left",
    annotation_font_color="#e3b341",
    annotation_font_size=12
)

# Milestone: Vendor B (Standard) Arrival
fig.add_vline(
    x=effective_alpha_lead,
    line_dash="dash",
    line_color="#a371f7",
    line_width=2.5,
    annotation_text=f"🚚 Vendor B (Standard: Day {effective_alpha_lead})",
    annotation_position="top right",
    annotation_font_color="#a371f7",
    annotation_font_size=12
)

# Vulnerability Shaded Window
if stockout_day < effective_alpha_lead:
    fig.add_vrect(
        x0=stockout_day,
        x1=min(14.0, effective_alpha_lead),
        fillcolor="#da3633",
        opacity=0.12,
        layer="below",
        line_width=0,
        annotation_text="⚠️ CRITICAL STOCKOUT GAP",
        annotation_position="bottom left",
        annotation_font_color="#f85149",
        annotation_font_size=11
    )

fig.update_layout(
    height=420,
    margin=dict(l=20, r=20, t=35, b=20),
    template="plotly_dark",
    paper_bgcolor="#0e1117",
    plot_bgcolor="#161b22",
    xaxis=dict(
        title="Forward Timeline (Days)",
        range=[0, 14],
        dtick=1,
        gridcolor="#21262d"
    ),
    yaxis=dict(
        title="Inventory Units On-Hand / Deficit",
        gridcolor="#21262d"
    ),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1
    )
)

st.plotly_chart(fig, use_container_width=True)

# -----------------------------------------------------------------------------
# FEATURE 3: AUTOMATED CRITICAL STOCKOUT ALERTING ENGINE (Webhook & Email)
# -----------------------------------------------------------------------------
st.write("")
st.subheader("🚨 Automated Incident Alerting Engine (Webhook + Mock Email)")

with st.expander("⚙️ Alert Routing & Incident Dispatch Management", expanded=(effective_risk == "CRITICAL")):
    st.markdown("Configure autonomous alerting endpoints to trigger instantaneous Webhook `POST` payloads and manager escalation emails on **CRITICAL_P0** stockout detection.")

    c_cfg1, c_cfg2 = st.columns(2)
    with c_cfg1:
        webhook_url_input = st.text_input(
            "Webhook Target Endpoint",
            value="https://webhook.site/demo-replenish-alerts",
            help="HTTP POST webhook endpoint (e.g., Slack, Discord, PagerDuty, or Webhook.site test route)."
        )
    with c_cfg2:
        escalation_email_input = st.text_input(
            "Manager Escalation Email",
            value="procurement-alerts@company.internal",
            help="Designated recipient for high-priority stockout escalation alerts."
        )

    c_tog, c_btn = st.columns([2, 1])
    with c_tog:
        auto_dispatch_enabled = st.checkbox(
            "⚡ Auto-dispatch webhook on CRITICAL stockout detection",
            value=True,
            help="Automatically sends webhook notification as soon as Days of Supply falls below lead time."
        )

    # Build standardized alert payload matching exact user specification
    alert_payload = build_alert_payload(
        sku=selected_sku,
        product_name=base_report.product_name,
        on_hand_stock=base_stock,
        effective_daily_demand=effective_demand,
        days_of_supply=effective_dos,
        standard_lead_time_days=effective_alpha_lead,
        unfulfilled_demand_units=lost_demand_units,
        preferred_vendor=beta_info["supplier_name"],
        emergency_order_qty=lost_demand_units if lost_demand_units > 0 else 30.0,
        bulk_followup_qty=effective_beta_roq
    )

    with c_btn:
        st.write("")
        can_dispatch = (effective_risk == "CRITICAL")
        manual_dispatch = st.button(
            "🚨 Dispatch Emergency Alert Now",
            type="primary" if can_dispatch else "secondary",
            disabled=not can_dispatch,
            use_container_width=True,
            help="Manually broadcast emergency stockout alert to webhook and email endpoints."
        )

    # Handle Automatic or Manual Trigger
    dispatch_trigger = False
    trigger_source = "Manual Trigger"

    if manual_dispatch and can_dispatch:
        dispatch_trigger = True
        trigger_source = "Manual Operator Dispatch"
    elif auto_dispatch_enabled and effective_risk == "CRITICAL":
        alert_signature = f"{selected_sku}-{effective_dos}-{effective_alpha_lead}"
        if alert_signature not in st.session_state["dispatched_alerts"]:
            dispatch_trigger = True
            trigger_source = "Autonomous System Detection"
            st.session_state["dispatched_alerts"].add(alert_signature)

    if dispatch_trigger:
        # 1. Dispatch Webhook
        wh_result = dispatch_webhook(webhook_url_input, alert_payload)
        # 2. Format Escalation Email
        email_result = format_escalation_email(escalation_email_input, alert_payload)

        # Log into history
        st.session_state["alert_history"].insert(0, {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "trigger": trigger_source,
            "sku": selected_sku,
            "severity": "CRITICAL_P0",
            "webhook_status": wh_result.get("status", "unknown").upper(),
            "webhook_msg": wh_result.get("message", ""),
            "email_status": "SENT",
            "email_recipient": escalation_email_input,
            "payload": alert_payload,
            "email_body": email_result.get("body", "")
        })

    # Display Active Alerts if any
    if effective_risk == "CRITICAL":
        st.markdown(f"""
        <div class="alert-card">
            <h4 style="margin:0 0 8px 0; color:#f85149;">🚨 INCIDENT ACTIVE: CRITICAL_P0 STOCKOUT DETECTED</h4>
            <p style="margin:0; color:#c9d1d9; font-size:14px;">
                <strong>SKU:</strong> {selected_sku} ({base_report.product_name}) |
                <strong>DoS:</strong> {effective_dos:.1f} Days |
                <strong>Lead Time:</strong> {effective_alpha_lead} Days |
                <strong>Lost Demand Exposure:</strong> {lost_demand_units:.0f} units
            </p>
        </div>
        """, unsafe_allow_html=True)
        st.write("")

    # Display Alert History and Payload Inspector
    col_wh_payload, col_email_view = st.columns(2)
    with col_wh_payload:
        st.markdown("**Standardized Webhook JSON Payload Schema (`POST`):**")
        st.json(alert_payload)

    with col_email_view:
        st.markdown("**Formatted Escalation Email (`procurement-alerts`):**")
        sample_email = format_escalation_email(escalation_email_input, alert_payload)
        st.code(sample_email["body"], language="text")

    # Recent Dispatch Log
    if st.session_state["alert_history"]:
        st.write("")
        st.markdown("**Recent Incident Notification Log:**")
        df_log = pd.DataFrame([
            {
                "Timestamp": h["timestamp"],
                "Trigger Source": h["trigger"],
                "SKU": h["sku"],
                "Severity": h["severity"],
                "Webhook Dispatch": h["webhook_status"],
                "Email Dispatch": f"SENT ({h['email_recipient']})"
            }
            for h in st.session_state["alert_history"][:5]
        ])
        st.dataframe(df_log, use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# Section 4: Agent Reasoning Trace & Reorder Deductions
# -----------------------------------------------------------------------------
st.write("")
st.subheader("4. Autonomous Agent Reasoning & Mathematical Deductions")

with st.expander("🔍 Inspect Agent Step-by-Step Tool Trace (5 Steps)", expanded=False):
    for trace in base_report.traces:
        st.markdown(f"""
        <div class="card-container">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <span class="trace-header">Step {trace.step_number}: {trace.step_name}</span>
                <span class="trace-tool">{trace.tool_name}()</span>
            </div>
            <p style="margin:4px 0; color:#c9d1d9; font-size:14px;"><strong>🧠 Agent Thought:</strong> {trace.agent_thought}</p>
            <p style="margin:4px 0; color:#7ee787; font-size:14px; font-family:monospace; white-space:pre-wrap;"><strong>📐 Mathematical Deduction:</strong><br>{trace.mathematical_deduction}</p>
        </div>
        """, unsafe_allow_html=True)
        with st.expander(f"View Raw Tool Arguments & Output (Step {trace.step_number})", expanded=False):
            st.json({"tool_args": trace.tool_args, "tool_output": trace.tool_output})

# -----------------------------------------------------------------------------
# Section 5: Dual-Strategy Supplier Trade-off Matrix
# -----------------------------------------------------------------------------
st.write("")
st.subheader("5. Dual-Strategy Supplier Trade-off Matrix")

# Calculate landed costs with shock values
alpha_subtotal = round(effective_roq * alpha_info["unit_price"], 2)
alpha_landed = round(alpha_subtotal + alpha_info["shipping_cost"], 2)
alpha_unit_eff = round(alpha_landed / effective_roq, 2)

beta_subtotal = round(effective_beta_roq * beta_info["unit_price"], 2)
beta_landed = round(beta_subtotal + beta_info["shipping_cost"], 2)
beta_unit_eff = round(beta_landed / effective_beta_roq, 2)

beta_gap_deficit = max(0.0, -effective_beta_gap)
alpha_gap_deficit = max(0.0, -effective_gap)
units_saved = max(0.0, alpha_gap_deficit - beta_gap_deficit)
days_saved = effective_alpha_lead - effective_beta_lead
cost_diff = round(beta_landed - alpha_landed, 2)

tradeoff_table = {
    "Operational Metric": [
        "Supplier Partner",
        "Strategy Profile",
        "Effective Lead Time (Transit Shocked)",
        "Lead Time Demand (LTD)",
        "Stockout Gap (Stock - LTD)",
        "Expected Stockout Duration",
        "Unfulfilled Demand (Lost Units)",
        "Recommended Order Quantity (ROQ)",
        "Unit Price",
        "Shipping & Freight Cost",
        "Total Landed Cost",
        "Effective Landed Cost / Unit"
    ],
    "Strategy Alpha (Cost-Optimized)": [
        alpha_info["supplier_name"],
        "Lowest Landed Cost / Standard Freight",
        f"{effective_alpha_lead} Days",
        f"{effective_ltd:.1f} Units",
        f"{effective_gap:+.1f} Units",
        f"{outage_duration_days:.1f} Days Out of Stock",
        f"{alpha_gap_deficit:.1f} Units Lost",
        f"{effective_roq:.0f} Units",
        f"${alpha_info['unit_price']:.2f}",
        f"${alpha_info['shipping_cost']:.2f}",
        f"${alpha_landed:,.2f}",
        f"${alpha_unit_eff:.2f}"
    ],
    "Strategy Beta (Expedited / Speed)": [
        beta_info["supplier_name"],
        "Priority Dispatch / Fast Recovery",
        f"{effective_beta_lead} Days",
        f"{effective_beta_ltd:.1f} Units",
        f"{effective_beta_gap:+.1f} Units",
        f"{max(0.0, effective_beta_lead - stockout_day):.1f} Days Out of Stock",
        f"{beta_gap_deficit:.1f} Units Lost",
        f"{effective_beta_roq:.0f} Units",
        f"${beta_info['unit_price']:.2f}",
        f"${beta_info['shipping_cost']:.2f}",
        f"${beta_landed:,.2f}",
        f"${beta_unit_eff:.2f}"
    ]
}

df_trade = pd.DataFrame(tradeoff_table)
st.dataframe(df_trade, use_container_width=True, hide_index=True)

if units_saved > 0:
    st.info(
        f"💡 **Strategic Trade-off Analysis**: Strategy Beta delivers **{days_saved} days faster**, preventing "
        f"**{units_saved:.0f} unfulfilled customer orders** for an expedited cost delta of **${cost_diff:,.2f}**."
    )
else:
    st.success(
        f"💡 **Strategic Trade-off Analysis**: Strategy Alpha fulfills inventory without lead-time stockout, saving "
        f"**${abs(cost_diff):,.2f}** over expedited freight."
    )

# -----------------------------------------------------------------------------
# Section 6: Actionable Purchase Order Recommendation & One-Click Export
# -----------------------------------------------------------------------------
st.write("")
st.subheader("6. Actionable Purchase Order Recommendation & One-Click Export")

# Select strategy based on shocked risk
if effective_risk == "CRITICAL" and units_saved > 0:
    chosen_supplier = beta_info
    chosen_strategy = "Strategy Beta (Expedited)"
    chosen_order_qty = effective_beta_roq
    chosen_landed = beta_landed
    contract_type = "EXPEDITED"
    rec_rationale = (
        f"CRITICAL STOCKOUT IMMINENT: Current Days of Supply ({effective_dos:.1f} days) is less than standard supplier lead time "
        f"({effective_alpha_lead} days). Strategy Alpha causes {outage_duration_days:.1f} days of complete stockout ({alpha_gap_deficit:.0f} lost orders). "
        f"Recommending expedited Strategy Beta ({beta_info['supplier_name']}): goods arrive in {effective_beta_lead} days, preventing "
        f"{units_saved:.0f} lost orders. The ${cost_diff:.2f} expedite premium is justified."
    )
else:
    chosen_supplier = alpha_info
    chosen_strategy = "Strategy Alpha (Cost-Optimized)"
    chosen_order_qty = effective_roq
    chosen_landed = alpha_landed
    contract_type = "STANDARD"
    rec_rationale = (
        f"Cost-optimized Strategy Alpha selected. Standard lead time ({effective_alpha_lead} days) provides the lowest landed cost "
        f"(${alpha_unit_eff:.2f}/unit) with minimal operational stockout impact."
    )

po_number = f"PO-{datetime.now().strftime('%Y%m%d')}-{selected_sku}-AUTO"
vendor_id = chosen_supplier.get("supplier_id") or ("SUP-VELOCITY" if "Beta" in chosen_strategy else "SUP-APEX")
vendor_name = chosen_supplier.get("supplier_name", "Primary Logistics Vendor")
vendor_contact = chosen_supplier.get("contact_email", "orders@supplychain.internal")
unit_price = float(chosen_supplier.get("unit_price", 0.0))
shipping_cost = float(chosen_supplier.get("shipping_cost", 0.0))
committed_lead = int(chosen_supplier.get("lead_time_days", 5)) + transit_delay_days
expected_arrival_date = (datetime.now() + pd.Timedelta(days=committed_lead)).strftime("%Y-%m-%d")

# Complete structured PO schema for Feature 2
po_payload = {
    "purchase_order": {
        "po_number": po_number,
        "created_at": datetime.now().isoformat(),
        "status": "APPROVED_DRAFT",
        "item_details": {
            "sku": selected_sku,
            "product_name": base_report.product_name,
            "units_ordered": int(round(chosen_order_qty))
        },
        "vendor_details": {
            "vendor_id": vendor_id,
            "vendor_name": vendor_name,
            "contract_type": contract_type,
            "unit_price_usd": unit_price,
            "shipping_fee_usd": shipping_cost,
            "total_landed_cost_usd": float(chosen_landed),
            "committed_lead_time_days": committed_lead,
            "expected_arrival_date": expected_arrival_date
        },
        "procurement_rationale": rec_rationale,
        "authorizing_agent": "ReplenishAI Autonomous Agent v1.0"
    }
}

st.markdown(f"""
<div class="po-container">
    <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #30363d; padding-bottom:12px; margin-bottom:16px;">
        <div>
            <h3 style="margin:0; color:#f0f2f6;">PURCHASE ORDER: <span style="color:#58a6ff;">{po_number}</span></h3>
            <span style="color:#8b949e; font-size:13px;">Selected Strategy: <strong>{chosen_strategy}</strong> | Contract: <strong>{contract_type}</strong></span>
        </div>
        <div>
            <span style="background-color:#238636; color:white; padding:6px 14px; border-radius:20px; font-weight:700; font-size:13px;">
                ● APPROVED_DRAFT
            </span>
        </div>
    </div>
    <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:16px; margin-bottom:16px;">
        <div>
            <span style="color:#8b949e; font-size:12px;">VENDOR / SUPPLIER</span><br>
            <strong>{vendor_name}</strong><br>
            <span style="color:#7ee787; font-size:12px;">ID: {vendor_id}</span>
        </div>
        <div>
            <span style="color:#8b949e; font-size:12px;">ORDER QUANTITY</span><br>
            <strong style="font-size:18px;">{chosen_order_qty:.0f} units</strong><br>
            <span style="color:#8b949e; font-size:12px;">Expected Arrival: {expected_arrival_date}</span>
        </div>
        <div>
            <span style="color:#8b949e; font-size:12px;">PRICING & FREIGHT</span><br>
            <strong>${unit_price:.2f} / unit</strong><br>
            <span style="color:#8b949e; font-size:12px;">Freight: ${shipping_cost:.2f}</span>
        </div>
        <div>
            <span style="color:#8b949e; font-size:12px;">TOTAL LANDED COMMITMENT</span><br>
            <strong style="font-size:22px; color:#58a6ff;">${chosen_landed:,.2f}</strong>
        </div>
    </div>
    <div style="background-color:#0d1117; border-left:4px solid #58a6ff; padding:12px 16px; border-radius:4px; margin-bottom:16px;">
        <strong style="color:#58a6ff;">Procurement Rationale:</strong><br>
        <span style="color:#c9d1d9; font-size:14px; line-height:1.5;">{rec_rationale}</span>
    </div>
    <div style="color:#8b949e; font-size:12px; text-align:right;">
        Authorizing Agent: <strong>ReplenishAI Autonomous Agent v1.0</strong>
    </div>
</div>
""", unsafe_allow_html=True)

# ONE-CLICK PO EXPORT BUTTON
st.write("")
col_po_btn, col_json_preview = st.columns([1, 3])

po_export_str = json.dumps(po_payload, indent=2)

with col_po_btn:
    st.download_button(
        label="📥 Export Purchase Order",
        data=po_export_str,
        file_name=f"{po_number}.json",
        mime="application/json",
        type="primary",
        use_container_width=True,
        help="One-click download of the complete structured Purchase Order JSON payload."
    )

with col_json_preview:
    with st.expander("👁️ View Downloadable Purchase Order JSON Payload", expanded=False):
        st.json(po_payload)

# -----------------------------------------------------------------------------
# Section 7: Live Database & 30-Day Historical Sales Explorer
# -----------------------------------------------------------------------------
st.write("")
st.write("")
st.subheader("7. Live Inventory & Demand History Explorer")

tab_prod, tab_sup, tab_sales = st.tabs(["📋 Products Catalog", "🚚 Supplier Directory", "📈 30-Day Demand Log"])

with tab_prod:
    df_prods = pd.DataFrame(get_all_products())
    st.dataframe(df_prods, use_container_width=True, hide_index=True)

with tab_sup:
    df_sups = pd.DataFrame(get_suppliers_for_sku(selected_sku))
    st.dataframe(df_sups, use_container_width=True, hide_index=True)

with tab_sales:
    sales_data = get_sales_log_for_sku(selected_sku, days=30)
    df_sales = pd.DataFrame(sales_data)
    df_sales = df_sales.rename(columns={"day_offset": "Day", "units_sold": "Units Sold"})
    st.line_chart(df_sales.set_index("Day")["Units Sold"])
    st.dataframe(df_sales.T, use_container_width=True)
