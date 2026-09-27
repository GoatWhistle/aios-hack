import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { CouncilCard } from '@/jarvis/cards/CouncilCard/CouncilCard';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(() => cleanup());

describe('CouncilCard measurement units', () => {
  it('renders field and group allocation bounds in m³/day', () => {
    render(<I18nProvider><CouncilCard payload={{
      step: 3, date: '2020-01-01',
      levels: [
        { rank: 0, agent: 'FieldCoordinator', verdict: 'ALLOW', bounds: [250, 300], decisions: [] },
        { rank: 1, agent: 'GroupAllocator', verdict: 'VETO', bounds: [120, 100], decisions: [] }
      ],
      outcome: { well: '13', action: 'SET_LRAT', rule: null }, agents_fired: []
    }} /></I18nProvider>);

    expect(screen.getByText('250 м³/сут → 300 м³/сут')).toBeTruthy();
    expect(screen.getByText('120 м³/сут → 100 м³/сут')).toBeTruthy();
    expect(screen.getByText('Координатор поля')).toBeTruthy();
    expect(screen.getByText('Разрешено')).toBeTruthy();
    expect(screen.getByText('Распределитель по группам')).toBeTruthy();
    expect(screen.getByText('Отклонено')).toBeTruthy();
    expect(screen.getByText('13 · Задать дебит жидкости')).toBeTruthy();
  });

  it('shows council code translations in English and preserves unknown codes', () => {
    window.localStorage.setItem('aios-lang', 'en');
    render(<I18nProvider><CouncilCard payload={{
      step: 3, levels: [
        { rank: 0, agent: 'WellExecutor', verdict: 'ALLOW', bounds: [], decisions: [] },
        { rank: 1, agent: 'NewAgent', verdict: 'NEW_VERDICT', bounds: [], decisions: [] }
      ],
      outcome: { well: '10', action: 'NEW_ACTION', rule: null }, agents_fired: []
    }} /></I18nProvider>);
    expect(screen.getByText('Well executor')).toBeTruthy();
    expect(screen.getByText('Allowed')).toBeTruthy();
    expect(screen.getByText('NewAgent')).toBeTruthy();
    expect(screen.getByText('NEW_VERDICT')).toBeTruthy();
    expect(screen.getByText('10 · NEW_ACTION')).toBeTruthy();
  });

  it('localizes agents_fired while preserving unknown agent identifiers', () => {
    render(<I18nProvider><CouncilCard payload={{
      step: 3, levels: [{ rank: 0, agent: 'FieldCoordinator', verdict: 'ALLOW', bounds: [], decisions: [] }],
      agents_fired: ['FieldCoordinator', 'ExternalAgent']
    }} /></I18nProvider>);

    expect(screen.getByText('Координатор поля · ExternalAgent')).toBeTruthy();
  });
});
