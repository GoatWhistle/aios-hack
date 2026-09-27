import { isNum, isRecord, isStr, list, numOrNull } from '@/jarvis/cards/payloads/payloadPrimitives';

export interface RunSeriesRow {
  step: number;
  date: string;
  input_rate: number | null;
  scheduled_rate: number | null;
}

export interface RunSeriesPayload {
  run_id: string;
  well: string;
  role: string;
  metric: string;
  unit: string;
  input_source: string;
  schedule_source: string;
  rows: RunSeriesRow[];
}

export const readRunSeries = (value: unknown): RunSeriesPayload | null => {
  if (!isRecord(value) || !isStr(value.run_id) || !isStr(value.well)) return null;
  const rows = list(value.rows)
    .filter((row): row is Record<string, unknown> => isRecord(row) && isNum(row.step))
    .map((row) => ({
      step: row.step as number,
      date: isStr(row.date) ? row.date : '',
      input_rate: numOrNull(row.input_rate),
      scheduled_rate: numOrNull(row.scheduled_rate)
    }));
  if (rows.length === 0) return null;
  return {
    run_id: value.run_id,
    well: value.well,
    role: isStr(value.role) ? value.role : '',
    metric: isStr(value.metric) ? value.metric : '',
    unit: isStr(value.unit) ? value.unit : '',
    input_source: isStr(value.input_source) ? value.input_source : '',
    schedule_source: isStr(value.schedule_source) ? value.schedule_source : '',
    rows
  };
};
