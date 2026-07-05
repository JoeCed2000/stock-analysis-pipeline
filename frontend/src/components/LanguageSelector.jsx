import translations from '../i18n.js';

const FLAGS = {
  en: '🇺🇸',
  jp: '🇯🇵',
};

const LABELS = {
  en: 'English',
  jp: '日本語',
};

export default function LanguageSelector({ lang, onLanguageChange }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6,
      fontSize: 13, color: 'var(--muted)',
    }}>
      <span style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {translations[lang]?.language || 'Language'}
      </span>
      <select
        value={lang}
        onChange={(e) => onLanguageChange(e.target.value)}
        style={{
          background: 'rgba(13,21,38,0.7)',
          border: '1px solid rgba(125,155,195,0.22)',
          borderRadius: 4,
          color: 'var(--ink)',
          padding: '4px 8px',
          fontSize: 13,
          cursor: 'pointer',
          fontFamily: 'inherit',
        }}
      >
        {Object.keys(FLAGS).map(code => (
          <option key={code} value={code}>
            {FLAGS[code]} {LABELS[code]}
          </option>
        ))}
      </select>
    </div>
  );
}
