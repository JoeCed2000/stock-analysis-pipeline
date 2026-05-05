import translations from '../i18n.js';

const FLAGS = {
  en: '🇺🇸',
  ja: '🇯🇵',
};

const LABELS = {
  en: 'English',
  ja: '日本語',
};

export default function LanguageSelector({ lang, onLanguageChange }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6,
      fontSize: 13, color: '#8b949e',
    }}>
      <span style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {translations[lang]?.language || 'Language'}
      </span>
      <select
        value={lang}
        onChange={(e) => onLanguageChange(e.target.value)}
        style={{
          background: '#1a1d27',
          border: '1px solid #30363d',
          borderRadius: 4,
          color: '#e1e4e8',
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
