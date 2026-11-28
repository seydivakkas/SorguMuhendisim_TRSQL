-- TRSQL PostgreSQL Least-Privilege Read-Only Role Setup (AR-07)
-- Password MUST be provisioned out-of-band via environment/vault; never commit passwords.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nl2sql_reader') THEN
        CREATE ROLE nl2sql_reader WITH
            LOGIN
            NOINHERIT
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOREPLICATION
            NOBYPASSRLS
            CONNECTION LIMIT 5;
    ELSE
        ALTER ROLE nl2sql_reader WITH
            LOGIN
            NOINHERIT
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOREPLICATION
            NOBYPASSRLS
            CONNECTION LIMIT 5;
    END IF;
END
$$;

-- Hardened session defaults for the nl2sql_reader role
ALTER ROLE nl2sql_reader SET default_transaction_read_only = on;
ALTER ROLE nl2sql_reader SET statement_timeout = '5000ms';
ALTER ROLE nl2sql_reader SET lock_timeout = '2000ms';
ALTER ROLE nl2sql_reader SET idle_in_transaction_session_timeout = '10000ms';
ALTER ROLE nl2sql_reader SET search_path = public;
ALTER ROLE nl2sql_reader SET row_security = on;

-- Remove unsafe PUBLIC schema privileges and grant minimal read usage
REVOKE CREATE ON SCHEMA public FROM PUBLIC, nl2sql_reader;
GRANT USAGE ON SCHEMA public TO nl2sql_reader;

-- Revoke all privileges on base tables first, then grant SELECT selectively
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM nl2sql_reader;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM nl2sql_reader;
REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public FROM nl2sql_reader;

-- Default privileges: never auto-grant write or future table access without explicit policy
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM nl2sql_reader;

-- Grant SELECT on non-sensitive analytical tables when present (idempotent across init order)
DO $$
DECLARE
    tbl text;
    allowed_tables text[] := ARRAY[
        'bolgeler', 'bayiler', 'kategoriler', 'urunler', 'depolar',
        'stok_hareketleri', 'siparisler', 'siparis_kalemleri',
        'iadeler', 'iade_kalemleri', 'faturalar', 'odemeler',
        'kampanyalar', 'satis_hedefleri', 'departmanlar', 'masraflar',
        'tedarikciler', 'satin_alma_siparisleri', 'sevkiyatlar',
        'destek_talepleri', 'cust_loyalty', 'inv_ledger',
        'sales', 'dealers'
    ];
    sensitive_tables text[] := ARRAY['salaries', 'maaslar'];
BEGIN
    FOREACH tbl IN ARRAY allowed_tables LOOP
        IF to_regclass(format('public.%I', tbl)) IS NOT NULL THEN
            EXECUTE format('GRANT SELECT ON TABLE public.%I TO nl2sql_reader', tbl);
        END IF;
    END LOOP;

    FOREACH tbl IN ARRAY sensitive_tables LOOP
        IF to_regclass(format('public.%I', tbl)) IS NOT NULL THEN
            EXECUTE format('REVOKE ALL ON TABLE public.%I FROM nl2sql_reader', tbl);
        END IF;
    END LOOP;
END
$$;

-- Restrict dangerous built-in server filesystem / sleep / dblink functions if present
DO $$
BEGIN
    REVOKE EXECUTE ON FUNCTION pg_sleep(double precision) FROM PUBLIC, nl2sql_reader;
EXCEPTION WHEN undefined_function THEN NULL;
END
$$;

DO $$
BEGIN
    REVOKE EXECUTE ON FUNCTION pg_read_file(text) FROM PUBLIC, nl2sql_reader;
    REVOKE EXECUTE ON FUNCTION pg_read_file(text, bigint, bigint) FROM PUBLIC, nl2sql_reader;
    REVOKE EXECUTE ON FUNCTION pg_read_binary_file(text) FROM PUBLIC, nl2sql_reader;
    REVOKE EXECUTE ON FUNCTION pg_ls_dir(text) FROM PUBLIC, nl2sql_reader;
EXCEPTION WHEN undefined_function THEN NULL;
END
$$;
