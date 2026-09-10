"use client";

import { motion } from "framer-motion";
import { Download } from "lucide-react";
import { StepTimeline, type StepState } from "./StepTimeline";
import { StreamingText } from "./StreamingText";
import { ChartRenderer } from "./ChartRenderer";
import { downloadUrl } from "@/lib/stream";
import type { FinalResult } from "@/lib/types";

export interface AssistantTurnData {
  id: string;
  sessionId: string;
  steps: StepState[];
  final: FinalResult | null;
  streaming: boolean;
}

export function AssistantTurn({ turn }: { turn: AssistantTurnData }) {
  const showChart =
    turn.final?.chart_spec &&
    turn.final.chart_spec.chart_type !== "kpi_callout" &&
    turn.final.query_result;

  const canDownload =
    turn.final?.chart_spec && turn.final.chart_spec.chart_type !== "kpi_callout" && turn.final.query_result;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex flex-col gap-3"
    >
      <StepTimeline steps={turn.steps} />

      {turn.final?.narration && (
        <div className="rounded-xl border border-border bg-surface px-5 py-4">
          <StreamingText
            key={turn.final.narration}
            text={turn.final.narration}
            className="text-[15.5px] leading-[1.7] text-foreground"
          />
        </div>
      )}

      {turn.final?.error && !turn.final?.narration && (
        <div className="rounded-xl border border-danger/30 bg-danger/5 px-5 py-4 text-[14px] text-danger">
          {turn.final.error}
        </div>
      )}

      {showChart && turn.final?.chart_spec && turn.final?.query_result && (
        <ChartRenderer spec={turn.final.chart_spec} data={turn.final.query_result} />
      )}

      {canDownload && (
        <a
          href={downloadUrl(turn.sessionId)}
          className="inline-flex w-fit items-center gap-2 rounded-lg border border-border bg-surface px-3.5 py-2 text-[13.5px] font-medium text-foreground transition-colors hover:border-accent/40 hover:bg-accent-soft"
        >
          <Download className="h-4 w-4 text-accent" strokeWidth={2} />
          Download analysis workbook
        </a>
      )}
    </motion.div>
  );
}
