import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import type { ConsoleAction } from '@/jarvis/actions/lib/consoleAction';
import { emptyScenes, scenesReducer, type ScenesState } from '@/jarvis/model/scenes';
import type { JarvisAskContext } from '@/jarvis/transport/events';
import { WalkthroughControls } from '@/jarvis/scene/WalkthroughControls/WalkthroughControls';

const context: JarvisAskContext = {
  scenario: 'base', run_id: 'run-1', step: 4, date: '2015-01-01', selected_well: '10',
  workspace: 'field', view: 'maps', context_version: 'v1'
};

const Harness = ({ askQuestion = vi.fn(), applyAction = vi.fn(), cancel = vi.fn() }: {
  askQuestion?: (question: string, context?: JarvisAskContext) => void;
  applyAction?: (action: ConsoleAction) => void;
  cancel?: () => void;
}) => {
  const [scenes, setScenes] = useState<ScenesState>(emptyScenes);
  const selectScene = (index: number) => setScenes((value) => ({ ...value, activeIndex: index }));
  const addInterruption = () => setScenes((value) => scenesReducer(value, {
    type: 'scene', scene_id: 'follow-up', question: 'What about the neighbour?', context
  }));
  return <I18nProvider><WalkthroughControls scenes={scenes} context={context} busy={false}
    askQuestion={(question, askContext) => { askQuestion(question, askContext); setScenes((value) => scenesReducer(value, {
      type: 'scene', scene_id: `guided-${value.scenes.length}`, question, context: askContext ?? context
    })); }}
    selectScene={selectScene} applyAction={applyAction} cancel={cancel} />
    <button type="button" onClick={addInterruption}>Ask follow-up</button>
    <output data-testid="active-scene">{scenes.activeIndex}</output>
    <output data-testid="scene-count">{scenes.scenes.length}</output>
  </I18nProvider>;
};

describe('guided walkthrough controls', () => {
  it('creates all five evidence stages as separate scenes in order', () => {
    const askQuestion = vi.fn();
    render(<Harness askQuestion={askQuestion} />);

    fireEvent.click(screen.getByRole('button', { name: 'Начать разбор' }));
    const stages = ['ситуация', 'ограничение', 'решение', 'результат', 'допуск'];
    stages.forEach((stage, index) => {
      expect(screen.getByText(new RegExp(`Разбор ${index + 1} из 5`))).toBeTruthy();
      expect(screen.getByText(new RegExp(stage, 'i'))).toBeTruthy();
      expect(askQuestion.mock.calls[index][0]).toContain('4');
      expect(askQuestion.mock.calls[index][0]).toContain('2015-01-01');
      if (index < stages.length - 1) {
        fireEvent.click(screen.getByRole('button', { name: 'Дальше' }));
      }
    });

    expect(askQuestion).toHaveBeenCalledTimes(5);
    expect(screen.getByTestId('scene-count').textContent).toBe('5');
    expect((screen.getByRole('button', { name: 'Дальше' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('steps forward, back, and stops while keeping questions on the starting well and date', () => {
    const askQuestion = vi.fn();
    const applyAction = vi.fn();
    const cancel = vi.fn();
    render(<Harness askQuestion={askQuestion} applyAction={applyAction} cancel={cancel} />);

    fireEvent.click(screen.getByRole('button', { name: 'Начать разбор' }));
    expect(askQuestion).toHaveBeenCalledTimes(1);
    expect(askQuestion.mock.calls[0][1]).toMatchObject({ step: 4, date: '2015-01-01', selected_well: '10' });
    fireEvent.click(screen.getByRole('button', { name: 'Дальше' }));
    expect(askQuestion).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole('button', { name: 'Назад' }));
    expect(screen.getByTestId('active-scene').textContent).toBe('0');
    fireEvent.click(screen.getByRole('button', { name: 'Дальше' }));
    expect(askQuestion).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole('button', { name: 'Остановить' }));
    expect(cancel).toHaveBeenCalledTimes(1);
    expect(applyAction).toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Начать разбор' })).toBeTruthy();
  });

  it('pauses for a follow-up question and restores focus to the walkthrough', () => {
    const applyAction = vi.fn();
    render(<Harness applyAction={applyAction} />);
    fireEvent.click(screen.getByRole('button', { name: 'Начать разбор' }));
    fireEvent.click(screen.getByRole('button', { name: 'Ask follow-up' }));
    fireEvent.click(screen.getByRole('button', { name: 'Вернуться к разбору' }));
    expect(screen.getByTestId('active-scene').textContent).toBe('0');
    expect(applyAction).toHaveBeenCalledWith(expect.objectContaining({ step: 4, well: '10' }));
  });
});
