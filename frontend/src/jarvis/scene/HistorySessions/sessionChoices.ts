import type { SessionRow } from '@/jarvis/model/sessions';
import { beadTime, sessionDayKey } from '@/jarvis/scene/lib/cardGlyphs';

export const NEW_SESSION = '';

export interface SessionChoice {
  id: string;
  question: string;
  time: string;
  day: string;
  scenes: number;
}

export interface SessionGroup {
  day: string;
  items: readonly SessionChoice[];
}

interface Labels {
  today: string;
  yesterday: string;
  noQuestion: string;
  newSession: string;
}

export const buildChoices = (
  rows: readonly SessionRow[],
  lang: string,
  labels: Labels,
  today: Date
): SessionChoice[] => [
  { id: NEW_SESSION, question: labels.newSession, time: '', day: '', scenes: 0 },
  ...rows.map((row) => {
    const key = sessionDayKey(lang, row.last, today);
    const day = key === 'today' ? labels.today : key === 'yesterday' ? labels.yesterday : key;
    return {
      id: row.id,
      question: row.first_question.length === 0 ? labels.noQuestion : row.first_question,
      time: beadTime(lang, row.last),
      day,
      scenes: row.scenes
    };
  })
];

export const groupChoices = (choices: readonly SessionChoice[]): SessionGroup[] => {
  const groups: SessionGroup[] = [];
  for (const choice of choices.slice(1)) {
    const last = groups[groups.length - 1];
    if (last !== undefined && last.day === choice.day) {
      groups[groups.length - 1] = { day: last.day, items: [...last.items, choice] };
      continue;
    }
    groups.push({ day: choice.day, items: [choice] });
  }
  return groups;
};

export const labelOf = (choice: SessionChoice | undefined): string => {
  if (choice === undefined) {
    return '';
  }
  if (choice.id === NEW_SESSION || choice.time.length === 0) {
    return choice.question;
  }
  return `${choice.day} ${choice.time} · ${choice.question}`;
};
