import type { WellComparisonPayload, WellComparisonSide } from '@/jarvis/cards/payloads/payloadTypes';
import { isNum, isRecord, isStr, list, numOrNull, strOrNull } from '@/jarvis/cards/payloads/payloadPrimitives';

const side = (value: unknown): WellComparisonSide | null => {
  if (!isRecord(value) || !isStr(value.well)) return null;
  return {
    well: value.well,
    role: strOrNull(value.role),
    availability: strOrNull(value.availability),
    operating_status: strOrNull(value.operating_status),
    liquid_rate: numOrNull(value.liquid_rate),
    injection_rate: numOrNull(value.injection_rate),
    watercut: numOrNull(value.watercut),
    bhp: numOrNull(value.bhp),
    setpoint: numOrNull(value.setpoint),
    npv_whole_horizon: numOrNull(value.npv_whole_horizon)
  };
};

export const readWellComparison = (payload: unknown): WellComparisonPayload | null => {
  if (!isRecord(payload)) return null;
  const a = side(payload.a);
  const b = side(payload.b);
  if (!a || !b || !isNum(payload.step) || !isStr(payload.date) || !isStr(payload.scenario)) return null;
  const rawDeltas = isRecord(payload.deltas_b_minus_a) ? payload.deltas_b_minus_a : {};
  const deltas = Object.fromEntries(Object.entries(rawDeltas).map(([key, value]) => [key, numOrNull(value)]));
  const connection = isRecord(payload.direct_connection) && payload.direct_connection.measured === true
    ? {
        measured: true,
        weight: numOrNull(payload.direct_connection.weight),
        lag_months: numOrNull(payload.direct_connection.lag_months),
        provenance: isStr(payload.direct_connection.provenance) ? payload.direct_connection.provenance : 'unknown'
      }
    : null;
  const rawEvidence = isRecord(payload.decision_evidence) ? payload.decision_evidence : {};
  const rawConstraints = isRecord(rawEvidence.well_constraints) ? rawEvidence.well_constraints : {};
  const rawOutages = isRecord(rawConstraints.outages) ? rawConstraints.outages : {};
  const outages = Object.fromEntries(Object.entries(rawOutages).map(([well, entries]) => [well,
    list(entries).flatMap((entry) => isRecord(entry) && isStr(entry.well) && isNum(entry.control_step_from) && isNum(entry.control_step_to)
      ? [{ well: entry.well, control_step_from: entry.control_step_from, control_step_to: entry.control_step_to }]
      : [])
  ]));
  const rawWells = isRecord(rawEvidence.wells) ? rawEvidence.wells : {};
  const wells = Object.fromEntries(Object.entries(rawWells).flatMap(([key, value]) => {
    if (!isRecord(value)) return [];
    return [[key, {
      recorded: typeof value.recorded === 'boolean' ? value.recorded : null,
      rule_count: list(value.rule_facts).length,
      rules: list(value.rule_facts).flatMap((fact) => {
        if (!isRecord(fact)) return [];
        const entry = isRecord(fact.entry) ? fact.entry : {};
        return isStr(fact.level) && isStr(fact.agent) && isStr(entry.rule) && isStr(entry.decision)
          ? [{ level: fact.level, agent: fact.agent, rule: entry.rule, decision: entry.decision }]
          : [];
      }),
      final_event_count: list(value.final_events).length,
      group_allocations: list(value.group_allocations)
        .filter(isRecord)
        .filter((allocation) => isStr(allocation.group_id))
        .map((allocation) => ({
          group_id: allocation.group_id as string,
          injection_m3_per_day: numOrNull(allocation.injection_m3_per_day)
        })),
      field_injection_limit_m3_per_day: numOrNull(value.field_injection_limit_m3_per_day)
    }]];
  }));
  return {
    scenario: payload.scenario,
    step: payload.step,
    date: payload.date,
    a,
    b,
    deltas_b_minus_a: deltas,
    npv_provenance: isStr(payload.npv_provenance) ? payload.npv_provenance : 'unknown',
    npv_source_run_id: strOrNull(payload.npv_source_run_id),
    direct_connection: connection,
    decision_evidence: {
      run_id: strOrNull(rawEvidence.run_id),
      status: isStr(rawEvidence.status) ? rawEvidence.status : 'not-checked',
      source_alignment: isStr(rawEvidence.source_alignment) ? rawEvidence.source_alignment : 'unverified',
      state_source_run_id: strOrNull(rawEvidence.state_source_run_id),
      pairwise_preference: isStr(rawEvidence.pairwise_preference) ? rawEvidence.pairwise_preference : 'not-recorded',
      well_constraints: {
        status: isStr(rawConstraints.status) ? rawConstraints.status : 'not-checked',
        ...(isStr(rawConstraints.constraints_hash) ? { constraints_hash: rawConstraints.constraints_hash } : {}),
        outages
      },
      wells
    },
    alternative_status: isStr(payload.alternative_status) ? payload.alternative_status : 'separate-calculation-required',
    comparison_note: isStr(payload.comparison_note) ? payload.comparison_note : ''
  };
};
