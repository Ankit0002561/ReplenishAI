"""
Mathematical formulas and deterministic decision rules for ReplenishAI.
Strictly implements Core Rules 1-6 from the Supply Chain Operations specification.
"""

from dataclasses import dataclass
from typing import Dict, Any, Tuple


@dataclass
class ReorderMetrics:
    sku: str
    available_stock: float
    add: float  # Average Daily Demand
    lead_time_days: int
    target_coverage_days: int
    safety_stock_days: int
    dos: float  # Days of Supply
    ltd: float  # Lead Time Demand
    stockout_gap: float  # Available Stock - LTD
    risk_level: str  # CRITICAL, HIGH, SAFE
    roq: float  # Recommended Order Quantity
    stockout_duration_days: float  # Expected stockout days before shipment arrives
    unfulfilled_demand_units: float  # Demand that cannot be fulfilled before arrival


def calculate_dos(available_stock: float, add: float) -> float:
    """
    Core Rule 1:
    Days of Supply (DoS) = Current Available Stock / Average Daily Demand (ADD)
    """
    if add <= 0:
        return 999.0 if available_stock > 0 else 0.0
    return round(available_stock / add, 2)


def calculate_ltd(add: float, lead_time_days: int) -> float:
    """
    Core Rule 2:
    Lead Time Demand (LTD) = ADD * Supplier Lead Time (Days)
    """
    return round(add * lead_time_days, 2)


def calculate_stockout_gap(available_stock: float, ltd: float) -> float:
    """
    Core Rule 3:
    Stockout Gap = Available Stock - LTD
    Negative indicates a deficit / stockout before delivery.
    """
    return round(available_stock - ltd, 2)


def calculate_roq(
    add: float,
    target_coverage_days: int,
    safety_stock_days: int,
    stockout_gap: float,
) -> float:
    """
    Core Rule 4:
    Recommended Order Quantity (ROQ) = (ADD * (Target Coverage Days + Safety Stock Days)) + max(0, -Stockout Gap)
    """
    base_coverage_units = add * (target_coverage_days + safety_stock_days)
    deficit_compensation = max(0.0, -stockout_gap)
    return round(base_coverage_units + deficit_compensation, 2)


def triage_risk(dos: float, lead_time_days: int, safety_stock_days: int = 3) -> str:
    """
    Core Rule 5:
    Risk Triage:
    - CRITICAL: Days of Supply < Supplier Lead Time (Stockout inevitable before delivery).
    - AT RISK: Days of Supply <= Supplier Lead Time + buffer days (e.g., 3 days buffer).
    - HEALTHY: Days of Supply > Supplier Lead Time + buffer days.
    """
    if dos < lead_time_days:
        return "CRITICAL"
    elif dos <= (lead_time_days + safety_stock_days):
        return "AT RISK"
    else:
        return "HEALTHY"


def compute_all_reorder_metrics(
    sku: str,
    available_stock: float,
    add: float,
    lead_time_days: int,
    target_coverage_days: int = 30,
    safety_stock_days: int = 7,
) -> ReorderMetrics:
    """
    Executes full mathematical chain for a given SKU and supplier configuration.
    """
    dos = calculate_dos(available_stock, add)
    ltd = calculate_ltd(add, lead_time_days)
    gap = calculate_stockout_gap(available_stock, ltd)
    risk = triage_risk(dos, lead_time_days, safety_stock_days)
    roq = calculate_roq(add, target_coverage_days, safety_stock_days, gap)

    # Operational stockout metrics
    stockout_duration = max(0.0, round(lead_time_days - dos, 2)) if dos < lead_time_days else 0.0
    unfulfilled_demand = max(0.0, round(-gap, 2))

    return ReorderMetrics(
        sku=sku,
        available_stock=available_stock,
        add=add,
        lead_time_days=lead_time_days,
        target_coverage_days=target_coverage_days,
        safety_stock_days=safety_stock_days,
        dos=dos,
        ltd=ltd,
        stockout_gap=gap,
        risk_level=risk,
        roq=roq,
        stockout_duration_days=stockout_duration,
        unfulfilled_demand_units=unfulfilled_demand,
    )


def evaluate_supplier_strategy(
    metrics: ReorderMetrics,
    unit_price: float,
    shipping_cost: float,
    moq: int = 1,
    strategy_type: str = "Alpha",
) -> Dict[str, Any]:
    """
    Evaluates Strategy Alpha vs Beta trade-offs, factoring in MOQ, landed cost,
    and unfulfilled stockout duration.
    """
    effective_order_qty = max(float(moq), metrics.roq)
    unit_subtotal = round(effective_order_qty * unit_price, 2)
    landed_cost = round(unit_subtotal + shipping_cost, 2)
    effective_unit_cost = round(landed_cost / effective_order_qty, 2)

    return {
        "strategy_type": strategy_type,
        "lead_time_days": metrics.lead_time_days,
        "roq": metrics.roq,
        "effective_order_qty": effective_order_qty,
        "moq": moq,
        "unit_price": unit_price,
        "shipping_cost": shipping_cost,
        "unit_subtotal": unit_subtotal,
        "landed_cost": landed_cost,
        "effective_unit_cost": effective_unit_cost,
        "dos": metrics.dos,
        "ltd": metrics.ltd,
        "stockout_gap": metrics.stockout_gap,
        "risk_level": metrics.risk_level,
        "stockout_duration_days": metrics.stockout_duration_days,
        "unfulfilled_demand_units": metrics.unfulfilled_demand_units,
    }
