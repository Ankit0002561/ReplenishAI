"""
ReplenishAI Autonomous Agent Orchestrator.
Coordinates inventory lookup, sales velocity analysis, supplier evaluation,
mathematical replenishment calculations, and procurement order formulation.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import secrets
from typing import Dict, List, Any, Optional
from agent.tools import inventory_lookup, sales_history_analysis, supplier_comparison, reorder_calculation
from agent.formulas import evaluate_supplier_strategy, compute_all_reorder_metrics, calculate_dos, triage_risk
from data.database import get_all_products, get_suppliers_for_sku


@dataclass
class AgentStepTrace:
    step_number: int
    step_name: str
    tool_name: str
    tool_args: Dict[str, Any]
    agent_thought: str
    tool_output: Dict[str, Any]
    mathematical_deduction: str
    status: str = "completed"


@dataclass
class AuditReport:
    sku: str
    product_name: str
    category: str
    run_timestamp: str
    target_coverage_days: int
    safety_stock_days: int
    traces: List[AgentStepTrace]
    overall_risk: str
    days_of_supply: float
    average_daily_demand: float
    current_stock: float
    strategy_alpha_analysis: Dict[str, Any]
    strategy_beta_analysis: Dict[str, Any]
    tradeoff_summary: Dict[str, Any]
    final_recommendation: Dict[str, Any]
    po_payload: Dict[str, Any] = field(default_factory=dict)


def get_fleet_overview(buffer_days: int = 3, db_path: Optional[Any] = None) -> List[Dict[str, Any]]:
    """
    Computes top-level fleet overview for all SKUs:
    SKU | Product Name | On-Hand Stock | Daily Demand | Days of Supply | Risk Status
    """
    products = get_all_products(db_path)
    overview = []
    for p in products:
        sku = p["sku"]
        stock = float(p["available_stock"])
        sales_data = sales_history_analysis(sku, window_days=30)
        add = sales_data.get("add", 0.0)
        suppliers = get_suppliers_for_sku(sku, db_path)
        alpha = next((s for s in suppliers if s["strategy_type"] == "Alpha"), None)
        std_lead = alpha["lead_time_days"] if alpha else 5

        dos = calculate_dos(stock, add)
        risk = triage_risk(dos, std_lead, safety_stock_days=buffer_days)

        overview.append({
            "sku": sku,
            "product_name": p["name"],
            "category": p["category"],
            "on_hand_stock": stock,
            "daily_demand": add,
            "days_of_supply": dos,
            "standard_lead_time": std_lead,
            "risk_status": risk
        })
    return overview


class ReplenishAIAgent:
    """
    Autonomous Supply Chain Operations and Procurement Agent.
    """

    SYSTEM_PROMPT = """
You are ReplenishAI, an autonomous Supply Chain Operations and Procurement Agent. Your responsibility is to analyze inventory levels, sales velocity, and vendor catalogs to eliminate stockouts and formulate optimal procurement orders.

CORE RULES & FORMULAS:
1. Days of Supply (DoS) = Current Available Stock / Average Daily Demand (ADD)
2. Lead Time Demand (LTD) = ADD * Supplier Lead Time (Days)
3. Stockout Gap = Available Stock - LTD
4. Recommended Order Quantity (ROQ) = (ADD * (Target Coverage Days + Safety Stock Days)) + max(0, -Stockout Gap)
5. Risk Triage:
   - CRITICAL: Days of Supply < Supplier Lead Time (Stockout inevitable before delivery).
   - AT RISK: Days of Supply <= Supplier Lead Time + Safety Stock / Buffer Days.
   - HEALTHY: Days of Supply > Supplier Lead Time + Safety Stock / Buffer Days.
6. Always evaluate two trade-off strategies:
   - Strategy Alpha: Cost-Optimized (standard lead time, lowest landed cost).
   - Strategy Beta: Lead-Time Optimized / Expedited (fastest delivery to prevent stockout).
