/**
 * SA V2.6 T5 — Export Menu (dropdown)
 *
 * Pure UI component: renders an Export dropdown button wired to
 * T2 (CSV), T3 (PNG), and T4 (Copy Summary) export engines.
 *
 * All data flows through `getSnapshotData()` — called at click time,
 * no network calls inside the export path.  html2canvas is lazy-loaded
 * only when the user clicks "PNG — Current Group".
 */
import { useState, useRef, useEffect, useCallback } from 'react';
import { buildExportSnapshot } from '../export/exportSnapshot.js';
import { generateCsv, buildCsvFilename, downloadCsv } from '../export/csvExport.js';
import { copySummaryToClipboard } from '../export/copySummary.js';

// ── Helpers ─────────────────────────────────────────────────────────────────

const TOAST_DURATION = 3500;

// ── Component ───────────────────────────────────────────────────────────────

export default function ExportMenu({
  getSnapshotData,
  t,
  lang,
  disabled = false,
  disabledReason = '',
}) {
  const [open, setOpen] = useState(false);
  const [pngLoading, setPngLoading] = useState(false);
  const [toast, setToast] = useState(null);   // { type: 'success'|'error'|'info', message }
  const menuRef = useRef(null);
  const btnRef = useRef(null);
  const itemsRef = useRef([]);
  const [focusIdx, setFocusIdx] = useState(-1);

  // ── i18n fallbacks ──
  const L = useCallback((key, fallback) => (t ? t(key) : null) || fallback, [t]);

  // ── Outside click ──
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) close();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  // ── Keyboard ──
  useEffect(() => {
    if (!open) return;
    const ITEMS = disabled ? 1 : 4;  // 4 actions, or 1 disabled message
    const handler = (e) => {
      if (e.key === 'Escape') { close(); btnRef.current?.focus(); return; }
      if (e.key === 'ArrowDown') { e.preventDefault(); setFocusIdx(i => (i + 1) % ITEMS); return; }
      if (e.key === 'ArrowUp') { e.preventDefault(); setFocusIdx(i => (i - 1 + ITEMS) % ITEMS); return; }
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        itemsRef.current[focusIdx]?.click();
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, focusIdx, disabled]);

  // ── Focus management ──
  useEffect(() => {
    if (open) setFocusIdx(0);
    else setFocusIdx(-1);
  }, [open]);

  const close = () => setOpen(false);

  const showToast = (message, type = 'info') => {
    setToast({ type, message });
    setTimeout(() => setToast(null), TOAST_DURATION);
  };

  // ── Export handlers ──

  const doCsv = (mode) => {
    try {
      const data = getSnapshotData();
      if (!data) { showToast(L('exportUnavailable', 'Export unavailable: not enough data'), 'error'); return; }
      const snapshot = buildExportSnapshot(data);
      const csv = generateCsv(snapshot, mode);
      const filename = buildCsvFilename(snapshot, mode);
      downloadCsv(csv, filename);
      showToast(L('exportCsvOk', 'CSV exported'), 'success');
    } catch (err) {
      showToast(`${L('exportFailed', 'Export failed')}: ${err.message}`, 'error');
    }
    close();
  };

  const doCsvCurrent = () => doCsv('current-group');
  const doCsvFull = () => doCsv('full-analysis');

  const doPng = async () => {
    setPngLoading(true);
    close();
    try {
      const data = getSnapshotData();
      if (!data) { showToast(L('exportUnavailable', 'Export unavailable: not enough data'), 'error'); setPngLoading(false); return; }
      const snapshot = buildExportSnapshot(data);
      // Lazy-load pngExport module (html2canvas is loaded inside it)
      const { captureElementToPNG, downloadPNG } = await import('../export/pngExport.js');
      const groupEl = document.querySelector('[data-export-group]');
      if (!groupEl) { showToast('No group element found', 'error'); setPngLoading(false); return; }
      const { blob, filename } = await captureElementToPNG(groupEl, snapshot);
      downloadPNG(blob, filename);
      showToast(L('exportPngOk', 'PNG exported'), 'success');
    } catch (err) {
      showToast(`${L('exportFailed', 'Export failed')}: ${err.message}`, 'error');
    } finally {
      setPngLoading(false);
    }
  };

  const doCopy = async () => {
    try {
      const data = getSnapshotData();
      if (!data) { showToast(L('exportUnavailable', 'Export unavailable: not enough data'), 'error'); return; }
      const snapshot = buildExportSnapshot(data);
      const result = await copySummaryToClipboard(snapshot);
      if (result.ok) showToast(L('exportCopyOk', 'Summary copied'), 'success');
      else showToast(`${L('exportFailed', 'Export failed')}: ${result.error || 'clipboard denied'}`, 'error');
    } catch (err) {
      showToast(`${L('exportFailed', 'Export failed')}: ${err.message}`, 'error');
    }
    close();
  };

  // ── Menu items ──
  const menuItems = disabled
    ? [{ label: disabledReason || L('exportUnavailable', 'Export unavailable: not enough data'), disabled: true }]
    : [
        { label: L('csvCurrentGroup', 'CSV — Current Group'), action: doCsvCurrent },
        { label: L('csvFullAnalysis', 'CSV — Full Analysis'), action: doCsvFull },
        { label: L('pngCurrentGroup', 'PNG — Current Group'), action: doPng, loading: pngLoading },
        { label: L('copySummary', 'Copy Summary'), action: doCopy },
      ];

  const btnLabel = L('exportButton', 'Export');

  // ── Render ──
  return (
    <div ref={menuRef} style={{ position: 'relative', display: 'inline-block' }} data-export-hide>
      <button
        ref={btnRef}
        onClick={() => setOpen(o => !o)}
        disabled={disabled}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={btnLabel}
        className="export-btn"
        style={{
          background: open ? '#1f6feb' : '#21262d',
          border: `1px solid ${open ? '#388bfd' : '#30363d'}`,
          borderRadius: 5,
          color: disabled ? '#484f58' : open ? '#fff' : '#8b949e',
          padding: '4px 10px',
          fontSize: 10,
          fontWeight: 500,
          cursor: disabled ? 'not-allowed' : 'pointer',
          opacity: disabled ? 0.5 : 1,
          transition: 'background 0.15s, border 0.15s',
          fontFamily: 'inherit',
          whiteSpace: 'nowrap',
        }}
      >
        ⬇ {btnLabel}
      </button>

      {open && (
        <div
          role="menu"
          style={{
            position: 'absolute',
            top: '100%',
            right: 0,
            zIndex: 100,
            background: '#161b22',
            border: '1px solid #30363d',
            borderRadius: 6,
            minWidth: 220,
            marginTop: 4,
            boxShadow: '0 8px 24px rgba(0,0,0,0.45)',
            overflow: 'hidden',
            padding: '4px 0',
          }}
        >
          {menuItems.map((item, i) => (
            <button
              key={i}
              ref={el => { itemsRef.current[i] = el; }}
              role="menuitem"
              onClick={item.disabled ? undefined : item.action}
              disabled={item.disabled}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                padding: '7px 14px',
                fontSize: 11,
                fontWeight: 400,
                background: focusIdx === i ? '#21262d' : 'transparent',
                border: 'none',
                color: item.disabled ? '#484f58' : '#e1e4e8',
                cursor: item.disabled ? 'default' : 'pointer',
                fontFamily: 'inherit',
                outline: focusIdx === i ? '1px solid #388bfd' : 'none',
                outlineOffset: -1,
              }}
              onMouseEnter={() => setFocusIdx(i)}
            >
              {item.loading ? '⏳ ' : ''}{item.label}
            </button>
          ))}
        </div>
      )}

      {/* ── Toast ── */}
      {toast && (
        <div
          role="status"
          aria-live="polite"
          style={{
            position: 'fixed',
            bottom: 24,
            right: 24,
            zIndex: 10000,
            padding: '8px 16px',
            borderRadius: 6,
            fontSize: 12,
            fontWeight: 500,
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
            background:
              toast.type === 'success' ? '#238636'
              : toast.type === 'error' ? '#da3633'
              : '#1f6feb',
            color: '#fff',
            boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
            transition: 'opacity 0.2s',
          }}
        >
          {toast.message}
        </div>
      )}
    </div>
  );
}
