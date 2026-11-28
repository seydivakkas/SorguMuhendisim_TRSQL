import {
  extractTablesFromSqlPreview,
  inferInformationalTableHints,
} from "../utils/format";

interface PreflightProps {
  readonly mode: "preflight";
  readonly question: string;
  readonly connectionId: string;
  readonly isLoading: boolean;
  readonly onApprove: () => void;
  readonly onCancel: () => void;
}

interface ReportConfirmationProps {
  readonly mode: "report";
  readonly sql: string;
  readonly metricsUsed: readonly string[];
  readonly connectionId: string;
  readonly confirmed: boolean;
  readonly onToggleConfirm: () => void;
}

type HitlTableConfirmationProps = PreflightProps | ReportConfirmationProps;

export function HitlTableConfirmation(props: HitlTableConfirmationProps) {
  if (props.mode === "preflight") {
    const hints = inferInformationalTableHints(props.question);
    return (
      <section
        className="banner hitl"
        role="region"
        aria-labelledby="hitl-preflight-title"
      >
        <div className="banner-header">
          <h3 id="hitl-preflight-title" className="banner-title">
            Kullanılan Tablolar Onayı (Çalıştırma Öncesi HITL Önizlemesi)
          </h3>
          <span className="badge info">Bağlantı: {props.connectionId}</span>
        </div>

        <p className="muted-note" style={{ margin: 0 }}>
          Sorgu sunucuya gönderilmeden önce hedef bağlantı ve olası alan tabloları aşağıda
          özetlenmiştir. Nihai şema kapsamlama, RBAC ve 8 aşamalı SQL doğrulaması{" "}
          <strong>yalnızca sunucuda</strong> yapılır.
        </p>

        <div className="table-chips" aria-label="Tahmini domain tabloları">
          {hints.length > 0 ? (
            hints.map((hint) => (
              <span key={hint} className="badge info">
                {hint}
              </span>
            ))
          ) : (
            <span className="badge">
              Tablo eşleştirmesi sunucu L3 katmanında belirlenecek
            </span>
          )}
        </div>

        <div className="input-row">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={props.onApprove}
            disabled={props.isLoading}
          >
            {props.isLoading ? "Gönderiliyor…" : "Tablo Kapsamını Onayla ve Çalıştır"}
          </button>
          <button
            type="button"
            className="btn btn-sm"
            onClick={props.onCancel}
            disabled={props.isLoading}
          >
            İptal / Soruyu Düzenle
          </button>
        </div>
      </section>
    );
  }

  const tables = extractTablesFromSqlPreview(props.sql);

  return (
    <section
      className="banner hitl"
      role="region"
      aria-labelledby="hitl-report-title"
    >
      <div className="banner-header">
        <h3 id="hitl-report-title" className="banner-title">
          Kullanılan Tablolar Onayı (Sunucu Doğrulamalı)
        </h3>
        <span className={`badge ${props.confirmed ? "ok" : "warn"}`}>
          {props.confirmed ? "Analist Onaylı" : "İnceleme Bekliyor"}
        </span>
      </div>

      <p className="muted-note" style={{ margin: 0 }}>
        Aşağıdaki tablo ve metrik tanımları sunucunun onaylayıp çalıştırdığı SQL
        çıktısından görüntülenmektedir (bağlantı: <strong>{props.connectionId}</strong>).
      </p>

      <div className="table-chips" aria-label="Sorguda kullanılan tablolar">
        {tables.length > 0 ? (
          tables.map((tableName) => (
            <span key={tableName} className="badge info">
              Tablo: {tableName}
            </span>
          ))
        ) : (
          <span className="badge">Tablo adı tespit edilmedi</span>
        )}
        {props.metricsUsed.map((metric) => (
          <span key={metric} className="badge ok">
            Metrik: {metric}
          </span>
        ))}
      </div>

      <div>
        <button
          type="button"
          className={`btn btn-sm ${props.confirmed ? "" : "btn-primary"}`}
          onClick={props.onToggleConfirm}
        >
          {props.confirmed
            ? "Onay İşaretini Kaldır"
            : "Kullanılan Tabloları ve Metrikleri Onayladım"}
        </button>
      </div>
    </section>
  );
}
