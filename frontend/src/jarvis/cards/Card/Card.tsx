import type { ReactNode } from 'react';
import { useT } from '@/shared/i18n/I18nContext';
import type { JarvisCard } from '@/jarvis/transport/events';
import { provenanceKindOf, provenanceTitleKey } from '@/jarvis/cards/payloads/provenance';
import './Card.css';

interface CardProps {
  card: JarvisCard;
  expanded: boolean;
  onToggle: () => void;
  onOpenInConsole: () => void;
  children: ReactNode;
}

export const Card = ({ card, expanded, onToggle, onOpenInConsole, children }: CardProps) => {
  const t = useT();
  const kind = provenanceKindOf(card.provenance);

  return (
    <article
      className="jarvis-card"
      role="group"
      aria-label={t('jarvis-cards.cardLabel', { title: card.title })}
      data-type={card.type}
      data-expanded={expanded ? 'true' : undefined}
    >
      <header className="jarvis-card-head">
        <h3 className="jarvis-card-title">{card.title}</h3>
        <span
          className="jarvis-card-chip"
          data-kind={kind}
          title={card.provenance}
          aria-label={`${t(provenanceTitleKey(kind))}: ${card.provenance}`}
        >
          {t(`jarvis-cards.provenanceKind.${kind}`)}
        </span>
      </header>
      <div className="jarvis-card-body">{children}</div>
      <footer className="jarvis-card-foot">
        <button type="button" className="jarvis-card-toggle" onClick={onToggle}>
          {expanded ? t('jarvis-cards.collapse') : t('jarvis-cards.expand')}
        </button>
        {card.action === undefined ? null : (
          <button type="button" className="jarvis-card-open" onClick={onOpenInConsole}>
            {card.action.companion_only ? t('jarvis-cards.openBesideConsole') : t('jarvis-cards.openInConsole')}
          </button>
        )}
      </footer>
    </article>
  );
};
