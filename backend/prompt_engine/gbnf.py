from __future__ import annotations

from backend.core.contracts import Dialect, ReasoningMode, SchemaSnapshot


def _gbnf_literal(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _schema_identifier_rules(schema: SchemaSnapshot | None) -> list[str]:
    if schema is None or not schema.tables:
        return [
            "table-name ::= identifier",
            "column-name ::= identifier",
        ]

    table_names = sorted({t.name for t in schema.tables})
    col_names = sorted({c.name for t in schema.tables for c in t.columns})
    lines: list[str] = []
    if table_names:
        opts = " | ".join(_gbnf_literal(name) for name in table_names)
        lines.append(f"table-name ::= {opts}")
    else:
        lines.append("table-name ::= identifier")

    if col_names:
        opts = " | ".join(_gbnf_literal(name) for name in col_names)
        lines.append(f"column-name ::= {opts}")
    else:
        lines.append("column-name ::= identifier")
    return lines


def build_sql_gbnf(
    dialect: Dialect = Dialect.SQLITE,
    *,
    schema: SchemaSnapshot | None = None,
    allow_thinking: bool = False,
    fenced: bool = False,
) -> str:
    """Build a llama.cpp GBNF grammar constraining output to read-only SELECT queries.

    When ``allow_thinking=True``, the ``<think>...</think>`` reasoning block stays
    unconstrained and the SQL grammar constraint applies only to the final SQL
    output block after ``</think>`` (F7).
    """
    lines: list[str] = [
        f"# TRSQL read-only SELECT GBNF grammar (dialect={dialect.value}, allow_thinking={allow_thinking})",
    ]
    if allow_thinking:
        lines.append(
            "# Note: <think>...</think> reasoning stays unconstrained; grammar constrains only final SQL."
        )
        lines.append("root ::= think-block? ws sql-output ws")
        lines.append('think-block ::= "<think>" think-content "</think>" ws')
        lines.append(
            'think-content ::= ([^<] | "<" [^/] | "</" [^t] | "</t" [^h] '
            '| "</th" [^i] | "</thi" [^n] | "</thin" [^k] | "</think" [^>])*'
        )
    else:
        lines.append("root ::= ws sql-output ws")

    if fenced:
        lines.append('sql-output ::= "```sql" ws select-query (ws ";")? ws "```"')
    else:
        lines.append('sql-output ::= select-query (ws ";")?')

    lines.extend(
        [
            "select-query ::= with-clause? select-core (ws union-op ws select-core)*",
            'with-clause ::= "WITH" ws cte-def (ws "," ws cte-def)* ws',
            'cte-def ::= identifier ws "AS" ws "(" ws select-query ws ")"',
            'union-op ::= "UNION ALL" | "UNION"',
            (
                "select-core ::= select-clause from-clause? where-clause? "
                "group-by-clause? having-clause? order-by-clause? limit-clause?"
            ),
            'select-clause ::= "SELECT" ws ("DISTINCT" ws)? select-list',
            'select-list ::= select-item (ws "," ws select-item)*',
            'select-item ::= "*" | table-ref ".*" | expr (ws "AS" ws identifier)?',
            'from-clause ::= ws "FROM" ws table-source join-clause*',
            'table-source ::= (table-name | "(" ws select-query ws ")") (ws ("AS" ws)? identifier)?',
            (
                'join-clause ::= ws ("INNER " | "LEFT " | "RIGHT " | "FULL ")? '
                '"JOIN" ws table-source ws "ON" ws condition'
            ),
            'where-clause ::= ws "WHERE" ws condition',
            'group-by-clause ::= ws "GROUP BY" ws expr (ws "," ws expr)*',
            'having-clause ::= ws "HAVING" ws condition',
            'order-by-clause ::= ws "ORDER BY" ws order-item (ws "," ws order-item)*',
            'order-item ::= expr (ws ("ASC" | "DESC"))?',
            'limit-clause ::= ws "LIMIT" ws number (ws "OFFSET" ws number)?',
            'condition ::= predicate (ws ("AND" | "OR") ws predicate)*',
            (
                'predicate ::= ("NOT" ws)? (expr ws comp-op ws expr '
                '| expr ws ("NOT ")? "IN" ws "(" ws (select-query | literal-list) ws ")" '
                '| expr ws ("NOT ")? "BETWEEN" ws expr ws "AND" ws expr '
                '| expr ws "IS" ws ("NOT " )? "NULL" '
                '| "(" ws condition ws ")")'
            ),
            'literal-list ::= literal (ws "," ws literal)*',
        ]
    )

    if dialect is Dialect.POSTGRES:
        lines.append(
            'comp-op ::= "=" | "<>" | "!=" | "<=" | ">=" | "<" | ">" | "ILIKE" | "LIKE" | "NOT LIKE"'
        )
        lines.append(
            'func-name ::= "COUNT" | "SUM" | "AVG" | "MIN" | "MAX" | "COALESCE" | "NULLIF" '
            '| "ROUND" | "LOWER" | "UPPER" | "DATE_TRUNC" | "EXTRACT"'
        )
        lines.append('expr ::= term (ws ("+" | "-" | "*" | "/" | "||") ws term)* ("::" identifier)?')
    else:
        lines.append('comp-op ::= "=" | "<>" | "!=" | "<=" | ">=" | "<" | ">" | "LIKE" | "NOT LIKE"')
        lines.append(
            'func-name ::= "COUNT" | "SUM" | "AVG" | "MIN" | "MAX" | "COALESCE" | "IFNULL" '
            '| "NULLIF" | "ROUND" | "LOWER" | "UPPER" | "STRFTIME" | "DATE" | "DATETIME"'
        )
        lines.append('expr ::= term (ws ("+" | "-" | "*" | "/" | "||") ws term)*')

    lines.extend(
        [
            'term ::= func-call | case-expr | column-ref | literal | "(" ws expr ws ")"',
            'func-call ::= func-name "(" ws ("*" | ("DISTINCT" ws)? expr (ws "," ws expr)*)? ws ")"',
            (
                'case-expr ::= "CASE" (ws "WHEN" ws condition ws "THEN" ws expr)+ '
                '(ws "ELSE" ws expr)? ws "END"'
            ),
            'column-ref ::= (identifier ".")? column-name',
            "table-ref ::= identifier",
            *_schema_identifier_rules(schema),
            'literal ::= string-literal | number | "NULL" | "TRUE" | "FALSE"',
            'string-literal ::= "\'" ([^\'\n\r] | "\'\'")* "\'"',
            'number ::= "-"? [0-9]+ ("." [0-9]+)?',
            "identifier ::= [a-zA-Z_][a-zA-Z0-9_]*",
            "ws ::= [ \\t\\n\\r]*",
        ]
    )
    return "\n".join(lines)


def build_gbnf_grammar_for_mode(
    dialect: Dialect,
    mode: ReasoningMode,
    *,
    schema: SchemaSnapshot | None = None,
    fenced: bool = False,
) -> str:
    """Convenience wrapper selecting ``allow_thinking`` from ``ReasoningMode``."""
    return build_sql_gbnf(
        dialect,
        schema=schema,
        allow_thinking=(mode is ReasoningMode.THINKING),
        fenced=fenced,
    )
