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
  Telescope,
  Layers,
  Sparkles,
  Wrench,
  type LucideIcon,
} from "lucide-react";

export const STAGE_ORDER: StageName[] = [
  "route",
  "disambiguate",
  "generate_sql",
  "execute",
  "repair_sql",
  "handled_error",
  "run_tools",
  "plan_research",
  "run_probes",
  "synthesize",
  "analyze",
  "narrate",
  "chart",
];

export const STAGE_LABEL: Record<StageName, string> = {
  route: "Classifying the question",
  disambiguate: "Needs clarification",
  generate_sql: "Generating SQL",
  execute: "Executing query",
  repair_sql: "Correcting the query",
  handled_error: "Could not proceed",
  run_tools: "Running analytical tools",
  plan_research: "Planning deeper analysis",
  run_probes: "Investigating the data",
  synthesize: "Synthesising across panels",
  analyze: "Analyst reasoning",
  narrate: "Writing the answer",
  chart: "Choosing chart type",
};

export const STAGE_ICON: Record<StageName, LucideIcon> = {
  route: Compass,
  disambiguate: HelpCircle,
  generate_sql: DatabaseZap,
  execute: Play,
  repair_sql: Wrench,
  handled_error: AlertTriangle,
  run_tools: Calculator,
  plan_research: Telescope,
  run_probes: Layers,
  synthesize: Sparkles,
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
    case "repair_sql": {
      // The engine error that triggered the retry is the useful detail
      // here — showing the new SQL happens on the next execute step.
      if (update.sql_output?.sql) {
        return { kind: "sql", content: update.sql_output.sql };
      }
      return { kind: "text", content: "First attempt failed; retrying with the engine error." };
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
    case "analyze":
    case "synthesize": {
      const findings = update.analyst_output?.findings;
      if (findings && findings.length > 0) {
        return { kind: "text", content: findings.map((f) => `- ${f.text}`).join("\n") };
      }
      return { kind: "text", content: "Skipped (lookup question)." };
    }
    case "plan_research": {
      const plan = update.research_plan;
      if (!plan) return null;
      if (!plan.should_go_deeper) {
        return { kind: "text", content: plan.reasoning || "Answering at headline level." };
      }
      const lines = plan.probes.map((p) => `- ${p.title}: ${p.rationale}`);
      return { kind: "text", content: [plan.reasoning, ...lines].filter(Boolean).join("\n") };
    }
    case "run_probes": {
      const panels = update.panels;
      if (!panels || panels.length === 0) return null;
      const ok = panels.filter((p) => !p.error).length;
      return {
        kind: "text",
        content: `${ok} of ${panels.length} analyses returned data.`,
      };
    }
    case "chart": {
      const spec = update.chart_spec;
      return spec ? { kind: "text", content: `Chart type: ${spec.chart_type}` } : null;
    }
    default:
      return null;
  }
}
