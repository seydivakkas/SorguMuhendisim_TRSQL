import { useState } from "react";

interface SqlViewerProps {
  readonly sql: string;
  readonly attempts: number;
  readonly metricsUsed: readonly string[];
}

export function SqlViewer({ sql, attempts, metricsUsed }: SqlViewerProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  };

  return (
    <section className="card" aria-labelledby="sql-viewer-title">
      <div className="card-header">
        <div className="input-row" style={{ flexWrap: "wrap" }}>
          <h3 id="sql-viewer-title" className="card-title">
            SQL Görüntüleme (Salt Okunur)
          </h3>
          <span className="badge ok">
            {attempts} denemede L6 doğrulamasından geçti
          </span>
          {metricsUsed.map((metric) => (
            <span key={metric} className="badge info">
              {metric}
            </span>
          ))}
        </div>

        <button
          type="button"
          className="btn btn-sm"
          onClick={handleCopy}
          aria-label="Üretilen SQL sorgusunu panoya kopyala"
        >
          {copied ? "Kopyalandı ✓" : "SQL'i Kopyala"}
        </button>
      </div>

      <pre className="sql-pre" aria-readonly="true">
        <code>{sql}</code>
      </pre>
    </section>
  );
}
