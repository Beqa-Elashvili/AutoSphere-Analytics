# database/

All PostgreSQL objects are defined as plain, versioned SQL files.

| Folder | Contents |
|--------|----------|
| `schemas/` | Baseline DDL, executed in filename order (`00_`, `01_`, ...). Idempotent (`IF NOT EXISTS`). |
| `views/` | Analytical views for the `analytics` schema (Phase 7). |
| `seeds/` | Static reference data that isn't generated (e.g. the date dimension range). |
| `migrations/` | Incremental changes for an already-deployed database. Not needed while the schema can be rebuilt from scratch; this is where `ALTER TABLE` scripts would go once the warehouse holds history that must be preserved. |

## Commands

```powershell
python scripts/setup_database.py                # create missing objects (safe to repeat)
python scripts/setup_database.py --reset --yes  # drop + recreate staging, dw, analytics, audit
python scripts/inspect_database.py              # tables and row counts
python scripts/inspect_database.py --table staging.sales
python scripts/inspect_database.py --query "SELECT * FROM audit.pipeline_runs"
```

`--reset` only ever drops the four project schemas. `public` and other schemas are never touched.

## Conventions

- `snake_case` for all identifiers. Tables are named after the entity (plural in staging).
- Business keys are text (`CUS00001`). Warehouse surrogate keys are integers (`customer_key`).
- Money is `NUMERIC(12,2)` in GEL. Floats are never used for money.
- Timestamps are business-local time (Asia/Tbilisi). Audit timestamps are `TIMESTAMPTZ`.
- Categorical columns are lowercase canonical values, enforced with `CHECK` constraints.
- Every staging row has `loaded_at` for lineage.
