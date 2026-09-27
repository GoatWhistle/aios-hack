import type { RunManifest, RunSubmission } from '@/entities/runs/model/runTypes';
import type { ConstraintsDoc } from '@/entities/scenarios/types';

export interface UnseenYearly {
  absolute_error_pct: number | null;
}

export interface UnseenResult {
  focus_year: string;
  fitted_schedule_hashes_count: number;
  exact_fit_overlap: boolean;
  yearly: Record<string, Record<string, UnseenYearly>>;
  paired_comparison?: {
    predicted_npv_change_rub: number;
    opm_npv_change_rub: number;
  };
}

export interface RunValidation {
  dynamic_violations: number;
  blocking_dynamic_violations?: number;
  failed_identities: string[];
}

export interface LiveRun {
  run_id: string;
  status: string;
  mode: string;
  message: string;
  message_key?: string;
  budget: number;
  evaluations?: number;
  feasible_evaluations?: number;
  rejection_reasons?: string[];
  manifest?: RunManifest;
  submission?: RunSubmission;
  flow_seconds?: number | null;
  unseen_result?: UnseenResult;
  constraints?: ConstraintsDoc;
  progress?: { step: number; total: number; date?: string; stage?: string };
  economics?: { measured_npv?: number | null; sound?: boolean };
  provenance?: Partial<RunManifest>;
  validation?: RunValidation;
  case_request?: { request_id: string; request: string; scenario: string; base_constraints?: ConstraintsDoc };
  alternative_request?: AlternativeRequest;
  comparison_available?: boolean;
  cancel_requested?: boolean;
}

export interface AlternativeRequest {
  request_id: string;
  source_run_id: string;
  well: string;
  control_step: number;
  target_m3_per_day: number;
  source_manifest_hash: string;
  source_economics_hash: string;
  source_schedule_hash: string;
  alternative_schedule_hash: string;
  constraints_hash: string;
}

export const provenanceOf = (run: LiveRun): RunManifest | undefined => {
  if (run.manifest === undefined && run.provenance === undefined) {
    return undefined;
  }
  const merged: Record<string, unknown> = { ...run.provenance };
  for (const [key, value] of Object.entries(run.manifest ?? {})) {
    if (value !== null && value !== undefined) {
      merged[key] = value;
    }
  }
  return merged as RunManifest;
};

export const blockingViolationsOf = (run: LiveRun): number => {
  const validation = run.validation;
  if (validation === undefined) {
    return 0;
  }
  if (validation.blocking_dynamic_violations !== undefined) {
    return validation.blocking_dynamic_violations;
  }
  return run.manifest?.sound === true ? 0 : validation.dynamic_violations;
};
