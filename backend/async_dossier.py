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
PARIS = timezone(offset=datetime.now(timezone.utc).astimezone().utcoffset() or __import__("datetime").timedelta(hours=2))


def get_dossier_status(ticker: str) -> dict:
    """Check if dossier is ready for a ticker. Returns {ready, files, error}."""
    ticker_clean = ticker.replace(".", "_").upper()
    
    # Check in-memory registry first — but only if complete or failed
    # NEVER return "generating" from cache — the thread might have crashed
    # and files may already exist on disk (written by analyze_ticker_fast)
    with _registry_lock:
        if ticker_clean in _dossier_registry:
            cached = _dossier_registry[ticker_clean]
            if cached.get("stage") in ("complete", "failed"):
                return cached
            # If "generating", fall through to disk check
    
    # Check on disk
    analyses_dir = Path("analyses")
    if not analyses_dir.exists():
        return {"ready": False, "files": [], "stage": "not_started"}
    
    matches = sorted(analyses_dir.glob(f"*_{ticker_clean}_*"), reverse=True)
    if not matches:
        return {"ready": False, "files": [], "stage": "not_started"}
    
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
    file_strs = [str(f) for f in files]
    
    has_report = any("07_final_report/report" in s for s in file_strs)
    has_excel = any("financials_" in s and s.endswith(".xlsx") for s in file_strs)
    
    # Ready if we have report (md or pdf) + Excel — MD→PDF conversion happens on download
    ready = has_report and has_excel
    
    status = {
        "ready": ready,
        "files": [str(f.relative_to(dossier_dir)) for f in files],
        "directory": str(dossier_dir),
        "stage": "complete" if ready else "in_progress",
    }
    
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
            "ready": False, "files": [], "stage": "generating"
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
            with _registry_lock:
                _dossier_registry[ticker_clean] = {
                    "ready": True,
                    "files": [str(f.relative_to(dossier_dir)) for f in files],
                    "directory": str(dossier_dir),
                    "stage": "complete",
                }
            
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
    """Write the final markdown report to 07_final_report/report.md."""
    report_dir = os.path.join(output_dir, "07_final_report")
    os.makedirs(report_dir, exist_ok=True)
    
    scoring = result.scoring
    valuation = result.valuation
    management = result.management_tone
    financials = result.financials
    
    lines = []
    lines.append(f"# {company_name} ({ticker}) — Analysis Report")
    lines.append(f"**Date**: {datetime.now(PARIS).strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Decision**: {result.decision} (conviction: {result.conviction})")
    lines.append(f"**Score**: {scoring.total}/40")
    lines.append("")
    
    # Financial highlights
    lines.append("## Financial Highlights")
    lines.append(f"- Revenue (quarterly): {_fmt_billions(financials.revenue_quarterly)}")
    lines.append(f"- Revenue YoY growth: {_fmt_pct(financials.revenue_yoy_growth)}")
    lines.append(f"- Gross margin: {_fmt_pct(financials.gross_margin)}")
    lines.append(f"- Operating margin: {_fmt_pct(financials.operating_margin)}")
    lines.append(f"- Net income: {_fmt_billions(financials.net_income)}")
    lines.append(f"- Free cash flow: {_fmt_billions(financials.free_cash_flow)}")
    if financials.net_debt:
        lines.append(f"- Net debt: {_fmt_billions(financials.net_debt)}")
    lines.append("")
    
    # Valuation
    lines.append("## Valuation")
    lines.append(f"- P/E (trailing): {valuation.pe_current:.1f}" if valuation.pe_current else "- P/E: N/A")
    lines.append(f"- P/E (forward): {valuation.pe_forward:.1f}" if valuation.pe_forward else "")
    lines.append(f"- PEG ratio: {valuation.peg_ratio:.2f}" if valuation.peg_ratio else "")
    lines.append(f"- Margin of safety: {valuation.margin_of_safety}")
    lines.append("")
    
    # Management tone
    lines.append("## Management Discourse")
    lines.append(f"- Tone: {management.tone}")
    lines.append(f"- Confidence: {management.confidence}")
    lines.append(f"- Visibility: {management.visibility}")
    if management.concrete_promises:
        lines.append("- Concrete promises:")
        for p in management.concrete_promises:
            lines.append(f"  - {p}")
    if management.defensive_signals:
        lines.append("- Defensive signals:")
        for s in management.defensive_signals:
            lines.append(f"  - {s}")
    lines.append("")
    
    # Risks
    lines.append("## Risks")
    for risk in result.risks:
        r = risk if isinstance(risk, dict) else risk.model_dump()
        lines.append(f"- [{r.get('severity', 'N/A').upper()}] {r.get('category', '')}: {r.get('description', '')}")
    lines.append("")
    
    # Scoring breakdown
    lines.append("## Scoring Breakdown")
    scoring_dict = scoring.model_dump()
    for key, value in scoring_dict.items():
        if key != "total" and isinstance(value, (int, float)):
            lines.append(f"- {key}: {value}/5")
    lines.append(f"- **Total**: {scoring.total}/40")
    lines.append("")
    
    # AI insight
    lines.append("## AI Insight")
    try:
        from backend.kimi_provider import kimi_ai_insight
        insight = kimi_ai_insight(ticker, company_name, scoring.total, result.decision)
        lines.append(f"> {insight}")
    except Exception:
        lines.append(f"> {result.decision} — score {scoring.total}/40")
    lines.append("")
    
    lines.append("---")
    lines.append(f"*Report generated by Stock Analysis Pipeline — {datetime.now(PARIS).isoformat()}*")
    
    report_path = os.path.join(report_dir, "report.md")
    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    
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
