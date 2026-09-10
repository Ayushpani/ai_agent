"use client";

import { useMemo } from "react";
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
  AreaChart,
  Area,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from "recharts";
import type { ChartSpec } from "@/lib/types";
import { AXIS_TEXT, GRID_STROKE, MAX_SERIES, PRIMARY_SERIES, seriesColor } from "@/lib/palette";
import { formatCompact, formatValue, humanizeField } from "@/lib/format";

type Row = Record<string, unknown>;

export function ChartRenderer({
  spec,
  rows,
  height = 300,
}: {
  spec: ChartSpec;
  rows: Row[];
  height?: number;
}) {
  const prepared = useMemo(() => prepare(spec, rows), [spec, rows]);

  if (rows.length === 0) return null;

  if (spec.chart_type === "kpi_callout") {
    const [key] = Object.keys(rows[0]);
    return (
      <div className="px-1 py-2">
        <div className="text-[12px] font-medium uppercase tracking-wide text-muted">{key}</div>
        <div className="mt-1 text-4xl font-semibold tabular-nums text-accent-strong">
          {formatValue(rows[0][key])}
        </div>
      </div>
    );
  }

  return (
    <div>
      <ResponsiveContainer width="100%" height={height}>
        {renderChart(spec, prepared)}
      </ResponsiveContainer>
      {prepared.foldedCount > 0 && (
        <p className="mt-1 text-[12px] text-muted">
          Showing the {prepared.seriesKeys.length} largest of {prepared.seriesKeys.length + prepared.foldedCount} series.
        </p>
      )}
    </div>
  );
}

interface Prepared {
  rows: Row[];
  seriesKeys: string[];
  foldedCount: number;
}

/** Long-format (x, series, value) rows have to be pivoted to one column
 * per series before Recharts can draw several lines from them. */
function prepare(spec: ChartSpec, rows: Row[]): Prepared {
  if (spec.chart_type === "multi_line" && spec.series_field && spec.x_field && spec.y_field) {
    const { x_field, y_field, series_field } = spec;

    const totals = new Map<string, number>();
    for (const row of rows) {
      const key = String(row[series_field]);
      totals.set(key, (totals.get(key) ?? 0) + Number(row[y_field] ?? 0));
    }
    const ranked = [...totals.entries()].sort((a, b) => b[1] - a[1]).map(([k]) => k);
    const kept = ranked.slice(0, MAX_SERIES);
    const keptSet = new Set(kept);

    const byX = new Map<string, Row>();
    for (const row of rows) {
      const xValue = String(row[x_field]);
      const key = String(row[series_field]);
      if (!keptSet.has(key)) continue;
      if (!byX.has(xValue)) byX.set(xValue, { [x_field]: xValue });
      byX.get(xValue)![key] = row[y_field];
    }

    return {
      rows: [...byX.values()],
      seriesKeys: kept,
      foldedCount: ranked.length - kept.length,
    };
  }

  if (spec.chart_type === "grouped_bar" && spec.value_fields.length > 0) {
    return { rows, seriesKeys: spec.value_fields, foldedCount: 0 };
  }

  return { rows, seriesKeys: spec.y_field ? [spec.y_field] : [], foldedCount: 0 };
}

const axisProps = { tick: { fontSize: 11, fill: AXIS_TEXT }, stroke: GRID_STROKE };

const MAX_LABEL_CHARS = 14;

function truncate(value: unknown): string {
  const text = String(value ?? "");
  return text.length > MAX_LABEL_CHARS ? `${text.slice(0, MAX_LABEL_CHARS - 1)}…` : text;
}

/** Category labels are long enough to collide at panel width, so tilt
 * them rather than let Recharts run them together — which is what
 * happened with branch names ("Branch-RAJ-4Branch-TAM-3..."). */
function categoryAxisProps(rows: Row[], xField: string) {
  const longest = rows.reduce((max, row) => Math.max(max, String(row[xField] ?? "").length), 0);
  const tilt = rows.length > 4 || longest > 8;
  return {
    interval: 0 as const,
    angle: tilt ? -30 : 0,
    textAnchor: tilt ? ("end" as const) : ("middle" as const),
    height: tilt ? 64 : 30,
    tickMargin: 4,
    tickFormatter: truncate,
  };
}

/** On a time axis let Recharts thin ticks by spacing rather than
 * dropping an arbitrary one — a missing "2026-07" between 06 and 08
 * reads as a hole in the data. */
const timeAxisProps = { interval: "preserveStartEnd" as const, minTickGap: 24 };

