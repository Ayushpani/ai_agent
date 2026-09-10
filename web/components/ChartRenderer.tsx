"use client";

import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  ScatterChart,
  Scatter,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from "recharts";
import type { ChartSpec, DataFramePayload } from "@/lib/types";

const ACCENT = "#1f4e79";
const PIE_PALETTE = ["#1f4e79", "#3d7ab5", "#7ba7d1", "#b7cde3", "#dce6f1", "#164060", "#4f90c7"];

export function ChartRenderer({ spec, data }: { spec: ChartSpec; data: DataFramePayload }) {
  const rows = data.records;
  if (rows.length === 0) return null;

  if (spec.chart_type === "kpi_callout") {
    const [key] = Object.keys(rows[0]);
    return (
      <div className="rounded-xl border border-border bg-surface px-6 py-5">
        <div className="text-[13px] font-medium uppercase tracking-wide text-muted">{key}</div>
        <div className="mt-1 text-3xl font-semibold text-accent-strong">
          {formatValue(rows[0][key])}
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <ResponsiveContainer width="100%" height={320}>
        {renderChart(spec, rows)}
      </ResponsiveContainer>
    </div>
  );
}

function renderChart(spec: ChartSpec, rows: Record<string, unknown>[]) {
  const { chart_type, x_field, y_field, series_field } = spec;

  if (chart_type === "line" && x_field && y_field) {
    return (
      <LineChart data={rows} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e8ecf1" />
        <XAxis dataKey={x_field} tick={{ fontSize: 12, fill: "#5b6472" }} />
        <YAxis tick={{ fontSize: 12, fill: "#5b6472" }} tickFormatter={formatAxisNumber} />
        <Tooltip formatter={(v) => formatValue(v)} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line
          type="monotone"
          dataKey={y_field}
          stroke={ACCENT}
          strokeWidth={2.5}
          strokeDasharray={spec.forecast_forced ? "6 4" : undefined}
          dot={{ r: 3, fill: ACCENT }}
          activeDot={{ r: 5 }}
          isAnimationActive
          animationDuration={700}
        />
      </LineChart>
    );
  }

  if (chart_type === "bar" && x_field && y_field) {
    return (
      <BarChart data={rows} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e8ecf1" />
        <XAxis dataKey={x_field} tick={{ fontSize: 12, fill: "#5b6472" }} />
        <YAxis tick={{ fontSize: 12, fill: "#5b6472" }} tickFormatter={formatAxisNumber} />
        <Tooltip formatter={(v) => formatValue(v)} />
        <Bar dataKey={y_field} fill={ACCENT} radius={[4, 4, 0, 0]} isAnimationActive animationDuration={700} />
      </BarChart>
    );
  }

  if (chart_type === "pie" && series_field && y_field) {
    return (
      <PieChart margin={{ top: 8, right: 16, left: 16, bottom: 0 }}>
        <Pie
          data={rows}
          dataKey={y_field}
          nameKey={series_field}
          cx="50%"
          cy="50%"
          outerRadius={110}
          isAnimationActive
          animationDuration={700}
        >
          {rows.map((_, i) => (
            <Cell key={i} fill={PIE_PALETTE[i % PIE_PALETTE.length]} />
          ))}
        </Pie>
        <Tooltip formatter={(v) => formatValue(v)} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
      </PieChart>
    );
  }

  if (chart_type === "scatter" && x_field && y_field) {
    return (
      <ScatterChart margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e8ecf1" />
        <XAxis dataKey={x_field} tick={{ fontSize: 12, fill: "#5b6472" }} />
        <YAxis dataKey={y_field} tick={{ fontSize: 12, fill: "#5b6472" }} tickFormatter={formatAxisNumber} />
        <Tooltip formatter={(v) => formatValue(v)} />
        <Scatter data={rows} fill={ACCENT} isAnimationActive animationDuration={700} />
      </ScatterChart>
    );
  }

  return <div />;
}

function formatValue(value: unknown): string {
  if (typeof value === "number") {
    return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(value);
  }
  return String(value);
}

function formatAxisNumber(value: number): string {
  if (Math.abs(value) >= 1_00_00_000) return `${(value / 1_00_00_000).toFixed(1)}Cr`;
  if (Math.abs(value) >= 1_00_000) return `${(value / 1_00_000).toFixed(1)}L`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}
