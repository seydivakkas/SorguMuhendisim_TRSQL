import type { CellValue, ResultReport } from "../types/contracts";

const INT_FORMATTER = new Intl.NumberFormat("tr-TR", {
  maximumFractionDigits: 0,
});

const FLOAT_FORMATTER = new Intl.NumberFormat("tr-TR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
});

/**
 * Format a server-provided cell value for display in Turkish locale without
 * altering, rounding away precision, or recalculating any numbers (ADR-0008).
 */
export function formatTrCellValue(value: CellValue): string {
  if (value === null || value === undefined) {
    return "—";
  }
  if (typeof value === "boolean") {
    return value ? "Evet" : "Hayır";
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      return String(value);
    }
    if (Number.isInteger(value)) {
      return INT_FORMATTER.format(value);
    }
    return FLOAT_FORMATTER.format(value);
  }
  return String(value);
}

/**
 * Purely informational helper extracting table identifiers mentioned in ``report.sql``
 * for HITL display preview. Never used for security or authorization decisions.
 */
export function extractTablesFromSqlPreview(sql: string): string[] {
  const found = new Set<string>();
  const regex = /\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_."`]*)/gi;
  let match: RegExpExecArray | null = regex.exec(sql);
  while (match !== null) {
    const raw = match[1].replace(/["`]/g, "").trim();
    if (raw && !raw.startsWith("(")) {
      found.add(raw);
    }
    match = regex.exec(sql);
  }
  return Array.from(found);
}

const DOMAIN_TABLE_HINTS: ReadonlyArray<readonly [RegExp, string]> = [
  [/bayi/i, "dealers / bayiler"],
  [/sat[ıi][sş]|ciro|has[ıi]lat/i, "sales / siparisler"],
  [/m[üu][sş]teri/i, "musteriler"],
  [/[üu]r[üu]n|kategori/i, "urunler / kategoriler"],
  [/iade/i, "iadeler"],
  [/fatura|[öo]deme/i, "faturalar / odemeler"],
  [/stok|depo/i, "stok_hareketleri / depolar"],
  [/[çc]al[ıi][sş]an|maa[sş]|departman/i, "calisanlar / departmanlar (sunucu RBAC denetimli)"],
];

/**
 * Informational pre-flight table hint for the HITL confirmation dialog before
 * submitting to the backend. Actual schema linking & RBAC run strictly server-side.
 */
export function inferInformationalTableHints(question: string): string[] {
  const hints: string[] = [];
  for (const [pattern, label] of DOMAIN_TABLE_HINTS) {
    if (pattern.test(question)) {
      hints.push(label);
    }
  }
  return hints;
}

function csvEscape(raw: string): string {
  if (/[;"\n\r]/.test(raw)) {
    return `"${raw.replace(/"/g, '""')}"`;
  }
  return raw;
}

/**
 * Export exact server-returned rows as CSV with zero client-side recalculation.
 */
export function buildReportCsv(report: ResultReport): string {
  const header = report.columns.map((c) => csvEscape(c)).join(";");
  const lines = report.rows.map((row) =>
    row
      .map((cell) => {
        if (cell === null || cell === undefined) {
          return "";
        }
        return csvEscape(String(cell));
      })
      .join(";"),
  );
  return "\uFEFF" + [header, ...lines].join("\r\n");
}
