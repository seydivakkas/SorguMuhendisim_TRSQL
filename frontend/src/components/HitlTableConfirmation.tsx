import type { PlanPreview } from "../types/contracts";
import {
  extractTablesFromSqlPreview,
  inferInformationalTableHints,
} from "../utils/format";

interface PreflightProps {
  readonly mode: "preflight";
  readonly question: string;
  readonly connectionId: string;
  readonly isLoading: boolean;
  readonly planPreview: PlanPreview | null;
  readonly isPlanLoading: boolean;
  readonly planError: string | null;
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
    const showFallbackHints = !props.isPlanLoading && props.planPreview === null;
    const hints = showFallbackHints ? inferInformationalTableHints(props.question) : [];

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
          Nihai şema kapsamlama, RBAC ve 8 aşamalı SQL doğrulaması{" "}
          <strong>yalnızca sunucuda</strong> yapılır.
        </p>

        {props.isPlanLoading && (
          <p className="muted-note" style={{ margin: 0 }}>
            Sunucu planı (/v1/plan) hesaplanıyor…
          </p>
        )}

        {props.planError && (
          <div className="banner error" role="alert" style={{ padding: "0.5rem 0.75rem" }}>
            <strong>Plan önizleme hatası:</strong> {props.planError}
          </div>
        )}

        {props.planPreview !== null && (
          <div className="table-chips" aria-label="Sunucu planı tablo ve sütunları">
            {props.planPreview.tables.length > 0 ? (
              props.planPreview.tables.map((tbl) => (
                <span key={`tbl-${tbl}`} className="badge info">
                  Tablo: {tbl}
                </span>
              ))
            ) : (
              <span className="badge">Sunucu planında eşleşen tablo bulunamadı</span>
            )}
            {props.planPreview.columns.map((col) => (
              <span key={`col-${col}`} className="badge">
                Sütun: {col}
              </span>
            ))}
            {props.planPreview.metrics.map((metric) => (
              <span key={`met-${metric}`} className="badge ok">
                Metrik: {metric}
              </span>
            ))}
          </div>
        )}

        {props.planPreview?.clarification && (
          <p className="muted-note" style={{ margin: 0 }}>
            <strong>Sunucu netleştirme notu:</strong> {props.planPreview.clarification}
          </p>
        )}

        {showFallbackHints && (
          <div className="table-chips" aria-label="Bilgi amaçlı istemci tablo ipuçları">
            <span className="badge warn">Bilgi amaçlı (plan alınamadı):</span>
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
        )}

        <div className="input-row">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={props.onApprove}
            disabled={props.isLoading || props.isPlanLoading}
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
