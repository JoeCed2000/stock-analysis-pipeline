import { useState, useEffect } from 'react';
import { fetchQuarters } from '../api.js';

export default function QuarterSelector({ ticker, selectedQuarter, onQuarterChange, t }) {
  const [quarters, setQuarters] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchQuarters(ticker)
      .then(data => {
        if (!cancelled) {
          const qs = (data.quarters || []).slice(0, 4); // last 4 quarters
          setQuarters(qs);
          // Auto-select latest if nothing selected
          if (!selectedQuarter && qs.length > 0) {
            onQuarterChange(qs[0]);
          }
        }
      })
      .catch(() => setQuarters([]))
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [ticker]);

  if (loading || quarters.length === 0) return null;

  return (
    <select
      value={selectedQuarter || quarters[0]}
      onChange={e => onQuarterChange(e.target.value)}
      style={{
        background: '#161b22',
        border: '1px solid #30363d',
        borderRadius: 4,
        color: '#58a6ff',
        fontSize: 9,
        fontWeight: 500,
        padding: '2px 6px',
        cursor: 'pointer',
        outline: 'none',
        maxWidth: 80,
      }}
    >
      {quarters.map(q => (
        <option key={q} value={q}>{q}</option>
      ))}
    </select>
  );
}
