# Data Sources

All data is **synthetic**, generated locally by `scripts/generate_data.py` for the
fictional company AutoSphere Analytics. No real company, customer or employee data is used.
Names are random combinations of common Georgian first and last names. Emails use the
reserved `example.com` domain, and every brand and vehicle make is invented.

```powershell
python scripts/generate_data.py               # full size (~45 s), seed 42
python scripts/generate_data.py --scale 0.1   # 10% size for quick experiments
```

The same seed always produces byte-identical datasets. Generated files are git-ignored
and can be recreated at any time.

## Folders

| Folder | Contents |
|--------|----------|
| `raw/` | 11 CSV files as a source system would export them: all text, UTF-8, **with data-quality problems**. Plus `_generation_manifest.json`. |
| `processed/` | Cleaned outputs and rejected-row extracts written by the ETL (Phase 4+). |
| `evaluation/` | `feedback_labels.csv`: the generator's ground-truth language, sentiment and topic for every feedback record. **Used only to measure AI accuracy (Phase 8), never by the pipeline.** |

## Datasets

Business period: **2024-01-01 → 2026-09-30**. Currency: **GEL**.

| File | Rows (raw) | Grain | Description |
|------|-----------:|-------|-------------|
| `branches.csv` | ~9 | branch | 8 branches in Tbilisi (3), Batumi (2), Kutaisi, Rustavi and Zugdidi. One is service-only and one is a sales-only parts store. |
| `product_categories.csv` | ~13 | category | 12 categories across 4 business lines (vehicles, parts, accessories, consumables) |
| `products.csv` | ~42 | product | 40 products: new and used vehicles, tires, batteries, brakes, filters, oils, accessories |
| `employees.csv` | ~92 | employee | 90 staff: managers, sales consultants, service advisors, technicians, cashiers |
| `customers.csv` | ~5,075 | customer | 5,000 customers (8% corporate) |
| `vehicles.csv` | ~2,020 | vehicle | 2,000 customer-owned vehicles, with a unique VIN each |
| `sales.csv` | ~32,500 | invoice line | ~32,000 lines on ~13,500 invoices |
| `service_orders.csv` | ~11,100 | service visit | 11,000 work orders: maintenance, repair, diagnostics, tires, body work, warranty |
| `service_items.csv` | ~27,000 | service line | labour and part lines. Warranty work is billed at 0 GEL |
| `payments.csv` | ~25,100 | payment attempt | completed, failed and refunded payments for invoices and service orders |
| `customer_feedback.csv` | ~10,600 | feedback | free-text feedback, about 60% Georgian and 40% English, with an optional 1–5 rating |

## How the data is generated

Generation runs in two independent stages:

1. **Clean generation** (`datagen/generate.py`) produces internally consistent data:
   - every foreign key resolves;
   - customers never buy before registering, and products are never sold before launch;
   - completed payments add up exactly to invoice totals;
   - completed service orders always have a close time.
2. **Defect injection** (`datagen/corrupt.py`) serializes the data to text and injects
   38 types of data-quality problems. Each defect touches a distinct row, and its count
   is written to `raw/_generation_manifest.json`. The manifest lets later phases *prove*
   that the DQ framework catches what was injected.

### Injected data-quality problems

| Expected handling | Issue types |
|-------------------|-------------|
| **normalize** (fix and keep) | non-ISO date formats (`15.03.2025`, `15/03/2025`, `15-Mar-2025`), mis-cased categories (`In-Store`, `COMPLETED`, `canceled`, `labour`), city variants (`tbilisi`, `Tbilsi`, `თბილისი`), padded or lowercase IDs, decimal commas (`245,00`), currency casing (`gel`), missing city (becomes `Unknown`) |
| **deduplicate** | exact duplicate rows, the same key with cosmetic differences, the same VIN under two vehicle IDs |
| **nullify** (keep row, drop bad value) | missing or malformed email, rating outside 1–5 |
| **reject** (quarantine with reason) | negative or zero quantities, negative, zero or `N/A` amounts, discount above line value, non-GEL currency, orphan customer, product, branch, employee, vehicle, category or service-order IDs, future dates, unparseable dates, service closed before it opened, completed order without a close time, part line without a product, empty feedback text, missing model year |

**Date convention:** the source systems use **day-first** dates. `03/04/2025` means 3 April 2025.

## Business stories in the data

These trends are generated on purpose, so the dashboards and AI analysis have real insights to surface:

| Story | Where it shows up |
|-------|-------------------|
| Overall growth with seasonality: tire sales peak in spring and autumn, batteries in winter, service volume in winter | Revenue trend, category performance |
| **Kutaisi (BR05) revenue declines** from Q4 2025 (about −17% YTD in 2026) | Branch performance, declining branches |
| **Batumi (BR04) service slows down in 2026**: median maintenance turnaround rises from ~3h to ~5h (other branches stay at 3h) | Service analytics |
| …which causes **waiting-time complaints in Batumi to rise** | AI feedback page |
| **2026 price increase**: negative price feedback rises from ~25% to ~50% | AI feedback, topic trends |
| **Zugdidi (BR07) availability complaints**: about 11% of its feedback, versus ~5% at most branches | AI feedback by branch |
| **Rustavi (BR06) staff complaints** are above average | Sentiment by branch and topic |
| **Tbilisi Vake (BR01) service quality improves** over time | Sentiment trend |
| A low-volume, high-margin product exists (ceramic coating kit, ~71% margin) | "Low sales but high margin" requirement |
| Vehicles are about 70% of revenue but have thin margins (~8%). Parts and accessories carry the margin | Profit vs revenue by category |

Values are synthetic, so exact percentages depend on the seed. With the default seed 42, the stories above are clearly visible.
