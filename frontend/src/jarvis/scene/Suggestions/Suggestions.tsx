import { type CSSProperties } from 'react';
import { useT } from '@/shared/i18n/I18nContext';
import './Suggestions.css';

interface SuggestionsProps {
  items: readonly string[];
  onPick: (text: string) => void;
}

const MAX_STEPS = 6;

export const Suggestions = ({ items, onPick }: SuggestionsProps) => {
  const t = useT();
  if (items.length === 0) {
    return null;
  }
  return (
    <ul className="jarvis-suggestions" aria-label={t('jarvis-screen.suggestionsLabel')}>
      {items.map((text, index) => (
        <li key={text} style={{ '--suggestion-step': `${Math.min(index, MAX_STEPS)}` } as CSSProperties}>
          <button
            type="button"
            className="jarvis-suggestion"
            title={text}
            onClick={() => onPick(text)}
          >
            {text}
          </button>
        </li>
      ))}
    </ul>
  );
};
