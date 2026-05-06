# Async Data Contradiction (Props vs Fetch)

## Pattern
A React component receives some data via props (always available, synchronous) AND fetches
related data via an async API call (may return null/404). When the async fetch fails but
the props data renders correctly, the UI shows a contradiction: one part works, another shows an error.

## Symptoms
- Chart/graph renders fine (from props) but text below shows "Report not available" (from fetch)
- User thinks "analysis failed" even though scoring is complete
- Modal shows data + error simultaneously — confused UX

## Root cause
The component has TWO data sources with different reliability:
1. Props → always available (parent computed them from API response)
2. Async fetch → may return 404 if backend hasn't generated the artifact yet

## Fix: 4-state model
Replace boolean `loading`/`!loading` with explicit states:

```jsx
const [status, setStatus] = useState('loading'); // loading | success | empty | error
const [report, setReport] = useState(null);

useEffect(() => {
  setStatus('loading');
  getReport(ticker)
    .then(r => r ? setStatus('success') : setStatus('empty'))
    .catch(() => setStatus('error'));
}, [ticker]);
```

### State-specific UI
- **loading**: "⏳ Generating full analysis report…" (green banner)
- **error**: "⚠️ Report generation failed. The scoring chart reflects the live analysis." (red banner)
- **empty**: "📊 Scoring complete — full markdown report not yet generated. Run a new analysis." (blue banner)
- **success**: Full report content

## Key principle
When props data is visible AND async data is absent, the UI MUST explain WHY both states coexist.
Never show "Report not available" next to a working chart without context.

## Concrete case (stock-analysis-pipeline, 2026-05-04)
- ReportView received `scoring` via props (from `/api/analyze` response) → chart rendered
- `getReport(ticker)` called `/api/report/NVDA` → `07_final_report/report.md` not generated yet → 404
- UI showed: chart (working) + "Report not available" (confusing) — no explanation
- Fix: 4-state model with color-coded banners, Close button, score/decision in header
