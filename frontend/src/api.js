// Use deployed backend URL in production, local proxy in dev
const API_BASE = import.meta.env.VITE_API_URL || '/api';

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

// === Batch endpoints ===

export async function uploadTickerFile(file) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${API_BASE}/batch/upload`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw new Error(`Upload error: ${res.status}`);
  return res.json();
}

export async function submitBatch(tickers) {
  const res = await fetch(`${API_BASE}/batch/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tickers }),
  });
  if (!res.ok) throw new Error(`Batch error: ${res.status}`);
  return res.json();
}

export async function getBatchStatus(jobId) {
  const res = await fetch(`${API_BASE}/batch/${jobId}/status`);
  if (!res.ok) throw new Error(`Status error: ${res.status}`);
  return res.json();
}

export function getBatchDownloadUrl(jobId) {
  return `${API_BASE}/batch/${jobId}/download`;
}
