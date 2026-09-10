// Mirrors app/models/schemas.py and the SSE payload shape produced by
// app/api/main.py's _json_safe(). Kept intentionally loose (unknown /
// optional-heavy) where the backend's Pydantic models allow nulls, since
// this is a UI-facing contract, not a validator.

export type StageName =
  | "route"
  | "disambiguate"
  | "generate_sql"
  | "execute"
  | "repair_sql"
  | "handled_error"
  | "run_tools"
  | "plan_research"
  | "run_probes"
  | "synthesize"
  | "analyze"
  | "narrate"
  | "chart";

export type ResearchDepth = "standard" | "deep";

export type ProbeType =
  | "decompose_by"
  | "trend_by_segment"
  | "period_comparison"
  | "concentration"
  | "distribution"
  | "related_metric";

export interface RouterOutput {
  intent: "lookup" | "aggregation" | "comparison" | "trend" | "forecast" | "anomaly";
  requires_chart: boolean;
  requires_forecast: boolean;
  time_grain: "month" | "quarter" | "year" | "none";
  entities: string[];
  ambiguous_aggregation_level: boolean;
  ambiguity_reason: string | null;
}

export interface SQLGeneratorOutput {
  sql: string | null;
  error: { error: string; missing: string | null } | null;
}

export interface PeriodChange {
  period_label: string;
  absolute_change: number;
  pct_change: number;
}

export interface ZScoreResult {
  value: number;
  bucket: "normal" | "notable" | "extreme";
}

export interface DecompositionEntry {
  sub_segment: string;
  share_of_change: number;
}

export interface DataQualityFlag {
  kind: string;
  detail: string;
  severity: "info" | "warning" | "critical";
}

export interface ForecastResult {
  horizon: number;
  point_forecast: number[];
  interval_low: number[];
  interval_high: number[];
  model_used: string;
  backtest_mape: number;
  feasible: boolean;
  feasibility_reason: string | null;
}

export interface SignalsPackage {
  question: string;
  intent: string;
  query_result_summary: Record<string, unknown>;
  period_change: PeriodChange | null;
  yoy_change: PeriodChange | null;
  zscore: ZScoreResult | null;
  decomposition: DecompositionEntry[];
  concentration_index: number | null;
  forecast: ForecastResult | null;
  data_quality_flags: DataQualityFlag[];
}

export interface AnalystFinding {
  text: string;
  cites_figure: boolean;
}

export interface AnalystOutput {
  findings: AnalystFinding[];
  follow_up_question: string | null;
}

export type ChartType =
  | "line"
  | "bar"
  | "grouped_bar"
  | "multi_line"
  | "area"
  | "pie"
  | "scatter"
  | "kpi_callout";

export interface ChartSpec {
  chart_type: ChartType;
  x_field: string | null;
  y_field: string | null;
  series_field: string | null;
  value_fields: string[];
  forecast_forced: boolean;
}

export interface ProbeSpec {
  probe_type: ProbeType;
  title: string;
  rationale: string;
  metric: string;
  dimension: string | null;
  top_n: number;
}

export interface ResearchPlan {
  should_go_deeper: boolean;
  reasoning: string;
  probes: ProbeSpec[];
}

export interface AnalysisPanel {
  panel_id: string;
  title: string;
  rationale: string;
  probe_type: ProbeType | null;
  chart_spec: ChartSpec;
  records: Record<string, unknown>[];
  signals: SignalsPackage | null;
  sql: string;
  headline: string | null;
  error: string | null;
}

export interface DataFramePayload {
  __type: "dataframe";
  records: Record<string, unknown>[];
}

export interface FinalResult {
  narration: string | null;
  chart_spec: ChartSpec | null;
  query_result: DataFramePayload | null;
  signals: SignalsPackage | null;
  panels: AnalysisPanel[];
  research_plan: ResearchPlan | null;
  error: string | null;
  final_sql: string | null;
}

export interface StageStartEvent {
  kind: "stage_start";
  stage: StageName;
}

export interface StageEndEvent {
  kind: "stage_end";
  stage: StageName;
  update: {
    router_output?: RouterOutput;
    sql_output?: SQLGeneratorOutput;
    query_result?: DataFramePayload;
    error?: string;
    signals?: SignalsPackage;
    analyst_output?: AnalystOutput;
    narration?: string;
    chart_spec?: ChartSpec;
    research_plan?: ResearchPlan;
    panels?: AnalysisPanel[];
    [key: string]: unknown;
  };
}

export interface FinalEvent {
  kind: "final";
  result: FinalResult;
}

export type StreamEvent = StageStartEvent | StageEndEvent | FinalEvent;
