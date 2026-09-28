import { useEffect, useState, type CSSProperties } from 'react';
import { useT } from '@/shared/i18n/I18nContext';
import type { ConsoleAction } from '@/jarvis/actions/lib/consoleAction';
import { Card } from '@/jarvis/cards/Card/Card';
import { CardBody } from '@/jarvis/cards/CardBody/CardBody';
import type { SceneCard } from '@/jarvis/model/scenes';
import './Orbit.css';

interface OrbitProps {
  cards: readonly SceneCard[];
  onOpen: (action: ConsoleAction) => void;
  briefingLoading?: boolean;
}

const STAGGER_MS = 80;

export const Orbit = ({ cards, onOpen, briefingLoading = false }: OrbitProps) => {
  const t = useT();
  const [expanded, setExpanded] = useState<string | null>(null);
  const proposalId = cards.find((entry) =>
    entry.card.type === 'case-proposal' || entry.card.type === 'alternative-proposal'
  )?.id;
  const firstId = cards[0]?.id;
  useEffect(() => {
    setExpanded(proposalId ?? firstId ?? null);
  }, [proposalId, firstId]);

  return (
    <div
      className="jarvis-orbit"
      aria-label={t('jarvis-rail.orbitLabel')}
      role="group"
      data-dense={cards.length > 6 ? 'true' : undefined}
    >
      {cards.map((entry, index) => {
        const open = expanded === entry.id;
        const style = {
          '--orbit-delay': `${index * STAGGER_MS}ms`
        } as CSSProperties;
        return (
          <div
            className="jarvis-orbit-seat"
            key={entry.id}
            style={style}
            data-open={open ? 'true' : undefined}
          >
            <Card
              card={entry.card}
              expanded={open}
              onToggle={() => setExpanded(open ? null : entry.id)}
              onOpenInConsole={() => {
                if (entry.card.action !== undefined) {
                  onOpen(entry.card.action);
                }
              }}
            >
              <CardBody card={entry.card} onOpen={onOpen} briefingLoading={briefingLoading} />
            </Card>
          </div>
        );
      })}
    </div>
  );
};
