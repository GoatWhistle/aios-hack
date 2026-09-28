export const readEasing = (name: string, fallback: string): string => {
  if (typeof document === 'undefined' || typeof getComputedStyle !== 'function') {
    return fallback;
  }
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return raw.length === 0 ? fallback : raw;
};
