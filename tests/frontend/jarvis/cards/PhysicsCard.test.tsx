import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { PhysicsCard } from '@/jarvis/cards/PhysicsCard/PhysicsCard';

describe('PhysicsCard', () => {
  it('localizes known invariant ids and preserves unknown ids', () => {
    render(<I18nProvider><PhysicsCard payload={{
      run_id: 'run-1', admissible: false, blocking: 1, warnings: 0,
      checks: [
        { id: 'NON_NEGATIVE', status: 'fail', detail: null },
        { id: 'EXTERNAL_CHECK', status: 'future', detail: null }
      ]
    }} /></I18nProvider>);

    const known = screen.getByText('Неотрицательные дебиты и объёмы');
    expect(known.getAttribute('title')).toBe('NON_NEGATIVE');
    expect(screen.getByText('EXTERNAL_CHECK').getAttribute('title')).toBe('EXTERNAL_CHECK');
  });
});
