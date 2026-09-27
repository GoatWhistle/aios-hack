import { isRecord, isStr, list, numOrNull, strOrNull } from '@/jarvis/cards/payloads/payloadPrimitives';

export interface SubmissionPayload {
  run_id: string;
  assembled: boolean;
  code: string | null;
  status: string | null;
  claimed_npv_rub: number | null;
  reason: string | null;
  source: string | null;
  schedule_include_present: boolean;
  checks: {
    status_ready_to_submit: boolean | null;
    schedule_include_present: boolean | null;
    source_run_matches: boolean | null;
    schedule_hash_matches: boolean | null;
    missing_fields: string[];
  } | null;
}

export const readSubmission = (payload: unknown): SubmissionPayload | null => {
  if (!isRecord(payload) || !isStr(payload.run_id) || typeof payload.assembled !== 'boolean') return null;
  const rawChecks = isRecord(payload.checks) ? payload.checks : null;
  const boolOrNull = (value: unknown): boolean | null => typeof value === 'boolean' ? value : null;
  return {
    run_id: payload.run_id,
    assembled: payload.assembled,
    code: strOrNull(payload.code),
    status: strOrNull(payload.status),
    claimed_npv_rub: numOrNull(payload.claimed_npv_rub),
    reason: strOrNull(payload.reason),
    source: strOrNull(payload.source),
    schedule_include_present: payload.schedule_include_present === true,
    checks: rawChecks === null ? null : {
      status_ready_to_submit: boolOrNull(rawChecks.status_ready_to_submit),
      schedule_include_present: boolOrNull(rawChecks.schedule_include_present),
      source_run_matches: boolOrNull(rawChecks.source_run_matches),
      schedule_hash_matches: boolOrNull(rawChecks.schedule_hash_matches),
      missing_fields: list(rawChecks.missing_fields).filter(isStr)
    }
  };
};
