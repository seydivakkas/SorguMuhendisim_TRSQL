-- TRSQL PostgreSQL KVKK PII Masking Functions & Masked Views (AR-07)
-- Covers TCKN, tax_number, phone, email, and IBAN fields without exposing raw PII columns.

CREATE OR REPLACE FUNCTION public.trsql_mask_tckn(val text)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT CASE
        WHEN length(val) >= 4 THEN repeat('*', greatest(length(val) - 4, 7)) || right(val, 4)
        ELSE '***********'
    END;
$$;

CREATE OR REPLACE FUNCTION public.trsql_mask_tax_number(val text)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT CASE
        WHEN length(val) >= 4 THEN repeat('*', greatest(length(val) - 4, 6)) || right(val, 4)
        ELSE '**********'
    END;
$$;

CREATE OR REPLACE FUNCTION public.trsql_mask_phone(val text)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT CASE
        WHEN length(val) >= 6 THEN left(val, 4) || ' *** ** ' || right(val, 2)
        ELSE '***'
    END;
$$;

CREATE OR REPLACE FUNCTION public.trsql_mask_email(val text)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT CASE
        WHEN position('@' IN val) > 1 THEN
            left(split_part(val, '@', 1), 2) || '***@' || split_part(val, '@', 2)
        ELSE '***'
    END;
$$;

CREATE OR REPLACE FUNCTION public.trsql_mask_iban(val text)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT CASE
        WHEN length(replace(val, ' ', '')) >= 8 THEN
            left(replace(val, ' ', ''), 4) || ' **** **** **** **** ' || right(replace(val, ' ', ''), 4)
        ELSE 'TR** ****'
    END;
$$;

-- Dynamically build masked views excluding raw PII columns and replacing them with masked outputs.
DO $$
DECLARE
    target_tbl text;
    view_name text;
    select_list text;
    target_tables text[] := ARRAY['dealers', 'musteriler', 'bayiler', 'calisanlar'];
BEGIN
    FOREACH target_tbl IN ARRAY target_tables LOOP
        IF to_regclass(format('public.%I', target_tbl)) IS NULL THEN
            CONTINUE;
        END IF;

        SELECT string_agg(
            CASE lower(column_name)
                WHEN 'tckn' THEN format('public.trsql_mask_tckn(%I::text) AS %I', column_name, column_name)
                WHEN 'tc_kimlik_no' THEN format('public.trsql_mask_tckn(%I::text) AS %I', column_name, column_name)
                WHEN 'tax_number' THEN format('public.trsql_mask_tax_number(%I::text) AS %I', column_name, column_name)
                WHEN 'vergi_no' THEN format('public.trsql_mask_tax_number(%I::text) AS %I', column_name, column_name)
                WHEN 'phone' THEN format('public.trsql_mask_phone(%I::text) AS %I', column_name, column_name)
                WHEN 'telefon' THEN format('public.trsql_mask_phone(%I::text) AS %I', column_name, column_name)
                WHEN 'email' THEN format('public.trsql_mask_email(%I::text) AS %I', column_name, column_name)
                WHEN 'eposta' THEN format('public.trsql_mask_email(%I::text) AS %I', column_name, column_name)
                WHEN 'iban' THEN format('public.trsql_mask_iban(%I::text) AS %I', column_name, column_name)
                ELSE format('%I', column_name)
            END,
            ', ' ORDER BY ordinal_position
        )
        INTO select_list
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = target_tbl;

        IF select_list IS NOT NULL THEN
            view_name := format('v_%s_masked', target_tbl);
            EXECUTE format(
                'CREATE OR REPLACE VIEW public.%I AS SELECT %s FROM public.%I',
                view_name,
                select_list,
                target_tbl
            );
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nl2sql_reader') THEN
                EXECUTE format('GRANT SELECT ON public.%I TO nl2sql_reader', view_name);
            END IF;
        END IF;
    END LOOP;
END
$$;
