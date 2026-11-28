import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { App } from "./App";
import { previewPlan, TrsqlApiError } from "./api/client";
import { OutcomeStatus, type PipelineOutcome, type PlanPreview } from "./types/contracts";

function jsonResponse(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Error",
    json: async () => payload,
  } as Response;
}

const SAMPLE_PLAN: PlanPreview = {
  request_id: "11111111-1111-1111-1111-111111111111",
  status: OutcomeStatus.ANSWERED,
  intent: "ranking",
  tables: ["dealers", "sales"],
  columns: ["dealers.name", "sales.total_amount"],
  join_path: [],
  metrics: ["net_sales@v1"],
  rules: ["geçerli sipariş"],
  clarification: null,
  template_matched: null,
};

const SAMPLE_OUTCOME: PipelineOutcome = {
  request_id: "22222222-2222-2222-2222-222222222222",
  status: OutcomeStatus.ANSWERED,
  attempts: 1,
  report: {
    title: "Bayi Net Cirosu",
    summary: "Trabzon ilinde toplam 1 bayi listelendi.",
    columns: ["name", "net_sales"],
    rows: [["Karadeniz Ticaret", 150000]],
    chart: { kind: "table", x: null, y: null },
    sql: "SELECT d.name, SUM(s.total_amount) AS net_sales FROM dealers d JOIN sales s ON s.dealer_id = d.dealer_id GROUP BY d.name",
    metrics_used: ["net_sales@v1"],
    truncated: false,
  },
  clarification: null,
  reason: null,
};

describe("TRSQL frontend /v1/plan HITL flow", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("calls POST /v1/plan and throws Turkish errors on HTTP 401", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(SAMPLE_PLAN, 200))
      .mockResolvedValueOnce(jsonResponse({ detail: "geçersiz kimlik bilgisi" }, 401));
    vi.stubGlobal("fetch", fetchMock);

    const plan = await previewPlan("http://127.0.0.1:8000", "tok-1", {
      question: "Trabzon bayileri",
      connection_id: "demo",
    });
    expect(plan.tables).toEqual(["dealers", "sales"]);
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://127.0.0.1:8000/v1/plan",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ Authorization: "Bearer tok-1" }),
      }),
    );

    await expect(
      previewPlan("http://127.0.0.1:8000", "bad", {
        question: "Trabzon bayileri",
        connection_id: "demo",
      }),
    ).rejects.toThrowError(TrsqlApiError);
  });

  it("fetches server /v1/plan tables/columns before executing /v1/query", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/health")) {
        return jsonResponse({ status: "ok" });
      }
      if (url.endsWith("/v1/plan")) {
        return jsonResponse(SAMPLE_PLAN);
      }
      if (url.endsWith("/v1/query")) {
        return jsonResponse(SAMPLE_OUTCOME);
      }
      throw new Error(`Unexpected fetch URL: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    const textarea = screen.getByLabelText(
      /Veritabanına sormak istediğiniz Türkçe soru/i,
    );
    fireEvent.change(textarea, {
      target: { value: "Trabzon'daki bayilerin net satışı nedir?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sorguyu Çalıştır" }));

    await waitFor(() => {
      expect(screen.getByText("Tablo: dealers")).toBeInTheDocument();
      expect(screen.getByText("Tablo: sales")).toBeInTheDocument();
      expect(screen.getByText("Sütun: dealers.name")).toBeInTheDocument();
      expect(screen.getByText("Metrik: net_sales@v1")).toBeInTheDocument();
    });

    // /v1/query must not be called before HITL approval.
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/v1/query"))).toBe(false);

    fireEvent.click(
      screen.getByRole("button", { name: "Tablo Kapsamını Onayla ve Çalıştır" }),
    );

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/v1/query"))).toBe(true);
      expect(screen.getByText("Bayi Net Cirosu")).toBeInTheDocument();
    });
  });

  it("shows Turkish error message and informational-only hints if /v1/plan fails", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/health")) {
        return jsonResponse({ status: "ok" });
      }
      if (url.endsWith("/v1/plan")) {
        return jsonResponse({ detail: "Sunucu hatası" }, 500);
      }
      throw new Error(`Unexpected fetch URL: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    const textarea = screen.getByLabelText(
      /Veritabanına sormak istediğiniz Türkçe soru/i,
    );
    fireEvent.change(textarea, {
      target: { value: "Trabzon'daki bayilerin net satışı nedir?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sorguyu Çalıştır" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/Plan önizleme hatası/i);
      expect(screen.getByText(/Bilgi amaçlı \(plan alınamadı\):/i)).toBeInTheDocument();
      expect(screen.getByText("dealers / bayiler")).toBeInTheDocument();
    });
  });
});
