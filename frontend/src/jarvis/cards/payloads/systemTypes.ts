export interface DocHit {
  source: string;
  url?: string;
  heading: string;
  anchor: string | null;
  snippet: string;
  text: string;
  score: number | null;
  numbers: number[];
  scope: string | null;
}

export interface DocPayload {
  query: string;
  scope: string;
  terms: string[];
  hits: DocHit[];
  indexed_chunks: number;
  indexed_files: number;
}

export interface SystemNode {
  id: string;
  label: string;
  kind: string;
  summary: string;
  doc: string | null;
  route: string | null;
  files: string[];
}

export interface SystemEdge {
  from: string;
  to: string;
  label: string;
}

export interface SystemMapPayload {
  focus: string | null;
  nodes: SystemNode[];
  edges: SystemEdge[];
  total_nodes: number;
  total_edges: number;
}

export interface StatusAlert {
  pattern: string | null;
  name: string | null;
  well: string | null;
  severity: string | null;
  step: number | null;
  date: string | null;
  window: number[] | null;
  source: string | null;
}

export interface StatusBoardPayload {
  champion: {
    recorded: boolean;
    npv: number | null;
    sound: boolean | null;
    ood: number | null;
    reason: string | null;
  };
  last_run: {
    recorded: boolean;
    run_id: string | null;
    status: string | null;
    verified_npv: number | null;
    predicted_npv: number | null;
    reason: string | null;
  };
  scenario: string;
  step: number;
  date: string | null;
  data: string;
  generated_at: string | null;
  alerts: StatusAlert[];
  diagnostics: { recorded: boolean; reason: string | null };
  violations: {
    recorded: boolean;
    run_id: string | null;
    reason: string | null;
    rows: { kind: string; control_step: number | null; well: string | null; region: number | null; detail: string; value: number | null; blocking: boolean }[];
  };
}

export interface RunRow {
  run_id: string;
  ts: string;
  status: string | null;
  predicted_npv: number | null;
  verified_npv: number | null;
  sound: boolean | null;
  strategy: string | null;
  seed: number | null;
  scenario_role: string | null;
  generation_reasons_status: string | null;
  run_manifest_available: boolean | null;
  availability_note: string | null;
}

export interface RunListPayload {
  rows: RunRow[];
  total: number;
}

export interface PhysicsCheck {
  id: string;
  status: string;
  detail: string | null;
}

export interface PhysicsPayload {
  run_id: string;
  admissible: boolean | null;
  blocking: number | null;
  warnings: number | null;
  checks: PhysicsCheck[];
}

export interface RunPayload extends RunRow {
  schedule_hash: string | null;
  claimed_npv: number | null;
  has_submission: boolean;
  violations: { kind: string; detail: string }[];
  physics: PhysicsPayload | null;
  conclusion_markdown: string | null;
}

export interface ConstraintRow {
  key: string;
  group: string | null;
  value: string | number | boolean | null;
  unit: string | null;
  source: string | null;
  empty: boolean;
}

export interface ConstraintsPayload {
  case: string;
  items: ConstraintRow[];
}

export interface CouncilLevel {
  rank: number;
  agent: string;
  level: string | null;
  verdict: string;
  bounds: number[];
  decisions: number;
}

export interface CouncilPayload {
  step: number;
  date: string | null;
  group: string | null;
  agents_fired: string[];
  levels: CouncilLevel[];
  outcome: { well: string | null; action: string | null; rule: string | null };
}

export interface CompareStatus {
  status: string | null;
  sound: boolean | null;
  converged: boolean | null;
  self_consistent: boolean | null;
  ood_score: number | null;
  ood_threshold: number | null;
  has_submission: boolean | null;
  opm_status: string | null;
}

export interface CompareConstraints {
  total: number | null;
  empty: boolean | null;
  groups: { key: string; count: number }[];
}
