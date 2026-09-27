import type { ErrorPayload } from '@/jarvis/cards/payloads/payloadTypes';
import { isRecord, isStr, strOrNull } from '@/jarvis/cards/payloads/payloadPrimitives';

export const readError = (payload: unknown): ErrorPayload => {
  if (!isRecord(payload)) {
    return { code: 'unknown', tool: null, message: '', next_step: null };
  }
  return {
    code: isStr(payload.code) ? payload.code : 'unknown',
    tool: strOrNull(payload.tool),
    message: isStr(payload.message) ? payload.message : '',
    next_step: strOrNull(payload.next_step)
  };
};
