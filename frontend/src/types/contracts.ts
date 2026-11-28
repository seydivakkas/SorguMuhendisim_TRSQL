/**
 * TypeScript mirrors of ``backend/core/contracts.py`` and ``backend/api/app.py``.
 *
 * L0 client rules (frontend/README.md):
 * - Zero client-side security decisions.
 * - Consume ``PipelineOutcome`` and ``ResultReport`` faithfully.
 * - Never recalculate or synthesize numeric results on the client (ADR-0008).
 */

export const OutcomeStatus = {
  ANSWERED: "answered",
  NEEDS_CLARIFICATION: "needs_clarification",
  REJECTED: "rejected",
  RETRY_BUDGET_EXHAUSTED: "retry_budget_exhausted",
  ERROR: "error",
} as const;

export type OutcomeStatus = (typeof OutcomeStatus)[keyof typeof OutcomeStatus];

export type ChartKind = "bar" | "line" | "pie" | "table";

export type CellValue = string | number | boolean | null;

export interface ChartSpec {
  readonly kind: ChartKind;
  readonly x?: string | null;
  readonly y?: string | null;
}

export interface ResultReport {
  readonly title: string;
  readonly summary: string;
  readonly columns: readonly string[];
  readonly rows: readonly (readonly CellValue[])[];
  readonly chart: ChartSpec;
  readonly sql: string;
  readonly metrics_used: readonly string[];
  readonly truncated: boolean;
}

export interface PipelineOutcome {
  readonly request_id: string;
  readonly status: OutcomeStatus;
  readonly attempts: number;
  readonly report: ResultReport | null;
  readonly clarification: string | null;
  readonly reason: string | null;
}

export interface QueryBody {
  readonly question: string;
  readonly connection_id: string;
}

export interface HealthResponse {
  readonly status: string;
}

export interface ConnectionOption {
  readonly id: string;
  readonly label: string;
  readonly description: string;
}

export interface QueryHistoryEntry {
  readonly id: string;
  readonly timestamp: string;
  readonly question: string;
  readonly connectionId: string;
  readonly outcome: PipelineOutcome;
}
