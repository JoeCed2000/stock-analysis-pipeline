"""Market context via Gemini Cockpit — saves deep research report into 05_market_and_context."""
import os
import requests
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

GEMINI_API = os.getenv("GEMINI_API_URL", "http://127.0.0.1:7863")


def submit_market_research(ticker: str, company_name: str) -> Optional[str]:
    """Submit a Gemini Deep Research job for market context. Returns job_id or None."""
    try:
        resp = requests.post(
            f"{GEMINI_API}/api/research-jobs",
            json={
                "title": f"{ticker} Market Context",
                "prompt": (
                    f"Analyze {company_name} ({ticker}) market context as of {datetime.now(timezone.utc).strftime('%B %Y')}. "
                    f"Cover: (1) sector dynamics and competitive position, (2) key peers comparison with numbers, "
                    f"(3) macro context (rates, FX, supply chain), (4) regulatory environment, "
                    f"(5) growth catalysts, (6) analyst consensus and price targets, (7) key risks. "
                    f"Output structured markdown with a peer comparison table."
                ),
                "agent": "deep-research-preview-04-2026",
                "tools": ["google_search", "url_context"],
            },
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            job_id = data.get("id")
            logger.info(f"Gemini research submitted for {ticker}: {job_id}")
            return job_id
    except Exception as e:
        logger.warning(f"Gemini research submission failed: {e}")
    return None


def fetch_market_report(job_id: str, output_dir: str, ticker: str, timeout_minutes: int = 12) -> Optional[str]:
    """Poll Gemini job until completion and save report. Returns file path or None."""
    import time
    deadline = time.time() + timeout_minutes * 60

    while time.time() < deadline:
        try:
            resp = requests.get(f"{GEMINI_API}/api/research-jobs/{job_id}", timeout=10)
            if resp.status_code != 200:
                return None
            data = resp.json()
            status = data.get("status")
            if status == "completed":
                report = data.get("final_report_markdown", "")
                if not report:
                    return None

                # Save to 05_market_and_context
                market_dir = os.path.join(output_dir, "05_market_and_context")
                os.makedirs(market_dir, exist_ok=True)
                date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
                path = os.path.join(market_dir, f"market_context_{ticker}_{date_str}.md")
                with open(path, "w") as f:
                    f.write(report)

                logger.info(f"Market context saved: {path} ({len(report)} chars)")
                return path

            elif status == "failed":
                logger.warning(f"Gemini job {job_id} failed: {data.get('error_message')}")
                return None

        except Exception as e:
            logger.warning(f"Gemini poll error: {e}")

        time.sleep(30)

    logger.warning(f"Gemini job {job_id} timed out after {timeout_minutes} min")
    return None
