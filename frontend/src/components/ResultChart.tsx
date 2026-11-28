import { useState } from "react";
import type { ResultReport } from "../types/contracts";
import { formatTrCellValue } from "../utils/format";

interface ResultChartProps {
  readonly report: ResultReport;
}

interface DataPoint {
  readonly label: string;
  readonly value: number;
  readonly rawLabel: string;
}

const PALETTE = [
  "#14539a",
  "#0d7a53",
  "#d97706",
  "#7c3aed",
  "#0284c7",
  "#be123c",
  "#0f766e",
  "#4338ca",
];

function extractSeries(report: ResultReport): DataPoint[] | null {
  if (report.columns.length < 2 || report.rows.length === 0) {
    return null;
  }
  const xIndex = report.chart.x
    ? Math.max(0, report.columns.indexOf(report.chart.x))
    : 0;
  const yIndex = report.chart.y
    ? Math.max(0, report.columns.indexOf(report.chart.y))
    : 1;
  if (xIndex === yIndex || yIndex >= report.columns.length) {
    return null;
  }

  const points: DataPoint[] = [];
  for (const row of report.rows) {
    const rawY = row[yIndex];
    if (typeof rawY !== "number" || !Number.isFinite(rawY)) {
      return null;
    }
    const rawX = formatTrCellValue(row[xIndex]);
    const shortX = rawX.length > 16 ? `${rawX.slice(0, 15)}…` : rawX;
    points.push({ label: shortX, rawLabel: rawX, value: rawY });
  }
  return points;
}

function polarToCartesian(
  cx: number,
  cy: number,
  radius: number,
  angleRadians: number,
): [number, number] {
  return [
    cx + radius * Math.cos(angleRadians),
    cy + radius * Math.sin(angleRadians),
  ];
}

function describeArcSlice(
  cx: number,
  cy: number,
  outerR: number,
  innerR: number,
  startAngle: number,
  endAngle: number,
): string {
  const [x1, y1] = polarToCartesian(cx, cy, outerR, startAngle);
  const [x2, y2] = polarToCartesian(cx, cy, outerR, endAngle);
  const [x3, y3] = polarToCartesian(cx, cy, innerR, endAngle);
  const [x4, y4] = polarToCartesian(cx, cy, innerR, startAngle);
  const largeArc = endAngle - startAngle > Math.PI ? 1 : 0;

  return [
    `M ${x1.toFixed(2)} ${y1.toFixed(2)}`,
    `A ${outerR} ${outerR} 0 ${largeArc} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`,
    `L ${x3.toFixed(2)} ${y3.toFixed(2)}`,
    `A ${innerR} ${innerR} 0 ${largeArc} 0 ${x4.toFixed(2)} ${y4.toFixed(2)}`,
    "Z",
  ].join(" ");
}

