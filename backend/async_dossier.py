"""
Async dossier generator — non-blocking file generation after fast analysis.

Pattern:
    1. analyze_ticker_fast() → returns score + decision in <5s (no heavy file I/O)
    2. generate_dossier_background() → spawns thread to write PDF, Excel, 10-K, etc.
    3. GET /api/dossier/{ticker}/status → {ready: bool, files: [...]}

On Render free tier, the background thread may be killed if the server sleeps,
but files are persisted on disk. If killed, the dossier regenerates on next poll.
"""

import os
import json
import threading
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# In-memory registry: ticker → dossier status
# Survives between requests, lost on server restart (acceptable — files on disk)
_dossier_registry: Dict[str, dict] = {}
_registry_lock = threading.Lock()

# Paris timezone
PARIS = __import__("zoneinfo").ZoneInfo("Europe/Paris")


def _analyses_dir() -> Path:
    """Return the project analyses directory from either repo root or backend cwd."""
    cwd = Path.cwd()
    if cwd.name == "backend":
        return cwd.parent / "analyses"
    return cwd / "analyses"


def _blocked_status(stage: str, issues: list[str] | None = None) -> dict:
    verification_issues = issues or []
    return {
        "ready": False,
        "files": [],
        "stage": stage,
        "verified": False,
        "download_enabled": False,
        "verification_issues": verification_issues,
    }


def _apply_verification_status(status: dict) -> dict:
    verification_issues: list[str] = []

    if not status.get("ready"):
        verification_issues.append("Required dossier deliverables are not complete.")

    deep_dive_validated = status.get("deep_dive_validated")
    if deep_dive_validated is not True:
        if deep_dive_validated is None:
            verification_issues.append("Deep-dive validation has not run yet.")
        else:
            issues = status.get("deep_dive_issues") or []
            if issues:
                verification_issues.extend(str(issue) for issue in issues)
            else:
                verification_issues.append("Deep-dive validation failed.")

    verified = bool(status.get("ready")) and deep_dive_validated is True and not verification_issues
    status["verified"] = verified
    status["download_enabled"] = verified
    status["verification_issues"] = verification_issues
    return status


def get_dossier_status(ticker: str) -> dict:
    """Check if dossier is ready for a ticker. Returns {ready, files, error}."""
    ticker_clean = ticker.replace(".", "_").upper()
    
    # Check in-memory registry first — but only if complete or failed
    # NEVER return "generating" from cache — the thread might have crashed
    # and files may already exist on disk (written by analyze_ticker_fast)
    with _registry_lock:
        if ticker_clean in _dossier_registry:
            cached = _dossier_registry[ticker_clean]
            if cached.get("stage") == "failed":
                return cached
            # If "generating" or "complete", fall through to disk check so
            # validation state always reflects the latest generated files.
    
    # Check on disk
    analyses_dir = _analyses_dir()
    if not analyses_dir.exists():
        return _blocked_status("not_started")
    
    matches = sorted(analyses_dir.glob(f"*_{ticker_clean}_*"), reverse=True)
    # Skip dummy UPLOADED directories
    matches = [m for m in matches if "UPLOADED" not in str(m)]
    if not matches:
        return _blocked_status("not_started")
    
    # Prefer directories that have actual analysis content (report.md/report.pdf)
    # over dummy UPLOADED directories created by the upload endpoint
    best_match = None
    for m in matches:
        has_report = (m / "07_final_report" / "report.md").exists() or \
                     (m / "07_final_report" / "report.pdf").exists()
        if has_report:
            best_match = m
            break
    if not best_match:
        best_match = matches[0]  # fallback
    
    dossier_dir = best_match
    files = _list_dossier_files(dossier_dir)
    
    # Dossier is "ready" ONLY if we have the 4 key deliverables
    # Check by exact filename suffix (file-extension-agnostic for the directory)
    file_strs = [str(f).replace("\\", "/") for f in files]
    
    has_report = any(
        "07_final_report/report" in s
        or "en/07_final_report/report" in s
        for s in file_strs
    )
    has_excel = any(
        ("financials_" in s and s.endswith(".xlsx"))
        and ("/03_financial_data_sources/" in f"/{s}" or s.startswith("03_financial_data_sources/"))
        for s in file_strs
    )
    
    # Ready if we have report (md or pdf) + Excel — MD→PDF conversion happens on download
    ready = has_report and has_excel
    
    relative_files = [str(f.relative_to(dossier_dir)) for f in files]
    bonus_files = [
        path for path in relative_files
        if (
            path.endswith("07_final_report/earnings_deep_dive.md")
            or path.endswith("07_final_report/earnings_deep_dive.pdf")
        )
    ]

    status = {
        "ready": ready,
        "files": relative_files,
        "bonus_files": bonus_files,
        "directory": str(dossier_dir),
        "stage": "complete" if ready else "in_progress",
        "estimated_seconds": 0,
    }
    
    # Check deep-dive validation
    dd_val_path = dossier_dir / "07_final_report" / "deep_dive_validation.json"
    if dd_val_path.exists():
        try:
            with open(dd_val_path) as f:
                dd_val = json.load(f)
            status["deep_dive_validated"] = dd_val.get("passed", False)
            if not dd_val.get("passed"):
                status["deep_dive_issues"] = dd_val.get("issues", [])
        except Exception:
            status["deep_dive_validated"] = False
    else:
        status["deep_dive_validated"] = None  # Not yet generated

    _apply_verification_status(status)
    
    with _registry_lock:
        _dossier_registry[ticker_clean] = status
    
    return status


