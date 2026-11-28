import type {
  HealthResponse,
  PipelineOutcome,
  PlanPreview,
  QueryBody,
} from "../types/contracts";

export class TrsqlApiError extends Error {
  readonly statusCode: number | null;
  readonly detail: string;

  constructor(message: string, statusCode: number | null, detail: string) {
    super(message);
    this.name = "TrsqlApiError";
    this.statusCode = statusCode;
    this.detail = detail;
  }
}

function normalizeBaseUrl(baseUrl: string): string {
  const trimmed = baseUrl.trim();
  if (!trimmed) {
    return "/api";
  }
  return trimmed.endsWith("/") ? trimmed.slice(0, -1) : trimmed;
}

async function parseErrorDetail(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: unknown };
    if (typeof data.detail === "string" && data.detail.trim()) {
      return data.detail;
    }
  } catch {
    // Ignore non-JSON error bodies and fall back to status text.
  }
  return response.statusText || `HTTP ${response.status}`;
}

async function postJson<TResponse>(
  baseUrl: string,
  endpoint: string,
  token: string,
  body: QueryBody,
  networkErrorMessage: string,
  signal?: AbortSignal,
): Promise<TResponse> {
  const url = `${normalizeBaseUrl(baseUrl)}${endpoint}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };
  const trimmedToken = token.trim();
  if (trimmedToken) {
    headers.Authorization = `Bearer ${trimmedToken}`;
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify({
        question: body.question,
        connection_id: body.connection_id,
      }),
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw err;
    }
    throw new TrsqlApiError(
      networkErrorMessage,
      null,
      err instanceof Error ? err.message : "Bağlantı kurulamadı",
    );
  }

  if (!response.ok) {
    const detail = await parseErrorDetail(response);
    if (response.status === 401) {
      throw new TrsqlApiError(
        "Kimlik doğrulama başarısız (401). Lütfen geçerli bir Bearer Token girin.",
        401,
        detail,
      );
    }
    if (response.status === 422) {
      throw new TrsqlApiError(
        "Sorgu isteği doğrulama kurallarına uymuyor (422).",
        422,
        detail,
      );
    }
    throw new TrsqlApiError(
      `Sunucu isteği işleyemedi (${response.status}).`,
      response.status,
      detail,
    );
  }

  return (await response.json()) as TResponse;
}

export async function fetchHealth(
  baseUrl: string,
  signal?: AbortSignal,
): Promise<HealthResponse> {
  const url = `${normalizeBaseUrl(baseUrl)}/health`;
  let response: Response;
  try {
    response = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw err;
    }
    throw new TrsqlApiError(
      "API sağlık kontrolüne erişilemedi. Sunucu adresini ve yerel bağlantıyı kontrol edin.",
      null,
      err instanceof Error ? err.message : "Ağ hatası",
    );
  }

  if (!response.ok) {
    const detail = await parseErrorDetail(response);
    throw new TrsqlApiError(
      `API sağlık yanıtı başarısız (${response.status}).`,
      response.status,
      detail,
    );
  }

  return (await response.json()) as HealthResponse;
}

export async function previewPlan(
  baseUrl: string,
  token: string,
  body: QueryBody,
  signal?: AbortSignal,
): Promise<PlanPreview> {
  return postJson<PlanPreview>(
    baseUrl,
    "/v1/plan",
    token,
    body,
    "Plan önizlemesi alınamadı. TRSQL API sunucusunun çalıştığından emin olun.",
    signal,
  );
}

export async function submitQuery(
  baseUrl: string,
  token: string,
  body: QueryBody,
  signal?: AbortSignal,
): Promise<PipelineOutcome> {
  return postJson<PipelineOutcome>(
    baseUrl,
    "/v1/query",
    token,
    body,
    "TRSQL API sunucusuna ulaşılamadı. Servisin çalıştığından emin olun.",
    signal,
  );
}
