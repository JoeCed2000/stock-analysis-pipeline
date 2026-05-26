import { useState, useEffect, useRef } from 'react';
import { getDossierStatus, countDossierSections } from '../api.js';

/**
 * Custom hook managing the dossier polling lifecycle.
 * Returns all state needed by the dossier action buttons.
 */
export default function useDossierPolling(ticker) {
  const [dossierStatus, setDossierStatus] = useState({ sectionsReady: 0, pollFailures: 0 });
  const pollRef = useRef(null);
  const failedPollsRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    let poles = 0;
    const MAX_POLLS = 240;
    const poll = async () => {
      try {
        const status = await getDossierStatus(ticker);
        if (!cancelled) {
          failedPollsRef.current = 0;
          poles++;
          const sectionCount = countDossierSections(status.files || []);
          setDossierStatus({ ...status, sectionsReady: sectionCount, poles, pollFailures: 0 });
          const terminal = status.phase === 'complete' || status.phase === 'failed' || poles >= MAX_POLLS;
          if (terminal) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
        }
      } catch (error) {
        failedPollsRef.current += 1;
        console.warn('Dossier status poll failed', error);
        if (!cancelled) {
          setDossierStatus(prev => ({
            ...(prev || {}), sectionsReady: prev?.sectionsReady ?? 0,
            pollFailures: failedPollsRef.current,
          }));
        }
      }
    };
    poll();
    pollRef.current = setInterval(poll, 5000);
    return () => { cancelled = true; clearInterval(pollRef.current); };
  }, [ticker]);

  return dossierStatus;
}
