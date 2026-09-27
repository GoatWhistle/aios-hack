import type { EventStripPayload } from '@/jarvis/cards/payloads/payloadTypes';
import { isNum, isRecord, isStr, list, strOrNull } from '@/jarvis/cards/payloads/payloadPrimitives';

export const readEventStrip = (payload: unknown): EventStripPayload | null => {
  if (!isRecord(payload)) {
    return null;
  }
  return {
    from_step: isNum(payload.from_step) ? payload.from_step : 0,
    to_step: isNum(payload.to_step) ? payload.to_step : 0,
    from_date: strOrNull(payload.from_date),
    to_date: strOrNull(payload.to_date),
    events: list(payload.events)
      .filter((row): row is Record<string, unknown> => isRecord(row) && isNum(row.step))
      .filter((row) => isStr(row.well) && isStr(row.type))
      .map((row) => ({
        step: row.step as number,
        date: isStr(row.date) ? row.date : '',
        well: row.well as string,
        type: row.type as string
      }))
  };
};