export function ResultChart({ report }: ResultChartProps) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);
  const series = extractSeries(report);
  const kind = report.chart.kind;

  if (kind === "table" || !series) {
    return (
      <section className="card" aria-labelledby="chart-title">
        <div className="card-header">
          <h3 id="chart-title" className="card-title">
            Görselleştirme (Tablo Modu)
          </h3>
          <span className="badge">chart.kind = {kind}</span>
        </div>
        <p className="muted-note" style={{ margin: 0 }}>
          {kind === "table"
            ? "Sunucu L8 katmanı bu sonuç kümesi için doğrudan tablo görünümünü belirledi."
            : "Sonuç satırları grafik eksenleriyle eşleşmediği için veriler yalnızca aşağıdaki tabloda sunuluyor."}
        </p>
      </section>
    );
  }

  const xAxisTitle = report.chart.x ?? report.columns[0];
  const yAxisTitle = report.chart.y ?? report.columns[1];

  if (kind === "pie") {
    const hasNonPositive = series.some((pt) => pt.value <= 0);
    if (hasNonPositive) {
      return (
        <section className="card" aria-labelledby="chart-title">
          <div className="card-header">
            <h3 id="chart-title" className="card-title">
              Pasta Grafik
            </h3>
            <span className="badge warn">Pozitif Olmayan Değerler</span>
          </div>
          <p className="muted-note" style={{ margin: 0 }}>
            Sıfır veya negatif değerler pasta dilimi olarak çizilemediği için
            aşağıdaki deterministik tabloyu inceleyin.
          </p>
        </section>
      );
    }

    // Visual-only arc angle geometry; displayed numbers remain exact server values (ADR-0008).
    let geometricSum = 0;
    for (const pt of series) {
      geometricSum += pt.value;
    }

    const cx = 140;
    const cy = 140;
    const outerR = 112;
    const innerR = 54;
    let cursorAngle = -Math.PI / 2;

    return (
      <section className="card" aria-labelledby="chart-title">
        <div className="card-header">
          <h3 id="chart-title" className="card-title">
            Dağılım Grafiği ({xAxisTitle} → {yAxisTitle})
          </h3>
          <span className="badge info">Sunucu Verisi · Pasta</span>
        </div>

        <div className="pie-layout">
          <svg
            width="280"
            height="280"
            viewBox="0 0 280 280"
            role="img"
            aria-label={`${report.title} dağılım grafiği`}
          >
            {series.length === 1 ? (
              <circle
                cx={cx}
                cy={cy}
                r={(outerR + innerR) / 2}
                fill="none"
                stroke={PALETTE[0]}
                strokeWidth={outerR - innerR}
              >
                <title>
                  {series[0].rawLabel}: {formatTrCellValue(series[0].value)}
                </title>
              </circle>
            ) : (
              series.map((pt, idx) => {
                const sliceAngle = (pt.value / geometricSum) * Math.PI * 2;
                const start = cursorAngle;
                const end = cursorAngle + sliceAngle;
                cursorAngle = end;
                const color = PALETTE[idx % PALETTE.length];
                return (
                  <path
                    key={`${pt.rawLabel}-${idx}`}
                    d={describeArcSlice(cx, cy, outerR, innerR, start, end)}
                    fill={color}
                    stroke="#ffffff"
                    strokeWidth="2"
                    opacity={hoveredIdx === null || hoveredIdx === idx ? 1 : 0.65}
                    onMouseEnter={() => setHoveredIdx(idx)}
                    onMouseLeave={() => setHoveredIdx(null)}
                  >
                    <title>
                      {pt.rawLabel}: {formatTrCellValue(pt.value)}
                    </title>
                  </path>
                );
              })
            )}
          </svg>

          <ul className="pie-legend">
            {series.map((pt, idx) => (
              <li
                key={`${pt.rawLabel}-${idx}`}
                className="pie-legend-item"
                onMouseEnter={() => setHoveredIdx(idx)}
                onMouseLeave={() => setHoveredIdx(null)}
              >
                <span className="input-row">
                  <span
                    className="pie-swatch"
                    style={{ background: PALETTE[idx % PALETTE.length] }}
                    aria-hidden="true"
                  />
                  <span>{pt.rawLabel}</span>
                </span>
                <strong>{formatTrCellValue(pt.value)}</strong>
              </li>
            ))}
          </ul>
        </div>
      </section>
    );
  }

  // Bar & Line SVG geometry (exact server values rendered verbatim, no client-side math).
  const width = Math.max(620, series.length * 76);
  const height = 300;
  const padLeft = 40;
  const padRight = 24;
  const padTop = 34;
  const padBottom = 64;
  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;

  const rawValues = series.map((p) => p.value);
  const minVal = Math.min(0, ...rawValues);
  const maxVal = Math.max(0, ...rawValues);
  const span = maxVal - minVal || 1;
  const zeroY = padTop + ((maxVal - 0) / span) * plotH;

  const valueToY = (v: number): number => padTop + ((maxVal - v) / span) * plotH;

  return (
    <section className="card" aria-labelledby="chart-title">
      <div className="card-header">
        <h3 id="chart-title" className="card-title">
          {kind === "line" ? "Trend Grafiği" : "Sütun Grafiği"} ({xAxisTitle} →{" "}
          {yAxisTitle})
        </h3>
        <span className="badge info">
          Sunucu Verisi · {kind === "line" ? "Çizgi" : "Sütun"}
        </span>
      </div>

      <div className="chart-box">
        <svg
          className="chart-svg"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`${report.title} grafiği`}
        >
          {/* Baseline and guide rules */}
          {[0.25, 0.5, 0.75, 1].map((frac) => {
            const yPos = padTop + plotH * (1 - frac);
            return (
              <line
                key={frac}
                x1={padLeft}
                y1={yPos}
                x2={width - padRight}
                y2={yPos}
                stroke="#e5ecf6"
                strokeDasharray="4 4"
              />
            );
          })}
          <line
            x1={padLeft}
            y1={zeroY}
            x2={width - padRight}
            y2={zeroY}
            stroke="#9fb0c7"
            strokeWidth="1.5"
          />

          {kind === "bar" ? (
            series.map((pt, idx) => {
              const slotW = plotW / series.length;
              const barW = Math.min(46, Math.max(16, slotW * 0.58));
              const xCenter = padLeft + slotW * idx + slotW / 2;
              const yVal = valueToY(pt.value);
              const barTop = Math.min(yVal, zeroY);
              const barH = Math.max(2, Math.abs(zeroY - yVal));
              const isActive = hoveredIdx === idx;
              return (
                <g
                  key={`${pt.rawLabel}-${idx}`}
                  onMouseEnter={() => setHoveredIdx(idx)}
                  onMouseLeave={() => setHoveredIdx(null)}
                >
                  <rect
                    x={xCenter - barW / 2}
                    y={barTop}
                    width={barW}
                    height={barH}
                    rx="5"
                    fill={isActive ? "#0e3f78" : "#14539a"}
                  >
                    <title>
                      {pt.rawLabel}: {formatTrCellValue(pt.value)}
                    </title>
                  </rect>
                  <text
                    x={xCenter}
                    y={Math.max(16, barTop - 8)}
                    textAnchor="middle"
                    fontSize="11"
                    fontWeight="600"
                    fill="#102038"
                  >
                    {formatTrCellValue(pt.value)}
                  </text>
                  <text
                    x={xCenter}
                    y={height - 26}
                    textAnchor="middle"
                    fontSize="11.5"
                    fill="#3e516b"
                  >
                    {pt.label}
                  </text>
                </g>
              );
            })
          ) : (
            <>
              <polyline
                fill="none"
                stroke="#14539a"
                strokeWidth="3"
                strokeLinejoin="round"
                strokeLinecap="round"
                points={series
                  .map((pt, idx) => {
                    const slotW = plotW / Math.max(1, series.length - 1);
                    const xPos =
                      series.length === 1
                        ? padLeft + plotW / 2
                        : padLeft + slotW * idx;
                    const yPos = valueToY(pt.value);
                    return `${xPos.toFixed(1)},${yPos.toFixed(1)}`;
                  })
                  .join(" ")}
              />
              {series.map((pt, idx) => {
                const slotW = plotW / Math.max(1, series.length - 1);
                const xPos =
                  series.length === 1
                    ? padLeft + plotW / 2
                    : padLeft + slotW * idx;
                const yPos = valueToY(pt.value);
                const isActive = hoveredIdx === idx;
                return (
                  <g
                    key={`${pt.rawLabel}-${idx}`}
                    onMouseEnter={() => setHoveredIdx(idx)}
                    onMouseLeave={() => setHoveredIdx(null)}
                  >
                    <circle
                      cx={xPos}
                      cy={yPos}
                      r={isActive ? 6.5 : 4.5}
                      fill="#0d7a53"
                      stroke="#ffffff"
                      strokeWidth="2"
                    >
                      <title>
                        {pt.rawLabel}: {formatTrCellValue(pt.value)}
                      </title>
                    </circle>
                    <text
                      x={xPos}
                      y={Math.max(16, yPos - 10)}
                      textAnchor="middle"
                      fontSize="11"
                      fontWeight="600"
                      fill="#102038"
                    >
                      {formatTrCellValue(pt.value)}
                    </text>
                    <text
                      x={xPos}
                      y={height - 26}
                      textAnchor="middle"
                      fontSize="11.5"
                      fill="#3e516b"
                    >
                      {pt.label}
                    </text>
                  </g>
                );
              })}
            </>
          )}
        </svg>
      </div>
    </section>
  );
}
