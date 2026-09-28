import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { InputDock } from '@/jarvis/scene/InputDock/InputDock';
import { I18nProvider } from '@/shared/i18n/I18nContext';
import { useState } from 'react';
import { useJarvisSession } from '@/jarvis/provider/useJarvisSession';
import type { JarvisTransport } from '@/jarvis/transport/JarvisTransport';
import type { JarvisAskContext } from '@/jarvis/transport/events';

vi.mock('@/jarvis/voice/MicButton/MicButton', () => ({
  MicButton: ({ onCommit }: { onCommit: (text: string) => void }) => <>
    <button type="button" onClick={() => onCommit('Голосовой вопрос')}>Voice commit</button>
    <button type="button" onClick={() => onCommit('я'.repeat(650))}>Long voice commit</button>
  </>
}));
vi.mock('@/jarvis/model/sessions', async (original) => ({
  ...await original<typeof import('@/jarvis/model/sessions')>(),
  fetchSessionEvents: async () => []
}));

const transport: JarvisTransport = { mode: 'sse', async *ask() {} };
const context: JarvisAskContext = { scenario: 'base', step: 0, date: '', selected_well: null, workspace: 'field', view: 'projection' };
const DraftHarness = () => {
  const session = useJarvisSession(transport, 'ru', context);
  const [open, setOpen] = useState(true);
  return <>
    <button onClick={() => setOpen((value) => !value)}>Toggle Jarvis</button>
    <button onClick={() => session.loadSession('other')}>Other session</button>
    <button onClick={() => session.loadSession('original')}>Original session</button>
    <button onClick={() => session.pushEvents([{ type: 'scene', scene_id: 'legacy', question: 'old unfinished', context }])}>Restore unfinished</button>
    <p data-testid="current-question">{session.scenes.scenes.at(-1)?.question}</p>
    {open ? <InputDock onAsk={session.askQuestion} focusSignal={0} history={[]} sessionId={session.sessionId} draft={session.questionDraft} onDraftChange={session.setQuestionDraft} busy={session.scenes.status !== null} /> : null}
  </>;
};

describe('Jarvis question dock', () => {
  it('allows Enter after an unterminated archived answer is restored', async () => {
    render(<I18nProvider><DraftHarness /></I18nProvider>);
    fireEvent.click(screen.getByText('Restore unfinished'));
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Следующий вопрос' } });
    expect((screen.getByRole('button', { name: 'Спросить' }) as HTMLButtonElement).disabled).toBe(false);
    await act(async () => { fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' }); });
    expect(screen.getByTestId('current-question').textContent).toBe('Следующий вопрос');
  });
  it('preserves a session-specific draft across closing and reopening the screen', async () => {
    render(<I18nProvider><DraftHarness /></I18nProvider>);
    await act(async () => { fireEvent.click(screen.getByText('Original session')); });
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Покажи график скважины 62 для jarvis-policy-20260926.' } });
    fireEvent.click(screen.getByText('Toggle Jarvis'));
    fireEvent.click(screen.getByText('Toggle Jarvis'));
    expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('Покажи график скважины 62 для jarvis-policy-20260926.');
    await act(async () => { fireEvent.click(screen.getByText('Other session')); });
    expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('');
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Другой вопрос' } });
    await act(async () => { fireEvent.click(screen.getByText('Original session')); });
    expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('Покажи график скважины 62 для jarvis-policy-20260926.');
    await act(async () => { fireEvent.click(screen.getByText('Voice commit')); });
    expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('');
    await act(async () => { fireEvent.click(screen.getByText('Other session')); });
    expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('Другой вопрос');
  });
  it('keeps a drafted follow-up while a request is busy and offers cancellation', () => {
    const ask = vi.fn();
    const cancel = vi.fn();
    render(<I18nProvider><InputDock onAsk={ask} focusSignal={0} history={[]} busy onCancel={cancel} /></I18nProvider>);
    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'Следующий вопрос' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(ask).not.toHaveBeenCalled();
    expect((input as HTMLTextAreaElement).value).toBe('Следующий вопрос');
    fireEvent.click(screen.getByRole('button', { name: 'Остановить' }));
    expect(cancel).toHaveBeenCalledOnce();
  });

  it('does not submit an Enter used to complete IME composition', () => {
    const ask = vi.fn();
    render(<I18nProvider><InputDock onAsk={ask} focusSignal={0} history={[]} /></I18nProvider>);
    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'Вопрос' } });
    fireEvent.keyDown(input, { key: 'Enter', isComposing: true });
    fireEvent.keyDown(input, { key: 'Enter', keyCode: 229 });
    expect(ask).not.toHaveBeenCalled();
  });

  it('clears a submitted voice draft without relying on transcript callback ordering', () => {
    const ask = vi.fn();
    render(<I18nProvider><InputDock onAsk={ask} focusSignal={0} history={[]} /></I18nProvider>);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Предыдущий черновик' } });
    fireEvent.click(screen.getByText('Voice commit'));
    expect(ask).toHaveBeenCalledWith('Голосовой вопрос');
    expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('');
  });

  it('keeps voice as a bounded draft while busy and sends it when ready', () => {
    const ask = vi.fn();
    const { rerender } = render(<I18nProvider><InputDock onAsk={ask} focusSignal={0} history={[]} busy /></I18nProvider>);
    fireEvent.click(screen.getByText('Long voice commit'));
    expect(ask).not.toHaveBeenCalled();
    expect((screen.getByRole('textbox') as HTMLTextAreaElement).value.length).toBe(600);
    rerender(<I18nProvider><InputDock onAsk={ask} focusSignal={0} history={[]} /></I18nProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Спросить' }));
    expect(ask).toHaveBeenCalledWith('я'.repeat(600));
  });

  it('resets recall when history changes instead of recalling an absent entry', () => {
    const ask = vi.fn();
    const { rerender } = render(<I18nProvider><InputDock onAsk={ask} focusSignal={0} history={['Первый', 'Второй']} /></I18nProvider>);
    const input = screen.getByRole('textbox');
    fireEvent.keyDown(input, { key: 'ArrowUp' });
    fireEvent.keyDown(input, { key: 'ArrowUp' });
    rerender(<I18nProvider><InputDock onAsk={ask} focusSignal={0} history={[]} /></I18nProvider>);
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect((input as HTMLTextAreaElement).value).toBe('Первый');
  });

  it('keeps recall during same-question streaming updates and resets on session switch', () => {
    const ask = vi.fn();
    const { rerender } = render(<I18nProvider><InputDock onAsk={ask} focusSignal={0} history={['Первый', 'Второй']} sessionId="one" busy /></I18nProvider>);
    const input = screen.getByRole('textbox');
    fireEvent.keyDown(input, { key: 'ArrowUp' });
    fireEvent.keyDown(input, { key: 'ArrowUp' });
    rerender(<I18nProvider><InputDock onAsk={ask} focusSignal={0} history={['Первый', 'Второй']} sessionId="one" busy /></I18nProvider>);
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect((input as HTMLTextAreaElement).value).toBe('Второй');
    fireEvent.keyDown(input, { key: 'ArrowUp' });
    rerender(<I18nProvider><InputDock onAsk={ask} focusSignal={0} history={['Первый', 'Второй']} sessionId="two" busy /></I18nProvider>);
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect((input as HTMLTextAreaElement).value).toBe('Первый');
  });
});