def generate_dossier_background(ticker: str, company_name: str, yf_data: dict, result, output_dir: str):
    """
    Generate all heavy dossier files in a background thread.
    
    This is called after the fast analysis returns to the user.
    Does NOT block the API response.
    """
    ticker_clean = ticker.replace(".", "_").upper()
    
    with _registry_lock:
        _dossier_registry[ticker_clean] = {
            "ready": False, "files": [], "stage": "generating",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "estimated_seconds": 120,  # ~2 min for bilingual deep-dive
        }
    
    def _worker():
        try:
            logger.info(f"[{ticker}] Background dossier generation started")
            
            # 0. Create all 7 directories with README placeholders
            dossier_descriptions = {
                '01_official_company_sources': 'Company profile, investor presentations, official filings.',
                '02_sec_or_regulatory_filings': '10-K annual report, 10-Q quarterly, 8-K current events.',
                '03_financial_data_sources': 'Excel financial model, Yahoo Finance snapshot, Finnhub data.',
                '04_transcripts_and_management': 'Earnings call transcripts, management interviews, news.',
                '05_market_and_context': 'Sector data, peer comparison, macro indicators, competition.',
                '06_extracted_data': 'Traceability matrix, extracted financials, claim verification.',
                '07_final_report': 'Final analysis report (PDF + Markdown), executive summary.',
            }
            for folder, description in dossier_descriptions.items():
                folder_path = os.path.join(output_dir, folder)
                os.makedirs(folder_path, exist_ok=True)
                placeholder = os.path.join(folder_path, 'README.txt')
                if not os.path.exists(placeholder):
                    with open(placeholder, 'w') as f:
                        f.write(f'{folder}\n{"=" * len(folder)}\n\n{description}\n')
            
            # 1. Excel financials
            try:
                from backend.excel_generator import generate_excel
                excel_path = os.path.join(output_dir, "03_financial_data_sources", f"financials_{ticker}.xlsx")
                risks_data = [r.model_dump() if hasattr(r, 'model_dump') else r for r in result.risks]
                generate_excel(excel_path, ticker, company_name, yf_data, risks_data)
                logger.info(f"[{ticker}] Excel generated")
            except Exception as e:
                logger.warning(f"[{ticker}] Excel generation failed: {e}")
            
            # 2. 10-K PDF (if 10-K was downloaded)
            try:
                from backend.sources_collector import extract_10k_sections
                from backend.tenk_pdf import convert_10k_to_pdf
                sec_10k = extract_10k_sections(ticker, output_dir=output_dir)
                tenk_local = sec_10k.get("local_path", "")
                if tenk_local and os.path.exists(tenk_local):
                    convert_10k_to_pdf(tenk_local, output_dir, ticker)
                    logger.info(f"[{ticker}] 10-K PDF generated")
            except Exception as e:
                logger.warning(f"[{ticker}] 10-K PDF generation failed: {e}")
            
            # 3. 8-K download
            try:
                from backend.sec_8k import download_latest_8k
                download_latest_8k(ticker, output_dir)
                logger.info(f"[{ticker}] 8-K downloaded")
            except Exception as e:
                logger.warning(f"[{ticker}] 8-K download failed: {e}")
            
            # 4. Market context (Finnhub peers)
            try:
                _generate_market_context_bg(output_dir, ticker, yf_data)
                logger.info(f"[{ticker}] Market context generated")
            except Exception as e:
                logger.warning(f"[{ticker}] Market context failed: {e}")
            
            # 5. Final report markdown
            try:
                _write_final_report(output_dir, result, yf_data, ticker, company_name)
                logger.info(f"[{ticker}] Final report written")
                # Convert report.md → report.pdf
                try:
                    from backend.pdf_generator import md_to_pdf
                    report_md = os.path.join(output_dir, "07_final_report", "report.md")
                    report_pdf = os.path.join(output_dir, "07_final_report", "report.pdf")
                    if os.path.exists(report_md):
                        md_to_pdf(report_md, report_pdf, title=f"{company_name} ({ticker}) — Analysis Report")
                        logger.info(f"[{ticker}] Report PDF generated")
                except Exception as e:
                    logger.warning(f"[{ticker}] Report PDF conversion failed: {e}")
            except Exception as e:
                logger.warning(f"[{ticker}] Final report failed: {e}")
            
            # 6. Company profile MD → PDF
            try:
                from backend.company_profile import generate_company_profile
                from backend.pdf_generator import md_to_pdf
                profile_path = generate_company_profile(output_dir, ticker, yf_data)
                if profile_path and os.path.exists(profile_path):
                    profile_pdf = os.path.join(os.path.dirname(profile_path), f"company_profile_{ticker}.pdf")
                    md_to_pdf(profile_path, profile_pdf, title=f"{company_name} ({ticker}) — Company Profile")
                    logger.info(f"[{ticker}] Company profile PDF generated")
            except Exception as e:
                logger.warning(f"[{ticker}] Company profile failed: {e}")
            
            # 7. Convert MD/TXT files in 04/05 to PDF 
            try:
                from backend.pdf_generator import md_to_pdf
                for section in ["04_transcripts_and_management", "05_market_and_context"]:
                    section_dir = os.path.join(output_dir, section)
                    if os.path.isdir(section_dir):
                        for fname in os.listdir(section_dir):
                            fpath = os.path.join(section_dir, fname)
                            if fname.endswith('.md') and not os.path.exists(fpath.replace('.md', '.pdf')):
                                pdf_path = fpath.replace('.md', '.pdf')
                                md_to_pdf(fpath, pdf_path, title=f"{ticker} — {fname.replace('.md','').replace('_',' ').title()}")
                            elif fname.endswith('.txt') and fname != 'README.txt' and not os.path.exists(fpath.replace('.txt', '.pdf')):
                                pdf_path = fpath.replace('.txt', '.pdf')
                                md_to_pdf(fpath, pdf_path, title=f"{ticker} — {fname.replace('.txt','').replace('_',' ').title()}")
                logger.info(f"[{ticker}] Section PDFs generated")
            except Exception as e:
                logger.warning(f"[{ticker}] Section PDF conversion failed: {e}")
            
            # Update registry
            dossier_dir = Path(output_dir)
            files = _list_dossier_files(dossier_dir)
            final_status = {
                "ready": True,
                "files": [str(f.relative_to(dossier_dir)) for f in files],
                "directory": str(dossier_dir),
                "stage": "complete",
            }
            dd_val_path = dossier_dir / "07_final_report" / "deep_dive_validation.json"
            if dd_val_path.exists():
                try:
                    with open(dd_val_path) as f:
                        dd_val = json.load(f)
                    final_status["deep_dive_validated"] = dd_val.get("passed", False)
                    if not dd_val.get("passed"):
                        final_status["deep_dive_issues"] = dd_val.get("issues", [])
                except Exception:
                    final_status["deep_dive_validated"] = False
            else:
                final_status["deep_dive_validated"] = None
            _apply_verification_status(final_status)
            with _registry_lock:
                _dossier_registry[ticker_clean] = final_status
            
            logger.info(f"[{ticker}] Background dossier complete — {len(files)} files")
            
        except Exception as e:
            logger.error(f"[{ticker}] Background dossier crashed: {e}")
            with _registry_lock:
                _dossier_registry[ticker_clean] = {
                    "ready": False, "files": [], "stage": "failed", "error": str(e)
                }
    
    thread = threading.Thread(target=_worker, daemon=True, name=f"dossier-{ticker}")
    thread.start()
    logger.info(f"[{ticker}] Background dossier thread spawned")


