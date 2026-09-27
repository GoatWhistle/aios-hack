import { describe, expect, it } from 'vitest';
import { provenanceKindOf } from '@/jarvis/cards/payloads/provenance';

describe('Jarvis card provenance classification', () => {
  it.each([
    ['model-z-base-run', 'measured'],
    ['measured-connectivity', 'measured'],
    ['synthetic-demo', 'synthetic'],
    ['general', 'general'],
    ['knowledge', 'knowledge'],
    ['docs', 'knowledge'],
    ['config', 'configuration'],
    ['deck', 'configuration'],
    ['Model_Z deck, static properties', 'configuration'],
    ['policy', 'policy'],
    ['water-feasible-baseline', 'policy'],
    ['policy-search-candidate', 'policy'],
    ['policy-hierarchy-trace', 'recorded'],
    ['policy-hierarchy-replay', 'replay'],
    ['mixed', 'mixed'],
    ['run-manifest', 'recorded'],
    ['ablation-not-run', 'unmeasured'],
    ['unavailable', 'unavailable'],
    ['none', 'unknown'],
    ['future-source-type', 'unknown']
  ] as const)('classifies %s as %s', (provenance, expected) => {
    expect(provenanceKindOf(provenance)).toBe(expected);
  });
});
