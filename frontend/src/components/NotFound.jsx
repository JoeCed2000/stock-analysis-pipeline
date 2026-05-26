export default function NotFound({ onBack, t }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      minHeight: '60vh', textAlign: 'center', padding: 24,
    }}>
      <div style={{ fontSize: 72, fontWeight: 800, color: '#30363d', lineHeight: 1, marginBottom: 8 }}>404</div>
      <h2 style={{ fontSize: 20, fontWeight: 600, color: '#e1e4e8', margin: '0 0 8px' }}>
        {t ? t('pageNotFound') : 'Page Not Found'}
      </h2>
      <p style={{ fontSize: 13, color: '#8b949e', maxWidth: 400, margin: '0 0 24px' }}>
        {t ? t('pageNotFoundDesc') : "The page you're looking for doesn't exist or has been moved."}
      </p>
      <button
        onClick={onBack}
        style={{
          padding: '8px 20px', fontSize: 13, fontWeight: 500,
          background: '#21262d', border: '1px solid #30363d',
          borderRadius: 6, color: '#58a6ff', cursor: 'pointer',
          transition: 'background 0.15s',
        }}
        onMouseEnter={e => e.target.style.background = '#30363d'}
        onMouseLeave={e => e.target.style.background = '#21262d'}
      >
        ← {t ? t('backToHome') : 'Back to Home'}
      </button>
    </div>
  );
}
