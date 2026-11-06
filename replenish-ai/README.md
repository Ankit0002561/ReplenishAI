# ReplenishAI: Autonomous Supply Chain & Inventory Procurement Agent

ReplenishAI is a standalone agentic prototype for autonomous supply chain operations, inventory velocity tracking, risk triage, and procurement order formulation.

## Core Rules & Mathematical Formulas

1. **Days of Supply (DoS)**:
   $$\text{DoS} = \frac{\text{Current Available Stock}}{\text{Average Daily Demand (ADD)}}$$

2. **Lead Time Demand (LTD)**:
   $$\text{LTD} = \text{ADD} \times \text{Supplier Lead Time (Days)}$$

3. **Stockout Gap**:
   $$\text{Stockout Gap} = \text{Available Stock} - \text{LTD}$$
   *(A negative value indicates an unfulfilled deficit before the order arrives)*

4. **Recommended Order Quantity (ROQ)**:
   $$\text{ROQ} = (\text{ADD} \times (\text{Target Coverage Days} + \text{Safety Stock Days})) + \max(0, -\text{Stockout Gap})$$

5. **Risk Triage Matrix**:
   - **`CRITICAL`**: $\text{DoS} < \text{Supplier Lead Time}$ (Stockout inevitable before delivery)
   - **`HIGH`**: $\text{DoS} \le \text{Supplier Lead Time} + \text{Safety Stock Days}$ (Buffer eroded)
   - **`SAFE`**: $\text{DoS} > \text{Supplier Lead Time} + \text{Safety Stock Days}$ (Adequate coverage)

6. **Dual Strategy Evaluation**:
   - **Strategy Alpha**: Cost-Optimized (Standard lead time, lowest landed cost).
   - **Strategy Beta**: Lead-Time Optimized / Expedited (Fast delivery to eliminate/minimize stockouts).

---

## Verified Example (SKU-101)

- **Available Stock**: 15 units
- **Average Daily Demand**: 10 units/day
- **Standard Supplier Lead Time**: 5 days @ $18.00/unit
- **Expedited Supplier Lead Time**: 2 days @ $24.50/unit
- **Target Coverage**: 30 days | **Safety Stock**: 7 days

**Calculations**:
- $\text{DoS} = \frac{15}{10} = 1.50\text{ days}$
- $\text{Lead Time} = 5\text{ days} \implies \text{DoS } (1.5) < 5 \implies \mathbf{CRITICAL}$
- $\text{LTD} = 10 \times 5 = 50\text{ units}$
- $\text{Stockout Gap} = 15 - 50 = -35\text{ units}$ (3.5 days of complete stockout)
- $\text{ROQ} = (10 \times (30 + 7)) + 35 = 370 + 35 = 405\text{ units}$
- **Agent Decision**: Recommends **Strategy Beta** (Expedited: 2 days) to avoid 30 units of lost sales, arriving with only 5 units deficit vs 35 units under Strategy Alpha.

---

## 4 Agent Functional Tools

1. `inventory_lookup(sku)`: Fetches warehouse location, unit cost, and available stock.
2. `sales_history_analysis(sku, window_days=30)`: Computes Average Daily Demand (ADD), standard deviation, and velocity momentum.
3. `supplier_comparison(sku)`: Queries approved vendors for Strategy Alpha vs Strategy Beta.
4. `reorder_calculation(available_stock, add, lead_time_days, target_coverage, safety_stock)`: Computes DoS, LTD, Stockout Gap, Risk level, and ROQ.

---

## Quickstart

### 1. Run Unit Tests (Pytest)
```bash
python -m pytest tests/ -v
```

### 2. Run CLI Audit
```bash
python cli.py --sku SKU-101
python cli.py --sku SKU-102
python cli.py --sku SKU-103
```

### 3. Launch Web Dashboard (Streamlit)
```bash
python -m streamlit run app.py
```
Open your browser at `http://localhost:8501`.
