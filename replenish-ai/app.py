"""
ReplenishAI: Autonomous Supply Chain & Inventory Procurement Agent
Interactive Streamlit Web Dashboard
"""

import streamlit as st
import pandas as pd
import json
from pathlib import Path
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.database import init_db, get_all_products, get_suppliers_for_sku, get_sales_log_for_sku
from agent.orchestrator import ReplenishAIAgent, AuditReport

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
        padding: 16px;
        text-align: center;
    }
    .metric-value {
        font-size: 26px;
        font-weight: 700;
        color: #f0f2f6;
    }
    .metric-label {
        font-size: 13px;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    /* Risk Badges */
    .badge-critical {
        background: linear-gradient(135deg, #e63946, #b7094c);
        color: white;
        padding: 12px 20px;
        border-radius: 8px;
        font-weight: 800;
        font-size: 20px;
        text-align: center;
        letter-spacing: 1px;
        box-shadow: 0 4px 14px rgba(230, 57, 70, 0.4);
    }
    .badge-high {
        background: linear-gradient(135deg, #f77f00, #d62828);
        color: white;
        padding: 12px 20px;
        border-radius: 8px;
        font-weight: 800;
        font-size: 20px;
        text-align: center;
        letter-spacing: 1px;
        box-shadow: 0 4px 14px rgba(247, 127, 0, 0.3);
    }
    .badge-safe {
        background: linear-gradient(135deg, #2a9d8f, #1b4332);
        color: white;
        padding: 12px 20px;
        border-radius: 8px;
        font-weight: 800;
        font-size: 20px;
        text-align: center;
        letter-spacing: 1px;
        box-shadow: 0 4px 14px rgba(42, 157, 143, 0.3);
    }
    /* Trace Stepper */
    .trace-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 12px;
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
        padding: 24px;
        box-shadow: 0 6px 20px rgba(35, 134, 54, 0.15);
    }
</style>
""", unsafe_allow_html=True)


# Initialize Database on first load
@st.cache_resource
def setup_database():
    init_db()
    return True

setup_database()

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

        **5. Risk Triage**:
        - `CRITICAL`: DoS < Supplier Lead Time
        - `HIGH`: DoS <= Supplier Lead Time + Safety Days
        - `SAFE`: DoS > Supplier Lead Time + Safety Days

        **6. Dual Trade-off**:
        - Strategy Alpha: Cost-Optimized standard lead time
        - Strategy Beta: Expedited delivery to avert stockout
        """)

    st.markdown("---")
    if st.button("🔄 Reset Mock Database", use_container_width=True):
        init_db(force_reset=True)
        st.success("Database restored to seed state.")
        st.rerun()


# -----------------------------------------------------------------------------
# Main Header
# -----------------------------------------------------------------------------
st.title("📦 ReplenishAI Autonomous Procurement Agent")
st.markdown("Simulating autonomous multi-step reasoning, velocity analysis, risk triage, and supplier trade-offs to eliminate supply chain stockouts.")

# SKU Selector
products = get_all_products()
sku_options = {
    f"{p['sku']} - {p['name']} (On-hand: {p['available_stock']:g} units)": p["sku"]
    for p in products
}

col_sku, col_btn = st.columns([3, 1])
with col_sku:
    selected_label = st.selectbox("Select Target Product SKU:", list(sku_options.keys()), index=0)
    selected_sku = sku_options[selected_label]

with col_btn:
    st.write("") # Spacer
    st.write("")
    run_audit = st.button("⚡ Run Procurement Audit", type="primary", use_container_width=True)

# -----------------------------------------------------------------------------
# Agent Execution & State
# -----------------------------------------------------------------------------
if "audit_report" not in st.session_state or run_audit or st.session_state.get("last_sku") != selected_sku:
    agent = ReplenishAIAgent(target_coverage_days=target_coverage, safety_stock_days=safety_stock)
    report = agent.run_procurement_audit(selected_sku)
    st.session_state["audit_report"] = report
    st.session_state["last_sku"] = selected_sku
else:
    report = st.session_state["audit_report"]

st.markdown("---")

# -----------------------------------------------------------------------------
# Inventory Health & Risk Triage
# -----------------------------------------------------------------------------
st.subheader("1. Inventory Health & Risk Triage")

m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns([1.5, 1.2, 1.2, 1.2, 1.2])

with m_col1:
    risk = report.overall_risk
    if risk == "CRITICAL":
        st.markdown('<div class="badge-critical">CRITICAL RISK<br><span style="font-size:12px;font-weight:400;">STOCKOUT INEVITABLE</span></div>', unsafe_allow_html=True)
    elif risk == "HIGH":
        st.markdown('<div class="badge-high">HIGH RISK<br><span style="font-size:12px;font-weight:400;">BUFFER ERODED</span></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="badge-safe">SAFE STATUS<br><span style="font-size:12px;font-weight:400;">SUFFICIENT STOCK</span></div>', unsafe_allow_html=True)

with m_col2:
    st.metric(
        label="Available Stock",
        value=f"{report.current_stock:g} units",
        delta=f"Loc: {report.traces[0].tool_output.get('warehouse_location', 'WH')}"
    )

with m_col3:
    st.metric(
        label="Average Daily Demand (ADD)",
        value=f"{report.average_daily_demand:.1f} u/day",
        delta=f"{report.traces[1].tool_output.get('trend', 'STABLE')}"
    )

with m_col4:
    st.metric(
        label="Days of Supply (DoS)",
        value=f"{report.days_of_supply:.2f} days",
        delta=f"{'Deficit' if report.days_of_supply < report.strategy_alpha_analysis['lead_time_days'] else 'Adequate'}",
        delta_color="inverse" if report.days_of_supply < report.strategy_alpha_analysis['lead_time_days'] else "normal"
    )

with m_col5:
    alpha_gap = report.strategy_alpha_analysis["stockout_gap"]
    st.metric(
        label="Stockout Gap (Std)",
        value=f"{alpha_gap:+.1f} units",
        delta=f"{'Deficit' if alpha_gap < 0 else 'Surplus'}",
        delta_color="inverse" if alpha_gap < 0 else "normal"
    )

# -----------------------------------------------------------------------------
# Agent Step-by-Step Execution Trace
# -----------------------------------------------------------------------------
st.write("")
with st.expander("🔍 Agent Reasoning & Tool Invocation Trace (5 Steps)", expanded=True):
    for trace in report.traces:
        step_color = "#58a6ff"
        st.markdown(f"""
        <div class="trace-card">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <span class="trace-header">Step {trace.step_number}: {trace.step_name}</span>
                <span class="trace-tool">{trace.tool_name}()</span>
            </div>
            <p style="margin:4px 0; color:#c9d1d9; font-size:14px;"><strong>🧠 Agent Thought:</strong> {trace.agent_thought}</p>
            <p style="margin:4px 0; color:#7ee787; font-size:14px; font-family:monospace; white-space:pre-wrap;"><strong>📐 Mathematical Deduction:</strong><br>{trace.mathematical_deduction}</p>
        </div>
        """, unsafe_allow_html=True)
        with st.expander(f"View Raw Tool Input/Output (Step {trace.step_number})", expanded=False):
            st.json({"tool_args": trace.tool_args, "tool_output": trace.tool_output})

# -----------------------------------------------------------------------------
# Dual-Strategy Trade-off Comparison Matrix
# -----------------------------------------------------------------------------
st.subheader("2. Dual-Strategy Supplier Trade-off Matrix")

alpha = report.strategy_alpha_analysis
beta = report.strategy_beta_analysis
summary = report.tradeoff_summary

# Comparative Table
table_data = {
    "Operational Metric": [
        "Supplier Partner",
        "Strategy Profile",
        "Delivery Lead Time",
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
        alpha["supplier_name"],
        "Lowest Landed Cost / Standard Freight",
        f"{alpha['lead_time_days']} Days",
        f"{alpha['ltd']:.1f} Units",
        f"{alpha['stockout_gap']:+.1f} Units",
        f"{alpha['stockout_duration_days']:.1f} Days Out of Stock",
        f"{alpha['unfulfilled_demand_units']:.1f} Units Lost",
        f"{alpha['roq']:.0f} Units",
        f"${alpha['unit_price']:.2f}",
        f"${alpha['shipping_cost']:.2f}",
        f"${alpha['landed_cost']:,.2f}",
        f"${alpha['effective_unit_cost']:.2f}"
    ],
    "Strategy Beta (Expedited / Speed)": [
        beta["supplier_name"],
        "Priority Air Dispatch / Fast Recovery",
        f"{beta['lead_time_days']} Days",
        f"{beta['ltd']:.1f} Units",
        f"{beta['stockout_gap']:+.1f} Units",
        f"{beta['stockout_duration_days']:.1f} Days Out of Stock",
        f"{beta['unfulfilled_demand_units']:.1f} Units Lost",
        f"{beta['roq']:.0f} Units",
        f"${beta['unit_price']:.2f}",
        f"${beta['shipping_cost']:.2f}",
        f"${beta['landed_cost']:,.2f}",
        f"${beta['effective_unit_cost']:.2f}"
    ]
}

df_tradeoff = pd.DataFrame(table_data)
st.dataframe(df_tradeoff, use_container_width=True, hide_index=True)

# Trade-off insights callout
if summary["units_stockout_prevented"] > 0:
    st.info(
        f"💡 **Strategic Trade-off Analysis**: Strategy Beta delivers **{summary['days_faster']} days faster**, preventing "
        f"**{summary['units_stockout_prevented']:.0f} unfulfilled customer orders** for an expedited cost delta of **${summary['expedited_premium']:,.2f}**."
    )
else:
    st.success(
        f"💡 **Strategic Trade-off Analysis**: Strategy Alpha fulfills inventory without lead-time stockout, saving **${abs(summary['expedited_premium']):,.2f}** over expedited freight."
    )

# -----------------------------------------------------------------------------
# Final Actionable Purchase Order Recommendation
# -----------------------------------------------------------------------------
st.subheader("3. Finalized Autonomous Purchase Order Recommendation")

rec = report.final_recommendation

st.markdown(f"""
<div class="po-container">
    <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #30363d; padding-bottom:12px; margin-bottom:16px;">
        <div>
            <h3 style="margin:0; color:#f0f2f6;">PURCHASE ORDER: <span style="color:#58a6ff;">{rec['po_number']}</span></h3>
            <span style="color:#8b949e; font-size:13px;">Selected Strategy: <strong>{rec['selected_strategy']}</strong></span>
        </div>
        <div>
            <span style="background-color:#238636; color:white; padding:6px 14px; border-radius:20px; font-weight:700; font-size:13px;">
                ● {rec['status']}
            </span>
        </div>
    </div>
    <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:16px; margin-bottom:16px;">
        <div>
            <span style="color:#8b949e; font-size:12px;">VENDOR / SUPPLIER</span><br>
            <strong>{rec['supplier_name']}</strong><br>
            <span style="color:#7ee787; font-size:12px;">{rec['supplier_contact']}</span>
        </div>
        <div>
            <span style="color:#8b949e; font-size:12px;">ORDER QUANTITY</span><br>
            <strong style="font-size:18px;">{rec['order_quantity']:.0f} units</strong><br>
            <span style="color:#8b949e; font-size:12px;">Target Coverage: {report.target_coverage_days}d + Safety: {report.safety_stock_days}d</span>
        </div>
        <div>
            <span style="color:#8b949e; font-size:12px;">UNIT PRICE / FREIGHT</span><br>
            <strong>${rec['unit_price']:.2f} / unit</strong><br>
            <span style="color:#8b949e; font-size:12px;">Freight: ${rec['shipping_cost']:.2f}</span>
        </div>
        <div>
            <span style="color:#8b949e; font-size:12px;">TOTAL LANDED COMMITMENT</span><br>
            <strong style="font-size:22px; color:#58a6ff;">${rec['total_landed_cost']:,.2f}</strong>
        </div>
    </div>
    <div style="background-color:#0d1117; border-left:4px solid #58a6ff; padding:12px 16px; border-radius:4px;">
        <strong style="color:#58a6ff;">Autonomous Agent Rationale:</strong><br>
        <span style="color:#c9d1d9; font-size:14px; line-height:1.5;">{rec['rationale']}</span>
    </div>
</div>
""", unsafe_allow_html=True)

# Export options
col_dl1, col_dl2 = st.columns([1, 4])
with col_dl1:
    po_json = json.dumps(rec, indent=2)
    st.download_button(
        label="📥 Export PO (JSON)",
        data=po_json,
        file_name=f"{rec['po_number']}.json",
        mime="application/json",
        use_container_width=True
    )

# -----------------------------------------------------------------------------
# Database & Historical Velocity Explorer
# -----------------------------------------------------------------------------
st.write("")
st.write("")
st.subheader("4. Live Database & Historical Sales Explorer")

tab_prod, tab_sup, tab_sales = st.tabs(["📋 All Products", "🚚 Supplier Contracts", "📈 30-Day Sales Demand Log"])

with tab_prod:
    df_prods = pd.DataFrame(get_all_products())
    st.dataframe(df_prods, use_container_width=True, hide_index=True)

with tab_sup:
    df_sups = pd.DataFrame(get_suppliers_for_sku(selected_sku))
    st.dataframe(df_sups, use_container_width=True, hide_index=True)

with tab_sales:
    sales_data = get_sales_log_for_sku(selected_sku, days=30)
    df_sales = pd.DataFrame(sales_data)
    df_sales.rename(columns={"day_offset": "Day", "units_sold": "Units Sold"}, inplace=True)
    st.line_chart(df_sales.set_index("Day")["Units Sold"])
    st.dataframe(df_sales.T, use_container_width=True)
