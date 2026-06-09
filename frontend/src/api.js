// Use deployed backend URL in production, local proxy in dev
const API_BASE = import.meta.env.VITE_API_URL || '/api';
export { API_BASE };

// ngrok free tier requires this header to skip the browser warning interstitial
const NGROK_HEADER = { 'ngrok-skip-browser-warning': 'true' };

export async function analyzeTickers(tickers, lang = 'en') {
  // 90s timeout — Cloudflare tunnel kills connections at ~100s.
  // For slow analyses, caller should use analyzeTickersAsync instead.
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 90000);
  const res = await fetch(`${API_BASE}/analyze?lang=${lang}`, {
    method: 'POST',
    headers: { ...NGROK_HEADER, 'Content-Type': 'application/json' },
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

/** Submit analysis via async endpoint — returns job_id immediately. Never times out. */
export async function analyzeTickersAsync(tickers, lang = 'en') {
  const res = await fetch(`${API_BASE}/analyze/async?lang=${lang}`, {
    method: 'POST',
    headers: { ...NGROK_HEADER, 'Content-Type': 'application/json' },
    body: JSON.stringify({ tickers }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const err = new Error(body?.detail?.error || `Async analysis error: ${res.status}`);
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return res.json(); // { job_id, status: "pending" }
}

/** Poll async job status. Returns { job_id, status, progress, result, error }. */
export async function getJobStatus(jobId) {
  const res = await fetch(`${API_BASE}/analyze/job/${jobId}`, { headers: NGROK_HEADER });
  if (!res.ok) throw new Error(`Job status error: ${res.status}`);
  return res.json();
}

export async function getReport(ticker) {
  const res = await fetch(`${API_BASE}/report/${ticker}`, { headers: NGROK_HEADER });
  if (!res.ok) return null;
  return res.text();
}

export async function getSources(ticker) {
  const res = await fetch(`${API_BASE}/sources/${ticker}`, { headers: NGROK_HEADER });
  if (!res.ok) return null;
  return res.json();
}

export async function listAnalyses() {
  const res = await fetch(`${API_BASE}/analyses`, { headers: NGROK_HEADER });
  if (!res.ok) return { analyses: [] };
  return res.json();
}

// === Batch endpoints ===

export async function uploadTickerFile(file) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${API_BASE}/batch/upload`, {
    method: 'POST',
    headers: NGROK_HEADER,
    body: formData,
  });
  if (!res.ok) throw new Error(`Upload error: ${res.status}`);
  return res.json();
}

export async function submitBatch(tickers) {
  const res = await fetch(`${API_BASE}/batch/analyze`, {
    method: 'POST',
    headers: { ...NGROK_HEADER, 'Content-Type': 'application/json' },
    body: JSON.stringify({ tickers }),
  });
  if (!res.ok) throw new Error(`Batch error: ${res.status}`);
  return res.json();
}

export async function getBatchStatus(jobId) {
  const res = await fetch(`${API_BASE}/batch/${jobId}/status`, { headers: NGROK_HEADER });
  if (!res.ok) throw new Error(`Status error: ${res.status}`);
  return res.json();
}

export function getBatchDownloadUrl(jobId) {
  return `${API_BASE}/batch/${jobId}/download`;
}

export function getTickerDownloadUrl(ticker, lang = 'en', quarter = null) {
  const base = `${API_BASE}/dossier/${ticker}/download?lang=${lang}`;
  if (quarter) {
    return base + `&quarter=${quarter}`;
  }
  return base;
}

export function getFeedbackAttachmentUrl(ticker, fileName) {
  const bucket = (ticker || 'GENERAL').trim().toUpperCase();
  return `${API_BASE}/feedback-file/${encodeURIComponent(bucket)}/${encodeURIComponent(fileName)}`;
}

export function getCompanyOverviewDownloadUrl(ticker, format = 'auto') {
  return `${API_BASE}/company-overview/${encodeURIComponent(ticker)}/download?format=${encodeURIComponent(format)}`;
}

export async function getSeekingAlphaAccessStatus() {
  const res = await fetch(`${API_BASE}/admin/seeking-alpha/access`, { headers: NGROK_HEADER });
  if (!res.ok) throw new Error(`Seeking Alpha status error: ${res.status}`);
  return res.json();
}

export async function saveSeekingAlphaAccess(cookieHeader, userAgent = '') {
  const res = await fetch(`${API_BASE}/admin/seeking-alpha/access`, {
    method: 'POST',
    headers: { ...NGROK_HEADER, 'Content-Type': 'application/json' },
    body: JSON.stringify({ cookie_header: cookieHeader, user_agent: userAgent || undefined }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail || `Seeking Alpha save error: ${res.status}`);
  }
  return res.json();
}

export async function clearSeekingAlphaAccess() {
  const res = await fetch(`${API_BASE}/admin/seeking-alpha/access`, {
    method: 'DELETE',
    headers: NGROK_HEADER,
  });
  if (!res.ok) throw new Error(`Seeking Alpha clear error: ${res.status}`);
  return res.json();
}

export async function uploadSeekingAlphaHar(file) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${API_BASE}/admin/seeking-alpha/access/har`, {
    method: 'POST',
    headers: NGROK_HEADER,
    body: formData,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail || `HAR upload error: ${res.status}`);
  }
  return res.json();
}

export async function testSeekingAlphaAccess(ticker = 'NVDA') {
  const res = await fetch(`${API_BASE}/admin/seeking-alpha/test`, {
    method: 'POST',
    headers: { ...NGROK_HEADER, 'Content-Type': 'application/json' },
    body: JSON.stringify({ ticker }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail || `Seeking Alpha test error: ${res.status}`);
  }
  return res.json();
}

export async function getDossierStatus(ticker) {
  const res = await fetch(`${API_BASE}/dossier/${ticker}/status`, { headers: NGROK_HEADER });
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
  // Language subdirectories (en/, jp/, fr/, etc.) share the same 7-section structure
  // — skip them so we count sections once regardless of language variants present.
  const LANG_PREFIXES = new Set(['en', 'jp', 'fr', 'de', 'zh', 'ko', 'es', 'pt']);
  const sectionsWithContent = new Set();
  for (const f of files) {
    const parts = f.split('/');
    // File with lang prefix: en/01_section/file → parts[0]='en', parts[1]='01_section'
    // File without:          01_section/file     → parts[0]='01_section'
    if (parts.length < 2) continue;
    let sectionIdx = 0;
    if (parts.length >= 3 && LANG_PREFIXES.has(parts[0].toLowerCase())) {
      sectionIdx = 1;
    }
    const section = parts[sectionIdx];
    const filename = parts.slice(sectionIdx + 1).join('/');
    // Skip placeholder files — only real content counts
    if (filename === 'README.txt' || filename === '.placeholder.txt') continue;
    sectionsWithContent.add(section);
  }
  return sectionsWithContent.size;
}

// ── Quarter selector ──

export async function fetchQuarters(ticker) {
  const res = await fetch(`${API_BASE}/earnings/quarters/${ticker}`, { headers: NGROK_HEADER });
  if (!res.ok) return { quarters: [], latest: null };
  return res.json();
}

export async function generateDeepDive(ticker, quarter, lang = 'en') {
  const res = await fetch(`${API_BASE}/earnings/deep-dive`, {
    method: 'POST',
    headers: { ...NGROK_HEADER, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ticker,
      quarter,
      language: lang,
      output_dir: `analyses/deepdive_${ticker}`,
    }),
  });
  if (!res.ok) throw new Error(`Deep-dive failed: ${res.status}`);
  return res.json();
}

/** Fetch valuation context signals from V2.4 backend endpoint. */
export async function fetchValuationContext(ticker) {
  const res = await fetch(`${API_BASE}/valuation-context/${ticker}`, { headers: NGROK_HEADER });
  if (!res.ok) return null;
  return res.json();
}

/** Fetch peer benchmark data from V2.5 backend endpoint. */
export async function fetchPeerBenchmark(ticker) {
  const res = await fetch(`${API_BASE}/peer-benchmark/${ticker}`, { headers: NGROK_HEADER });
  if (!res.ok) return null;
  return res.json();
}

export async function fetchRecentSearches(limit = 50) {
  const res = await fetch(`${API_BASE}/recent-searches?limit=${limit}`, { headers: NGROK_HEADER });
  if (!res.ok) return { searches: [] };
  return res.json();
}
