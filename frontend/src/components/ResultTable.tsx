import type { ResultReport } from "../types/contracts";
import { buildReportCsv, formatTrCellValue } from "../utils/format";

interface ResultTableProps {
  readonly report: ResultReport;
}

export function ResultTable({ report }: ResultTableProps) {
  const numericColumnFlags = report.columns.map((_, colIdx) =>
    report.rows.some((row) => typeof row[colIdx] === "number"),
  );

  const handleDownloadCsv = () => {
    const csv = buildReportCsv(report);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "trsql-sonuc.csv";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <section className="card" aria-labelledby="result-table-title">
      <div className="card-header">
        <div className="input-row">
          <h3 id="result-table-title" className="card-title">
            Deterministik Sonuç Tablosu
          </h3>
          <span className="badge">{report.rows.length} satır</span>
          {report.truncated && (
            <span className="badge warn">Satır Sınırı Nedeniyle Kısaltıldı</span>
          )}
        </div>

        <button
          type="button"
          className="btn btn-sm"
          onClick={handleDownloadCsv}
          disabled={report.columns.length === 0}
        >
          CSV İndir
        </button>
      </div>

      {report.truncated && (
        <p className="muted-note" style={{ marginTop: 0 }}>
          Sunucu güvenlik politikası satır sınırı nedeniyle yalnızca ilk{" "}
          {report.rows.length} satır döndürüldü.
        </p>
      )}

      {report.rows.length === 0 ? (
        <p className="muted-note" style={{ margin: 0 }}>
          Sorgu sonuç döndürmedi.
        </p>
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                {report.columns.map((col, idx) => (
                  <th
                    key={`${col}-${idx}`}
                    scope="col"
                    className={numericColumnFlags[idx] ? "num" : undefined}
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {report.rows.map((row, rowIdx) => (
                <tr key={rowIdx}>
                  {report.columns.map((_, colIdx) => {
                    const cell = row[colIdx] ?? null;
                    const isNum = typeof cell === "number";
                    return (
                      <td
                        key={colIdx}
                        className={isNum || numericColumnFlags[colIdx] ? "num" : undefined}
                      >
                        {formatTrCellValue(cell)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
