import type { TraceRecord } from '@/entities/trace/types';
import type { JarvisAskContext, JarvisCard, JarvisEvent } from '@/jarvis/transport/events';

export interface ExplainFact {
  rule: string;
  name: string;
  inputs: Record<string, number>;
  decision: string;
}

export interface ExplainRequest {
  well: string;
  step: number;
  date: string;
  records: readonly TraceRecord[];
  context: JarvisAskContext;
  provenance: string;
  question: string;
  ruleName: (rule: string) => string;
  caption: (facts: ExplainFact[]) => string;
  noEntryTitle: string;
  noEntryMessage: string;
  cardTitle: (rule: string, well: string) => string;
}

export const NO_TRACE_ENTRY = 'no-trace-entry';

const finite = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value);

export const factsOf = (
  records: readonly TraceRecord[],
  ruleName: (rule: string) => string
): ExplainFact[] => records.flatMap((record) => {
  if (!record || typeof record.rule !== 'string' || record.rule.length === 0 ||
      typeof record.decision !== 'string' || record.decision.length === 0) return [];
  const inputs: Record<string, number> = {};
  for (const [key, value] of Object.entries(record.inputs ?? {})) {
    if (finite(value)) inputs[key] = value;
  }
  return [{ rule: record.rule, name: ruleName(record.rule), inputs, decision: record.decision }];
});

export const allowedNumbers = (facts: readonly ExplainFact[]): number[] => {
  const allowed = new Set<number>();
  for (const fact of facts) {
    for (const value of Object.values(fact.inputs)) {
      allowed.add(value);
      allowed.add(Math.abs(value));
      allowed.add(value * 100);
      allowed.add(Math.abs(value) * 100);
    }
    for (const match of fact.decision.matchAll(/-?\d+(?:[.,]\d+)?/g)) {
      const value = Number(match[0].replace(',', '.'));
      if (Number.isFinite(value)) { allowed.add(value); allowed.add(Math.abs(value)); }
    }
  }
  return [...allowed];
};

const NUMBER_PATTERN = /(?<![\w.,])-?\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?(?![\w])|(?<![\w.,])-?\d+(?:[.,]\d+)?(?![\w])/g;
const MASK_PATTERN = /\d{4}-\d{2}-\d{2}|\bR\d+\b|(?:скважин[а-яё]*|well)\s*(?:№|#)?\s*-?\d+/giu;
const supported = (candidate: number, allowed: readonly number[]) => allowed.some((value) =>
  value === 0 ? Math.abs(candidate) < 1e-12 : Math.abs(candidate - value) <= Math.abs(value) * 1e-9
);

export const unsupportedNumbers = (text: string, allowed: readonly number[]): string[] => {
  const masked = text.replace(MASK_PATTERN, (match) => '#'.repeat(match.length));
  return [...masked.matchAll(NUMBER_PATTERN)].flatMap((match) => {
    const index = match.index ?? 0;
    const raw = text.slice(index, index + match[0].length);
    const value = Number(raw.replace(/[   ]/g, '').replace(',', '.'));
    return Number.isFinite(value) && !supported(value, allowed) ? [raw] : [];
  });
};

export const guardCaption = (text: string, facts: readonly ExplainFact[]) => {
  const dropped = unsupportedNumbers(text, allowedNumbers(facts));
  let cleaned = text;
  for (const raw of dropped) cleaned = cleaned.replace(raw, '');
  cleaned = cleaned.replace(/\s{2,}/g, ' ').replace(/\s+([,.;:!?])/g, '$1').trim();
  return { text: cleaned, guarded: true, dropped };
};

export const explainEvents = (request: ExplainRequest): JarvisEvent[] => {
  const sceneId = `explain-${request.well}-${request.step}-${Date.now().toString(36)}`;
  const events: JarvisEvent[] = [{ type: 'scene', scene_id: sceneId, question: request.question, context: request.context }];
  const facts = factsOf(request.records, request.ruleName);
  if (facts.length === 0) {
    const card: JarvisCard = {
      type: 'error', title: request.noEntryTitle,
      payload: { code: NO_TRACE_ENTRY, tool: 'decision_journal', message: request.noEntryMessage, well: request.well, step: request.step },
      provenance: 'none'
    };
    events.push({ type: 'card', scene_id: sceneId, card_id: `${sceneId}-c1`, order: 1, card });
    events.push({ type: 'caption', scene_id: sceneId, text: request.noEntryMessage, guarded: true });
  } else {
    facts.forEach((fact, index) => {
      const card: JarvisCard = {
        type: 'rule', title: request.cardTitle(fact.rule, request.well),
        payload: { rule: fact.rule, name: fact.name, statement: '', inputs: fact.inputs, decision: fact.decision, well: request.well, step: request.step, date: request.date, source: 'trace.json' },
        provenance: request.provenance,
        action: { workspace: 'decisions', view: 'rules', scenario: request.context.scenario, step: request.step, well: request.well, spotlight: 'rules-trace' }
      };
      events.push({ type: 'card', scene_id: sceneId, card_id: `${sceneId}-c${index + 1}`, order: index + 1, card });
    });
    const guarded = guardCaption(request.caption(facts), facts);
    if (guarded.dropped.length) events.push({ type: 'warning', code: 'number-dropped', detail: guarded.dropped.join(', ') });
    events.push({ type: 'caption', scene_id: sceneId, text: guarded.text, guarded: true });
  }
  events.push({ type: 'done', scene_id: sceneId, tool_rounds: 0, elapsed_ms: 0 });
  return events;
};
