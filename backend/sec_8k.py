"""SEC 8-K / earnings release downloader — supplements 10-K with quarterly filings."""
import os
import re
import requests
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def download_latest_8k(ticker: str, output_dir: str) -> Optional[str]:
    """Download the latest 8-K (earnings release) for a ticker as HTML.
    Returns local path or None."""
    from backend.sources_collector import _resolve_cik

    cik = _resolve_cik(ticker)
    if not cik:
        return None

    # Get filing list from SEC submissions API
    try:
        resp = requests.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            headers={"User-Agent": "StockAnalysisPipeline/1.0 (contact@example.com)"},
            timeout=10
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        filings = data.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        docs = filings.get("primaryDocument", [])
        accessions = filings.get("accessionNumber", [])
        dates = filings.get("filingDate", [])

        # Find first 8-K
        for i in range(min(50, len(forms))):
            if forms[i] in ("8-K", "10-Q"):
                doc = docs[i]
                acc = accessions[i].replace("-", "")
                filing_date = dates[i]
                cik_int = int(cik)
                url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc}/{doc}"

                # Download
                resp2 = requests.get(
                    url,
                    headers={"User-Agent": "StockAnalysisPipeline/1.0 (contact@example.com)"},
                    timeout=30
                )
                if resp2.status_code != 200:
                    continue

                # Save
                sec_dir = os.path.join(output_dir, "02_sec_or_regulatory_filings")
                os.makedirs(sec_dir, exist_ok=True)
                form_type = forms[i].replace("/", "_")
                fname = f"{form_type}_{ticker}_{filing_date}.htm"
                local_path = os.path.join(sec_dir, fname)

                with open(local_path, "w", encoding="utf-8") as f:
                    f.write(resp2.text)

                logger.info(f"{form_type} saved: {local_path} ({len(resp2.text)} bytes)")
                return local_path

    except Exception as e:
        logger.warning(f"8-K download failed for {ticker}: {e}")

    return None
