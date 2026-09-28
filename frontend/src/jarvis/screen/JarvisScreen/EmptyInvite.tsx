import { useI18n } from '@/shared/i18n/I18nContext';

const EXAMPLE_KEYS = ['exampleFund', 'exampleWell', 'exampleRun', 'exampleScreen'] as const;

interface EmptyInviteProps {
  onPick: (question: string) => void;
}

export const EmptyInvite = ({ onPick }: EmptyInviteProps) => {
  const { t } = useI18n();
  return (
    <div className="jarvis-screen-empty">
      <p className="jarvis-screen-empty-title">{t('jarvis-screen.emptyTitle')}</p>
      <p className="jarvis-screen-empty-body">{t('jarvis-screen.emptyBody')}</p>
      <ul className="jarvis-screen-examples" aria-label={t('jarvis-screen.examplesLabel')}>
        {EXAMPLE_KEYS.map((key) => {
          const question = t(`jarvis-screen.${key}`);
          return (
            <li key={key}>
              <button type="button" className="jarvis-screen-example" onClick={() => onPick(question)}>
                {question}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
};
