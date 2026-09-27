import type { CompareConstraints, CompareStatus } from '@/jarvis/cards/payloads/systemTypes';

export type * from '@/jarvis/cards/payloads/systemTypes';

export interface SparkPoint {
  step: number;
  value: number | null;
}

export interface MetricPayload {
  id: string;
  label: string;
  value: number;
  unit: string;
  delta: number | null;
  spark: SparkPoint[];
}

export interface WellPayload {
  well: string;
  step: number | null;
  date: string | null;
  role: string;
  availability: string;
  operating_status: string;
  liquid_rate: number;
  injection_rate: number;
  watercut: number | null;
  bhp: number;
  setpoint: number;
  npv: number | null;
  npv_provenance: string;
  npv_source_run_id: string | null;
  spark: SparkPoint[];
}

export interface WellListRow {
  well: string;
  value: number;
  share: number | null;
}

export interface WellListPayload {
  by: string;
  unit: string;
  order: string;
  period: 'whole_horizon' | 'control_step';
  step: number | null;
  date: string | null;
  total_count: number;
  rows: WellListRow[];
}

export interface SeriesRow {
  step: number;
  date: string;
  value: number | null;
}

export interface SeriesPayload {
  metric: string;
  unit: string;
  rows: SeriesRow[];
  window: [number, number] | null;
}

export interface RulePayload {
  rule: string;
  name: string;
  statement: string;
  inputs: Record<string, number>;
  decision: string;
  why: string | null;
  delta_npv: number | null;
  share: number | null;
}

export interface RuleSummaryPayload {
  npv_total: number | null;
  rules: RulePayload[];
}

export interface CompareSide {
  id: string;
  npv: number | null;
  npv_basis: string | null;
  status: CompareStatus;
  constraints: CompareConstraints;
}

export interface ComparePayload {
  a: CompareSide;
  b: CompareSide;
  delta_npv: number | null;
  delta_npv_reason: string | null;
  top_diff_wells: { well: string; delta: number }[];
  comparison_reason: string | null;
  comparability: { status: string; note: string; missing_fields: string[] | null; mismatched_fields: string[] | null } | null;
  economic_breakdown: { recorded: boolean; deltas_b_minus_a: Record<string, number> | null; reason: string | null };
  production_injection: {
    recorded: boolean;
    reason: string | null;
    matched_rows: number;
    unmatched_rows: number | null;
    totals_delta_b_minus_a: { oil_mass_delta: number; injection_volume_delta: number } | null;
    top_diff_wells_steps: { well: string; control_step: number; oil_mass_delta_b_minus_a: number; injection_volume_delta_b_minus_a: number }[];
  };
  conclusion_markdown: string | null;
}

export interface WellComparisonSide {
  well: string;
  role: string | null;
  availability: string | null;
  operating_status: string | null;
  liquid_rate: number | null;
  injection_rate: number | null;
  watercut: number | null;
  bhp: number | null;
  setpoint: number | null;
  npv_whole_horizon: number | null;
}

export interface WellComparisonPayload {
  scenario: string;
  step: number;
  date: string;
  a: WellComparisonSide;
  b: WellComparisonSide;
  deltas_b_minus_a: Record<string, number | null>;
  npv_provenance: string;
  npv_source_run_id: string | null;
  direct_connection: { measured: boolean; weight: number | null; lag_months: number | null; provenance: string } | null;
  decision_evidence: {
    run_id: string | null;
    status: string;
    source_alignment: string;
    state_source_run_id: string | null;
    pairwise_preference: string;
    well_constraints: {
      status: string;
      constraints_hash?: string;
      outages: Record<string, { well: string; control_step_from: number; control_step_to: number }[]>;
    };
    wells: Record<string, {
      recorded: boolean | null;
      rule_count: number;
      rules: { level: string; agent: string; rule: string; decision: string }[];
      final_event_count: number;
      group_allocations: { group_id: string; injection_m3_per_day: number | null }[];
      field_injection_limit_m3_per_day: number | null;
    }>;
  };
  alternative_status: string;
  comparison_note: string;
}

export interface FieldEventRow {
  step: number;
  date: string;
  well: string;
  type: string;
}

export interface EventStripPayload {
  from_step: number;
  to_step: number;
  from_date: string | null;
  to_date: string | null;
  events: FieldEventRow[];
}

export interface FieldMapEdge {
  injector: string;
  producer: string;
  weight: number;
}

export interface FieldMapPayload {
  focus: string[];
  highlight: string[];
  edges: FieldMapEdge[];
  layer: string | null;
}

export interface PatternPayload {
  pattern_id: string;
  name: string;
  well: string;
  severity: string;
  step: number | null;
  date: string | null;
  window: { from_step: number; to_step: number } | null;
  window_dates: [string, string] | null;
  inputs: Record<string, number>;
}

export interface ErrorPayload {
  code: string;
  tool: string | null;
  message: string;
  next_step: string | null;
}

export interface WhereInPlatform {
  workspace: string;
  view: string;
  what: string;
  spotlight: string | null;
}

export interface GlossaryPayload {
  id: string;
  term: string;
  definition: string;
  formula: string | null;
  unit: string | null;
  source: string | null;
  where_in_platform: WhereInPlatform[];
  related: string[];
}

export interface GuideControl {
  label: string;
  spotlight: string | null;
  hotkey: string | null;
}

export interface GuidePayload {
  workspace: string;
  view: string;
  title: string;
  what: string;
  how_to_read: string;
  controls: GuideControl[];
  questions: string[];
}
