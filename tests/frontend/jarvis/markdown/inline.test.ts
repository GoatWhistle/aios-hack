import { describe, expect, it } from 'vitest';
import { parseInline } from '@/jarvis/markdown/lib/inline';

describe('markdown source links', () => {
  it('renders same-origin artifact links', () => {
    expect(parseInline('[manifest](/api/jarvis/run-artifacts/run-1/manifest)')).toEqual([
      { kind: 'link', href: '/api/jarvis/run-artifacts/run-1/manifest', spans: [{ kind: 'text', text: 'manifest' }] }
    ]);
  });

  it('does not turn an unsafe protocol into a link', () => {
    expect(parseInline('[source](javascript:alert(1))')).toEqual([
      { kind: 'text', text: '[source](javascript:alert(1))' }
    ]);
  });

  it('does not allow protocol-relative external URLs', () => {
    expect(parseInline('[source](//example.com/path)')).toEqual([
      { kind: 'text', text: '[source](//example.com/path)' }
    ]);
  });
});
