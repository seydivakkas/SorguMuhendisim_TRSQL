import { OutcomeStatus, type PipelineOutcome } from "../types/contracts";

interface StatusBannerProps {
  readonly outcome?: PipelineOutcome;
  readonly clientError?: string | null;
  readonly onEditQuestion?: () => void;
}

export function StatusBanner({
  outcome,
  clientError,
  onEditQuestion,
}: StatusBannerProps) {
  if (clientError) {
    return (
      <section className="banner error" role="alert">
        <div className="banner-header">
          <h3 className="banner-title">İstek / Bağlantı Hatası</h3>
          <span className="badge danger">HTTP / Ağ</span>
        </div>
        <p style={{ margin: 0 }}>{clientError}</p>
      </section>
    );
  }

  if (!outcome) {
    return null;
  }

  if (outcome.status === OutcomeStatus.REJECTED) {
    return (
      <section className="banner rejected" role="alert">
        <div className="banner-header">
          <h3 className="banner-title">Güvenlik Politikası Engeli (REJECTED)</h3>
          <span className="badge danger">
            İstek: {outcome.request_id.slice(0, 8)} · Yeniden denenmedi
          </span>
        </div>
        <p style={{ margin: 0 }}>
          {outcome.reason ||
            "Bu istek güvenlik politikası nedeniyle yerine getirilemedi."}
        </p>
        <p className="muted-note" style={{ margin: 0, color: "inherit" }}>
          ADR-0005 gereği güvenlik ihlalleri modele geri beslenmez ve yeniden
          denenmez.
        </p>
      </section>
    );
  }

  if (outcome.status === OutcomeStatus.RETRY_BUDGET_EXHAUSTED) {
    return (
      <section className="banner retry" role="alert">
        <div className="banner-header">
          <h3 className="banner-title">
            Yeniden Deneme Bütçesi Doldu (RETRY_BUDGET_EXHAUSTED)
          </h3>
          <span className="badge warn">
            {outcome.attempts} deneme · İstek: {outcome.request_id.slice(0, 8)}
          </span>
        </div>
        <p style={{ margin: 0 }}>
          {outcome.reason ||
            "Geçerli bir sorgu üretilemedi; lütfen soruyu yeniden ifade edin."}
        </p>
        {onEditQuestion && (
          <div>
            <button
              type="button"
              className="btn btn-sm"
              onClick={onEditQuestion}
            >
              Soruyu Yeniden İfade Et
            </button>
          </div>
        )}
      </section>
    );
  }

  if (outcome.status === OutcomeStatus.ERROR) {
    return (
      <section className="banner error" role="alert">
        <div className="banner-header">
          <h3 className="banner-title">Çalıştırma Hatası (ERROR)</h3>
          <span className="badge danger">
            {outcome.attempts} deneme · İstek: {outcome.request_id.slice(0, 8)}
          </span>
        </div>
        <p style={{ margin: 0 }}>
          {outcome.reason ||
            "Sorgu veritabanında yürütülürken beklenmeyen bir hata oluştu."}
        </p>
      </section>
    );
  }

  return null;
}
