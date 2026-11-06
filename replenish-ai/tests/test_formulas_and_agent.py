"""
Comprehensive unit test suite for ReplenishAI.
Validates:
1. Core Rules 1-6 mathematical correctness against the specified example.
2. The 4 functional agent tools.
3. The end-to-end agent orchestrator audit loop and trade-off evaluation.
"""

import pytest
from pathlib import Path
import sys

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.formulas import (
    calculate_dos,
    calculate_ltd,
    calculate_stockout_gap,
    calculate_roq,
    triage_risk,
    compute_all_reorder_metrics,
    evaluate_supplier_strategy
)
from agent.tools import (
    inventory_lookup,
    sales_history_analysis,
    supplier_comparison,
    reorder_calculation
)
from agent.orchestrator import ReplenishAIAgent
from data.database import init_db


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Initializes the SQLite database before running tests."""
    init_db(force_reset=True)


def test_core_math_example_from_prompt():
    """
    Validates example from user prompt:
    Stock: 15, Demand: 10/day, Lead Time: 5 days
    Target Coverage: 30 days, Safety Stock: 7 days
    Expected:
    - DoS = 1.5
    - LTD = 50
    - Stockout Gap = -35 (Deficit)
    - Risk = CRITICAL
    - ROQ = (10 * (30 + 7)) + 35 = 405
    """
    stock = 15.0
    add = 10.0
    lead_time = 5
    coverage = 30
    safety = 7

    # 1. Days of Supply
    dos = calculate_dos(stock, add)
    assert dos == 1.5, f"Expected DoS=1.5, got {dos}"

    # 2. Lead Time Demand
    ltd = calculate_ltd(add, lead_time)
    assert ltd == 50.0, f"Expected LTD=50.0, got {ltd}"

    # 3. Stockout Gap
    gap = calculate_stockout_gap(stock, ltd)
    assert gap == -35.0, f"Expected Stockout Gap=-35.0, got {gap}"

    # 4. Risk Triage
    risk = triage_risk(dos, lead_time, safety)
    assert risk == "CRITICAL", f"Expected Risk='CRITICAL', got {risk}"

    # 5. ROQ
    roq = calculate_roq(add, coverage, safety, gap)
    assert roq == 405.0, f"Expected ROQ=405.0, got {roq}"


def test_safe_inventory_scenario():
    """
    Validates SAFE inventory scenario:
    Stock: 250, Demand: 8/day, Lead Time: 4 days, Safety Stock: 5 days
    DoS = 31.25 > 9 (Lead + Safety) -> SAFE
    Stockout Gap = 250 - 32 = +218 (No deficit)
    ROQ = 8 * (30 + 5) + 0 = 280
    """
    stock = 250.0
    add = 8.0
    lead_time = 4
    coverage = 30
    safety = 5

    dos = calculate_dos(stock, add)
    assert dos == 31.25

    risk = triage_risk(dos, lead_time, safety)
    assert risk == "SAFE"

    gap = calculate_stockout_gap(stock, calculate_ltd(add, lead_time))
    assert gap == 218.0

    roq = calculate_roq(add, coverage, safety, gap)
    assert roq == 280.0


def test_high_risk_inventory_scenario():
    """
    Validates HIGH risk scenario:
    Stock: 80, Demand: 10/day, Lead Time: 5 days, Safety Stock: 7 days
    DoS = 8.0.
    Since 5 < 8.0 <= (5 + 7 = 12) -> HIGH
    Stockout Gap = 80 - 50 = +30
    ROQ = 10 * 37 + 0 = 370
    """
    stock = 80.0
    add = 10.0
    lead_time = 5
    coverage = 30
    safety = 7

    dos = calculate_dos(stock, add)
    assert dos == 8.0

    risk = triage_risk(dos, lead_time, safety)
    assert risk == "HIGH"

    gap = calculate_stockout_gap(stock, calculate_ltd(add, lead_time))
    assert gap == 30.0

    roq = calculate_roq(add, coverage, safety, gap)
    assert roq == 370.0


def test_tool_inventory_lookup():
    """Tests Tool 1: inventory_lookup"""
    res = inventory_lookup("SKU-101")
    assert res["status"] == "success"
    assert res["sku"] == "SKU-101"
    assert res["available_stock"] == 15.0
    assert res["unit_cost"] == 18.0


def test_tool_sales_history_analysis():
    """Tests Tool 2: sales_history_analysis"""
    res = sales_history_analysis("SKU-101", window_days=30)
    assert res["status"] == "success"
    assert res["window_days"] == 30
    assert res["add"] == 10.0
    assert res["trend"] in ["STABLE", "ACCELERATING", "DECELERATING"]


def test_tool_supplier_comparison():
    """Tests Tool 3: supplier_comparison"""
    res = supplier_comparison("SKU-101")
    assert res["status"] == "success"
    assert res["alpha_supplier"] is not None
    assert res["beta_supplier"] is not None
    assert res["alpha_supplier"]["lead_time_days"] == 5
    assert res["alpha_supplier"]["unit_price"] == 18.00
    assert res["beta_supplier"]["lead_time_days"] == 2
    assert res["beta_supplier"]["unit_price"] == 24.50


def test_tool_reorder_calculation():
    """Tests Tool 4: reorder_calculation"""
    res = reorder_calculation(available_stock=15, add=10, lead_time_days=5, target_coverage_days=30, safety_stock_days=7)
    assert res["status"] == "success"
    assert res["dos"] == 1.5
    assert res["ltd"] == 50.0
    assert res["stockout_gap"] == -35.0
    assert res["risk_level"] == "CRITICAL"
    assert res["roq"] == 405.0
    assert res["stockout_duration_days"] == 3.5
    assert res["unfulfilled_demand_units"] == 35.0


def test_orchestrator_complete_audit_sku_101():
    """Tests full agent orchestrator execution for SKU-101"""
    agent = ReplenishAIAgent(target_coverage_days=30, safety_stock_days=7)
    report = agent.run_procurement_audit("SKU-101")

    assert report.sku == "SKU-101"
    assert report.overall_risk == "CRITICAL"
    assert report.days_of_supply == 1.5
    assert len(report.traces) == 5

    # Strategy comparison
    alpha = report.strategy_alpha_analysis
    beta = report.strategy_beta_analysis
    assert alpha["lead_time_days"] == 5
    assert beta["lead_time_days"] == 2
    assert alpha["stockout_gap"] == -35.0
    assert beta["stockout_gap"] == -5.0

    # Final decision should recommend expedited (Beta) because 35 lost orders are averted
    rec = report.final_recommendation
    assert "Beta" in rec["selected_strategy"]
    assert rec["supplier_id"] == "SUP-VELOCITY"
    assert rec["order_quantity"] == 375.0  # (10 * 37) + 5
    assert rec["status"] == "APPROVED_FOR_DISPATCH"
