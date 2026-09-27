import type {
  CompareConstraints,
  ComparePayload,
  CompareSide,
  CompareStatus
} from '@/jarvis/cards/payloads/payloadTypes';
import { isNum, isRecord, isStr, list, numOrNull, strOrNull } from '@/jarvis/cards/payloads/payloadPrimitives';

const NUMERIC_SKIP = new Set(['empty', 'recorded']);

const compareStatus = (value: unknown): CompareStatus => {
  if (!isRecord(value)) {
    return {
      status: isStr(value) ? value : null,
      sound: null,
      converged: null,
      self_consistent: null,
      ood_score: null,
      ood_threshold: null,
      has_submission: null,
      opm_status: null
    };
  }
  const flag = (key: string): boolean | null =>
    typeof value[key] === 'boolean' ? (value[key] as boolean) : null;
  return {
    status: strOrNull(value.status),
    sound: flag('sound'),
    converged: flag('converged'),
    self_consistent: flag('self_consistent'),
    ood_score: numOrNull(value.ood_score),
    ood_threshold: numOrNull(value.ood_threshold),
    has_submission: flag('has_submission'),
    opm_status: strOrNull(value.opm_status)
  };
};

const compareConstraints = (value: unknown): CompareConstraints => {
  if (isNum(value)) {
    return { total: value, empty: value === 0, groups: [] };
  }
  if (!isRecord(value)) {
    return { total: null, empty: null, groups: [] };
  }
  const groups: { key: string; count: number }[] = [];
  let total = 0;
  for (const key of Object.keys(value)) {
    if (NUMERIC_SKIP.has(key)) {
      continue;
    }
    const entry = value[key];
    if (!isNum(entry)) {
      continue;
    }
    groups.push({ key, count: entry });
    total += entry;
  }
  const dynamic = numOrNull(value.dynamic_violations);
  return {
    total: groups.length === 0 ? dynamic : total,
    empty: typeof value.empty === 'boolean' ? value.empty : null,
    groups
  };
};

const compareSide = (value: unknown): CompareSide | null => {
  if (!isRecord(value) || !isStr(value.id)) {
    return null;
  }
  return {
    id: value.id,
    npv: numOrNull(value.npv),
    npv_basis: isStr(value.npv_basis) ? value.npv_basis : null,
    status: compareStatus(value.status),
    constraints: compareConstraints(value.constraints)
  };
};

export const readCompare = (payload: unknown): ComparePayload | null => {
  if (!isRecord(payload)) {
    return null;
  }
  const a = compareSide(payload.a);
  const b = compareSide(payload.b);
  if (a === null || b === null) {
    return null;
  }
  const breakdown = isRecord(payload.economic_breakdown) ? payload.economic_breakdown : null;
  const rawDeltas = breakdown && isRecord(breakdown.deltas_b_minus_a) ? breakdown.deltas_b_minus_a : null;
  const deltas = rawDeltas === null ? null : Object.fromEntries(
    Object.entries(rawDeltas).filter((entry): entry is [string, number] => isNum(entry[1]))
  );
  const production = isRecord(payload.production_injection) ? payload.production_injection : null;
  const productionTotals = production && isRecord(production.totals_delta_b_minus_a)
    && isNum(production.totals_delta_b_minus_a.oil_mass_delta)
    && isNum(production.totals_delta_b_minus_a.injection_volume_delta)
    ? { oil_mass_delta: production.totals_delta_b_minus_a.oil_mass_delta, injection_volume_delta: production.totals_delta_b_minus_a.injection_volume_delta }
    : null;
  return {
    a,
    b,
    delta_npv: numOrNull(payload.delta_npv),
    delta_npv_reason: strOrNull(payload.delta_npv_reason),
    top_diff_wells: list(payload.top_diff_wells)
      .filter((row): row is Record<string, unknown> => isRecord(row) && isStr(row.well))
      .filter((row) => isNum(row.delta))
      .map((row) => ({ well: row.well as string, delta: row.delta as number })),
    comparison_reason: strOrNull(payload.comparison_reason),
    comparability: isRecord(payload.comparability) && isStr(payload.comparability.status) && isStr(payload.comparability.note)
      ? {
        status: payload.comparability.status,
        note: payload.comparability.note,
        missing_fields: Array.isArray(payload.comparability.missing_fields)
          ? payload.comparability.missing_fields.filter(isStr) : null,
        mismatched_fields: Array.isArray(payload.comparability.mismatched_fields)
          ? payload.comparability.mismatched_fields.filter(isStr) : null
      }
      : null,
    economic_breakdown: {
      recorded: breakdown?.recorded === true,
      deltas_b_minus_a: deltas,
      reason: strOrNull(breakdown?.reason)
    },
    production_injection: {
      recorded: production?.recorded === true,
      reason: strOrNull(production?.reason),
      matched_rows: isNum(production?.matched_rows) ? production.matched_rows : 0,
      unmatched_rows: numOrNull(production?.unmatched_rows),
      totals_delta_b_minus_a: productionTotals,
      top_diff_wells_steps: list(production?.top_diff_wells_steps)
        .filter((row): row is Record<string, unknown> => isRecord(row) && isStr(row.well) && isNum(row.control_step))
        .filter((row) => isNum(row.oil_mass_delta_b_minus_a) && isNum(row.injection_volume_delta_b_minus_a))
        .map((row) => ({ well: row.well as string, control_step: row.control_step as number,
          oil_mass_delta_b_minus_a: row.oil_mass_delta_b_minus_a as number,
          injection_volume_delta_b_minus_a: row.injection_volume_delta_b_minus_a as number }))
    },
    conclusion_markdown: strOrNull(payload.conclusion_markdown)
  };
};
