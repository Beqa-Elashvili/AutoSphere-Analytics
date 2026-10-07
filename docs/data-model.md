# Data Model

The database is organized into four schemas, each representing one layer of the platform.

| Schema | Layer | Keys | Rebuilt each run? | Who reads it |
|--------|-------|------|-------------------|--------------|
| `staging` | Clean source entities | Business (natural) keys | Yes | ETL (to build `dw`), DQ checks, AI pipeline |
| `dw` | Star schema warehouse | Surrogate keys | Yes (full refresh) | Power BI, `analytics` views |
| `analytics` | KPI / reporting views | — | Views (always current) | Power BI, automated reports |
| `audit` | Pipeline metadata | Identity columns | No (history kept) | Engineers, DQ dashboard |

---

## 1. Staging layer — the data contract

Staging contains data **after** Python validation and cleaning. Its constraints act as
a second line of defense. If a cleaning bug ever let an invalid row through,
PostgreSQL would reject the load rather than let it reach the warehouse.

Staging deliberately has **no foreign keys**. Each table can then be truncated
and reloaded on its own, and referential integrity is checked by the DQ framework
instead. Real foreign keys are enforced in `dw`.

### Master data

| Table | Grain (one row per…) | Business key | Notable rules |
|-------|----------------------|--------------|---------------|
| `branches` | branch | `branch_id` | `branch_type` ∈ {sales_and_service, sales_only, service_only} |
| `product_categories` | product category | `category_id` | unique name; `business_line` ∈ {vehicles, parts, accessories, consumables} |
| `products` | product (vehicle model, part, accessory) | `product_id` | `list_price > 0`, `unit_cost >= 0` |
| `employees` | employee | `employee_id` | role/department from fixed lists |
| `customers` | customer | `customer_id` | individuals need first and last name, corporates need a company name; unknown city → `'Unknown'` |
| `vehicles` | customer-owned vehicle | `vehicle_id` | VIN unique and 17 characters |

### Transactions

| Table | Grain (one row per…) | Business key | Notable rules |
|-------|----------------------|--------------|---------------|
| `sales` | invoice line | `sale_line_id` | `quantity > 0`; `discount_amount <= quantity × unit_price`; `unit_cost` stored at time of sale (needed for correct historical profit) |
| `service_orders` | service visit (work order) | `service_order_id` | `closed_at >= opened_at`; completed orders must have `closed_at` |
| `service_items` | labour or part line on a service order | `service_item_id` | part lines require `product_id`; labour hours may be fractional |
| `payments` | payment attempt | `payment_id` | `amount > 0`; currency is always `GEL`; references an invoice or a service order |
| `customer_feedback` | feedback submission | `feedback_id` | non-empty free text (Georgian/English); optional 1–5 rating |

**Why is `unit_cost` stored on each sale line?** Product costs change over
time. Calculating historical profit with *today's* cost from `products` would
misstate past margins. Storing the cost at transaction time is how ERP systems
record cost of goods sold.

**Order vs line:** an *order* is an `invoice_number`, and a *line* is one product
on that invoice. Average Order Value therefore divides revenue by **distinct
invoices**, not by line count.

---

## 2. Audit layer

| Table | Purpose |
|-------|---------|
| `pipeline_runs` | One row per execution: start and end time, status, row counts (JSONB), error message. |
| `data_quality_report` | One row per check per run: `check_name`, `table_name`, `status` (PASS/FAIL), `severity` (INFO/WARNING/CRITICAL), `failed_rows`, `message`, `executed_at`. `stage` separates checks on raw source data from post-load checks. |
| `rejected_rows` | Quarantine for every row removed during cleaning, with the reason and the original record as JSONB. Nothing is dropped silently. |

All three link to `pipeline_runs.run_id`, so every number on a dashboard can be traced back to the run that produced it.

---

## 3. Warehouse layer (star schema)

*Designed and documented in Phase 6.*
