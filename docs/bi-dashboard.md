# BI Dashboard

The Power BI solution is documented in [`powerbi/`](../powerbi/README.md). This page is the
short overview for business readers.

| Document | For |
|----------|-----|
| [powerbi/README.md](../powerbi/README.md) | How to connect, build, refresh and validate the report |
| [powerbi/data-model.md](../powerbi/data-model.md) | Tables, relationships, star schema, SCD2 handling |
| [powerbi/dax-measures.md](../powerbi/dax-measures.md) | All 79 DAX measures |
| [powerbi/dashboard-spec.md](../powerbi/dashboard-spec.md) | The 8 pages: questions, visuals, decisions |

## The eight pages

| # | Page | Main question | Example finding in the current data |
|---|------|---------------|-------------------------------------|
| 1 | Executive Overview | How is the business doing, and where do I look first? | Revenue **+15.6%** YTD; only Kutaisi declining |
| 2 | Sales Performance | What drives revenue and margin? | Vehicles bring revenue; tyres and consumables bring margin |
| 3 | Branch Performance | Which branches grow or decline, and why? | Kutaisi **−16.4%** YTD from **28% fewer orders** |
| 4 | Product & Category | What sells, and what earns money? | Accessories with ~60% margin but low sales: cross-sell candidates |
| 5 | Customers | Who are our customers, and who are we losing? | Champions (25% of customers) bring 57% of revenue |
| 6 | Service Operations | Are we fast and profitable in service? | Batumi median maintenance turnaround **2.8 h → 7.1 h** |
| 7 | Customer Feedback (AI) | Why are customers unhappy, and where? | Batumi waiting-time complaints at **2.1×** baseline; negative rate 39% in 2026 vs 32% in 2025 |
| 8 | Data Quality & Pipeline | Can I trust today's numbers? | 340 checks, 0 critical; 2.7% of source rows quarantined with reasons |

## Design principles

- **One number, one definition.** Power BI reads the `bi` views. These views use the same business rules as the SQL KPIs and the daily report, and they are reconciled on every run.
- **Comparable periods.** Headline growth compares the same calendar window (YTD). A partial year never shows annual growth.
- **Evidence next to AI.** The feedback page shows the real comments behind every number, and how each label was produced.
- **Trust is visible.** Page 8 shows the status of the last refresh to every user.

Expected values for validating a freshly built report: `python scripts/powerbi_reference.py`.
