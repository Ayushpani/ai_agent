"use client";

import { motion } from "framer-motion";
import { Download } from "lucide-react";
import { type StepState } from "./StepTimeline";
import { ReasoningPanel } from "./ReasoningPanel";
import { StreamingText } from "./StreamingText";
import { ChartRenderer } from "./ChartRenderer";
import { SignalStrip } from "./SignalStrip";
import { AnalysisPanelCard } from "./AnalysisPanelCard";
import { DataTable } from "./DataTable";
import { downloadUrl } from "@/lib/stream";
import type { FinalResult } from "@/lib/types";

export interface AssistantTurnData {
  id: string;
  sessionId: string;
  steps: StepState[];
  final: FinalResult | null;
  streaming: boolean;
  startedAt: number;
  durationMs: number | null;
}

export function AssistantTurn({ turn }: { turn: AssistantTurnData }) {
  const final = turn.final;
  const panels = final?.panels ?? [];
  const hasChart =
    final?.chart_spec && final.chart_spec.chart_type !== "kpi_callout" && final.query_result;
  const canDownload = Boolean(hasChart);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex flex-col gap-3"
    >
      <ReasoningPanel
        steps={turn.steps}
        streaming={turn.streaming}
        durationMs={turn.durationMs}
      />

      {final?.narration && (
        <div className="rounded-xl border border-border bg-surface px-5 py-4">
          <StreamingText
            key={final.narration}
            text={final.narration}
            className="text-[15.5px] leading-[1.7] text-foreground"
          />
        </div>
      )}

      {final?.error && !final?.narration && (
        <div className="rounded-xl border border-danger/30 bg-danger/5 px-5 py-4 text-[14px] text-danger">
          {final.error}
        </div>
      )}

      {final?.signals && <SignalStrip signals={final.signals} />}

      {hasChart && final?.chart_spec && final?.query_result && (
        <div className="rounded-xl border border-border bg-surface p-4">
          <ChartRenderer spec={final.chart_spec} rows={final.query_result.records} height={300} />
        </div>
      )}

      {final?.query_result && final.query_result.records.length > 0 && (
        <details className="group rounded-xl border border-border bg-surface px-4 py-3">
          <summary className="cursor-pointer list-none text-[13px] font-medium text-muted transition-colors hover:text-accent">
            Underlying rows ({final.query_result.records.length})
          </summary>
          <div className="pt-3">
            <DataTable rows={final.query_result.records} />
          </div>
        </details>
      )}

      {panels.length > 0 && (
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-3 pt-1">
            <h2 className="text-[13px] font-semibold uppercase tracking-wide text-muted">
              Further analysis
            </h2>
            <div className="h-px flex-1 bg-border" />
          </div>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {panels.map((panel, i) => (
              <AnalysisPanelCard key={panel.panel_id} panel={panel} index={i} />
            ))}
          </div>
        </div>
      )}

      {canDownload && (
        <a
          href={downloadUrl(turn.sessionId)}
          className="inline-flex w-fit items-center gap-2 rounded-lg border border-border bg-surface px-3.5 py-2 text-[13.5px] font-medium text-foreground transition-colors hover:border-accent/40 hover:bg-accent-soft"
        >
          <Download className="h-4 w-4 text-accent" strokeWidth={2} />
          Download analysis workbook
          {panels.length > 0 && (
            <span className="text-[12px] text-muted">
              ({panels.length + 1} dashboards)
            </span>
          )}
        </a>
      )}
    </motion.div>
  );
}
