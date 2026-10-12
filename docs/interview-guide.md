# Interview Guide

Thirty questions a BI / Data / AI developer interview is likely to include. Each answer has
two parts: **the concept** (one or two sentences) and **how this project does it** (the part
that makes an answer convincing). Paths point to the evidence.

> **Tip.** Answer with the concept in one sentence, then move straight to "in my project…",
> and offer to show it. Concrete numbers (340 checks, 3,046 rows quarantined, YTD +15.6% vs a
> fake −18.5%) are more memorable than definitions.

**Contents**
1. [BI and data warehousing](#1-bi-and-data-warehousing) (Q1–Q6)
2. [ETL and data quality](#2-etl-and-data-quality) (Q7–Q12)
3. [Technology and design choices](#3-technology-and-design-choices) (Q13–Q16)
4. [Power BI and DAX](#4-power-bi-and-dax) (Q17–Q23)
5. [Scale, change and automation](#5-scale-change-and-automation) (Q24–Q26)
6. [AI](#6-ai) (Q27–Q29)
7. [Communication](#7-communication) (Q30)

---

## 1. BI and data warehousing

### Q1. What is Business Intelligence?
**Concept.** Turning operational data into trusted information that people use to make decisions.
The key words are *trusted* and *decisions*.

**In this project.** Five branches produce sales, service and feedback data. BI turns that into
answers such as "Kutaisi is down 16.4% year-to-date because it has 28% fewer orders" and
"Batumi's service got slower and customers say so". The full chain is source CSV → cleaning
and checks → warehouse → KPI views → Power BI and a daily report. Each of the 12 business
requirements ends in a *decision*, not just a chart (`docs/business-requirements.md`).

### Q2. What is a Data Warehouse?
**Concept.** A database designed for analysis rather than transactions. It is integrated (one
version of customers, products, branches), historical, and modelled for querying.

**In this project.** The PostgreSQL schema `dw` holds 7 dimensions and 5 fact tables, built
from the cleaned `staging` layer. It keeps history (SCD Type 2 customers), integrates every
source through surrogate keys, and is rebuilt idempotently: running it twice gives identical
keys and numbers (`test_rebuild_is_idempotent_with_stable_surrogate_keys`).

### Q3. OLTP vs OLAP?
**Concept.** OLTP systems run the business: many small inserts and updates, normalised tables,
the current state. OLAP systems analyse it: few large reads, denormalised star schemas, history.

**In this project.** The raw CSVs simulate OLTP exports: normalised tables, IDs, one row per
event. The `dw` schema is the OLAP side. A question like "revenue by branch, category and
month" is one join from a fact to three dimensions instead of a chain of normalised joins.
`staging` stays close to the source (business keys); `dw` is shaped for questions.

### Q4. What is a Star Schema?
**Concept.** A fact table of measurable events in the centre, joined to descriptive dimension
tables. It is simple for users and fast for BI tools.

**In this project.** `fact_sales` (grain: one invoice line) joins `dim_date`, `dim_branch`,
`dim_product`, `dim_category`, `dim_customer` and `dim_employee`. Four more facts share the
same *conformed* dimensions: service orders, service items, payments and feedback. That is
why one Branch slicer in Power BI filters sales, service and complaints together.
Diagram: `docs/data-model.md`.

### Q5. Fact vs Dimension?
**Concept.** Facts are numeric, additive measurements at a defined grain (amount, quantity).
Dimensions are the context you filter and group by (who, what, where, when).

**In this project.**
- `fact_sales` holds `quantity`, `net_amount`, `cost_amount` and `profit_amount` per invoice line.
- `dim_product` holds name, brand, price band and launch date.
- Grain matters: `fact_service_orders` (one row per order, with turnaround) and `fact_service_items` (one row per labour or part line) are separate facts. Mixing them would double-count order-level values. A test checks that order totals equal the sum of their lines (`test_service_order_grain_aggregates_its_lines`).

### Q6. Why use surrogate keys?
**Concept.** System-generated integer keys that are independent of source IDs.

**In this project.** Three concrete reasons:
1. **History.** With SCD Type 2 a customer has several versions, so `customer_id` is no longer unique and `customer_key` is.
2. **Unknown members.** Every dimension has key `-1` "Unknown" and `-2` "Not applicable". A sale whose product is missing from master data still counts in revenue under "Unknown product" instead of being silently lost (`test_master_data_gaps_map_to_unknown_instead_of_losing_sales`). Labour lines use `-2` for product.
3. **Performance and stability.** Integer joins are faster; keys stay stable across rebuilds.

## 2. ETL and data quality

### Q7. What is ETL?
**Concept.** Extract data from sources, Transform it (clean, conform, model), Load it into the target.

**In this project.** `scripts/run_pipeline.py` runs 9 logged steps (`etl/pipeline.py`):
1. extract the CSVs as text (bad values are not lost to type conversion);
2. clean and validate;
3. apply the source gate;
4. write processed files;
5. load staging, with quarantine and post-load checks in one transaction;
6. AI enrichment of the feedback;
7. build the star schema and check it;
8. build the KPI views and check them;
9. generate AI insights.

Every run is recorded in `audit.pipeline_runs`.

### Q8. ETL vs ELT?
**Concept.** In ETL the transformation happens before loading, in an external engine. In ELT the
raw data is loaded first and transformed inside the database with SQL.

**In this project.** It is deliberately **hybrid**:
- **ETL in Python** for messy row-level cleaning: normalising `tbilisi`, `TBILISI` and `Tbilsi`; parsing three date formats; detecting non-numeric amounts. This is awkward in SQL and easy to unit-test in pandas.
- **ELT in SQL** for modelling: dimensions, SCD2, facts and KPIs (`database/warehouse/*.sql`, `database/views/*.sql`). Set-based joins are what the database is best at.

I would say: "use each tool where it is strongest".

### Q9. What is Data Quality?
**Concept.** Whether data is fit for its purpose. The usual dimensions are completeness,
validity, uniqueness, consistency, timeliness and referential integrity.

**In this project.** It is a framework, not ad-hoc checks (`etl/validation/`):
- **Declarative rules.** Each check is SQL that counts violating rows, with a severity of INFO, WARNING or CRITICAL.
- **Gates at four stages.** A source gate (invalid-row rate: warning above 2%, critical above 10%), post-load checks on staging, warehouse reconciliation, and analytics plus Power BI layer reconciliation. That is 340 checks per run.
- **Rollback on critical.** A CRITICAL failure rolls the load back, so dashboards keep yesterday's good data.
- **Audit trail.** Results go to `audit.data_quality_report`; rejected rows go to `audit.rejected_rows` with a reason and the raw record.
- **Proof.** The generator injects 38 defect types, and a test proves every one of them is detected (`test_every_injected_defect_type_is_detected`).

### Q10. How do you detect duplicates?
**Concept.** Exact duplicates (the whole row repeated) vs business-key duplicates (same ID,
different content) vs fuzzy duplicates (same entity, different spelling).

**In this project.** Two levels:
1. **Exact duplicates.** Identical rows are dropped and counted (`rejected_exact_duplicate`); for example, 322 duplicate sales lines from a double export.
2. **Business-key duplicates.** Rows that share an ID but differ in content are a conflict, e.g. `rejected_duplicate_business_key` for 25 customers. They are quarantined, not guessed. The same is done for duplicate VINs on vehicles.

After loading, `unique_*` checks on every business key are CRITICAL. Exact duplicates don't count towards the invalid-row rate, because they are harmless once removed (`test_duplicates_do_not_count_towards_the_invalid_rate`).

### Q11. How do you handle missing data?
**Concept.** It depends on the field's role: reject, impute, default, or keep and flag.
The rule must be explicit, never silent.

**In this project.** A documented policy:
- **Transactions** with a missing key (a sale without a customer) are rejected, because revenue can't be attributed.
- **Master data** with gaps (a product without a list price) is kept and nullable, and reported as a WARNING. Deleting the product would delete its sales.
- **Unknown references** in the warehouse map to the "Unknown" member (-1).
- **Missing ratings** stay NULL and are excluded from averages, not treated as 0.
- **Empty feedback text** is rejected, because there is nothing to classify.

### Q12. What is referential integrity?
**Concept.** Every foreign key points to an existing parent row. No orphans.

**In this project.** Orphans are deliberately injected: sales for customer `CUS99999`,
payments for invoices that don't exist. They are caught at three levels:
1. **Cleaning.** Orphan transactions are quarantined.
2. **Staging.** `fk_*` checks are CRITICAL for transactions and WARNING for master data.
3. **Warehouse.** *Logical* foreign keys are verified set-based after each build.

The warehouse does not use *enforced* FK constraints. Enforced FK triggers made the fact
load about 6× slower on the hosted database, and the post-build check gives the same
guarantee with a clear report. I can show the measurement.

## 3. Technology and design choices

### Q13. Why PostgreSQL?
**In this project.** It's free and open source, and it has everything a small warehouse needs:
- **Schemas for layers:** `staging`, `dw`, `analytics`, `audit`, `bi`.
- **Analytics SQL:** window functions (`LAG`, `NTILE` for RFM), `percentile_cont` for median turnaround, `GROUPING SETS`, `FILTER`.
- **Fast loading:** materialized views and `COPY`.
- **Flexible storage:** `JSONB`, used for AI insight facts and quarantined raw records.
- **Portability:** a native Power BI connector, a managed cloud instance (Render), and Docker Compose for local use.

At larger scale the same model moves to a columnar warehouse (see Q24).

### Q14. Why this schema?
**In this project.** It is driven by the business questions, not by the source tables:
- **Grain per process.** Five facts: sales lines, service orders, service lines, payments, feedback.
- **Conformed dimensions** so branches can be compared across sales, service and feedback.
- **SCD2 on customers only.** Loyalty tier and city change, and revenue by tier must use the historical tier. Other dimensions are SCD1, because a corrected product name should simply be corrected.
- **Feedback as a fact with AI labels**, so sentiment can be sliced exactly like revenue.

### Q15. What is a KPI?
**Concept.** A metric tied to a business objective and a target, used to steer decisions.

**In this project.** Every KPI has a written definition in `docs/kpi-dictionary.md`: formula,
grain, inclusion rules and an owner question. Examples:
- **Revenue** = net amount of *completed* sales lines.
- **AOV** = revenue / distinct invoices, **not lines**. A test guards this (`test_aov_divides_by_orders_not_lines`).
- **Repeat Customer Rate**, **Negative Feedback Rate**, **Median Turnaround**.

### Q16. KPI vs metric?
**Concept.** Every KPI is a metric, but not every metric is a KPI. A metric measures something;
a KPI is one of the few metrics chosen to steer a goal.

**In this project.** Hundreds of metrics exist: units per category, payment attempts, label
confidence. The management report's headline cards show only five KPIs (YTD revenue,
orders, AOV, margin, service revenue) plus alerts. Median turnaround is a metric for most
people, but it is *the* KPI for the service manager: which KPI matters depends on the stakeholder.

## 4. Power BI and DAX

### Q17. Power BI architecture?
**Concept.** Power BI has three parts:
- **Power Query**: data acquisition and shaping;
- **the semantic model**: VertiPaq in-memory tables, relationships and DAX measures;
- **reports**: visuals.

Power BI Service adds publishing, refresh, sharing and security.

**In this project.**
- **Source:** Power BI imports only the `bi` schema, 17 views that form a stable contract (`database/views/10_bi.sql`).
- **Model:** a star schema with single-direction many-to-one relationships, 79 DAX measures and 8 pages (`powerbi/`).
- **Mode:** Import, not DirectQuery. The data is small (<150k rows) and the database is ~170 ms away, so Import is faster and supports all DAX.
- **Validation:** the report is checked against `scripts/powerbi_reference.py`.

### Q18. What is Power Query?
**Concept.** The ETL tool inside Power BI (M language): connect, filter, rename, merge, change types.

**In this project.** It is deliberately thin: connect to PostgreSQL, select the 17 `bi`
views, rename them (e.g. `bi.fact_sales` → `Sales`). The heavy transformations are in Python
and SQL, where they are version-controlled, tested and reused by the daily report. If cleaning
lived in Power Query, the report and the SQL KPIs could disagree, and nobody could unit-test it.

### Q19. What is DAX?
**Concept.** The formula language of the Power BI model, used for measures, calculated
columns and tables. It evaluates in a *filter context*.

**In this project.** `powerbi/dax-measures.md` has 79 measures in display folders:
- **Base:** `Revenue = SUM(Sales[net_amount])`, `DIVIDE()` everywhere.
- **Time intelligence:** `SAMEPERIODLASTYEAR`, `DATESINPERIOD`, `TOTALYTD`.
- **Inactive relationship:** `USERELATIONSHIP` for closed service orders.
- **Data quality:** status measures driving conditional formatting.

A test parses the file and checks that every referenced `Table[column]` exists in the database
and every `[Measure]` is defined.

### Q20. Measure vs calculated column?
**Concept.** A calculated column is computed at refresh, row by row, and stored (it uses
memory). A measure is computed at query time in the current filter context, and nothing is stored.

**In this project.** Almost everything is a measure. **Profit Margin %** must be
`DIVIDE([Profit], [Revenue])` over the current context; summing a row-level margin column
would be mathematically wrong. Row attributes that *would* be calculated columns are computed
in SQL instead: the YTD flags on the date table, `rating_agreement` on feedback, `rfm_segment`
on customers. They are tested once and reused by the report.

### Q21. What is filter context?
**Concept.** The set of filters active when a measure is evaluated: slicers, visual
rows and columns, and `CALCULATE` modifiers. Row context, inside iterators, is different.
`CALCULATE` turns row context into filter context.

**In this project.** Three examples:
- **Ignoring a filter on purpose:** `Branch Revenue Share % = DIVIDE([Revenue], CALCULATE([Revenue], REMOVEFILTERS(Branch)))`.
- **Replacing a filter:** `Revenue CY YTD` uses `REMOVEFILTERS('Date')` plus the YTD flag, so the headline card ignores the year slicer and always shows the comparable period.
- **Context transition:** `Repeat Customers = COUNTROWS(FILTER(VALUES(Sales[customer_id]), CALCULATE([Orders]) >= 2))`. `CALCULATE` makes [Orders] evaluate per customer.

### Q22. Time intelligence?
**Concept.** Comparing periods (YTD, LY, MoM, rolling) using a proper date table.

**In this project.** A real pitfall I designed for: the data ends on **30 September 2026**.
Comparing 2026 (9 months) with 2025 (12 months) shows **−18.5%**, but the comparable
year-to-date is actually **+15.6%**. So:
- the Date table has `is_current_ytd` / `is_prior_ytd` flags computed in SQL;
- headline cards use them;
- annual growth is shown only between two complete years (`Revenue YoY % (Complete Years)`).

SQL does the same (`v_kpi_ytd`, NULL growth for partial years), and tests check both
(`test_partial_year_has_no_misleading_annual_growth`).

### Q23. SCD Type 1 vs Type 2?
**Concept.** Type 1 overwrites the old value (no history). Type 2 closes the old row and
inserts a new version with validity dates.

**In this project.**
- `dim_customer` is **SCD2**, with `valid_from`, `valid_to`, `is_current` and a new `customer_key` per version.
- Facts look up the version **valid at the transaction date** (point-in-time join), so revenue by loyalty tier uses the tier the customer had then.
- In Power BI, distinct customers count `customer_id`, not the key.
- The other dimensions are SCD1 upserts.
- `python scripts/demo_scd2.py` shows a customer moving from silver to gold, inside a rolled-back transaction.

## 5. Scale, change and automation

### Q24. How would you scale the warehouse?
**In this project, at today's size** (~110k rows, a full rebuild in ~2 minutes), simplicity wins.
I have already hit and fixed the first scaling limits:
- **Batched checks.** Hundreds of quality checks are batched into a few round trips, because network latency dominated.
- **Materialized base views.** The KPI views read materialized base views with byte-order (`COLLATE "C"`) keys, because sorting with linguistic collation was the bottleneck.
- **Short statements.** Statements are chunked so the hosted database doesn't drop long ones.

Next steps, in order:
1. **Incremental loads:** facts are keyed by date, so load only new days instead of rebuilding.
2. **Partitioning** facts by month; indexes on fact foreign keys.
3. **Incremental refresh** in Power BI.
4. **A columnar warehouse** (BigQuery, Snowflake, Redshift) when data grows by orders of magnitude. The star schema and SQL carry over almost unchanged.
5. **An orchestrator** (Airflow, Dagster) only when there are many jobs with dependencies.

### Q25. How would you handle changing business requirements?
**In this project.** The layering is designed for change:
1. **Clear layers.** New questions usually need a new view in `analytics`, not a new pipeline.
2. **Stable contract.** The `bi` layer is a contract: warehouse tables can change without breaking the report.
3. **KPI dictionary.** A definition change ("revenue should include returns") is made once in SQL, documented in the dictionary, and reconciled automatically everywhere.
4. **Traceability.** Every requirement links question → KPI → SQL → page → test (`docs/business-requirements.md`), so I can see what a change touches.
5. **Safety net.** 238 tests and the end-to-end check catch regressions.

### Q26. How would you automate reporting?
**In this project.** `scripts/scheduled_run.py` runs daily via Windows Task Scheduler, cron
or GitHub Actions (manual button). It does the following:
- **Lock:** prevents overlapping runs.
- **Refresh:** runs the pipeline, retrying once on a connection error and *never* on a data-quality error.
- **Report:** writes an HTML and Markdown management report with rule-based alerts (Kutaisi decline, Batumi turnaround, feedback anomalies).
- **Status:** writes `last_run.json` and returns exit codes the scheduler understands.

The key principle: **a failed refresh never shows wrong numbers, only old numbers that are
clearly labelled as old.** That is the rollback plus a red banner naming the last good run.
By default the scheduled job never calls the paid AI API. (`docs/automated-reporting.md`)

## 6. AI

### Q27. Why is AI useful here?
**In this project.** Star ratings say *that* customers are unhappy; text says *why*.
10,352 comments in Georgian and English can't be read by hand. AI turns each comment into
structured columns (language, sentiment, topic, confidence), which then flow through the same
warehouse, KPIs and dashboards as revenue.

Result: management sees that Batumi's waiting-time complaints doubled (2.1× baseline) *at
the same time* as its median turnaround rose from 2.8 h to 7.1 h. Two independent sources
tell the same story. AI is one enrichment step in the BI pipeline, not a chatbot.

### Q28. How would you validate AI output?
**In this project.** Four layers:
1. **Contract.** A JSON schema with enums is sent to Gemini, validated again in Python and enforced by CHECK constraints in the database. Invalid answers fall back per item to the rule-based classifier and are marked `rule_based_fallback`.
2. **Ground truth.** On 10,352 generated items Gemini scores 95.7% sentiment and 98.0% topic accuracy. On a **hand-written held-out set** with new phrasing it scores 100% / 97.5%. The rule-based classifier looks perfect on the templates but scores only 27.5% / 35% on the held-out set, which shows why an LLM is needed.
3. **Independent signal.** AI sentiment vs the customer's own star rating: 3% contradictions, about the share deliberately injected.
4. **Numbers stay in SQL.** For the insight narratives, every fact is computed in SQL and stored with the text, and the model only writes the narrative.

### Q29. How would you monitor AI quality?
**In this project.**
- **Every run:** checks on label coverage (CRITICAL) and fallback share (WARNING above 2%).
- **Lineage:** every row stores the method and model (`gemini:gemini-3.5-flash`), so any dashboard number can be traced to the model that produced it.
- **Dashboard:** page 7 shows model share, fallback share, low-confidence labels and the rating-contradiction rate.
- **Drift:** compare label distributions month to month.
- **Human review:** low-confidence and contradicting labels are reviewed and added to the held-out set.
- **Model changes:** a model change is just configuration (`AI_MODEL`), and it is only accepted after re-running `evaluate_ai.py` on the held-out set.
- **Cost** is monitored too: cache by text hash, per-run budget, insights reused when facts are unchanged.

## 7. Communication

### Q30. How would you explain this project to a non-technical manager?
> "Every morning, the system collects yesterday's sales, service and customer-feedback data
> from all branches, checks it for errors, and only then updates the dashboards. If something
> is wrong with the data, the dashboards keep showing the last correct numbers and say so.
> It then sends you a one-page report: what is going well, and three or four things that need
> your attention. Right now: Kutaisi's sales are down 16% because fewer customers come in, and
> Batumi's service has become slow, which is exactly what customers complain about in their
> comments. The comments are read automatically by AI in Georgian and English, so you see
> *why* customers are unhappy, not just a star rating."

Then show: the management report (`reports/management/latest.html`), Power BI page 1, and the
end-to-end check (`16/16 passed`).

---

## Likely follow-up questions (short answers)

| Question | Answer from the project |
|----------|-------------------------|
| What was the hardest problem? | The hosted database dropped connections on long statements. I fixed it with materialized base views, byte-order collation keys, and chunked, batched checks. The pipeline became reliable on the hosted database. |
| What would you do differently? | Start with incremental loads and a small human-labelled feedback set (a few hundred items) from day one. |
| How do you know the numbers are right? | Every KPI is computed three independent ways (view, stand-alone SQL, pandas) and compared in tests. Revenue reconciles from warehouse to KPI views to the Power BI layer on every run. |
| How much did the AI cost? | One full classification of 10k comments was ~0.9M tokens. After that only new or edited comments are sent (cache by text hash), and the scheduled job uses free local mode by default. |
| Is the data real? | No. The company is fictional and all data is synthetic, generated with a fixed seed and with realistic defects and business stories built in. |
| What are the limitations? | Synthetic data, a small held-out AI set (40 items), full rebuild instead of incremental, and the `.pbix` must be built from the specification in Power BI Desktop. |