"""

    def __init__(self, target_coverage_days: int = 30, safety_stock_days: int = 7):
        self.target_coverage_days = target_coverage_days
        self.safety_stock_days = safety_stock_days

    def run_procurement_audit(self, sku: str) -> AuditReport:
        clean_sku = sku.strip().upper()
        traces: List[AgentStepTrace] = []

        # -------------------------------------------------------------
        # STEP 1: Inventory Lookup
        # -------------------------------------------------------------
        thought_1 = (
            f"Querying real-time warehouse inventory for SKU '{clean_sku}' "
            "to establish baseline on-hand available stock and storage location."
        )
        inv_res = inventory_lookup(clean_sku)
        if inv_res.get("status") == "error":
            raise ValueError(inv_res.get("message"))

        available_stock = inv_res["available_stock"]
        product_name = inv_res["name"]
        category = inv_res["category"]

        deduction_1 = (
            f"Verified on-hand stock: {available_stock:g} units located at {inv_res['warehouse_location']}. "
            f"Standard unit cost basis: ${inv_res['unit_cost']:.2f}."
        )
        traces.append(AgentStepTrace(
            step_number=1,
            step_name="Inventory Inspection",
            tool_name="inventory_lookup",
            tool_args={"sku": clean_sku},
            agent_thought=thought_1,
            tool_output=inv_res,
            mathematical_deduction=deduction_1
        ))

        # -------------------------------------------------------------
        # STEP 2: Sales History Analysis
        # -------------------------------------------------------------
        thought_2 = (
            f"Extracting 30-day demand log for '{clean_sku}' to compute Average Daily Demand (ADD), "
            "assess consumption variance, and evaluate velocity momentum."
        )
        sales_res = sales_history_analysis(clean_sku, window_days=30)
        add = sales_res["add"]
        trend = sales_res["trend"]

        deduction_2 = (
            f"Demand analysis over 30 days yields Total Sales: {sales_res['total_units_sold']} units. "
            f"Average Daily Demand (ADD) = {sales_res['total_units_sold']} / 30 = {add:.2f} units/day "
            f"(std dev: {sales_res['std_dev']:.2f}, momentum: {trend})."
        )
        traces.append(AgentStepTrace(
            step_number=2,
            step_name="Sales Velocity & Consumption Analysis",
            tool_name="sales_history_analysis",
            tool_args={"sku": clean_sku, "window_days": 30},
            agent_thought=thought_2,
            tool_output=sales_res,
            mathematical_deduction=deduction_2
        ))

        # -------------------------------------------------------------
        # STEP 3: Supplier Catalog Comparison
        # -------------------------------------------------------------
        thought_3 = (
            f"Auditing approved suppliers for SKU '{clean_sku}'. Retrieving quotes for "
            "Strategy Alpha (Cost-Optimized Standard) vs. Strategy Beta (Lead-Time Optimized Expedited)."
        )
        sup_res = supplier_comparison(clean_sku)
        alpha_sup = sup_res.get("alpha_supplier")
        beta_sup = sup_res.get("beta_supplier")

        if not alpha_sup or not beta_sup:
            raise ValueError(f"Incomplete vendor catalog: both Alpha and Beta suppliers must exist for {clean_sku}")

        deduction_3 = (
            f"Identified 2 qualified vendor pathways:\n"
            f"• Strategy Alpha: {alpha_sup['supplier_name']} - Lead Time: {alpha_sup['lead_time_days']}d @ ${alpha_sup['unit_price']:.2f}/unit (Shipping: ${alpha_sup['shipping_cost']:.2f}, MOQ: {alpha_sup['moq']})\n"
            f"• Strategy Beta: {beta_sup['supplier_name']} - Lead Time: {beta_sup['lead_time_days']}d @ ${beta_sup['unit_price']:.2f}/unit (Shipping: ${beta_sup['shipping_cost']:.2f}, MOQ: {beta_sup['moq']})"
        )
        traces.append(AgentStepTrace(
            step_number=3,
            step_name="Supplier Catalog Benchmarking",
            tool_name="supplier_comparison",
            tool_args={"sku": clean_sku},
            agent_thought=thought_3,
            tool_output=sup_res,
            mathematical_deduction=deduction_3
        ))

        # -------------------------------------------------------------
        # STEP 4: Dual Reorder Calculations & Mathematical Deduction
        # -------------------------------------------------------------
        thought_4 = (
            "Executing deterministic replenishment formulas for both vendor options. "
            "Calculating Days of Supply (DoS), Lead Time Demand (LTD), Stockout Gap, "
            "Risk Triage (CRITICAL/AT RISK/HEALTHY), and Recommended Order Quantity (ROQ)."
        )

        # Standard Alpha metrics
        metrics_alpha = compute_all_reorder_metrics(
            sku=clean_sku,
            available_stock=available_stock,
            add=add,
            lead_time_days=alpha_sup["lead_time_days"],
            target_coverage_days=self.target_coverage_days,
            safety_stock_days=self.safety_stock_days,
        )
        alpha_eval = evaluate_supplier_strategy(
            metrics_alpha,
            unit_price=alpha_sup["unit_price"],
            shipping_cost=alpha_sup["shipping_cost"],
            moq=alpha_sup["moq"],
            strategy_type="Alpha (Cost-Optimized Standard)"
        )
        alpha_eval["supplier_id"] = alpha_sup["supplier_id"]
        alpha_eval["supplier_name"] = alpha_sup["supplier_name"]
        alpha_eval["contact_email"] = alpha_sup["contact_email"]

        # Expedited Beta metrics
        metrics_beta = compute_all_reorder_metrics(
            sku=clean_sku,
            available_stock=available_stock,
            add=add,
            lead_time_days=beta_sup["lead_time_days"],
            target_coverage_days=self.target_coverage_days,
            safety_stock_days=self.safety_stock_days,
        )
        beta_eval = evaluate_supplier_strategy(
            metrics_beta,
            unit_price=beta_sup["unit_price"],
            shipping_cost=beta_sup["shipping_cost"],
            moq=beta_sup["moq"],
            strategy_type="Beta (Lead-Time Expedited)"
        )
        beta_eval["supplier_id"] = beta_sup["supplier_id"]
        beta_eval["supplier_name"] = beta_sup["supplier_name"]
        beta_eval["contact_email"] = beta_sup["contact_email"]

        # Overall triage based on Standard Lead Time
        overall_risk = metrics_alpha.risk_level

        deduction_4 = (
            f"1. Days of Supply (DoS) = {available_stock:g} / {add:.2f} = {metrics_alpha.dos:.2f} days.\n"
            f"2. Strategy Alpha ({alpha_sup['lead_time_days']}d lead):\n"
            f"   - LTD = {add:.2f} * {alpha_sup['lead_time_days']} = {metrics_alpha.ltd:.2f} units\n"
            f"   - Stockout Gap = {available_stock:g} - {metrics_alpha.ltd:.2f} = {metrics_alpha.stockout_gap:+.2f} units\n"
            f"   - Risk: {metrics_alpha.risk_level} (DoS {metrics_alpha.dos:.2f} vs Lead Time {alpha_sup['lead_time_days']}d + Safety {self.safety_stock_days}d)\n"
            f"   - ROQ = ({add:.2f} * ({self.target_coverage_days} + {self.safety_stock_days})) + max(0, {-metrics_alpha.stockout_gap:.2f}) = {metrics_alpha.roq:.2f} units\n"
            f"3. Strategy Beta ({beta_sup['lead_time_days']}d lead):\n"
            f"   - LTD = {add:.2f} * {beta_sup['lead_time_days']} = {metrics_beta.ltd:.2f} units\n"
            f"   - Stockout Gap = {available_stock:g} - {metrics_beta.ltd:.2f} = {metrics_beta.stockout_gap:+.2f} units\n"
            f"   - Risk: {metrics_beta.risk_level}\n"
            f"   - ROQ = {metrics_beta.roq:.2f} units"
        )

        calc_tool_out = {
            "dos": metrics_alpha.dos,
            "overall_risk": overall_risk,
            "alpha": alpha_eval,
            "beta": beta_eval
        }
        traces.append(AgentStepTrace(
            step_number=4,
            step_name="Replenishment Mathematics & Risk Triage",
            tool_name="reorder_calculation",
            tool_args={
                "available_stock": available_stock,
                "add": add,
                "alpha_lead_time": alpha_sup["lead_time_days"],
                "beta_lead_time": beta_sup["lead_time_days"],
                "target_coverage_days": self.target_coverage_days,
                "safety_stock_days": self.safety_stock_days
            },
            agent_thought=thought_4,
            tool_output=calc_tool_out,
            mathematical_deduction=deduction_4
        ))

        # -------------------------------------------------------------
        # STEP 5: Trade-off Synthesis & Final Order Recommendation
        # -------------------------------------------------------------
        thought_5 = (
            "Weighing financial landed cost savings versus operational stockout penalty. "
            "Synthesizing the trade-off matrix to deliver an optimal, audit-ready purchase order."
        )

        cost_diff = round(beta_eval["landed_cost"] - alpha_eval["landed_cost"], 2)
        days_saved = alpha_sup["lead_time_days"] - beta_sup["lead_time_days"]
        unfulfilled_diff = round(alpha_eval["unfulfilled_demand_units"] - beta_eval["unfulfilled_demand_units"], 2)

        tradeoff_summary = {
            "alpha_landed_cost": alpha_eval["landed_cost"],
            "beta_landed_cost": beta_eval["landed_cost"],
            "expedited_premium": cost_diff,
            "days_faster": days_saved,
            "units_stockout_prevented": max(0.0, unfulfilled_diff),
            "alpha_stockout_duration_days": alpha_eval["stockout_duration_days"],
            "beta_stockout_duration_days": beta_eval["stockout_duration_days"]
        }

        # Decision Logic:
        # If CRITICAL and Alpha creates a severe stockout gap (>0 unfulfilled units),
        # Beta is strongly recommended or emergency expedited order is triggered.
        if overall_risk == "CRITICAL":
            if unfulfilled_diff > 0:
                selected_strategy = "Strategy Beta (Expedited)"
                contract_type = "EXPEDITED"
                chosen_supplier = beta_sup
                chosen_eval = beta_eval
                order_qty = beta_eval["effective_order_qty"]
                recommendation_rationale = (
                    f"CRITICAL STOCKOUT IMMINENT: Current Days of Supply ({metrics_alpha.dos:.1f} days) is less than "
                    f"the standard supplier lead time ({alpha_sup['lead_time_days']} days). Placing an order via Strategy Alpha "
                    f"would result in {alpha_eval['stockout_duration_days']:.1f} days completely out of stock with "
                    f"{alpha_eval['unfulfilled_demand_units']:.0f} lost customer orders. "
                    f"Recommending expedited Strategy Beta ({beta_sup['supplier_name']}): goods arrive in {beta_sup['lead_time_days']} days, "
                    f"reducing stockout deficit by {unfulfilled_diff:.0f} units. The ${cost_diff:.2f} expedite premium is justified "
                    f"to protect customer SLA and catalog revenue."
                )
            else:
                selected_strategy = "Strategy Alpha (Cost-Optimized)"
                contract_type = "STANDARD"
                chosen_supplier = alpha_sup
                chosen_eval = alpha_eval
                order_qty = alpha_eval["effective_order_qty"]
                recommendation_rationale = (
                    f"CRITICAL inventory alert, but expedited dispatch offers no deficit advantage. "
                    f"Strategy Alpha selected to minimize landed costs."
                )
        elif overall_risk in ["AT RISK", "HIGH"]:
            selected_strategy = "Strategy Alpha (Cost-Optimized)"
            contract_type = "STANDARD"
            chosen_supplier = alpha_sup
            chosen_eval = alpha_eval
            order_qty = alpha_eval["effective_order_qty"]
            recommendation_rationale = (
                f"AT RISK: Current Days of Supply ({metrics_alpha.dos:.1f} days) is sufficient to cover standard lead time "
                f"({alpha_sup['lead_time_days']} days), but low buffer remains (threshold: {self.safety_stock_days} days). "
                f"Since no immediate stockout will occur during the delivery window (Stockout Gap: {metrics_alpha.stockout_gap:+.1f} units), "
                f"Strategy Alpha is optimal. It saves ${cost_diff:.2f} in landed costs while replenishing inventory before zero-stock is reached."
            )
        else:  # HEALTHY / SAFE
            selected_strategy = "Strategy Alpha (Cost-Optimized / Routine)"
            contract_type = "STANDARD"
            chosen_supplier = alpha_sup
            chosen_eval = alpha_eval
            order_qty = alpha_eval["effective_order_qty"]
            recommendation_rationale = (
                f"HEALTHY: Inventory levels ({available_stock:g} units, {metrics_alpha.dos:.1f} DoS) comfortably exceed lead time plus "
                f"safety buffer ({alpha_sup['lead_time_days'] + self.safety_stock_days} days). No emergency reorder needed. "
                f"For routine forward-looking replenishment, Strategy Alpha provides the lowest landed cost basis "
                f"(${alpha_eval['effective_unit_cost']:.2f}/unit all-in)."
            )

        now_dt = datetime.now()
        date_str = now_dt.strftime("%Y%m%d")
        random4 = secrets.token_hex(2).upper()
        po_number = f"PO-{date_str}-{clean_sku}-{random4}"
        lead_days = int(chosen_supplier["lead_time_days"])
        expected_arrival = (now_dt + timedelta(days=lead_days)).strftime("%Y-%m-%d")

        final_recommendation = {
            "po_number": po_number,
            "selected_strategy": selected_strategy,
            "supplier_id": chosen_supplier["supplier_id"],
            "supplier_name": chosen_supplier["supplier_name"],
            "supplier_contact": chosen_supplier["contact_email"],
            "lead_time_days": lead_days,
            "unit_price": chosen_supplier["unit_price"],
            "order_quantity": order_qty,
            "subtotal": round(order_qty * chosen_supplier["unit_price"], 2),
            "shipping_cost": chosen_supplier["shipping_cost"],
            "total_landed_cost": chosen_eval["landed_cost"],
            "rationale": recommendation_rationale,
            "status": "APPROVED_FOR_DISPATCH"
        }

        # Structured schema adhering strictly to Feature 2 One-Click PO Export specification
        po_payload = {
            "purchase_order": {
                "po_number": po_number,
                "created_at": now_dt.isoformat(),
                "status": "APPROVED_DRAFT",
                "item_details": {
                    "sku": clean_sku,
                    "product_name": product_name,
                    "units_ordered": int(round(order_qty))
                },
                "vendor_details": {
                    "vendor_id": chosen_supplier["supplier_id"],
                    "vendor_name": chosen_supplier["supplier_name"],
                    "contract_type": contract_type,
                    "unit_price_usd": float(chosen_supplier["unit_price"]),
                    "shipping_fee_usd": float(chosen_supplier["shipping_cost"]),
                    "total_landed_cost_usd": float(chosen_eval["landed_cost"]),
                    "committed_lead_time_days": lead_days,
                    "expected_arrival_date": expected_arrival
                },
                "procurement_rationale": recommendation_rationale,
                "authorizing_agent": "ReplenishAI Autonomous Agent v1.0"
            }
        }

        deduction_5 = (
            f"Audit Complete. Final Decision: {selected_strategy}.\n"
            f"Drafted Purchase Order {po_number} with {chosen_supplier['supplier_name']}.\n"
            f"Total Landed Cost: ${chosen_eval['landed_cost']:,.2f} for {order_qty:.0f} units."
        )
        traces.append(AgentStepTrace(
            step_number=5,
            step_name="Strategic Trade-off Synthesis & Purchase Order Drafting",
            tool_name="procurement_decision_engine",
            tool_args={"overall_risk": overall_risk, "cost_diff": cost_diff, "days_saved": days_saved},
            agent_thought=thought_5,
            tool_output=final_recommendation,
            mathematical_deduction=deduction_5
        ))

        return AuditReport(
            sku=clean_sku,
            product_name=product_name,
            category=category,
            run_timestamp=now_dt.strftime("%Y-%m-%d %H:%M:%S"),
            target_coverage_days=self.target_coverage_days,
            safety_stock_days=self.safety_stock_days,
            traces=traces,
            overall_risk=overall_risk,
            days_of_supply=metrics_alpha.dos,
            average_daily_demand=add,
            current_stock=available_stock,
            strategy_alpha_analysis=alpha_eval,
            strategy_beta_analysis=beta_eval,
            tradeoff_summary=tradeoff_summary,
            final_recommendation=final_recommendation,
            po_payload=po_payload
        )
