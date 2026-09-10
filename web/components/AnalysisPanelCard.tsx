"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, BarChart3, ChevronDown, Code2, Table2 } from "lucide-react";
import { ChartRenderer } from "./ChartRenderer";
import { DataTable } from "./DataTable";
import type { AnalysisPanel } from "@/lib/types";

type View = "chart" | "table" | "sql";

export function AnalysisPanelCard({ panel, index }: { panel: AnalysisPanel; index: number }) {
  const [view, setView] = useState<View>("chart");
  const [showRationale, setShowRationale] = useState(false);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: Math.min(index * 0.07, 0.4), ease: [0.22, 1, 0.36, 1] }}
      className="flex flex-col rounded-xl border border-border bg-surface p-4"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-[14.5px] font-semibold text-foreground">{panel.title}</h3>
          <button
            onClick={() => setShowRationale((v) => !v)}
            className="mt-0.5 flex items-center gap-1 text-[12px] text-muted hover:text-accent"
          >
            Why this was run
            <ChevronDown
              className={`h-3 w-3 transition-transform ${showRationale ? "rotate-180" : ""}`}
              strokeWidth={2}
            />
          </button>
        </div>

        {!panel.error && (
          <ViewSwitch
            view={view}
            setView={setView}
            hasSql={Boolean(panel.sql)}
            switchId={panel.panel_id}
          />
        )}
      </div>

      <AnimatePresence>
        {showRationale && (
          <motion.p
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden text-[12.5px] leading-relaxed text-muted"
          >
            <span className="block pt-2">{panel.rationale}</span>
          </motion.p>
        )}
      </AnimatePresence>

      {panel.error ? (
        <div className="mt-4 flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/5 px-3 py-2.5 text-[12.5px] text-warning">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={2} />
          <span>{panel.error}</span>
        </div>
      ) : (
        <>
          <div className="mt-3">
            {view === "chart" && (
              <ChartRenderer spec={panel.chart_spec} rows={panel.records} height={260} />
            )}
            {view === "table" && <DataTable rows={panel.records} />}
            {view === "sql" && (
              <pre className="overflow-x-auto rounded-lg bg-[#0f1720] px-3 py-2.5 text-[12px] leading-relaxed text-[#d7e3f0] font-mono">
                {panel.sql}
              </pre>
            )}
          </div>

          {panel.headline && (
            <p className="mt-3 border-t border-border pt-3 text-[13px] leading-relaxed text-foreground">
              {panel.headline}
            </p>
          )}
        </>
      )}
    </motion.div>
  );
}

function ViewSwitch({
  view,
  setView,
  hasSql,
  switchId,
}: {
  view: View;
  setView: (v: View) => void;
  hasSql: boolean;
  switchId: string;
}) {
  const options: { key: View; label: string; Icon: typeof Table2 }[] = [
    { key: "chart", label: "Chart", Icon: BarChart3 },
    { key: "table", label: "Table", Icon: Table2 },
    ...(hasSql ? [{ key: "sql" as View, label: "SQL", Icon: Code2 }] : []),
  ];

  return (
    <div className="flex shrink-0 items-center gap-0.5 rounded-lg border border-border bg-background p-0.5">
      {options.map(({ key, label, Icon }) => (
        <button
          key={key}
          onClick={() => setView(key)}
          aria-label={label}
          title={label}
          className={`relative rounded-md px-2 py-1 transition-colors ${
            view === key ? "text-white" : "text-muted hover:text-accent"
          }`}
        >
          {view === key && (
            // Scoped to this panel — a layoutId shared across panels would
            // make the pill fly between cards when two are clicked.
            <motion.span
              layoutId={`view-switch-${switchId}`}
              className="absolute inset-0 rounded-md bg-accent"
              transition={{ type: "spring", stiffness: 400, damping: 30 }}
            />
          )}
          <Icon className="relative h-3.5 w-3.5" strokeWidth={2} />
        </button>
      ))}
    </div>
  );
}
