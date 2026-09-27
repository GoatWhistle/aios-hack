import type { StatusBoardPayload } from '@/jarvis/cards/payloads/systemTypes';
import { boolOrNull } from '@/jarvis/cards/payloads/scalars';
import { isNum, isRecord, isStr, list, numOrNull, strOrNull } from '@/jarvis/cards/payloads/payloadPrimitives';

export const readStatusBoard = (payload: unknown): StatusBoardPayload | null => {
  if (!isRecord(payload)) {
    return null;
  }
  const champion = isRecord(payload.champion) ? payload.champion : {};
  const last = isRecord(payload.last_run) ? payload.last_run : {};
  const diagnostics = isRecord(payload.diagnostics) ? payload.diagnostics : {};
  const violations = isRecord(payload.violations) ? payload.violations : {};
  const alertSource = isRecord(payload.diagnostics) ? diagnostics.rows : payload.alerts;
  return {
    champion: {
      recorded: champion.recorded === true,
      npv: numOrNull(champion.opm_npv_rub),
      sound: boolOrNull(champion.sound),
      ood: numOrNull(champion.ood_score),
      reason: strOrNull(champion.reason)
    },
    last_run: {
      recorded: last.recorded === true,
      run_id: strOrNull(last.run_id),
      status: strOrNull(last.status),
      verified_npv: numOrNull(last.verified_npv),
      predicted_npv: numOrNull(last.predicted_npv),
      reason: strOrNull(last.reason)
    },
    scenario: isStr(payload.scenario) ? payload.scenario : '',
    step: isNum(payload.step) ? payload.step : 0,
    date: strOrNull(payload.date),
    data: isStr(payload.data) ? payload.data : '',
    generated_at: strOrNull(payload.generated_at),
    alerts: list(alertSource)
      .filter(isRecord)
      .map((row) => ({
        pattern: strOrNull(row.pattern),
        name: strOrNull(row.name),
        well: strOrNull(row.well),
        severity: strOrNull(row.severity),
        step: numOrNull(row.step),
        date: strOrNull(row.date),
        window: Array.isArray(row.window) ? row.window.filter(isNum) : null,
        source: strOrNull(row.source)
      })),
    diagnostics: {
      recorded: diagnostics.recorded === true || (!isRecord(payload.diagnostics) && Array.isArray(payload.alerts)),
      reason: strOrNull(diagnostics.reason)
    },
    violations: {
      recorded: violations.recorded === true,
      run_id: strOrNull(violations.run_id),
      reason: strOrNull(violations.reason),
      rows: list(violations.rows).filter(isRecord).filter((row) => isStr(row.kind)).map((row) => ({
        kind: row.kind as string,
        control_step: numOrNull(row.control_step),
        well: strOrNull(row.well),
        region: numOrNull(row.region),
        detail: isStr(row.detail) ? row.detail : '',
        value: numOrNull(row.value),
        blocking: row.blocking === true
      }))
    }
  };
};
