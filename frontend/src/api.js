const API_BASE = '/api';

export async function analyzeTickers(tickers) {
  const res = await fetch(`${API_BASE}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tickers }),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getReport(ticker) {
  const res = await fetch(`${API_BASE}/report/${ticker}`);
  if (!res.ok) return null;
  return res.text();
}

export async function getSources(ticker) {
  const res = await fetch(`${API_BASE}/sources/${ticker}`);
  if (!res.ok) return null;
  return res.json();
}

export async function listAnalyses() {
  const res = await fetch(`${API_BASE}/analyses`);
  if (!res.ok) return { analyses: [] };
  return res.json();
}
