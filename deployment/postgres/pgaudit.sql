-- TRSQL PostgreSQL Audit Logging Configuration (pgAudit + KVKK-safe settings)
-- Requires shared_preload_libraries = 'pgaudit' in postgresql.conf when pgAudit is enabled.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'pgaudit') THEN
        CREATE EXTENSION IF NOT EXISTS pgaudit;
    END IF;
EXCEPTION WHEN insufficient_privilege THEN
    RAISE NOTICE 'pgAudit extension could not be created due to insufficient privilege; skipping.';
END
$$;

-- Apply pgAudit settings scoped to nl2sql_reader role if available and pgAudit is loaded
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nl2sql_reader')
       AND EXISTS (SELECT 1 FROM pg_settings WHERE name = 'pgaudit.log') THEN
        ALTER ROLE nl2sql_reader SET pgaudit.log = 'read, ddl, role, misc';
        ALTER ROLE nl2sql_reader SET pgaudit.log_catalog = 'off';
        ALTER ROLE nl2sql_reader SET pgaudit.log_parameter = 'off'; -- KVKK: avoid unmasked parameter values in logs
        ALTER ROLE nl2sql_reader SET pgaudit.log_relation = 'on';
        ALTER ROLE nl2sql_reader SET pgaudit.log_statement_once = 'on';
    END IF;
END
$$;

-- Standard PostgreSQL slow/connection audit settings (no PII parameter leakage)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nl2sql_reader') THEN
        ALTER ROLE nl2sql_reader SET log_min_duration_statement = '1000ms';
    END IF;
END
$$;