function tooltip() {
  return (
    <Tooltip
      formatter={(v: unknown) => formatValue(v)}
      contentStyle={{
        borderRadius: 8,
        border: "1px solid #e4e7ec",
        fontSize: 12,
        boxShadow: "0 4px 14px rgba(16,24,40,0.08)",
      }}
      cursor={{ stroke: GRID_STROKE, strokeWidth: 1 }}
    />
  );
}

/** A legend is required for two or more series; a single series is named
 * by the panel title above the chart, so a one-row legend box there is
 * redundant chrome. */
function legend(seriesCount: number, iconType: "line" | "square" = "line") {
  return seriesCount >= 2 ? (
    <Legend wrapperStyle={{ fontSize: 11 }} iconType={iconType} />
  ) : null;
}

function renderChart(spec: ChartSpec, prepared: Prepared) {
  const { rows, seriesKeys } = prepared;
  const { chart_type, x_field, y_field, series_field } = spec;
  const margin = { top: 8, right: 12, left: 4, bottom: 0 };

  if ((chart_type === "line" || chart_type === "multi_line") && x_field) {
    return (
      <LineChart data={rows} margin={margin}>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
        <XAxis dataKey={x_field} {...axisProps} {...timeAxisProps} />
        <YAxis {...axisProps} tickFormatter={formatCompact} width={56} />
        {tooltip()}
        {legend(seriesKeys.length)}
        {seriesKeys.map((key, i) => (
          <Line
            key={key}
            type="monotone"
            dataKey={key}
            name={humanizeField(key)}
            stroke={seriesKeys.length === 1 ? PRIMARY_SERIES : seriesColor(i)}
            strokeWidth={2}
            strokeDasharray={spec.forecast_forced ? "6 4" : undefined}
            dot={{ r: 3, strokeWidth: 2, fill: "#ffffff" }}
            activeDot={{ r: 5 }}
            isAnimationActive
            animationDuration={650}
          />
        ))}
      </LineChart>
    );
  }

  if (chart_type === "area" && x_field && y_field) {
    return (
      <AreaChart data={rows} margin={margin}>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
        <XAxis dataKey={x_field} {...axisProps} {...timeAxisProps} />
        <YAxis {...axisProps} tickFormatter={formatCompact} width={56} />
        {tooltip()}
        <Area
          type="monotone"
          dataKey={y_field}
          stroke={PRIMARY_SERIES}
          strokeWidth={2}
          fill={PRIMARY_SERIES}
          fillOpacity={0.12}
          isAnimationActive
          animationDuration={650}
        />
      </AreaChart>
    );
  }

  if ((chart_type === "bar" || chart_type === "grouped_bar") && x_field) {
    return (
      <BarChart data={rows} margin={margin} barGap={2}>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
        <XAxis dataKey={x_field} {...axisProps} {...categoryAxisProps(rows, x_field)} />
        <YAxis {...axisProps} tickFormatter={formatCompact} width={56} />
        {tooltip()}
        {legend(seriesKeys.length, "square")}
        {seriesKeys.map((key, i) => (
          <Bar
            key={key}
            dataKey={key}
            name={humanizeField(key)}
            fill={seriesKeys.length === 1 ? PRIMARY_SERIES : seriesColor(i)}
            radius={[4, 4, 0, 0]}
            isAnimationActive
            animationDuration={650}
          />
        ))}
      </BarChart>
    );
  }

  if (chart_type === "pie" && series_field && y_field) {
    return (
      <PieChart margin={margin}>
        <Pie
          data={rows}
          dataKey={y_field}
          nameKey={series_field}
          cx="50%"
          cy="50%"
          outerRadius={100}
          paddingAngle={1}
          isAnimationActive
          animationDuration={650}
        >
          {rows.map((_, i) => (
            <Cell key={i} fill={seriesColor(i)} stroke="#ffffff" strokeWidth={2} />
          ))}
        </Pie>
        {tooltip()}
        <Legend wrapperStyle={{ fontSize: 11 }} />
      </PieChart>
    );
  }

  if (chart_type === "scatter" && x_field && y_field) {
    return (
      <ScatterChart margin={margin}>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
        <XAxis dataKey={x_field} {...axisProps} tickFormatter={formatCompact} />
        <YAxis dataKey={y_field} {...axisProps} tickFormatter={formatCompact} width={56} />
        {tooltip()}
        <Scatter data={rows} fill={PRIMARY_SERIES} isAnimationActive animationDuration={650} />
      </ScatterChart>
    );
  }

  return <div />;
}
