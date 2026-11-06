"""
CLI interface for ReplenishAI Autonomous Agent.
Allows instantaneous terminal execution and verification of procurement audits.
"""

import argparse
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from data.database import init_db
from agent.orchestrator import ReplenishAIAgent


def main():
    parser = argparse.ArgumentParser(description="ReplenishAI: Autonomous Supply Chain & Inventory Procurement Agent")
    parser.add_argument("--sku", type=str, default="SKU-101", help="Target product SKU (e.g., SKU-101, SKU-102, SKU-103, SKU-104)")
    parser.add_argument("--coverage", type=int, default=30, help="Target inventory coverage days (default: 30)")
    parser.add_argument("--safety", type=int, default=7, help="Safety stock buffer days (default: 7)")
    parser.add_argument("--init-db", action="store_true", help="Force reinitialize SQLite database from mock data")

    args = parser.parse_args()

    # Ensure DB is initialized
    init_db(force_reset=args.init_db)

    print("=" * 80)
    print(" [REPLENISH-AI] AUTONOMOUS PROCUREMENT & SUPPLY CHAIN AUDIT")
    print("=" * 80)
    print(f"Target SKU: {args.sku}")
    print(f"Parameters: Target Coverage = {args.coverage} days | Safety Stock = {args.safety} days")
    print("-" * 80)

    agent = ReplenishAIAgent(target_coverage_days=args.coverage, safety_stock_days=args.safety)

    try:
        report = agent.run_procurement_audit(args.sku)
    except Exception as e:
        print(f"\n[ERROR] Audit failed: {e}")
        sys.exit(1)

    # 1. Print Trace Steps
    print("\n[AGENT EXECUTION TRACE]")
    for trace in report.traces:
        print(f"\n>> Step {trace.step_number}: {trace.step_name} [{trace.tool_name}]")
        print(f"   Thought: {trace.agent_thought}")
        print(f"   Deduction: {trace.mathematical_deduction}")

    # 2. Risk Triage Banner
    print("\n" + "=" * 80)
    print(f" INVENTORY HEALTH & RISK TRIAGE: [{report.overall_risk}]")
    print("=" * 80)
    print(f"• Product:                 {report.product_name} ({report.category})")
    print(f"• Current Stock:           {report.current_stock:g} units")
    print(f"• Average Daily Demand:    {report.average_daily_demand:.2f} units/day")
    print(f"• Days of Supply (DoS):    {report.days_of_supply:.2f} days")

    # 3. Trade-off Comparison Table
    alpha = report.strategy_alpha_analysis
    beta = report.strategy_beta_analysis

    print("\n" + "-" * 80)
    print(" DUAL-STRATEGY SUPPLIER TRADE-OFF MATRIX")
    print("-" * 80)
    header = f"{'Metric':<28} | {'Strategy Alpha (Standard)':<26} | {'Strategy Beta (Expedited)':<26}"
    print(header)
    print("-" * len(header))

    def row(label, val_a, val_b):
        print(f"{label:<28} | {str(val_a):<26} | {str(val_b):<26}")

    row("Supplier Name", alpha["supplier_name"][:26], beta["supplier_name"][:26])
    row("Lead Time (Days)", f"{alpha['lead_time_days']} days", f"{beta['lead_time_days']} days")
    row("Lead Time Demand (LTD)", f"{alpha['ltd']:.1f} units", f"{beta['ltd']:.1f} units")
    row("Stockout Gap", f"{alpha['stockout_gap']:+.1f} units", f"{beta['stockout_gap']:+.1f} units")
    row("Stockout Duration", f"{alpha['stockout_duration_days']:.1f} days", f"{beta['stockout_duration_days']:.1f} days")
    row("Unfulfilled Demand", f"{alpha['unfulfilled_demand_units']:.1f} units", f"{beta['unfulfilled_demand_units']:.1f} units")
    row("Recommended Order Qty (ROQ)", f"{alpha['roq']:.0f} units", f"{beta['roq']:.0f} units")
    row("Unit Price", f"${alpha['unit_price']:.2f}", f"${beta['unit_price']:.2f}")
    row("Shipping Cost", f"${alpha['shipping_cost']:.2f}", f"${beta['shipping_cost']:.2f}")
    row("Total Landed Cost", f"${alpha['landed_cost']:,.2f}", f"${beta['landed_cost']:,.2f}")

    # 4. Final Recommendation
    rec = report.final_recommendation
    print("\n" + "=" * 80)
    print(f" ACTIONABLE PURCHASE ORDER RECOMMENDATION: {rec['po_number']}")
    print("=" * 80)
    print(f"Strategy:       {rec['selected_strategy']}")
    print(f"Supplier:       {rec['supplier_name']} ({rec['supplier_contact']})")
    print(f"Order Quantity: {rec['order_quantity']:.0f} units @ ${rec['unit_price']:.2f}/unit")
    print(f"Total Landed:   ${rec['total_landed_cost']:,.2f} (Includes ${rec['shipping_cost']:.2f} freight)")
    print(f"Status:         {rec['status']}")
    print(f"\nRationale:\n{rec['rationale']}")
    print("=" * 80)


if __name__ == "__main__":
    main()
