export type ProvenanceKind =
  | 'measured'
  | 'synthetic'
  | 'general'
  | 'knowledge'
  | 'configuration'
  | 'policy'
  | 'mixed'
  | 'recorded'
  | 'replay'
  | 'unmeasured'
  | 'unavailable'
  | 'unknown';

export const provenanceKindOf = (provenance: string): ProvenanceKind => {
  const value = provenance.trim().toLowerCase();
  if (value.length === 0 || value === 'none') {
    return 'unknown';
  }
  if (value === 'general') {
    return 'general';
  }
  if (value === 'knowledge' || value === 'docs') {
    return 'knowledge';
  }
  if (value.includes('synthetic') || value.includes('demo')) {
    return 'synthetic';
  }
  if (value === 'config' || value === 'deck' || value.includes('model_z deck')) {
    return 'configuration';
  }
  if (value === 'policy' || value === 'water-feasible-baseline') {
    return 'policy';
  }
  if (value === 'policy-hierarchy-replay') {
    return 'replay';
  }
  if (value === 'policy-hierarchy-trace') {
    return 'recorded';
  }
  if (value.startsWith('policy-')) {
    return 'policy';
  }
  if (value === 'mixed') {
    return 'mixed';
  }
  if (value === 'ablation-not-run') {
    return 'unmeasured';
  }
  if (value === 'unavailable') {
    return 'unavailable';
  }
  if (['runs', 'run-manifest', 'submission-bundle', 'scenario-registry', 'recorded-generation-journal'].includes(value)) {
    return 'recorded';
  }
  if (value.startsWith('model-z-') || value.startsWith('opm-') || value.startsWith('measured-')) {
    return 'measured';
  }
  return 'unknown';
};

export const provenanceTitleKey = (kind: ProvenanceKind): string => {
  if (kind === 'general') {
    return 'jarvis-cards.provenanceGeneral';
  }
  if (kind === 'knowledge') {
    return 'jarvis-cards.provenanceKnowledge';
  }
  return `trust.provenance.${kind}`;
};
