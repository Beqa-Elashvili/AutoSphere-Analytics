# Architecture

> AutoSphere Analytics is a **fictional** automotive and mobility company. All data is
> synthetic and generated locally. This is an independent portfolio project.

## 1. Goal

Turn raw operational data (sales, service orders, payments, customer feedback)
into trusted, analysis-ready information for management. The platform answers
questions like *"Which branch is losing revenue?"* or *"Are waiting-time
complaints increasing?"*.

## 2. High-level data flow

```mermaid
flowchart LR
    subgraph SRC[Sources]
        CSV[Raw CSV files<br/>data/raw/<br/>synthetic, with DQ issues]
    end

    subgraph PY[Python ETL - etl/]
        EX[Extract<br/>read as text,<br/>schema check]
        VC[Validate and Clean<br/>DQ rules, normalize,<br/>deduplicate, quarantine]
    end

    subgraph PG[PostgreSQL]
        STG[(staging schema<br/>clean, typed rows)]
        DW[(dw schema<br/>star schema:<br/>dims + facts)]
        AN[(analytics schema<br/>KPI views)]
        AUD[(audit schema<br/>DQ report, run log)]
    end

    subgraph AI[AI / NLP - ai/]
        CLS[Feedback classifier<br/>Gemini or local rules]
    end

    CSV --> EX --> VC --> STG
    VC -- rejected rows --> AUD
    STG -- SQL transforms --> DW
    STG -- feedback text --> CLS -- sentiment, topic, confidence --> DW
    DW --> AN
    DW -- post-load checks --> AUD
    AN --> PBI[Power BI<br/>dashboards]
    DW --> PBI
    AN --> RPT[Automated report<br/>reports/]
```

## 3. Layers and responsibilities

| # | Layer | Location | Responsibility |
|---|-------|----------|----------------|
| 1 | **Raw** | `data/raw/*.csv` | Source data exactly as received. Never modified. Contains deliberate quality problems. |
| 2 | **Extract** | `etl/extract/` | Reads CSVs as text, so bad values aren't lost to type conversion. Checks that expected columns exist. |
| 3 | **Validate and Clean** | `etl/validation/`, `etl/transform/` | Runs reusable DQ rules. Normalizes casing, cities, dates and categories. Removes duplicates. Rejected rows are quarantined with a reason. |
| 4 | **Staging** | PostgreSQL `staging` schema | Clean, typed, deduplicated copy of each source entity. Uses business (natural) keys. |
| 5 | **Warehouse** | PostgreSQL `dw` schema | Star schema with surrogate keys: `dim_*` tables plus `fact_*` tables at a defined grain. Built from staging with SQL (the ELT step). |
| 6 | **AI enrichment** | `ai/` | Classifies feedback text into language, sentiment, topic and confidence. Results are written as structured columns into the warehouse. |
| 7 | **Analytics** | PostgreSQL `analytics` schema, `analytics/sql/` | Reusable views for KPIs (revenue, margin, AOV, growth, repeat rate, sentiment). |
| 8 | **Audit** | PostgreSQL `audit` schema | `data_quality_report` (one row per check per run) and the pipeline run log. |
| 9 | **BI** | `powerbi/` | Power BI model (star schema import), DAX measures, six dashboard pages. |
| 10 | **Reporting** | `scripts/`, scheduler docs | Scheduled refresh: pipeline, then quality checks, then a KPI summary report. |

## 4. Key design decisions

### Hybrid ETL + ELT
- **ETL in Python** for cleaning. Rules such as "normalize `tbilisi`, `TBILISI` and
  `Tbilsi` to `Tbilisi`" or "parse three different date formats" are easier to
  express and test in Python/pandas than in SQL.
- **ELT in SQL** for modelling. Once data is clean and in PostgreSQL, the
  database builds dimensions and facts (surrogate-key lookups, joins and
  aggregations). This is what it does best, and the SQL is easy to read.

### Four database schemas
Separating `staging`, `dw`, `analytics` and `audit` gives clear ownership and
permissions. Power BI only needs read access to `dw` and `analytics`, and the
`audit` tables are kept apart from business data.

### Fail fast on critical quality issues
Every DQ check has a severity (`INFO`, `WARNING` or `CRITICAL`). A `CRITICAL`
failure stops the pipeline before bad data reaches the warehouse, so dashboards
never show silently corrupted numbers.

### Reproducibility
- Synthetic data uses a fixed `RANDOM_SEED`, so every run produces the same datasets.
- The pipeline is **idempotent**: each run rebuilds staging and the warehouse
  from raw files. Running it twice gives the same result.
- Generated files (`data/`, `reports/`, `logs/`) are git-ignored and can be
  recreated with one command.

### AI is configurable and optional
- `AI_PROVIDER=gemini` with an API key uses the external model.
- An empty `AI_PROVIDER` uses a deterministic, offline rule-based classifier.
  It needs no network or cost, which makes it suitable for tests and CI.
- An API key alone never triggers paid calls. The provider must be chosen
  explicitly. Every classification row records which method produced it.

### What we deliberately did **not** add
| Not used | Why |
|----------|-----|
| Airflow / Dagster | One linear daily pipeline. A Python entry point plus an OS scheduler is enough, and an orchestrator would add infrastructure without analytical value. |
| dbt | SQL transforms are few and are kept as plain, versioned `.sql` files. dbt would be a natural next step at larger scale. |
| Microservices / web API / frontend | Power BI is the presentation layer, and nothing needs to serve data over HTTP. |
| Kubernetes | A single database and a batch job are enough. |

## 5. Configuration

All configuration comes from environment variables, resolved in
`common/config.py`. See `.env.example`.

| Variable | Purpose | Default |
|----------|---------|---------|
| `DATABASE_URL` (alias `POSTGRESQL_URL`) | PostgreSQL connection | required |
| `DB_SSLMODE` | SSL mode; managed cloud databases need `require` | `prefer` |
| `AI_PROVIDER` | `gemini`, or empty for local | empty, meaning local |
| `AI_MODEL` (alias `GEMINI_MODEL`) | Model name for the provider | `gemini-3.5-flash` |
| `AI_API_KEY` (alias `GEMINI_API_KEY`) | Provider key | - |
| `RANDOM_SEED` | Synthetic data seed | `42` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |

Database options:
- **Managed PostgreSQL**: any hosted PostgreSQL 14+ instance. Set `DATABASE_URL`.
- **Local Docker**: run `docker compose up -d`, then set
  `DATABASE_URL=postgresql://autosphere:autosphere@localhost:5432/autosphere`.

## 6. Repository map

```
common/      shared config, DB connection, logging
datagen/     synthetic data generator (clean data + injected DQ issues)
data/        raw/ (generated CSVs), processed/ (cleaned + rejected rows)
database/    schemas/ (DDL), warehouse/ (star-schema ELT SQL), views/, migrations/, seeds/
etl/         extract/, validation/, transform/, load/, pipeline.py
analytics/   sql/ (10 business questions), kpi_queries/ (independent KPI implementations)
ai/          sentiment/, classification/, pipeline.py
powerbi/     data model, DAX measures, dashboard spec
scripts/     CLI entry points (generate data, setup DB, run pipeline, checks)
tests/       pytest suite
docs/        architecture, data model, DQ, ETL, KPIs, BI, AI, interview guide
```
