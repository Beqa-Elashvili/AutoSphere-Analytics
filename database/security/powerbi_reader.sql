-- =============================================================================
-- powerbi_reader.sql — read-only login for Power BI (least privilege)
--
-- NOT run by the pipeline. Optional: run it once, manually, as the database owner with
-- psql (the password is passed as a variable, so it never appears in this file):
--   psql "$DATABASE_URL" -v reader_password="'<strong password>'" -f database/security/powerbi_reader.sql
-- Without it, Power BI can connect with the owner login (fine for a local portfolio demo).
--
-- Result: Power BI can read the `bi` views and nothing else. It cannot see staging,
-- the raw warehouse tables, rejected rows (raw records) or customer contact data, and
-- it cannot write anything. Views run with the owner's rights, so SELECT on `bi` is enough.
-- =============================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'powerbi_reader') THEN
        CREATE ROLE powerbi_reader LOGIN;
    END IF;
END $$;

ALTER ROLE powerbi_reader WITH PASSWORD :reader_password;
ALTER ROLE powerbi_reader SET default_transaction_read_only = on;
ALTER ROLE powerbi_reader SET statement_timeout = '60s';

GRANT USAGE ON SCHEMA bi TO powerbi_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA bi TO powerbi_reader;
-- Views are recreated by every pipeline run: grant SELECT on future views automatically.
ALTER DEFAULT PRIVILEGES IN SCHEMA bi GRANT SELECT ON TABLES TO powerbi_reader;

REVOKE ALL ON SCHEMA staging, dw, analytics, audit FROM powerbi_reader;