def _list_dossier_files(dossier_dir: Path) -> list:
    """Recursively list all files in dossier directory."""
    files = []
    if dossier_dir.exists():
        for fpath in sorted(dossier_dir.rglob("*")):
            if fpath.is_file():
                files.append(fpath)
    return files


def _generate_market_context_bg(output_dir: str, ticker: str, data: dict):
    """Generate market context from Finnhub peers."""
    from backend.sources_collector import get_finnhub_data
    
    market_dir = os.path.join(output_dir, "05_market_and_context")
    os.makedirs(market_dir, exist_ok=True)
    
    peers_path = os.path.join(market_dir, f"peers_{ticker}.json")
    
    # Try Finnhub peers
    try:
        fh = get_finnhub_data(ticker)
        peers = fh.get("peers", [])
        if peers:
            with open(peers_path, "w") as f:
                json.dump({"ticker": ticker, "peers": peers, "source": "Finnhub"}, f, indent=2)
            
            # Write readable version
            readme_path = os.path.join(market_dir, "README.md")
            with open(readme_path, "w") as f:
                f.write(f"# Market Context — {ticker}\n\n")
                f.write(f"**Peers** (from Finnhub): {', '.join(peers[:10])}\n\n")
                f.write(f"**Sector**: {data.get('sector', 'N/A')}\n")
                f.write(f"**Industry**: {data.get('industry', 'N/A')}\n")
                f.write(f"**Market Cap**: {data.get('market_cap', 'N/A')}\n")
                f.write(f"**Currency**: {data.get('currency', 'USD')}\n")
    except Exception as e:
        logger.warning(f"Market context generation failed: {e}")


def _write_final_report(output_dir: str, result, yf_data: dict, ticker: str, company_name: str):
    """Delegate to _generate_report for the rich 9-section markdown format."""
    from backend.pipeline import _generate_report
    report_dir = os.path.join(output_dir, "07_final_report")
    os.makedirs(report_dir, exist_ok=True)
    
    report_md = _generate_report(result, yf_data, result.sources if hasattr(result, 'sources') else [])
    report_path = os.path.join(report_dir, "report.md")
    with open(report_path, "w") as f:
        f.write(report_md)
    
    logger.info(f"Final report written: {report_path}")


def _fmt_billions(val) -> str:
    if val is None:
        return "N/A"
    if abs(val) >= 1e12:
        return f"${val/1e12:.2f}T"
    return f"${val/1e9:.1f}B"


def _fmt_pct(val) -> str:
    if val is None:
        return "N/A"
    return f"{val*100:.1f}%"
