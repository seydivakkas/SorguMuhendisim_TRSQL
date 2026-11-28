import type { FormEvent, KeyboardEvent } from "react";

interface QuickPrompt {
  readonly label: string;
  readonly question: string;
}

const QUICK_PROMPTS: readonly QuickPrompt[] = [
  {
    label: "Trabzon en çok satış yapan 5 bayi",
    question: "Geçen ay Trabzon'daki en çok satış yapan beş bayimiz hangileri?",
  },
  {
    label: "Şehir bazında net ciro",
    question: "Son çeyrekte şehirlere göre toplam net ciro dağılımını göster.",
  },
  {
    label: "Aylık satış trendi",
    question: "Bu yıl aylık net satış trendi nasıl değişti?",
  },
  {
    label: "Belirsiz soru (Netleştirme testi)",
    question: "İyi bayiler hangileri?",
  },
  {
    label: "Yetkisiz tablo (RBAC testi)",
    question: "Maaş tablosundaki tüm çalışan maaşlarını listele.",
  },
];

interface QueryBoxProps {
  readonly question: string;
  readonly onQuestionChange: (value: string) => void;
  readonly onSubmit: () => void;
  readonly isLoading: boolean;
  readonly hitlEnabled: boolean;
  readonly onHitlToggle: (enabled: boolean) => void;
}

export function QueryBox({
  question,
  onQuestionChange,
  onSubmit,
  isLoading,
  hitlEnabled,
  onHitlToggle,
}: QueryBoxProps) {
  const trimmedLength = question.trim().length;
  const maxChars = 2000;

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!isLoading && trimmedLength > 0) {
      onSubmit();
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      if (!isLoading && trimmedLength > 0) {
        onSubmit();
      }
    }
  };

  return (
    <section className="card" aria-labelledby="query-box-title">
      <div className="card-header">
        <h2 id="query-box-title" className="card-title">
          Türkçe Sorgu Kutusu
        </h2>
        <span className="muted-note">
          {question.length} / {maxChars} karakter · Göndermek için Ctrl+Enter
        </span>
      </div>

      <form onSubmit={handleSubmit}>
        <label htmlFor="turkish-question-input" className="sr-only">
          Veritabanına sormak istediğiniz Türkçe soru
        </label>
        <textarea
          id="turkish-question-input"
          className="query-textarea"
          value={question}
          maxLength={maxChars}
          onChange={(e) => onQuestionChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Örn: Geçen ay Trabzon'daki en çok satış yapan beş bayimiz hangileri?"
          disabled={isLoading}
        />

        <div className="query-actions">
          <label className="hitl-toggle">
            <input
              type="checkbox"
              checked={hitlEnabled}
              onChange={(e) => onHitlToggle(e.target.checked)}
              disabled={isLoading}
            />
            <span>Çalıştırma öncesi kullanılan tablolar onayını göster (HITL)</span>
          </label>

          <div className="input-row">
            {question.length > 0 && (
              <button
                type="button"
                className="btn"
                onClick={() => onQuestionChange("")}
                disabled={isLoading}
              >
                Temizle
              </button>
            )}
            <button
              type="submit"
              className="btn btn-primary"
              disabled={isLoading || trimmedLength === 0}
            >
              {isLoading ? "Sorgulanıyor…" : "Sorguyu Çalıştır"}
            </button>
          </div>
        </div>
      </form>

      <div className="quick-prompts" aria-label="Örnek kurumsal sorular">
        <span className="muted-note">Örnek sorular:</span>
        {QUICK_PROMPTS.map((item) => (
          <button
            key={item.label}
            type="button"
            className="prompt-chip"
            onClick={() => onQuestionChange(item.question)}
            disabled={isLoading}
          >
            {item.label}
          </button>
        ))}
      </div>
    </section>
  );
}
