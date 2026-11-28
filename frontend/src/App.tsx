import { useCallback, useEffect, useState } from "react";
import { fetchHealth, previewPlan, submitQuery, TrsqlApiError } from "./api/client";
import { ClarificationPanel } from "./components/ClarificationPanel";
import { Header, type HealthState } from "./components/Header";
import { HistorySidebar } from "./components/HistorySidebar";
import { HitlTableConfirmation } from "./components/HitlTableConfirmation";
import { QueryBox } from "./components/QueryBox";
import { ResultChart } from "./components/ResultChart";
import { ResultTable } from "./components/ResultTable";
import { SqlViewer } from "./components/SqlViewer";
import { StatusBanner } from "./components/StatusBanner";
import {
  OutcomeStatus,
  type ConnectionOption,
  type PipelineOutcome,
  type PlanPreview,
  type QueryHistoryEntry,
} from "./types/contracts";

const DEFAULT_CONNECTIONS: readonly ConnectionOption[] = [
  { id: "demo", label: "demo (Yerel SQLite / Demo)", description: "Sentetik demo şeması" },
  {
    id: "erp_onprem",
    label: "erp_onprem (PostgreSQL 16)",
    description: "Kurum içi salt okunur ERP veritabanı",
  },
  {
    id: "erp_raporlama",
    label: "erp_raporlama (Analitik)",
    description: "Raporlama replikası",
  },
];

const DEFAULT_API_BASE =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) || "/api";

