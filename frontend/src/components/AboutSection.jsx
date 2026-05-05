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

export default function AboutSection({ t }) {
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
        {t('whatIsThis')}
      </button>
    );
  }

  const sources = t('aboutSources');
  const criteria = t('aboutCriteria');
  const rules = t('aboutRules');
  const verdictColors = { BUY: '#238636', HOLD: '#d29922', SELL: '#da3633' };

  return (
    <div style={SECTION_STYLE.base}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <span style={SECTION_STYLE.title}>{t('aboutMainTitle')}</span>
        <button
          onClick={() => setOpen(false)}
          style={{ background: 'none', border: 'none', color: '#8b949e', fontSize: 16, cursor: 'pointer', padding: '0 4px', lineHeight: 1 }}
        >
          ✕
        </button>
      </div>

      <p style={{ margin: '0 0 10px 0' }}>
        {t('aboutIntro')}
      </p>

      <div style={SECTION_STYLE.title}>{t('aboutDataSources')}</div>
      <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 10 }}>
        <tbody>
          {sources.map(([name, desc]) => (
            <tr key={name}>
              <td style={{ ...SECTION_STYLE.label, padding: '3px 8px 3px 0', whiteSpace: 'nowrap', width: 140 }}>{name}</td>
              <td style={SECTION_STYLE.muted}>{desc}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div style={SECTION_STYLE.title}>{t('aboutScoring')}</div>
      <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 10 }}>
        <tbody>
          {criteria.map(([name, desc]) => (
            <tr key={name}>
              <td style={{ ...SECTION_STYLE.label, padding: '3px 8px 3px 0', whiteSpace: 'nowrap', width: 150 }}>{name}</td>
              <td style={SECTION_STYLE.muted}>{desc}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div style={SECTION_STYLE.title}>{t('aboutDecisionRules')}</div>
      <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 6 }}>
        <tbody>
          {rules.map(([verdict, desc], i) => (
            <tr key={i}>
              <td style={{ padding: '2px 12px 2px 0', whiteSpace: 'nowrap', width: 80 }}>
                <span style={{
                  color: verdictColors[verdict] || verdictColors.HOLD,
                  fontWeight: 700,
                  fontSize: verdict.length > 6 ? 10 : 13,
                }}>
                  {verdict}
                </span>
              </td>
              <td style={SECTION_STYLE.muted}>{desc}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div style={{ marginTop: 10, fontSize: 11, color: '#484f58', borderTop: '1px solid #30363d', paddingTop: 8 }}>
        {t('aboutDisclaimer')}
      </div>
    </div>
  );
}
