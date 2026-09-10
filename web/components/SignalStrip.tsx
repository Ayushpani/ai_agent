"use client";

import { motion } from "framer-motion";
import { AlertTriangle } from "lucide-react";
import type { SignalsPackage } from "@/lib/types";
import { formatPercent } from "@/lib/format";

interface Tile {
  label: string;
  value: string;
  tone?: "neutral" | "notable" | "extreme";
}

/** The at-a-glance row a real BI dashboard leads with, mirroring the KPI
 * strip in the Excel workbook so chat and export agree. */
export function SignalStrip({ signals }: { signals: SignalsPackage | null }) {
  if (!signals) return null;

  const tiles: Tile[] = [];

  if (signals.period_change) {
    tiles.push({ label: "Period change", value: formatPercent(signals.period_change.pct_change) });
  }
  if (signals.yoy_change) {
    tiles.push({ label: "Year on year", value: formatPercent(signals.yoy_change.pct_change) });
  }
  if (signals.zscore) {
    tiles.push({
      label: "Z-score",
      value: signals.zscore.value.toFixed(2),
      tone: signals.zscore.bucket === "normal" ? "neutral" : (signals.zscore.bucket as Tile["tone"]),
    });
  }
  if (signals.concentration_index !== null && signals.concentration_index !== undefined) {
    tiles.push({ label: "Concentration", value: signals.concentration_index.toFixed(2) });
  }
  if (signals.forecast?.feasible) {
    tiles.push({ label: "Forecast MAPE", value: `${signals.forecast.backtest_mape.toFixed(1)}%` });
  }

  const flags = signals.data_quality_flags ?? [];
  if (tiles.length === 0 && flags.length === 0) return null;

  return (
    <div className="flex flex-col gap-2">
      {tiles.length > 0 && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {tiles.map((tile, i) => (
            <motion.div
              key={tile.label}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.28, delay: i * 0.05 }}
              className="rounded-lg border border-border bg-surface px-3 py-2"
            >
              <div className="text-[11px] font-medium uppercase tracking-wide text-muted">
                {tile.label}
              </div>
              <div
                className={`mt-0.5 text-[19px] font-semibold tabular-nums ${
                  tile.tone === "extreme"
                    ? "text-danger"
                    : tile.tone === "notable"
                      ? "text-warning"
                      : "text-accent-strong"
                }`}
              >
                {tile.value}
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {flags.map((flag, i) => (
        <div
          key={i}
          className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/5 px-3 py-2 text-[12.5px] leading-relaxed text-warning"
        >
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={2} />
          <span>{flag.detail}</span>
        </div>
      ))}
    </div>
  );
}
