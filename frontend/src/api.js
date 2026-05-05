// Use deployed backend URL in production, local proxy in dev
const API_BASE = import.meta.env.VITE_API_URL || '/api';

export async function analyzeTickers(tickers, lang = 'en') {
  // 45s timeout — Render free tier kills requests after ~30s
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 45000);
  const res = await fetch(`${API_BASE}/analyze?lang=${lang}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tickers }),
    signal: controller.signal,
  }).finally(() => clearTimeout(timeoutId));

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const err = new Error(body?.detail?.message || `Analysis error: ${res.status}`);
    err.status = res.status;
    err.body = body;
    throw err;
  }
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

export function getTickerDownloadUrl(ticker, lang = 'en') {
  const base = `${API_BASE}/dossier/${ticker}/download?lang=${lang}`;
  return base;
}

export async function getDossierStatus(ticker) {
  const res = await fetch(`${API_BASE}/dossier/${ticker}/status`);
  if (!res.ok) return { ready: false, files: [], stage: 'error' };
  return res.json();
}

const ALL_SECTIONS = [
  '01_official_company_sources',
  '02_sec_or_regulatory_filings',
  '03_financial_data_sources',
  '04_transcripts_and_management',
  '05_market_and_context',
  '06_extracted_data',
  '07_final_report',
];

export function countDossierSections(files) {
  // Count how many of the 7 sections have files (exclude .placeholder/.README)
  const sectionsWithContent = new Set();
  for (const f of files) {
    const parts = f.split('/');
    if (parts.length >= 2) {
      const section = parts[0];
      const filename = parts.slice(1).join('/');
      // Skip placeholder files — only real content counts
      if (filename === 'README.txt' || filename === '.placeholder.txt') continue;
      sectionsWithContent.add(section);
    }
  }
  return sectionsWithContent.size;
}
