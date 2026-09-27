import { isNum, isRecord, isStr, list, numOrNull, strOrNull } from '@/jarvis/cards/payloads/payloadPrimitives';

export interface RunViolationLocation {
  kind: string;
  control_step: number | null;
  well: string | null;
  region: number | null;
  value: number | null;
  detail: string;
  blocking: boolean;
}

export interface RunConstraintCheck {
  constraint: string;
  status: string;
  violations: number | null;
  blocking: boolean | null;
  enforcement: string | null;
  detail: string;
}

export interface RunStatusPayload {
  run_id: string;
  status: string | null;
  acceptance: { verdict: string; opm_status: string | null; sound: boolean | null; blocking_violations: number | null; dynamic_violations: number | null; unverified_reason: string | null; npv_sources: { predicted: { value: number | null; source: string }; verified: { value: number | null; source: string } } | null } | null;
  constraints: { recorded: boolean; checks: RunConstraintCheck[]; unavailable_reason: string | null };
  violation_locations: { recorded: boolean; rows: RunViolationLocation[]; total: number | null; truncated: boolean; reason: string | null };
}

export const readRunStatus = (payload: unknown): RunStatusPayload | null => {
  if (!isRecord(payload) || !isStr(payload.run_id)) return null;
  const acceptance = isRecord(payload.acceptance) && isStr(payload.acceptance.verdict)
    ? {
        verdict: payload.acceptance.verdict,
        opm_status: strOrNull(payload.acceptance.opm_status),
        sound: typeof payload.acceptance.sound === 'boolean' ? payload.acceptance.sound : null,
        blocking_violations: numOrNull(payload.acceptance.blocking_violations),
        dynamic_violations: numOrNull(payload.acceptance.dynamic_violations),
        unverified_reason: strOrNull(payload.acceptance.unverified_reason),
        npv_sources: isRecord(payload.acceptance.npv_sources)
          ? {
              predicted: isRecord(payload.acceptance.npv_sources.predicted)
                ? { value: numOrNull(payload.acceptance.npv_sources.predicted.value), source: strOrNull(payload.acceptance.npv_sources.predicted.source) ?? 'not recorded' }
                : { value: null, source: 'not recorded' },
              verified: isRecord(payload.acceptance.npv_sources.verified)
                ? { value: numOrNull(payload.acceptance.npv_sources.verified.value), source: strOrNull(payload.acceptance.npv_sources.verified.source) ?? 'not recorded' }
                : { value: null, source: 'not recorded' }
            }
          : null
      }
    : null;
  const constraints = isRecord(payload.constraints) ? payload.constraints : null;
  const checks = constraints
    ? list(constraints.checks).filter(isRecord).filter((row) => isStr(row.constraint) && isStr(row.status)).map((row) => ({
        constraint: row.constraint as string,
        status: row.status as string,
        violations: numOrNull(row.n_violations),
        blocking: typeof row.blocking === 'boolean' ? row.blocking : null,
        enforcement: strOrNull(row.enforcement),
        detail: isStr(row.detail) ? row.detail : ''
      }))
    : [];
  const locations = isRecord(payload.violation_locations) ? payload.violation_locations : null;
  const rows = locations ? list(locations.rows).filter(isRecord).filter((row) => isStr(row.kind)).map((row) => ({
    kind: row.kind as string,
    control_step: isNum(row.control_step) ? row.control_step : null,
    well: strOrNull(row.well),
    region: isNum(row.region) ? row.region : null,
    value: numOrNull(row.value),
    detail: isStr(row.detail) ? row.detail : '',
    blocking: row.blocking === true
  })) : [];
  return {
    run_id: payload.run_id,
    status: strOrNull(payload.status),
    acceptance,
    constraints: {
      recorded: constraints?.recorded === true,
      checks,
      unavailable_reason: strOrNull(constraints?.unavailable_reason)
    },
    violation_locations: {
      recorded: locations?.recorded === true,
      rows,
      total: numOrNull(locations?.total),
      truncated: locations?.truncated === true,
      reason: strOrNull(locations?.reason)
    }
  };
};
