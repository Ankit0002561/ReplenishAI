"""
Four Agent Functional Tools for ReplenishAI:
1. inventory_lookup(sku)
2. sales_history_analysis(sku)
3. supplier_comparison(sku)
4. reorder_calculation(available_stock, add, lead_time_days)
"""

import math
from typing import Dict, List, Any, Optional
from data.database import get_product, get_suppliers_for_sku, get_sales_log_for_sku
from agent.formulas import compute_all_reorder_metrics, evaluate_supplier_strategy


def inventory_lookup(sku: str) -> Dict[str, Any]:
    """
    Tool 1: inventory_lookup(sku)
    Retrieves real-time warehouse inventory and metadata for the requested SKU.
    """
    clean_sku = sku.strip().upper()
    product = get_product(clean_sku)
    if not product:
        return {
            "status": "error",
            "sku": clean_sku,
            "message": f"Product with SKU '{clean_sku}' not found in inventory catalog."
        }

    return {
        "status": "success",
        "sku": product["sku"],
        "name": product["name"],
        "category": product["category"],
        "available_stock": float(product["available_stock"]),
        "unit_cost": float(product["unit_cost"]),
        "reorder_point": float(product["reorder_point"]),
        "warehouse_location": product["warehouse_location"]
    }


def sales_history_analysis(sku: str, window_days: int = 30) -> Dict[str, Any]:
    """
    Tool 2: sales_history_analysis(sku)
    Queries historical demand logs, calculates Average Daily Demand (ADD),
    demand variance, and velocity momentum.
    """
    clean_sku = sku.strip().upper()
    logs = get_sales_log_for_sku(clean_sku, days=window_days)
    if not logs:
        return {
            "status": "error",
            "sku": clean_sku,
            "message": f"No sales log entries recorded for SKU '{clean_sku}'."
        }

    daily_units = [float(row["units_sold"]) for row in logs]
    total_sales = sum(daily_units)
    num_days = len(daily_units)
    add = round(total_sales / num_days, 2) if num_days > 0 else 0.0

    # Calculate standard deviation
    if num_days > 1:
        variance = sum((x - add) ** 2 for x in daily_units) / (num_days - 1)
        std_dev = round(math.sqrt(variance), 2)
    else:
        std_dev = 0.0

    # Trend detection (comparing first half vs second half)
    half = num_days // 2
    if half > 0:
        first_half_avg = sum(daily_units[:half]) / half
        second_half_avg = sum(daily_units[half:]) / (num_days - half)
        diff = second_half_avg - first_half_avg
        if diff > 0.5:
            trend = "ACCELERATING"
        elif diff < -0.5:
            trend = "DECELERATING"
        else:
            trend = "STABLE"
    else:
        trend = "STABLE"

    return {
        "status": "success",
        "sku": clean_sku,
        "window_days": num_days,
        "total_units_sold": total_sales,
        "add": add,  # Average Daily Demand
        "std_dev": std_dev,
        "min_demand": min(daily_units),
        "max_demand": max(daily_units),
        "trend": trend,
        "history": daily_units
    }


def supplier_comparison(sku: str) -> Dict[str, Any]:
    """
    Tool 3: supplier_comparison(sku)
    Retrieves qualified vendors capable of fulfilling this SKU, including
    Strategy Alpha (Cost-Optimized Standard) and Strategy Beta (Speed-Optimized Expedited).
    """
    clean_sku = sku.strip().upper()
    suppliers = get_suppliers_for_sku(clean_sku)
    if not suppliers:
        return {
            "status": "error",
            "sku": clean_sku,
            "message": f"No active suppliers configured for SKU '{clean_sku}'."
        }

    alpha_supplier = next((s for s in suppliers if s["strategy_type"] == "Alpha"), None)
    beta_supplier = next((s for s in suppliers if s["strategy_type"] == "Beta"), None)

    return {
        "status": "success",
        "sku": clean_sku,
        "total_suppliers_found": len(suppliers),
        "alpha_supplier": alpha_supplier,
        "beta_supplier": beta_supplier,
        "all_suppliers": suppliers
    }


def reorder_calculation(
    available_stock: float,
    add: float,
    lead_time_days: int,
    target_coverage_days: int = 30,
    safety_stock_days: int = 7,
    sku: str = "GENERIC"
) -> Dict[str, Any]:
    """
    Tool 4: reorder_calculation(available_stock, add, lead_time_days)
    Computes mathematical replenishment metrics: DoS, LTD, Stockout Gap, Risk Triage, and ROQ.
    """
    metrics = compute_all_reorder_metrics(
        sku=sku,
        available_stock=available_stock,
        add=add,
        lead_time_days=lead_time_days,
        target_coverage_days=target_coverage_days,
        safety_stock_days=safety_stock_days,
    )

    return {
        "status": "success",
        "sku": sku,
        "available_stock": metrics.available_stock,
        "add": metrics.add,
        "lead_time_days": metrics.lead_time_days,
        "target_coverage_days": metrics.target_coverage_days,
        "safety_stock_days": metrics.safety_stock_days,
        "dos": metrics.dos,
        "ltd": metrics.ltd,
        "stockout_gap": metrics.stockout_gap,
        "risk_level": metrics.risk_level,
        "roq": metrics.roq,
        "stockout_duration_days": metrics.stockout_duration_days,
        "unfulfilled_demand_units": metrics.unfulfilled_demand_units,
    }
