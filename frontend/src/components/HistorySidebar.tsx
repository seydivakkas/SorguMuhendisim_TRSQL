import { OutcomeStatus, type QueryHistoryEntry } from "../types/contracts";

interface HistorySidebarProps {
  readonly items: readonly QueryHistoryEntry[];
  readonly selectedId: string | null;
  readonly onSelect: (entry: QueryHistoryEntry) => void;
  readonly onClear: () => void;
}

function statusMeta(status: OutcomeStatus): { label: string; cls: string } {
  switch (status) {
    case OutcomeStatus.ANSWERED:
      return { label: "Yanıtlandı", cls: "ok" };
    case OutcomeStatus.NEEDS_CLARIFICATION:
      return { label: "Netleştirme", cls: "info" };
    case OutcomeStatus.REJECTED:
      return { label: "Reddedildi", cls: "danger" };
    case OutcomeStatus.RETRY_BUDGET_EXHAUSTED:
      return { label: "Bütçe Doldu", cls: "warn" };
    case OutcomeStatus.ERROR:
      return { label: "Hata", cls: "danger" };
  }
}

export function HistorySidebar({
  items,
  selectedId,
  onSelect,
  onClear,
}: HistorySidebarProps) {
  return (
    <aside className="sidebar card" aria-labelledby="history-title">
      <div className="card-header" style={{ marginBottom: "0.4rem" }}>
        <h2 id="history-title" className="card-title">
          Sorgu Geçmişi
        </h2>
        {items.length > 0 && (
          <button type="button" className="btn btn-sm" onClick={onClear}>
            Temizle
          </button>
        )}
      </div>

      {items.length === 0 ? (
        <p className="muted-note" style={{ margin: 0 }}>
          Bu oturumda henüz sorgu çalıştırılmadı. Çalıştırdığınız sorular ve
          sunucu yanıtları burada listelenir.
        </p>
      ) : (
        <ul className="history-list">
          {items.map((entry) => {
            const meta = statusMeta(entry.outcome.status);
            const isActive = entry.id === selectedId;
            return (
              <li key={entry.id}>
                <button
                  type="button"
                  className={`history-item ${isActive ? "active" : ""}`}
                  onClick={() => onSelect(entry)}
                >
                  <span className="history-question">{entry.question}</span>
                  <span className="history-meta">
                    <span className={`badge ${meta.cls}`}>{meta.label}</span>
                    <span>
                      {entry.connectionId} · {entry.timestamp}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
