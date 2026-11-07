"""
Comprehensive unit test suite for ReplenishAI.
Validates:
1. Core Rules 1-6 mathematical correctness against the specified example.
2. Multi-SKU Portfolio risk profiles (SKU-101 to SKU-104).
3. One-Click Purchase Order JSON export payload schema.
4. Supply Chain Shock Simulator calculations (Feature 1).
5. Automated Critical Stockout Alerting Engine & Webhook payload (Feature 3).
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
from agent.orchestrator import ReplenishAIAgent, get_fleet_overview
from agent.alerting import build_alert_payload, dispatch_webhook, format_escalation_email
from data.database import init_db


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Initializes the SQLite database before running tests."""
    init_db(force_reset=True)


def test_core_math_example_from_prompt():
    """Validates baseline example from user prompt: Stock 15, Demand 10, Lead 5."""
    stock = 15.0
    add = 10.0
    lead_time = 5
    coverage = 30
    safety = 7

    dos = calculate_dos(stock, add)
    assert dos == 1.5, f"Expected DoS=1.5, got {dos}"

    ltd = calculate_ltd(add, lead_time)
    assert ltd == 50.0, f"Expected LTD=50.0, got {ltd}"

    gap = calculate_stockout_gap(stock, ltd)
    assert gap == -35.0, f"Expected Stockout Gap=-35.0, got {gap}"

    risk = triage_risk(dos, lead_time, safety)
    assert risk == "CRITICAL", f"Expected Risk='CRITICAL', got {risk}"

    roq = calculate_roq(add, coverage, safety, gap)
    assert roq == 405.0, f"Expected ROQ=405.0, got {roq}"


def test_healthy_inventory_scenario():
    """Validates HEALTHY inventory scenario (SKU-103 Hydraulic Seal C)."""
    stock = 320.0
    add = 6.0
    lead_time = 3
    buffer_days = 3

    dos = calculate_dos(stock, add)
    assert dos == 53.33

    risk = triage_risk(dos, lead_time, buffer_days)
    assert risk == "HEALTHY"


def test_at_risk_inventory_scenario():
    """Validates AT RISK scenario (SKU-102 Precision Valve B)."""
    stock = 65.0
    add = 10.0
    lead_time = 5
    buffer_days = 3

    dos = calculate_dos(stock, add)
    assert dos == 6.5

    risk = triage_risk(dos, lead_time, buffer_days)
    assert risk == "AT RISK"


def test_fleet_overview_all_four_skus():
    """Validates Multi-SKU Portfolio Dashboard fleet overview."""
    fleet = get_fleet_overview(buffer_days=3)
    assert len(fleet) == 4

    skus = {item["sku"]: item for item in fleet}
    assert skus["SKU-101"]["risk_status"] == "CRITICAL"
    assert skus["SKU-102"]["risk_status"] == "AT RISK"
    assert skus["SKU-103"]["risk_status"] == "HEALTHY"
    assert skus["SKU-104"]["risk_status"] == "CRITICAL"


def test_po_payload_schema():
    """Validates One-Click Purchase Order JSON export schema."""
    agent = ReplenishAIAgent(target_coverage_days=30, safety_stock_days=7)
    report = agent.run_procurement_audit("SKU-101")

    payload = report.po_payload
    assert "purchase_order" in payload
    po = payload["purchase_order"]
    assert po["status"] == "APPROVED_DRAFT"
    assert po["po_number"].startswith("PO-")
    assert "SKU-101" in po["po_number"]
    assert po["authorizing_agent"] == "ReplenishAI Autonomous Agent v1.0"
    assert po["item_details"]["sku"] == "SKU-101"
    assert po["vendor_details"]["contract_type"] in ["EXPEDITED", "STANDARD"]


def test_supply_chain_shock_simulation_feature_1():
    """
    Feature 1: Tests Demand Surge Multiplier and Port Delay re-computation.
    Base Demand = 10, Multiplier = 1.5x -> Effective Demand = 15.0
    Base Lead Time = 5d, Delay = +2d -> Effective Lead Time = 7d
    Stock = 15
    Expected:
    - DoS = 15 / 15.0 = 1.0 day
    - LTD = 15.0 * 7 = 105.0 units
    - Gap = 15 - 105 = -90.0 units
    - Risk = CRITICAL
    """
    base_demand = 10.0
    surge_mult = 1.5
    effective_demand = base_demand * surge_mult
    assert effective_demand == 15.0

    base_lead = 5
    port_delay = 2
    effective_lead = base_lead + port_delay
    assert effective_lead == 7

    stock = 15.0
    dos = calculate_dos(stock, effective_demand)
    assert dos == 1.0

    ltd = calculate_ltd(effective_demand, effective_lead)
    assert ltd == 105.0

    gap = calculate_stockout_gap(stock, ltd)
    assert gap == -90.0

    risk = triage_risk(dos, effective_lead, safety_stock_days=3)
    assert risk == "CRITICAL"

    roq = calculate_roq(effective_demand, target_coverage_days=30, safety_stock_days=7, stockout_gap=gap)
    # (15 * (30 + 7)) + 90 = 555 + 90 = 645
    assert roq == 645.0


def test_alerting_engine_and_webhook_payload_feature_3():
    """
    Feature 3: Tests Standardized Webhook JSON Payload Schema and Escalation Email.
    """
    payload = build_alert_payload(
        sku="SKU-101",
        product_name="Industrial Widget A",
        on_hand_stock=15.0,
        effective_daily_demand=10.0,
        days_of_supply=1.5,
        standard_lead_time_days=5,
        unfulfilled_demand_units=35.0,
        preferred_vendor="Velocity Freight (Expedited)",
        emergency_order_qty=35.0,
        bulk_followup_qty=370.0
    )

    # Validate exact payload schema
    assert payload["event"] == "INVENTORY_CRITICAL_STOCKOUT_DETECTED"
    assert payload["severity"] == "CRITICAL_P0"
    assert payload["alert_id"].startswith("ALT-")
    assert payload["sku"] == "SKU-101"
    assert payload["product_name"] == "Industrial Widget A"

    # Validate metrics sub-object
    metrics = payload["metrics"]
    assert metrics["on_hand_stock"] == 15.0
    assert metrics["effective_daily_demand"] == 10.0
    assert metrics["days_of_supply"] == 1.5
    assert metrics["standard_lead_time_days"] == 5
    assert metrics["projected_stockout_hours"] == 36.0  # 1.5 * 24
    assert metrics["unfulfilled_demand_units"] == 35.0

    # Validate intervention sub-object
    intervention = payload["recommended_intervention"]
    assert intervention["action"] == "EXPEDITE_PURCHASE_ORDER"
    assert intervention["preferred_vendor"] == "Velocity Freight (Expedited)"
    assert intervention["emergency_order_qty"] == 35.0
    assert intervention["bulk_followup_qty"] == 370.0

    # Test webhook dispatcher (simulated mock)
    wh_result = dispatch_webhook("https://webhook.site/test-route", payload)
    assert wh_result["status"] in ["delivered", "simulated"]

    # Test email formatter
    email_result = format_escalation_email("procurement-alerts@company.internal", payload)
    assert email_result["status"] == "sent"
    assert "CRITICAL_P0" in email_result["subject"]
    assert "SKU-101" in email_result["body"]
