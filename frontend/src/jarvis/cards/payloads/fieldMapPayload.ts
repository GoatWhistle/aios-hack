import type { FieldMapPayload } from '@/jarvis/cards/payloads/payloadTypes';
import { isNum, isRecord, isStr, list, strOrNull } from '@/jarvis/cards/payloads/payloadPrimitives';

export const readFieldMap = (payload: unknown): FieldMapPayload | null => {
  if (!isRecord(payload)) {
    return null;
  }
  const edges = list(payload.edges)
    .filter((edge): edge is Record<string, unknown> => isRecord(edge))
    .filter((edge) => isStr(edge.injector) && isStr(edge.producer) && isNum(edge.weight))
    .map((edge) => ({
      injector: edge.injector as string,
      producer: edge.producer as string,
      weight: edge.weight as number
    }));
  const focus = list(payload.focus).filter(isStr);
  const highlight = list(payload.highlight).filter(isStr);
  if (focus.length === 0 && highlight.length === 0 && edges.length === 0) {
    return null;
  }
  return {
    focus,
    highlight,
    edges,
    layer: strOrNull(payload.layer)
  };
};
