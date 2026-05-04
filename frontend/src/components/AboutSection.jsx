import { useState } from 'react';

const SECTION_STYLE = {
  base: {
    marginBottom: 16, padding: 14, borderRadius: 6,
    background: '#161b22', border: '1px solid #30363d',
    fontSize: 13, color: '#8b949e', lineHeight: 1.65,
  },
  title: { fontSize: 13, fontWeight: 600, color: '#e1e4e8', marginBottom: 8 },
  label: { color: '#58a6ff', fontWeight: 500 },
  muted: { color: '#8b949e' },
};

export default function AboutSection() {
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        style={{
          background: 'none', border: 'none', color: '#58a6ff',
          fontSize: 12, cursor: 'pointer', padding: 0, marginBottom: 12,
        }}
      >
        ▸ What is this? How does it work?
      </button>
    );
  }

  return (
    <div style={SECTION_STYLE.base}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <span style={SECTION_STYLE.title}>About the Stock Analysis Pipeline</span>
        <button
          onClick={() => setOpen(false)}
          style={{ background: 'none', border: 'none', color: '#8b949e', fontSize: 16, cursor: 'pointer', padding: '0 4px', lineHeight: 1 }}
        >
          ✕
        </button>
      </div>

      <p style={{ margin: '0 0 10px 0' }}>
        This tool performs <strong style={{ color: '#e1e4e8' }}>automated fundamental analysis</strong> on any
        publicly traded stock. For each ticker, it fetches data from multiple sources,
        scores the company across <strong style={{ color: '#e1e4e8' }}>8 weighted criteria</strong>,
        and produces a <span style={{ color: '#238636' }}>BUY</span>,
        {' '}<span style={{ color: '#d29922' }}>HOLD</span>, or
        {' '}<span style={{ color: '#da3633' }}>SELL</span> decision with full traceability.
      </p>

      <div style={SECTION_STYLE.title}>📊 Data Sources</div>
      <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 10 }}>
        <tbody>
          <tr>
            <td style={{ ...SECTION_STYLE.label, padding: '3px 8px 3px 0', whiteSpace: 'nowrap', width: 140 }}>SEC EDGAR</td>
            <td style={SECTION_STYLE.muted}>10-K / 10-Q filings — Items 1, 1A, 7, 7A, 8 (business, risks, MD&A, financials)</td>
          </tr>
          <tr>
            <td style={{ ...SECTION_STYLE.label, padding: '3px 8px 3px 0' }}>Yahoo Finance</td>
            <td style={SECTION_STYLE.muted}>Real-time price, market cap, sector, company description</td>
          </tr>
          <tr>
            <td style={{ ...SECTION_STYLE.label, padding: '3px 8px 3px 0' }}>Finnhub</td>
            <td style={SECTION_STYLE.muted}>Financial statements, valuation ratios (P/E, PEG), analyst estimates</td>
          </tr>
          <tr>
            <td style={{ ...SECTION_STYLE.label, padding: '3px 8px 3px 0' }}>Alpha Vantage</td>
            <td style={SECTION_STYLE.muted}>Earnings call transcripts — management tone & sentiment analysis</td>
          </tr>
          <tr>
            <td style={{ ...SECTION_STYLE.label, padding: '3px 8px 3px 0' }}>The Motley Fool</td>
            <td style={SECTION_STYLE.muted}>Fallback transcript source for US-listed stocks</td>
          </tr>
        </tbody>
      </table>

      <div style={SECTION_STYLE.title}>⚖️ Scoring Criteria (8 × /5 = /40)</div>
      <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 10 }}>
        <tbody>
          {[
            ['Growth', 'Revenue growth (YoY + annual), guidance trajectory'],
            ['Profitability', 'Gross margin, operating margin, net income'],
            ['Financial Strength', 'Free cash flow, net debt, balance sheet health'],
            ['Moat', 'Competitive advantage, market position, barriers to entry'],
            ['Management', 'Tone, confidence, visibility from earnings calls'],
            ['Valuation Risk', 'P/E, forward P/E, PEG ratio vs. growth'],
            ['Geopolitical Risk', 'Tariff exposure, supply chain, regulatory pressure'],
            ['Business Momentum', 'Segment trends, product cycles, market demand'],
          ].map(([name, desc]) => (
            <tr key={name}>
              <td style={{ ...SECTION_STYLE.label, padding: '3px 8px 3px 0', whiteSpace: 'nowrap', width: 150 }}>{name}</td>
              <td style={SECTION_STYLE.muted}>{desc}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div style={SECTION_STYLE.title}>📋 Decision Rules</div>
      <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 6 }}>
        <tbody>
          <tr>
            <td style={{ padding: '2px 12px 2px 0', whiteSpace: 'nowrap', width: 80 }}>
              <span style={{ color: '#238636', fontWeight: 700 }}>BUY</span>
            </td>
            <td style={SECTION_STYLE.muted}>Score ≥ 32/40 — strong fundamentals across most criteria</td>
          </tr>
          <tr>
            <td style={{ padding: '2px 12px 2px 0' }}>
              <span style={{ color: '#d29922', fontWeight: 700 }}>HOLD</span>
            </td>
            <td style={SECTION_STYLE.muted}>Score 26-31 — good quality, wait for a better entry point</td>
          </tr>
          <tr>
            <td style={{ padding: '2px 12px 2px 0' }}>
              <span style={{ color: '#d29922', fontWeight: 700 }}>HOLD<br/><span style={{ fontSize: 10 }}>fragile</span></span>
            </td>
            <td style={SECTION_STYLE.muted}>Score 18-25 — mixed signals, hold but do not add</td>
          </tr>
          <tr>
            <td style={{ padding: '2px 12px 2px 0' }}>
              <span style={{ color: '#da3633', fontWeight: 700 }}>SELL</span>
            </td>
            <td style={SECTION_STYLE.muted}>Score &lt; 18 — too many risks, avoid or exit</td>
          </tr>
        </tbody>
      </table>

      <div style={{ marginTop: 10, fontSize: 11, color: '#484f58', borderTop: '1px solid #30363d', paddingTop: 8 }}>
        ⚠️ Disclaimer: This is an automated research tool, not financial advice. All data is sourced from public records.
        Every claim in the report is traceable to a stored source file (10-K HTML, API snapshots, transcripts).
        Always verify before making investment decisions.
      </div>
    </div>
  );
}
