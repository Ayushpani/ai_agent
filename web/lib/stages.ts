import type { StageEndEvent, StageName } from "./types";
import {
  Compass,
  DatabaseZap,
  Play,
  AlertTriangle,
  Calculator,
  BrainCircuit,
  PenLine,
  BarChart3,
  HelpCircle,
  type LucideIcon,
} from "lucide-react";

export const STAGE_ORDER: StageName[] = [
  "route",
  "disambiguate",
  "generate_sql",
  "execute",
  "handled_error",
  "run_tools",
  "analyze",
  "narrate",
  "chart",
];

export const STAGE_LABEL: Record<StageName, string> = {
  route: "Classifying the question",
  disambiguate: "Needs clarification",
  generate_sql: "Generating SQL",
  execute: "Executing query",
  handled_error: "Could not proceed",
  run_tools: "Running analytical tools",
  analyze: "Analyst reasoning",
  narrate: "Writing the answer",
  chart: "Choosing chart type",
};

export const STAGE_ICON: Record<StageName, LucideIcon> = {
  route: Compass,
  disambiguate: HelpCircle,
  generate_sql: DatabaseZap,
  execute: Play,
  handled_error: AlertTriangle,
  run_tools: Calculator,
  analyze: BrainCircuit,
  narrate: PenLine,
  chart: BarChart3,
};

/** Short, human-readable content for a completed step — mirrors
 * app/ui/chainlit_app.py:_summarize_stage so both interfaces show the
 * same substance for the same pipeline run. */
export function summarizeStage(event: StageEndEvent): { kind: "text" | "sql"; content: string } | null {
  const { stage, update } = event;

  switch (stage) {
    case "route": {
      const intent = update.router_output?.intent;
      return intent ? { kind: "text", content: `Intent: ${intent}` } : null;
    }
    case "generate_sql": {
      if (update.sql_output?.sql) {
        return { kind: "sql", content: update.sql_output.sql };
      }
      if (update.sql_output?.error) {
        return { kind: "text", content: `Refused: ${update.sql_output.error.error}` };
      }
      return null;
    }
    case "execute": {
      if (update.query_result) {
        return { kind: "text", content: `${update.query_result.records.length} rows returned.` };
      }
      if (update.error) {
        return { kind: "text", content: update.error };
      }
      return null;
    }
    case "run_tools": {
      const signals = update.signals;
      if (!signals) return null;
      const parts: string[] = [];
      if (signals.period_change) {
        parts.push(`period change ${signals.period_change.pct_change >= 0 ? "+" : ""}${signals.period_change.pct_change.toFixed(1)}%`);
      }
      if (signals.zscore) {
        parts.push(`z-score ${signals.zscore.value.toFixed(2)} (${signals.zscore.bucket})`);
      }
      if (signals.data_quality_flags.length > 0) {
        parts.push(`${signals.data_quality_flags.length} data-quality flag(s)`);
      }
      return { kind: "text", content: parts.length > 0 ? parts.join("; ") : "No notable signals." };
    }
    case "analyze": {
      const findings = update.analyst_output?.findings;
      if (findings && findings.length > 0) {
        return { kind: "text", content: findings.map((f) => `- ${f.text}`).join("\n") };
      }
      return { kind: "text", content: "Skipped (lookup question)." };
    }
    case "chart": {
      const spec = update.chart_spec;
      return spec ? { kind: "text", content: `Chart type: ${spec.chart_type}` } : null;
    }
    default:
      return null;
  }
}
