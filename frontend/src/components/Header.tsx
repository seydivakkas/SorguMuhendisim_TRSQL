import { useState } from "react";
import type { ConnectionOption } from "../types/contracts";

export type HealthState = "checking" | "online" | "offline";

interface HeaderProps {
  readonly connections: readonly ConnectionOption[];
  readonly connectionId: string;
  readonly onConnectionChange: (value: string) => void;
  readonly token: string;
  readonly onTokenChange: (value: string) => void;
  readonly apiBaseUrl: string;
  readonly onApiBaseUrlChange: (value: string) => void;
  readonly healthState: HealthState;
  readonly healthDetail: string;
  readonly onRefreshHealth: () => void;
}

export function Header({
  connections,
  connectionId,
  onConnectionChange,
  token,
  onTokenChange,
  apiBaseUrl,
  onApiBaseUrlChange,
  healthState,
  healthDetail,
  onRefreshHealth,
}: HeaderProps) {
  const [showToken, setShowToken] = useState(false);
  const [customConnection, setCustomConnection] = useState(
    !connections.some((c) => c.id === connectionId),
  );

  const healthLabel =
    healthState === "online"
      ? "API Çevrimiçi"
      : healthState === "offline"
        ? "API Erişilemiyor"
        : "Kontrol Ediliyor…";

  const healthClass =
    healthState === "online" ? "ok" : healthState === "offline" ? "down" : "";

  return (
    <header className="topbar">
      <div className="topbar-inner">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            TR
          </div>
          <div>
            <h1 className="brand-title">TRSQL — Sorgu Mühendisim</h1>
            <p className="brand-subtitle">
              Kurum içi Türkçe NL2SQL · Deterministik sonuçlar · Çevrimdışı (KVKK)
            </p>
          </div>
        </div>

        <div className="header-controls">
          <div className="control-group">
            <label className="control-label" htmlFor="connection-select">
              Veritabanı Bağlantısı
            </label>
            <div className="input-row">
              {!customConnection ? (
                <select
                  id="connection-select"
                  className="select-input"
                  value={connectionId}
                  onChange={(e) => {
                    if (e.target.value === "__custom__") {
                      setCustomConnection(true);
                    } else {
                      onConnectionChange(e.target.value);
                    }
                  }}
                >
                  {connections.map((conn) => (
                    <option key={conn.id} value={conn.id}>
                      {conn.label}
                    </option>
                  ))}
                  <option value="__custom__">Özel bağlantı kimliği…</option>
                </select>
              ) : (
                <>
                  <input
                    id="connection-select"
                    type="text"
                    className="text-input"
                    value={connectionId}
                    onChange={(e) => onConnectionChange(e.target.value)}
                    placeholder="Örn: erp_prod"
                    aria-label="Özel bağlantı kimliği"
                  />
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={() => {
                      setCustomConnection(false);
                      if (!connections.some((c) => c.id === connectionId)) {
                        onConnectionChange(connections[0]?.id ?? "demo");
                      }
                    }}
                  >
                    Liste
                  </button>
                </>
              )}
            </div>
          </div>

          <div className="control-group">
            <label className="control-label" htmlFor="bearer-token-input">
              Bearer Token
            </label>
            <div className="input-row">
              <input
                id="bearer-token-input"
                type={showToken ? "text" : "password"}
                className="text-input token-input"
                value={token}
                onChange={(e) => onTokenChange(e.target.value)}
                placeholder="Sunucu erişim belirteci"
                autoComplete="off"
                spellCheck={false}
              />
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => setShowToken((prev) => !prev)}
                aria-label={showToken ? "Belirteci gizle" : "Belirteci göster"}
              >
                {showToken ? "Gizle" : "Göster"}
              </button>
            </div>
          </div>

          <div className="control-group">
            <label className="control-label" htmlFor="api-base-url">
              API Adresi
            </label>
            <input
              id="api-base-url"
              type="text"
              className="text-input url-input"
              value={apiBaseUrl}
              onChange={(e) => onApiBaseUrlChange(e.target.value)}
              placeholder="/api"
            />
          </div>

          <div className="control-group">
            <span className="control-label">Durum</span>
            <button
              type="button"
              className={`health-pill ${healthClass}`}
              onClick={onRefreshHealth}
              title={healthDetail || "API sağlık durumunu yenile"}
              aria-live="polite"
            >
              <span className="health-dot" aria-hidden="true" />
              <span>{healthLabel}</span>
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
