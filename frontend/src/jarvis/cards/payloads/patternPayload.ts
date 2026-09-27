import type { PatternPayload } from '@/jarvis/cards/payloads/payloadTypes';
import { isNum, isRecord, isStr, numbersOf, strOrNull } from '@/jarvis/cards/payloads/payloadPrimitives';

export const readPattern = (payload: unknown): PatternPayload | null => {
  if (!isRecord(payload) || !isStr(payload.pattern_id) || !isStr(payload.well)) {
    return null;
  }
  const rawWindow = payload.window;
  const range = Array.isArray(rawWindow) && rawWindow.length === 2
    ? { from_step: rawWindow[0], to_step: rawWindow[1] }
    : isRecord(rawWindow)
      ? rawWindow
      : null;
  const rawWindowDates = payload.window_dates;
  const windowDates = Array.isArray(rawWindowDates)
    && rawWindowDates.length === 2
    && isStr(rawWindowDates[0])
    && isStr(rawWindowDates[1])
    ? [rawWindowDates[0], rawWindowDates[1]] as [string, string]
    : null;
  return {
    pattern_id: payload.pattern_id,
    name: isStr(payload.name) ? payload.name : payload.pattern_id,
    well: payload.well,
    severity: isStr(payload.severity) ? payload.severity : '',
    step: isNum(payload.step) ? payload.step : null,
    date: strOrNull(payload.date),
    window: range !== null && isNum(range.from_step) && isNum(range.to_step)
      ? { from_step: range.from_step, to_step: range.to_step }
      : null,
    window_dates: windowDates,
    inputs: numbersOf(payload.inputs)
  };
};