export function App() {
  const [connectionId, setConnectionId] = useState<string>("demo");
  const [token, setToken] = useState<string>("");
  const [apiBaseUrl, setApiBaseUrl] = useState<string>(DEFAULT_API_BASE);
  const [healthState, setHealthState] = useState<HealthState>("checking");
  const [healthDetail, setHealthDetail] = useState<string>("");

  const [question, setQuestion] = useState<string>("");
  const [activeQuestion, setActiveQuestion] = useState<string>("");
  const [hitlEnabled, setHitlEnabled] = useState<boolean>(true);
  const [pendingPreflightQuestion, setPendingPreflightQuestion] = useState<
    string | null
  >(null);
  const [planPreview, setPlanPreview] = useState<PlanPreview | null>(null);
  const [isPlanLoading, setIsPlanLoading] = useState<boolean>(false);
  const [planError, setPlanError] = useState<string | null>(null);

  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [outcome, setOutcome] = useState<PipelineOutcome | null>(null);
  const [clientError, setClientError] = useState<string | null>(null);
  const [reportConfirmedIds, setReportConfirmedIds] = useState<
    Record<string, boolean>
  >({});

  const [history, setHistory] = useState<QueryHistoryEntry[]>([]);
  const [selectedHistoryId, setSelectedHistoryId] = useState<string | null>(
    null,
  );

  const checkHealth = useCallback(async () => {
    setHealthState("checking");
    try {
      const res = await fetchHealth(apiBaseUrl);
      if (res.status === "ok") {
        setHealthState("online");
        setHealthDetail("Sunucu /health yanıtı: ok");
      } else {
        setHealthState("offline");
        setHealthDetail(`Beklenmeyen durum: ${res.status}`);
      }
    } catch (err) {
      setHealthState("offline");
      setHealthDetail(
        err instanceof Error ? err.message : "API sağlık kontrolü başarısız",
      );
    }
  }, [apiBaseUrl]);

  useEffect(() => {
    void checkHealth();
  }, [checkHealth]);

  const executeQuery = useCallback(
    async (queryText: string) => {
      const cleaned = queryText.trim();
      if (!cleaned) {
        return;
      }
      setIsLoading(true);
      setClientError(null);
      setPendingPreflightQuestion(null);
      setPlanPreview(null);
      setPlanError(null);
      setActiveQuestion(cleaned);

      try {
        const result = await submitQuery(apiBaseUrl, token, {
          question: cleaned,
          connection_id: connectionId.trim() || "demo",
        });
        setOutcome(result);

        const nowLabel = new Date().toLocaleTimeString("tr-TR", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        });
        const entry: QueryHistoryEntry = {
          id: result.request_id,
          timestamp: nowLabel,
          question: cleaned,
          connectionId: connectionId.trim() || "demo",
          outcome: result,
        };
        setHistory((prev) => [entry, ...prev.slice(0, 49)]);
        setSelectedHistoryId(entry.id);
      } catch (err) {
        setOutcome(null);
        if (err instanceof TrsqlApiError) {
          setClientError(err.message);
        } else {
          setClientError("Sorgu gönderilirken beklenmeyen bir hata oluştu.");
        }
      } finally {
        setIsLoading(false);
      }
    },
    [apiBaseUrl, connectionId, token],
  );

  const loadPlanPreflight = useCallback(
    async (queryText: string) => {
      setClientError(null);
      setPendingPreflightQuestion(queryText);
      setPlanPreview(null);
      setPlanError(null);
      setIsPlanLoading(true);
      try {
        const plan = await previewPlan(apiBaseUrl, token, {
          question: queryText,
          connection_id: connectionId.trim() || "demo",
        });
        setPlanPreview(plan);
      } catch (err) {
        setPlanError(
          err instanceof TrsqlApiError
            ? err.message
            : "Plan önizlemesi alınırken beklenmeyen bir hata oluştu.",
        );
      } finally {
        setIsPlanLoading(false);
      }
    },
    [apiBaseUrl, connectionId, token],
  );

  const handleQuerySubmit = () => {
    const cleaned = question.trim();
    if (!cleaned) {
      return;
    }
    if (hitlEnabled) {
      void loadPlanPreflight(cleaned);
    } else {
      void executeQuery(cleaned);
    }
  };

  const handleSelectHistory = (entry: QueryHistoryEntry) => {
    setSelectedHistoryId(entry.id);
    setQuestion(entry.question);
    setActiveQuestion(entry.question);
    setConnectionId(entry.connectionId);
    setOutcome(entry.outcome);
    setClientError(null);
    setPendingPreflightQuestion(null);
    setPlanPreview(null);
    setPlanError(null);
  };

  const toggleReportConfirmed = (requestId: string) => {
    setReportConfirmedIds((prev) => ({
      ...prev,
      [requestId]: !prev[requestId],
    }));
  };

  return (
    <div className="app-shell">
      <Header
        connections={DEFAULT_CONNECTIONS}
        connectionId={connectionId}
        onConnectionChange={setConnectionId}
        token={token}
        onTokenChange={setToken}
        apiBaseUrl={apiBaseUrl}
        onApiBaseUrlChange={setApiBaseUrl}
        healthState={healthState}
        healthDetail={healthDetail}
        onRefreshHealth={() => void checkHealth()}
      />

      <main className="workspace">
        <HistorySidebar
          items={history}
          selectedId={selectedHistoryId}
          onSelect={handleSelectHistory}
          onClear={() => {
            setHistory([]);
            setSelectedHistoryId(null);
          }}
        />

        <div className="main-column">
          <QueryBox
            question={question}
            onQuestionChange={(val) => {
              setQuestion(val);
              if (pendingPreflightQuestion !== null) {
                setPendingPreflightQuestion(null);
                setPlanPreview(null);
                setPlanError(null);
              }
            }}
            onSubmit={handleQuerySubmit}
            isLoading={isLoading}
            hitlEnabled={hitlEnabled}
            onHitlToggle={setHitlEnabled}
          />

          {pendingPreflightQuestion && (
            <HitlTableConfirmation
              mode="preflight"
              question={pendingPreflightQuestion}
              connectionId={connectionId.trim() || "demo"}
              isLoading={isLoading}
              planPreview={planPreview}
              isPlanLoading={isPlanLoading}
              planError={planError}
              onApprove={() => void executeQuery(pendingPreflightQuestion)}
              onCancel={() => {
                setPendingPreflightQuestion(null);
                setPlanPreview(null);
                setPlanError(null);
              }}
            />
          )}

          <StatusBanner
            outcome={outcome ?? undefined}
            clientError={clientError}
            onEditQuestion={() => {
              if (activeQuestion) {
                setQuestion(activeQuestion);
              }
            }}
          />

          {outcome?.status === OutcomeStatus.NEEDS_CLARIFICATION && (
            <ClarificationPanel
              originalQuestion={activeQuestion || question}
              clarification={
                outcome.clarification ||
                "Sorunuzda belirsizlik tespit edildi; lütfen kapsamı netleştirin."
              }
              requestId={outcome.request_id}
              isLoading={isLoading}
              onRefineSubmit={(refined) => {
                setQuestion(refined);
                void executeQuery(refined);
              }}
            />
          )}

          {outcome?.status === OutcomeStatus.ANSWERED && outcome.report && (
            <div className="results-grid">
              <section className="card" aria-labelledby="report-summary-title">
                <div className="card-header">
                  <h2 id="report-summary-title" className="card-title">
                    {outcome.report.title}
                  </h2>
                  <span className="badge ok">
                    Deterministik Özet · İstek {outcome.request_id.slice(0, 8)}
                  </span>
                </div>
                <div className="summary-box">{outcome.report.summary}</div>
              </section>

              <HitlTableConfirmation
                mode="report"
                sql={outcome.report.sql}
                metricsUsed={outcome.report.metrics_used}
                connectionId={connectionId.trim() || "demo"}
                confirmed={Boolean(reportConfirmedIds[outcome.request_id])}
                onToggleConfirm={() => toggleReportConfirmed(outcome.request_id)}
              />

              <ResultChart report={outcome.report} />

              <ResultTable report={outcome.report} />

              <SqlViewer
                sql={outcome.report.sql}
                attempts={outcome.attempts}
                metricsUsed={outcome.report.metrics_used}
              />
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
