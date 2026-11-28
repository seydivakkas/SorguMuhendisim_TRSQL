-- TRSQL PostgreSQL Row-Level Security (RLS) Policies (AR-07)
-- Uses fail-closed current_setting('app.tenant_id', true) and current_setting('app.user_id', true).
-- When session variables are unset or empty, policies return FALSE (zero rows exposed).

DO $$
DECLARE
    tbl text;
    tenant_tables text[] := ARRAY[
        'sales', 'dealers', 'siparisler', 'faturalar', 'odemeler',
        'musteriler', 'iadeler', 'destek_talepleri'
    ];
    has_tenant_col boolean;
    has_user_col boolean;
BEGIN
    FOREACH tbl IN ARRAY tenant_tables LOOP
        IF to_regclass(format('public.%I', tbl)) IS NULL THEN
            CONTINUE;
        END IF;

        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = tbl AND column_name = 'tenant_id'
        ) INTO has_tenant_col;

        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = tbl AND column_name = 'user_id'
        ) INTO has_user_col;

        IF has_tenant_col THEN
            EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', tbl);
            EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', tbl);
            EXECUTE format('DROP POLICY IF EXISTS trsql_tenant_isolation ON public.%I', tbl);
            EXECUTE format(
                'CREATE POLICY trsql_tenant_isolation ON public.%I '
                'FOR SELECT '
                'USING ('
                '  NULLIF(current_setting(''app.tenant_id'', true), '''') IS NOT NULL '
                '  AND tenant_id::text = current_setting(''app.tenant_id'', true)'
                ')',
                tbl
            );
        END IF;

        IF has_user_col THEN
            EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', tbl);
            EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', tbl);
            EXECUTE format('DROP POLICY IF EXISTS trsql_user_isolation ON public.%I', tbl);
            EXECUTE format(
                'CREATE POLICY trsql_user_isolation ON public.%I '
                'FOR SELECT '
                'USING ('
                '  NULLIF(current_setting(''app.user_id'', true), '''') IS NOT NULL '
                '  AND user_id::text = current_setting(''app.user_id'', true)'
                ')',
                tbl
            );
        END IF;
    END LOOP;
END
$$;
