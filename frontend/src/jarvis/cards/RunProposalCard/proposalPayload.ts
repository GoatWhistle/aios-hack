import { isNum, isRecord, isStr } from '@/jarvis/cards/payloads/payloadPrimitives';

export interface CaseProposal {
  request_id: string;
  request: string;
  scenario: string;
  operation: string;
  constraints: Record<string, unknown>;
  base_constraints: Record<string, unknown>;
  well?: string;
  date_from?: string;
  date_to?: string;
  section?: string;
  year?: number;
  before?: number;
  after?: number;
  unit?: string;
}

export interface AlternativeProposal {
  request_id: string;
  source_run_id: string;
  source_manifest_hash: string;
  source_economics_hash: string;
  source_schedule_hash: string;
  alternative_schedule_hash: string;
  constraints_hash: string;
  source_npv_rub: number;
  additional_opm_evaluations: number;
  action: {
    well: string;
    from_step: number;
    through_step: number;
    original_target_m3_per_day: number;
    alternative_target_m3_per_day: number;
  };
}

export interface RecordedComparison {
  status: string;
  npv_delta_rub: number | null;
  reason: string | null;
}

export const readCase = (value: unknown): CaseProposal | null => {
  if (!isRecord(value) || !isStr(value.request_id) || !isStr(value.request)
    || !isStr(value.scenario) || !isStr(value.operation)
    || !isRecord(value.constraints) || !isRecord(value.base_constraints)
    || value.requires_confirmation !== true) return null;
  return value as unknown as CaseProposal;
};

export const readAlternative = (value: unknown): AlternativeProposal | null => {
  if (!isRecord(value) || !isStr(value.request_id) || !isStr(value.source_run_id)
    || !isStr(value.source_manifest_hash) || !isStr(value.source_economics_hash)
    || !isStr(value.source_schedule_hash) || !isStr(value.alternative_schedule_hash)
    || !isStr(value.constraints_hash) || !isNum(value.source_npv_rub)
    || !isNum(value.additional_opm_evaluations) || !isRecord(value.action)
    || !isStr(value.action.well) || !isNum(value.action.from_step)
    || !isNum(value.action.through_step)
    || !isNum(value.action.original_target_m3_per_day)
    || !isNum(value.action.alternative_target_m3_per_day)
    || value.requires_confirmation !== true) return null;
  return value as unknown as AlternativeProposal;
};

export const proposalRunBody = (
  type: 'case-proposal' | 'alternative-proposal',
  proposal: CaseProposal | AlternativeProposal,
  budget: number
): Record<string, unknown> => {
  if (type === 'case-proposal') {
    const value = proposal as CaseProposal;
    return {
      mode: 'search',
      budget,
      constraints: value.constraints,
      case_request: {
        request_id: value.request_id,
        request: value.request,
        scenario: value.scenario,
        base_constraints: value.base_constraints
      }
    };
  }
  const value = proposal as AlternativeProposal;
  return {
    mode: 'alternative',
    alternative_request: {
      request_id: value.request_id,
      source_run_id: value.source_run_id,
      well: value.action.well,
      control_step: value.action.from_step,
      target_m3_per_day: value.action.alternative_target_m3_per_day,
      source_manifest_hash: value.source_manifest_hash,
      source_economics_hash: value.source_economics_hash,
      source_schedule_hash: value.source_schedule_hash,
      alternative_schedule_hash: value.alternative_schedule_hash,
      constraints_hash: value.constraints_hash
    }
  };
};
