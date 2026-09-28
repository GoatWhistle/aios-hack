const parseDuration = (raw: string): number | null => {
  const text = raw.trim();
  if (text.length === 0) {
    return null;
  }
  const value = Number.parseFloat(text);
  if (!Number.isFinite(value)) {
    return null;
  }
  return text.endsWith('ms') ? value : value * 1000;
};

export const readDuration = (name: string, fallback: number): number => {
  if (typeof document === 'undefined' || typeof getComputedStyle !== 'function') {
    return fallback;
  }
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name);
  return parseDuration(raw) ?? fallback;
};
