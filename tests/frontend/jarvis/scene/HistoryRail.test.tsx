import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { HistoryRail } from '@/jarvis/scene/HistoryRail/HistoryRail';
import type { Scene } from '@/jarvis/model/scenes';
import { I18nProvider } from '@/shared/i18n/I18nContext';

vi.mock('@/jarvis/scene/HistorySessions/HistorySessions', () => ({
  HistorySessions: () => null
}));

const scene: Scene = {
  id: 'scene-1',
  sourceId: 's-01',
  question: 'Почему скважина изменила режим?',
  context: {
    scenario: 'base',
    run_id: 'run-42',
    step: 96,
    date: '2015-01-01',
    selected_well: '10',
    workspace: 'field',
    view: 'projection',
    context_version: 'v1'
  },
  cards: [],
  captionDraft: '',
  caption: 'Объяснение по журналу.',
  answerDraft: '',
  answer: null,
  ts: '2026-09-26T12:00:00Z',
  guarded: true,
  warnings: [],
  error: null,
  done: true
};

describe('history rail context', () => {
  beforeEach(() => {
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn()
    });
  });

  it('shows run, well, step, date, and scenario for the historical answer', () => {
    render(
      <I18nProvider>
        <HistoryRail scenes={[scene]} activeIndex={0} onSelect={vi.fn()} />
      </I18nProvider>
    );

    const button = screen.getByRole('button', { name: /run-42/ });
    expect(button.getAttribute('aria-label')).toContain('Скважина: 10');
    fireEvent.focus(button);

    const context = screen.getByText(/Прогон: run-42/);
    expect(context.textContent).toContain('Скважина: 10');
    expect(context.textContent).toContain('Шаг 96');
    expect(context.textContent).toContain('2015');
    expect(context.textContent).toContain('Сценарий: base');
  });

  it('consumes vertical wheel only when it can scroll history horizontally', () => {
    render(<I18nProvider><HistoryRail scenes={[scene]} activeIndex={0} onSelect={vi.fn()} /></I18nProvider>);
    const list = screen.getByRole('listbox');
    Object.defineProperty(list, 'scrollWidth', { configurable: true, value: 800 });
    Object.defineProperty(list, 'clientWidth', { configurable: true, value: 200 });
    const event = new WheelEvent('wheel', { deltaY: 50, bubbles: true, cancelable: true });
    list.dispatchEvent(event);
    expect(list.scrollLeft).toBe(50);
    expect(event.defaultPrevented).toBe(true);
    list.scrollLeft = 600;
    const edge = new WheelEvent('wheel', { deltaY: 50, bubbles: true, cancelable: true });
    list.dispatchEvent(edge);
    expect(edge.defaultPrevented).toBe(false);
  });

  it('allows Ctrl+wheel zoom and normalizes line/page scroll units', () => {
    render(<I18nProvider><HistoryRail scenes={[scene]} activeIndex={0} onSelect={vi.fn()} /></I18nProvider>);
    const list = screen.getByRole('listbox');
    Object.defineProperty(list, 'scrollWidth', { configurable: true, value: 800 });
    Object.defineProperty(list, 'clientWidth', { configurable: true, value: 200 });
    const zoom = new WheelEvent('wheel', { deltaY: 100, ctrlKey: true, bubbles: true, cancelable: true });
    list.dispatchEvent(zoom);
    expect(zoom.defaultPrevented).toBe(false);
    expect(list.scrollLeft).toBe(0);
    list.dispatchEvent(new WheelEvent('wheel', { deltaY: 3, deltaMode: 1, bubbles: true, cancelable: true }));
    expect(list.scrollLeft).toBe(96);
    list.dispatchEvent(new WheelEvent('wheel', { deltaY: 1, deltaMode: 2, bubbles: true, cancelable: true }));
    expect(list.scrollLeft).toBe(296);
  });
});
