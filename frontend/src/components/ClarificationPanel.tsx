import { useState, type FormEvent } from "react";

interface ClarificationPanelProps {
  readonly originalQuestion: string;
  readonly clarification: string;
  readonly requestId: string;
  readonly isLoading: boolean;
  readonly onRefineSubmit: (refinedQuestion: string) => void;
}

export function ClarificationPanel({
  originalQuestion,
  clarification,
  requestId,
  isLoading,
  onRefineSubmit,
}: ClarificationPanelProps) {
  const [reply, setReply] = useState("");

  const handleCombinedSubmit = (event: FormEvent) => {
    event.preventDefault();
    const cleaned = reply.trim();
    if (!cleaned || isLoading) {
      return;
    }
    const combined = `${originalQuestion.trim()} (${cleaned})`;
    onRefineSubmit(combined);
  };

  const handleReplaceSubmit = () => {
    const cleaned = reply.trim();
    if (!cleaned || isLoading) {
      return;
    }
    onRefineSubmit(cleaned);
  };

  return (
    <section
      className="banner clarification"
      role="region"
      aria-labelledby="clarification-title"
    >
      <div className="banner-header">
        <h3 id="clarification-title" className="banner-title">
          Netleştirme Gerekli (L2 Türkçe Çözümleme)
        </h3>
        <span className="badge info">İstek: {requestId.slice(0, 8)}</span>
      </div>

      <p style={{ margin: 0 }}>
        <strong>Sorunuz:</strong> {originalQuestion}
      </p>
      <p style={{ margin: 0 }}>
        <strong>Sistem Yanıtı:</strong> {clarification}
      </p>

      <form onSubmit={handleCombinedSubmit} style={{ marginTop: "0.4rem" }}>
        <label
          htmlFor="clarification-reply-input"
          className="control-label"
          style={{ display: "block", marginBottom: "0.3rem" }}
        >
          Eksik ölçüt, tarih aralığı veya detayı ekleyin
        </label>
        <div className="input-row" style={{ flexWrap: "wrap" }}>
          <input
            id="clarification-reply-input"
            type="text"
            className="text-input"
            style={{ flex: "1 1 280px" }}
            value={reply}
            onChange={(e) => setReply(e.target.value)}
            placeholder="Örn: Geçen ay net satış tutarına göre en yüksek 5 bayi"
            disabled={isLoading}
          />
          <button
            type="submit"
            className="btn btn-primary btn-sm"
            disabled={isLoading || reply.trim().length === 0}
          >
            Soruyu Tamamla ve Gönder
          </button>
          <button
            type="button"
            className="btn btn-sm"
            onClick={handleReplaceSubmit}
            disabled={isLoading || reply.trim().length === 0}
          >
            Doğrudan Bu Soruyla Ara
          </button>
        </div>
      </form>
    </section>
  );
}
