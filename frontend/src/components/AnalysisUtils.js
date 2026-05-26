/**
 * AnalysisCard helpers — scoring, conviction, insights, dossier status.
 * Extracted from AnalysisCard.jsx to reduce component complexity.
 */

export const SCORE_COLORS = {
  BUY: '#238636',
  HOLD: '#d29922',
  SELL: '#da3633',
};

export const CONVICTION_COLORS = {
  High: '#238636',
  Moderate: '#d29922',
  Low: '#da3633',
};

export function getConvictionLevel(conviction, scoring) {
  if (scoring?.total >= 28) return 'High';
  if (scoring?.total >= 18) return 'Moderate';
  if (scoring?.total < 18) return 'Low';
  if (!conviction) return 'Moderate';
  const c = conviction.toLowerCase();
  if (c.includes('high') || c.includes('strong')) return 'High';
  if (c.includes('low') || c.includes('weak') || c.includes('fragile')) return 'Low';
  return 'Moderate';
}

export function getInsight(scoring, t) {
  if (!scoring) return null;
  const s = scoring;
  const key = (() => {
    if (s.growth >= 8) return 'insight_growth';
    if (s.valuation >= 6 && s.growth >= 6) return 'insight_undervalued';
    if (s.financial_health >= 8) return 'insight_fundamentals';
    if (s.moat >= 3) return 'insight_moat';
    if (s.management >= 4) return 'insight_management';
    if (s.valuation <= 3) return 'insight_valuation_concern';
    if (s.sentiment <= 1) return 'insight_geopolitical';
    return 'insight_mixed';
  })();
  return t ? t(key) : key;
}

export function canDownloadDossier(status) {
  return Boolean(
    status?.ready === true
    && status?.verified === true
    && status?.download_enabled === true
    && status?.phase === 'complete'
  );
}

export function scorePercent(total) {
  return (total / 40) * 100;
}

export function scoreBarColor(total) {
  if (total >= 28) return '#238636';
  if (total >= 18) return '#d29922';
  return '#da3633';
}
