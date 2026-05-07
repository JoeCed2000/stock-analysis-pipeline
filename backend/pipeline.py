"""Main pipeline — executes the 9-step analysis for a single ticker."""
import os
import json
import hashlib
import logging
import re
import shutil
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from backend.models import (
    AnalysisResult, FinancialData, SegmentInfo, ManagementTone,
    RiskItem, ValuationData, Scoring, Source, Claim
)
from backend.sources_collector import get_stock_data, get_finnhub_data, get_sec_filings, convert_to_eur
from backend.scorer import score_ticker
from backend.excel_generator import generate_excel
from backend.tenk_pdf import convert_10k_to_pdf
from backend.company_profile import generate_company_profile
from backend.sec_8k import download_latest_8k
from backend.earnings_deep_dive.schemas import DeepDiveRequest, FinancialMetrics
from backend.transcript_finder import find_transcripts

logger = logging.getLogger(__name__)

# Paris timezone
PARIS = __import__("zoneinfo").ZoneInfo("Europe/Paris")


def md_to_pdf(md_path: str, pdf_path: str, title: str = "") -> str:
    """Lazy wrapper so importing the pipeline does not require PDF dependencies."""
    from backend.pdf_generator import md_to_pdf as _md_to_pdf

    return _md_to_pdf(md_path, pdf_path, title=title)


def _best_transcript_source(sources: List[Dict[str, Any]]) -> tuple[str, Dict[str, Any]]:
    """Return the longest usable transcript text and its source metadata."""
    best_text = ""
    best_source: Dict[str, Any] = {}
    for source in sources:
        text = source.get("text") or source.get("content") or source.get("transcript") or ""
        if isinstance(text, list):
            text = "\n".join(str(item) for item in text)
        if isinstance(text, str) and len(text.strip()) > len(best_text):
            best_text = text.strip()
            best_source = source
    return best_text, best_source


def _transcript_url(source: Dict[str, Any]) -> Optional[str]:
    """Return the source URL for transcript citation, when provided by a finder."""
    for key in ("url", "link", "source_url"):
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _parse_date(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            pass
    match = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text)
    if match:
        year, month, day = (int(part) for part in match.groups())
        try:
            return datetime(year, month, day)
        except ValueError:
            return None
    return None


def _is_forward_quarter(label: str, today: Optional[datetime] = None) -> bool:
    """Return True when a quarter label points beyond the current calendar quarter."""
    if not label:
        return False
    match = re.search(r"(?:FY)?(20\d{2})\s*Q([1-4])", label, re.IGNORECASE)
    if not match:
        match = re.search(r"(20\d{2})\s*Q([1-4])", label, re.IGNORECASE)
    if not match:
        return False
    year = int(match.group(1))
    quarter = int(match.group(2))
    today = today or datetime.now(PARIS)
    current_quarter = (today.month - 1) // 3 + 1
    return (year, quarter) > (today.year, current_quarter)


def _period_from_filing(filing: Dict[str, Any]) -> Optional[str]:
    filing_date = _parse_date(filing.get("date"))
    form = str(filing.get("form") or "").upper()
    if not filing_date:
        return None
    if form == "10-K":
        fiscal_year = filing_date.year - 1 if filing_date.month <= 6 else filing_date.year
        return f"FY{fiscal_year} Annual"
    if form == "10-Q":
        quarter = max(1, ((filing_date.month - 1) // 3))
        return f"FY{filing_date.year} Q{quarter}"
    return None


def _latest_filing_period(ticker: str) -> Optional[str]:
    try:
        filings = get_sec_filings(ticker).get("filings", [])
    except Exception:
        return None
    for filing in filings:
        period = _period_from_filing(filing)
        if period:
            return period
    return None


def _resolve_deep_dive_quarter(
    *,
    ticker: str,
    transcript_source: Dict[str, Any],
    yf_data: Dict[str, Any],
) -> str:
    """Prefer reported periods and never use a future-looking transcript label."""
    transcript_quarter = str(transcript_source.get("quarter") or "").strip()
    if transcript_quarter and transcript_quarter.lower() != "latest quarter":
        if not _is_forward_quarter(transcript_quarter):
            return transcript_quarter

    filing_period = _latest_filing_period(ticker)
    if filing_period:
        return filing_period

    data_quarter = str(yf_data.get("quarter") or "").strip()
    if data_quarter and not _is_forward_quarter(data_quarter):
        return data_quarter

    transcript_date = _parse_date(transcript_source.get("date"))
    if transcript_date:
        quarter = (transcript_date.month - 1) // 3 + 1
        label = f"FY{transcript_date.year} Q{quarter}"
        if not _is_forward_quarter(label):
            return label

    return "latest reported period"


def _company_website(yf_data: Dict[str, Any], fh_data: Optional[Dict[str, Any]] = None) -> Optional[str]:
    candidates = [
        yf_data.get("website"),
        yf_data.get("weburl"),
        yf_data.get("official_website"),
    ]
    if isinstance(fh_data, dict):
        profile = fh_data.get("profile")
        if isinstance(profile, dict):
            candidates.extend([profile.get("weburl"), profile.get("website")])
    for value in candidates:
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    return None


def _investor_relations_url(yf_data: Dict[str, Any], fh_data: Optional[Dict[str, Any]] = None) -> Optional[str]:
    candidates = [
        yf_data.get("investor_relations_url"),
        yf_data.get("investors_url"),
        yf_data.get("ir_url"),
    ]
    if isinstance(fh_data, dict):
        profile = fh_data.get("profile")
        if isinstance(profile, dict):
            candidates.extend([
                profile.get("investor_relations_url"),
                profile.get("investors_url"),
                profile.get("ir_url"),
            ])
    for value in candidates:
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    return None


def _copy_non_report_sections_to_language_dirs(output_dir: str) -> None:
    for language in ("en", "jp"):
        language_dir = os.path.join(output_dir, language)
        os.makedirs(language_dir, exist_ok=True)
        for section in (
            "01_official_company_sources",
            "02_sec_or_regulatory_filings",
            "03_financial_data_sources",
            "04_transcripts_and_management",
            "05_market_and_context",
            "06_extracted_data",
        ):
            src = os.path.join(output_dir, section)
            dst = os.path.join(language_dir, section)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)


def _move_final_report_to_language_dir(output_dir: str, language: str) -> str:
    report_dir = os.path.join(output_dir, "07_final_report")
    language_report_dir = os.path.join(output_dir, language, "07_final_report")
    os.makedirs(language_report_dir, exist_ok=True)
    if os.path.isdir(report_dir):
        for name in os.listdir(report_dir):
            src = os.path.join(report_dir, name)
            dst = os.path.join(language_report_dir, name)
            if os.path.isfile(dst) or os.path.islink(dst):
                os.remove(dst)
            elif os.path.isdir(dst):
                shutil.rmtree(dst)
            shutil.move(src, dst)
    return language_report_dir


def _normalize_report_language(language: str) -> str:
    return "jp" if language in ("jp", "ja") else "en"


def _deep_dive_metrics(result: AnalysisResult, yf_data: Dict[str, Any]) -> FinancialMetrics:
    """Map existing dossier metrics into the earnings deep-dive schema."""
    fin_data = yf_data.get("financials", {}) if isinstance(yf_data, dict) else {}
    financials = getattr(result, "financials", None)
    valuation = getattr(result, "valuation", None)

    def pick(name: str, fallback: Any = None) -> Any:
        if isinstance(fin_data, dict) and fin_data.get(name) is not None:
            return fin_data.get(name)
        if financials is not None and hasattr(financials, name):
            value = getattr(financials, name)
            if value is not None:
                return value
        return fallback

    guidance_value = pick("guidance")
    if guidance_value is None:
        guidance_value = pick("guidance_official")
    ticker_for_segments = (
        getattr(result, "ticker", None)
        or (yf_data.get("ticker") if isinstance(yf_data, dict) else None)
        or ""
    )

    return FinancialMetrics(
        eps_estimate=pick("eps_estimate"),
        eps_actual=pick("eps_actual"),
        eps_vs_estimate=pick("eps_vs_estimate"),
        eps_yoy=pick("eps_yoy"),
        revenue_estimate=pick("revenue_estimate"),
        revenue_actual=pick("revenue_quarterly"),
        revenue_yoy=pick("revenue_yoy_growth"),
        gross_margin=pick("gross_margin"),
        operating_margin=pick("operating_margin"),
        operating_income=pick("operating_income"),
        net_income=pick("net_income"),
        free_cash_flow=pick("free_cash_flow"),
        operating_cash_flow=pick("operating_cash_flow"),
        capex=pick("capex"),
        net_debt=pick("net_debt"),
        roic=pick("roic"),
        roe=pick("roe"),
        # v2.5 — new yfinance-extracted fields
        gross_profit=pick("gross_profit"),
        opex=pick("opex"),
        rotce=pick("rotce"),
        roa=pick("roa"),
        total_assets=pick("total_assets"),
        equity=pick("equity"),
        buybacks=pick("buybacks"),
        dividends=pick("dividends"),
        pe_forward=(
            (getattr(valuation, "pe_forward", None) if valuation else None)
            or (yf_data.get("pe_forward") if isinstance(yf_data, dict) else None)
        ),
        guidance=str(guidance_value) if guidance_value is not None else None,
        segments=_extract_segments(ticker_for_segments, guidance_value) if ticker_for_segments else {},
    )


def _segment_metrics_shape(segment_data: Dict[str, Any]) -> Dict[str, Any]:
    """Keep segment rows first for the PDF mapper while preserving raw product_segments."""
    if not isinstance(segment_data, dict):
        return {}

    shaped: Dict[str, Any] = {}
    product_segments = segment_data.get("product_segments")
    if isinstance(product_segments, list):
        for segment in product_segments:
            if not isinstance(segment, dict):
                continue
            name = str(segment.get("name") or "").strip()
            if not name:
                continue
            revenue = segment.get("revenue_quarterly")
            shaped[name] = {
                "revenue": revenue,
                "revenue_quarterly": revenue,
                "revenue_q_prior_year": segment.get("revenue_q_prior_year"),
                "source": segment.get("source") or segment_data.get("source") or "SEC XBRL",
            }

    for key in ("product_segments", "total_revenue_quarterly", "total_revenue_6m", "deferred_revenue_total", "deferred_revenue_1yr_pct", "source", "filing_date"):
        if key in segment_data:
            shaped[key] = segment_data[key]
    return shaped


def _extract_segments(ticker: str, guidance: Optional[str] = None) -> Dict[str, Any]:
    """Extract segment revenue data from SEC EDGAR XBRL via edgartools."""
    try:
        from backend.edgar_extractor import extract_segment_revenue
        return _segment_metrics_shape(extract_segment_revenue(ticker))
    except Exception:
        return {}


def _merge_press_release_segments(
    existing_segments: Dict[str, Any],
    press_release_data: Dict[str, Any],
) -> Dict[str, Any]:
    merged = dict(existing_segments) if isinstance(existing_segments, dict) else {}
    press_segments = press_release_data.get("product_segments") if isinstance(press_release_data, dict) else None
    if not isinstance(press_segments, list) or not press_segments:
        return merged

    raw_segments = []
    existing_raw = merged.get("product_segments")
    if isinstance(existing_raw, list):
        raw_segments.extend(item for item in existing_raw if isinstance(item, dict))

    seen = {str(item.get("name") or "").strip().lower() for item in raw_segments if item.get("name")}
    for press_segment in press_segments:
        if not isinstance(press_segment, dict):
            continue
        name = str(press_segment.get("name") or "").strip()
        if not name:
            continue
        revenue = press_segment.get("revenue_quarterly")
        row = merged.get(name)
        if isinstance(row, dict):
            if row.get("revenue") is None and revenue is not None:
                row["revenue"] = revenue
                row["revenue_quarterly"] = revenue
            row["source"] = "SEC XBRL + Press release" if row.get("source") else "Press release"
        else:
            row = {"name": name, "revenue_quarterly": revenue, "source": "Press release"}
        if name.lower() not in seen:
            raw_segments.append(row if isinstance(row, dict) and row.get("name") else press_segment)
            seen.add(name.lower())

    raw_segment_data: Dict[str, Any] = {
        "product_segments": raw_segments,
        "source": merged.get("source") or "SEC XBRL + Press release",
    }
    if merged.get("total_revenue_quarterly") or press_release_data.get("revenue"):
        raw_segment_data["total_revenue_quarterly"] = merged.get("total_revenue_quarterly") or press_release_data.get("revenue")
    for key in ("total_revenue_6m", "deferred_revenue_total", "deferred_revenue_1yr_pct", "filing_date"):
        if key in merged:
            raw_segment_data[key] = merged[key]
    return _segment_metrics_shape(raw_segment_data)


def _format_guidance_from_press_release(press_release_data: Dict[str, Any]) -> Optional[str]:
    guidance = press_release_data.get("guidance") if isinstance(press_release_data, dict) else None
    if not isinstance(guidance, dict) or not guidance:
        return None
    if guidance.get("text"):
        return str(guidance["text"])
    parts = []
    if guidance.get("revenue") is not None:
        parts.append(f"Revenue guidance: {guidance['revenue']}")
    if guidance.get("gross_margin_pct") is not None:
        parts.append(f"Gross margin guidance: {guidance['gross_margin_pct']}%")
    return "; ".join(parts) if parts else None


def _apply_press_release_metrics(
    metrics: FinancialMetrics,
    press_release_data: Dict[str, Any],
) -> FinancialMetrics:
    if not isinstance(press_release_data, dict) or press_release_data.get("error"):
        return metrics
    updates: Dict[str, Any] = {}
    url = press_release_data.get("url")
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        updates["press_release_url"] = url
    merged_segments = _merge_press_release_segments(metrics.segments, press_release_data)
    if merged_segments:
        updates["segments"] = merged_segments
    if not metrics.guidance:
        press_guidance = _format_guidance_from_press_release(press_release_data)
        if press_guidance:
            updates["guidance"] = press_guidance
    return metrics.model_copy(update=updates) if updates else metrics


def _strip_prompt_leak_text(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text
    cleaned = re.sub(
        r"(?im)^\s*please\s+(?:summarize|explain|state)\b[^\n]*(?:\n|$)",
        "",
        text,
    )
    cleaned = re.sub(r"(?i)\bplease\s+(?:summarize|explain|state)\b[:\s,.-]*", "", cleaned)
    return cleaned.strip()


def _strip_prompt_leaks_from_sections(sections: Dict[str, str]) -> Dict[str, str]:
    return {key: _strip_prompt_leak_text(value) for key, value in sections.items()}


def _add_earnings_deep_dive_if_transcript(
    *,
    ticker: str,
    company_name: str,
    output_dir: str,
    result: AnalysisResult,
    yf_data: Dict[str, Any],
    language: str = "en",
    company_website: Optional[str] = None,
) -> bool:
    """Generate the optional earnings deep-dive with transcript text when available."""
    try:
        report_language = _normalize_report_language(language)
        try:
            transcript_results = find_transcripts(ticker, output_dir=output_dir, company=company_name)
        except TypeError as exc:
            if "company" not in str(exc):
                raise
            transcript_results = find_transcripts(ticker, output_dir=output_dir)
        sources = transcript_results.get("sources", []) if isinstance(transcript_results, dict) else []
        transcript_text, transcript_source = _best_transcript_source(sources)
        transcript_url = _transcript_url(transcript_source)
        transcript_source_name = str(
            transcript_source.get("source")
            or transcript_source.get("title")
            or "Transcript"
        ).strip()
        if not transcript_text:
            logger.info(f"[{ticker}] Earnings deep-dive proceeding without usable transcript")

        try:
            from backend.press_release_fetcher import fetch_press_release_for_ticker
            press_release_data = fetch_press_release_for_ticker(ticker, output_dir=output_dir)
        except Exception as exc:
            logger.warning(f"[{ticker}] Press release fetch failed: {exc}")
            press_release_data = {}

        transcript_quarter = _resolve_deep_dive_quarter(
            ticker=ticker,
            transcript_source=transcript_source,
            yf_data=yf_data,
        )

        # If transcript is for a specific quarter, use quarter-specific yfinance data
        deep_dive_metrics = _deep_dive_metrics(result, yf_data)
        deep_dive_metrics = _apply_press_release_metrics(deep_dive_metrics, press_release_data)
        website = company_website or _company_website(yf_data)
        investor_relations = _investor_relations_url(yf_data)
        if website:
            deep_dive_metrics = deep_dive_metrics.model_copy(update={"company_website": website})
        if investor_relations:
            deep_dive_metrics = deep_dive_metrics.model_copy(update={"investor_relations_url": investor_relations})
        if transcript_source_name:
            deep_dive_metrics = deep_dive_metrics.model_copy(update={"transcript_source": transcript_source_name})
        if re.search(r"(?:FY)?20\d{2}\s*Q[1-4]|20\d{2}Q[1-4]", transcript_quarter, re.IGNORECASE):
            from backend.sources_collector import get_yahoo_data_for_quarter
            q_yf = get_yahoo_data_for_quarter(ticker, transcript_quarter)
            if q_yf:
                deep_dive_metrics = _deep_dive_metrics(result, q_yf)
                deep_dive_metrics = _apply_press_release_metrics(deep_dive_metrics, press_release_data)
                if website:
                    deep_dive_metrics = deep_dive_metrics.model_copy(update={"company_website": website})
                if investor_relations:
                    deep_dive_metrics = deep_dive_metrics.model_copy(update={"investor_relations_url": investor_relations})
                if transcript_source_name:
                    deep_dive_metrics = deep_dive_metrics.model_copy(update={"transcript_source": transcript_source_name})

        from backend.earnings_deep_dive.generator import generate_deep_dive
        from backend.earnings_deep_dive.mapper import build_earnings_deep_dive_report
        from backend.earnings_deep_dive.pdf_renderer import render_earnings_deep_dive_pdf

        response = generate_deep_dive(
            DeepDiveRequest(
                ticker=ticker,
                company=company_name,
                quarter=transcript_quarter,
                language=report_language,
                output_dir=output_dir,
                metrics=deep_dive_metrics,
                transcript_text=transcript_text,
                transcript_url=transcript_url,
            )
        )
        response.sections = _strip_prompt_leaks_from_sections(response.sections)

        pdf_path = os.path.join(output_dir, "07_final_report", "earnings_deep_dive.pdf")
        report_model = build_earnings_deep_dive_report(
            ticker=ticker,
            company=company_name,
            quarter=transcript_quarter,
            language=report_language,
            metrics=deep_dive_metrics,
            transcript_url=transcript_url,
            section_analysis=response.sections,
        )
        if website:
            from backend.earnings_deep_dive.report_model import SourceRef
            report_model.sources.append(SourceRef(label="Official Website", url=website))
        render_earnings_deep_dive_pdf(report_model, pdf_path)

        logger.info(f"[{ticker}] Earnings deep-dive added to dossier")
        
        # ── Post-generation validation ──
        from backend.earnings_deep_dive.deep_dive_validator import validate_deep_dive, validate_render_model
        
        en_md = response.markdown_path
        md_passed, issues = validate_deep_dive(en_md)
        render_issues = validate_render_model(report_model)
        issues = issues + render_issues
        passed = md_passed and not render_issues
        validation_result = {"passed": passed, "issues": issues, "checked_at": datetime.now(timezone.utc).isoformat()}
        
        # Write validation result next to the markdown
        val_path = os.path.join(os.path.dirname(en_md), "deep_dive_validation.json")
        with open(val_path, "w") as f:
            json.dump(validation_result, f, indent=2)
        
        if not passed:
            logger.warning(f"[{ticker}] Deep-dive validation FAILED ({len(issues)} issues)")
            for issue in issues[:5]:
                logger.warning(f"  - {issue}")
        else:
            logger.info(f"[{ticker}] Deep-dive validation PASSED")
        
        return True
    except Exception as e:
        logger.warning(f"[{ticker}] Earnings deep-dive skipped: {e}")
        return False


def analyze_ticker(ticker: str, output_base: str = "analyses") -> AnalysisResult:
    """
    Execute the full pipeline for a single ticker.
    Delegates to analyze_ticker_fast (the unified implementation).
    
    Kept for backward compatibility — _run_backlog.py and run_daily_backlog.py
    use this function name. Both paths now produce identical output.
    """
    return analyze_ticker_fast(ticker, output_base)
def _assess_risks(yf_data: Dict, fh_data: Dict, ticker: str) -> List[RiskItem]:
    """Identify risks from available data."""
    risks = []

    # Sector-specific risks
    sector = str(yf_data.get("sector", "")).lower()
    industry = str(yf_data.get("industry", "")).lower()

    if "technology" in sector or "semiconductor" in industry:
        risks.append(RiskItem(category="Sector", description="Tech/semiconductor cyclicality risk", severity="medium", source="Yahoo Finance sector classification"))
    if "china" in yf_data.get("description", "").lower() or "china" in industry:
        risks.append(RiskItem(category="Geopolitical", description="China exposure / trade tensions", severity="high", source="Company description analysis"))

    # Concentration risk
    if yf_data.get("market_cap") and yf_data.get("market_cap", 0) > 5e11:
        risks.append(RiskItem(category="Size", description="Mega-cap → growth harder to sustain", severity="low", source="Market cap analysis"))

    # Debt risk
    fin = yf_data.get("financials", {})
    if fin.get("net_debt") is not None and fin.get("net_debt", 0) > 1e10:
        risks.append(RiskItem(category="Financial", description=f"Significant net debt ({fin['net_debt']/1e9:.1f}B)", severity="medium", source="Yahoo Finance balance sheet"))

    # Valuation risk
    pe = yf_data.get("pe_current")
    if pe is not None and pe > 50:
        risks.append(RiskItem(category="Valuation", description=f"High PE ({pe:.1f}) → growth premium", severity="high", source="Yahoo Finance valuation"))

    # No risks found
    if not risks:
        risks.append(RiskItem(category="General", description="No major risks identified from available data", severity="low", source="Analysis"))

    return risks


def _margin_of_safety_text(pe: Any, fpe: Any) -> str:
    pe_val = fpe if fpe else pe
    if pe_val is None:
        return "DATA NOT AVAILABLE"
    if pe_val < 15:
        return "Comfortable margin of safety (PE < 15)"
    if pe_val < 25:
        return "Moderate margin of safety (PE 15-25)"
    if pe_val < 40:
        return "Weak margin of safety (PE 25-40)"
    return "No margin of safety (PE > 40)"


def _conviction_text(s: Scoring) -> str:
    t = s.total
    if t >= 35:
        return "Strong"
    if t >= 28:
        return "Moderate"
    if t >= 20:
        return "Weak"
    return "Very weak"


def _key_phrase(decision: str, name: str, total: int) -> str:
    if "BUY" in decision and "PULLBACK" not in decision:
        return f"{name} has a strong fundamental profile (score {total}/40) — buy."
    if "PULLBACK" in decision:
        return f"{name} is good quality (score {total}/40) but timing is suboptimal — wait for pullback."
    if "HOLD fragile" in decision:
        return f"{name} shows mixed signals (score {total}/40) — hold, do not add."
    return f"{name} carries too much risk (score {total}/40) — avoid or sell."


def _save_news_as_transcript(ticker: str, output_dir: str, fh_data: Dict) -> None:
    """Save Finnhub news articles as readable text in transcripts folder."""
    news = fh_data.get("news", [])
    if not news:
        return

    trans_dir = os.path.join(output_dir, "04_transcripts_and_management")
    os.makedirs(trans_dir, exist_ok=True)

    date_str = datetime.now(PARIS).strftime("%Y%m%d")
    filename = f"earnings_news_{ticker}_{date_str}.txt"
    path = os.path.join(trans_dir, filename)

    with open(path, "w") as f:
        f.write(f"=== {ticker} Recent News & Earnings Context ===\n")
        f.write(f"Source: Finnhub (last 30 days)\n")
        f.write(f"Generated: {datetime.now(PARIS).isoformat()}\n")
        f.write(f"Articles found: {len(news)}\n")
        f.write(f"{'='*60}\n\n")

        for i, article in enumerate(news[:15], 1):
            headline = article.get("headline", "No title")
            summary = article.get("summary", "")
            source = article.get("source", "Unknown")
            url = article.get("url", "")
            date_raw = article.get("datetime", 0)
            if date_raw:
                from datetime import datetime as dt
                article_date = dt.fromtimestamp(date_raw).strftime("%Y-%m-%d %H:%M")
            else:
                article_date = "Unknown"

            f.write(f"[{i}] {headline}\n")
            f.write(f"    Source: {source} | Date: {article_date}\n")
            f.write(f"    URL: {url}\n")
            if summary:
                f.write(f"    Summary: {summary[:500]}\n")
            f.write("\n")

    logger.info(f"Earnings news saved: {path} ({len(news)} articles)")


def _generate_market_context(output_dir: str, ticker: str, data: Dict) -> None:
    """Generate a simple market context document from available data."""
    market_dir = os.path.join(output_dir, "05_market_and_context")
    os.makedirs(market_dir, exist_ok=True)

    date_str = datetime.now(PARIS).strftime("%Y%m%d")
    path = os.path.join(market_dir, f"market_context_{ticker}_{date_str}.md")

    with open(path, "w") as f:
        f.write(f"# {data.get('company_name', ticker)} ({ticker}) — Market Context\n\n")
        f.write(f"**Generated:** {datetime.now(PARIS).isoformat()}\n")
        f.write(f"**Data sources:** Finnhub, Yahoo Finance\n\n")

        f.write("## Sector & Industry\n\n")
        f.write(f"- **Sector:** {data.get('sector', 'N/A')}\n")
        f.write(f"- **Industry:** {data.get('industry', 'N/A')}\n")
        f.write(f"- **Market Cap:** ")
        cap = data.get("market_cap")
        if cap:
            f.write(f"${cap/1e12:.2f}T" if cap >= 1e12 else f"${cap/1e9:.1f}B")
        else:
            f.write("N/A")
        f.write("\n\n")

        f.write("## Key Metrics\n\n")
        price = data.get("price")
        pe = data.get("pe_current")
        fpe = data.get("pe_forward")
        beta = data.get("beta")

        if price:
            f.write(f"- **Price:** ${price:,.2f}\n")
        if pe:
            f.write(f"- **P/E (Trailing):** {pe:.1f}\n")
        if fpe:
            f.write(f"- **P/E (Forward):** {fpe:.1f}\n")
        if beta:
            f.write(f"- **Beta:** {beta:.2f}\n")
        f.write(f"- **52W Range:** ${data.get('52w_low', 'N/A')} — ${data.get('52w_high', 'N/A')}\n\n")

        f.write("## Competitive Position\n\n")
        sector = str(data.get('sector', '')).lower()
        industry = str(data.get('industry', '')).lower()

        if 'technology' in sector:
            f.write("Technology sector — subject to rapid innovation cycles, regulatory scrutiny (antitrust, privacy), "
                    "and supply chain dependencies (semiconductors, rare earths).\n\n")
        elif 'financial' in sector:
            f.write("Financial sector — sensitive to interest rate cycles, credit spreads, and regulatory capital requirements.\n\n")
        elif 'healthcare' in sector:
            f.write("Healthcare sector — driven by drug pipelines, regulatory approvals (FDA/EMA), and demographic trends.\n\n")

        f.write("**Note:** For detailed peer comparison and analyst consensus, run a Gemini Deep Research job "
                "via the local Gemini Cockpit (port 7863).\n")

    logger.info(f"Market context saved: {path}")


def _write_output_files(output_dir: str, result: AnalysisResult,
                         yf_data: Dict, fin: Dict,
                         sources: List[Source], claims: List[Claim]):
    """Write report.md, manifest.json, traceability.csv, and extracted data JSON."""
    os.makedirs(os.path.join(output_dir, "06_extracted_data"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "07_final_report"), exist_ok=True)

    # Extracted data JSONs
    for fname, data in [
        ("extracted_financials.json", fin),
        ("extracted_risks.json", [r.model_dump() for r in result.risks]),
        ("sources_manifest.json", [s.model_dump() for s in sources]),
    ]:
        path = os.path.join(output_dir, "06_extracted_data", fname)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    # Claim traceability matrix CSV
    csv_path = os.path.join(output_dir, "06_extracted_data", "claim_traceability_matrix.csv")
    with open(csv_path, "w") as f:
        f.write("claim_id,claim,source_id,file_path,page_or_section,confidence,used_in_report\n")
        for c in claims:
            f.write(f"{c.claim_id},\"{c.claim}\",{c.source_id},{c.file_path or ''},{c.page_or_section or ''},{c.confidence},{'yes' if c.used_in_report else 'no'}\n")

    # Report markdown
    report = _generate_report(result, yf_data, sources)
    report_path = os.path.join(output_dir, "07_final_report", "report.md")
    with open(report_path, "w") as f:
        f.write(report)

    # Generate PDF
    try:
        from backend.pdf_generator import generate_pdf
        pdf_path = os.path.join(output_dir, "07_final_report", "report.pdf")
        generate_pdf(result, report, pdf_path)
        logger.info(f"PDF generated: {pdf_path}")
    except Exception as e:
        logger.warning(f"PDF generation failed: {e}")

    # Convert all MD/TXT deliverables to PDF
    try:
        from backend.pdf_generator import md_to_pdf
        conversions = []
        
        # Transcripts & Management — convert .txt to PDF
        tx_dir = os.path.join(output_dir, "04_transcripts_and_management")
        if os.path.isdir(tx_dir):
            for fname in os.listdir(tx_dir):
                if fname.endswith('.txt'):
                    txt_path = os.path.join(tx_dir, fname)
                    pdf_path = txt_path.replace('.txt', '.pdf')
                    md_to_pdf(txt_path, pdf_path, title=f"{ticker} — {fname.replace('.txt','').replace('_',' ').title()}")
                    conversions.append(pdf_path)
        
        # Market Context — convert all .md to PDF
        mc_dir = os.path.join(output_dir, "05_market_and_context")
        if os.path.isdir(mc_dir):
            for fname in os.listdir(mc_dir):
                if fname.endswith('.md'):
                    md_path = os.path.join(mc_dir, fname)
                    pdf_path = md_path.replace('.md', '.pdf')
                    md_to_pdf(md_path, pdf_path, title=f"{ticker} — {fname.replace('.md','').replace('_',' ').title()}")
                    conversions.append(pdf_path)
        
        if conversions:
            logger.info(f"MD/TXT → PDF: {len(conversions)} files converted")
    except Exception as e:
        logger.warning(f"MD/TXT → PDF conversion failed: {e}")

    logger.info(f"Output written to {output_dir}")


def _generate_report(result: AnalysisResult, yf_data: Dict, sources: List[Source]) -> str:
    """Generate the markdown analysis report."""
    fin = result.financials
    val = result.valuation
    sc = result.scoring

    def fmt(val: Any, unit: str = "") -> str:
        if val is None:
            return "DATA NOT AVAILABLE"
        if isinstance(val, float):
            if abs(val) > 1e9:
                return f"{val/1e9:.1f}B{unit}"
            if abs(val) > 1e6:
                return f"{val/1e6:.1f}M{unit}"
            return f"{val:.2f}{unit}"
        return str(val)

    lines = []
    lines.append(f"# {result.company_name} ({result.ticker}) — AI Analysis")
    lines.append(f"")
    lines.append(f"**Date:** {result.retrieved_at}")
    lines.append(f"**Price:** {fmt(result.price_native, ' ' + result.currency)}")
    lines.append(f"**EUR Price:** {fmt(result.price_eur, ' €')}")
    lines.append(f"**Market Cap:** {fmt(result.market_cap, ' ' + result.currency)}")
    lines.append(f"**Sector:** {result.sector or 'N/A'}")
    lines.append(f"")

    # 1. Executive Summary
    lines.append(f"## 1. Executive Summary")
    lines.append(f"")
    lines.append(f"**Decision:** {result.decision}")
    lines.append(f"**Conviction:** {result.conviction}")
    lines.append(f"**Key phrase:** {result.key_phrase}")
    lines.append(f"")

    # 2. Financial Data
    lines.append(f"## 2. Financial Data")
    lines.append(f"")
    for label, v, src_id in [
        ("Quarterly Revenue", fin.revenue_quarterly, "SRC-001"),
        ("YoY Growth", fin.revenue_yoy_growth, "SRC-001"),
        ("Annual Revenue", fin.revenue_annual, "SRC-001"),
        ("Annual Growth", fin.revenue_annual_growth, "SRC-001"),
        ("Gross Margin", fin.gross_margin, "SRC-001"),
        ("Operating Margin", fin.operating_margin, "SRC-001"),
        ("Net Income", fin.net_income, "SRC-001"),
        ("Free Cash Flow", fin.free_cash_flow, "SRC-001"),
        ("Net Debt", fin.net_debt, "SRC-001"),
        ("Official Guidance", fin.guidance_official, "SRC-001"),
    ]:
        formatted = fmt(v)
        if isinstance(v, float) and v is not None and v < 1 and (label.startswith("YoY") or label.startswith("Gross") or label.startswith("Operating") or label.startswith("Annual Growth")):
            formatted = f"{v*100:.1f}%"
        if label == "Official Guidance" and v is not None and isinstance(v, float):
            formatted = f"{v*100:.1f}%"

        if isinstance(v, float) and abs(v) > 1e6 and not label.startswith("YoY") and not label.startswith("Gross") and not label.startswith("Operating"):
            formatted = f"{v/1e9:.1f}B {result.currency}"
        lines.append(f"- **{label}:** {formatted}")

    lines.append(f"")

    # 3. Business
    lines.append(f"## 3. Business")
    lines.append(f"")
    lines.append(f"{yf_data.get('description', 'DATA NOT AVAILABLE')[:800]}")
    lines.append(f"")

    # 4. Management
    lines.append(f"## 4. Management")
    lines.append(f"")
    lines.append(f"**Tone:** {result.management_tone.tone}")
    lines.append(f"**Confidence:** {result.management_tone.confidence}")
    lines.append(f"**Visibility:** {result.management_tone.visibility}")
    lines.append(f"**Note:** Management tone analysis requires earnings call transcripts (SEC EDGAR or Seeking Alpha).")
    lines.append(f"")

    # 5. Risks
    lines.append(f"## 5. Risks")
    lines.append(f"")
    for r in result.risks:
        severity_emoji = {"high": "🔴", "medium": "🟠", "low": "🟡"}.get(r.severity, "⚪")
        lines.append(f"- {severity_emoji} **{r.category}** : {r.description}")
    lines.append(f"")

    # 6. Valuation
    lines.append(f"## 6. Valuation")
    lines.append(f"")
    lines.append(f"- **P/E (current):** {fmt(val.pe_current)}")
    lines.append(f"- **Forward P/E:** {fmt(val.pe_forward)}")
    lines.append(f"- **PEG ratio:** {fmt(val.peg_ratio)}")
    lines.append(f"- **Expected Growth:** {fmt(val.expected_growth, '%') if val.expected_growth else 'DATA NOT AVAILABLE'}")
    lines.append(f"- **Margin of Safety:** {val.margin_of_safety}")
    lines.append(f"")

    # 7. Scoring
    lines.append(f"## 7. Scoring")
    lines.append(f"")
    for criterion, score in [
        ("Growth", sc.growth),
        ("Profitability", sc.profitability),
        ("Financial Strength", sc.financial_strength),
        ("Moat", sc.moat),
        ("Management", sc.management),
        ("Valuation Risk", sc.valuation_risk),
        ("Geopolitical Risk", sc.geopolitical_risk),
        ("Business Momentum", sc.business_momentum),
    ]:
        bar = "█" * score + "░" * (5 - score)
        lines.append(f"- **{criterion}:** {bar} {score}/5")
    lines.append(f"")
    lines.append(f"**Total: {sc.total}/40**")
    lines.append(f"")

    # 8. Decision
    lines.append(f"## 8. Final Decision")
    lines.append(f"")
    lines.append(f"**Decision:** {result.decision}")
    lines.append(f"**Why:** Score {sc.total}/40 — {_decision_rationale(sc)}")
    lines.append(f"**Conditions to add:** Improved momentum, valuation pullback, positive guidance")
    lines.append(f"**Conditions to sell:** Deteriorating fundamentals, moat erosion, materialized geopolitical risk")
    lines.append(f"")

    # 9. Sources
    lines.append(f"## 9. Sources")
    lines.append(f"")
    for s in sources:
        lines.append(f"- [{s.id}] **{s.title}** ({s.publisher}) — fiabilité: {s.reliability}")
        lines.append(f"  URL: {s.url}")

    return "\n".join(lines)


def _decision_rationale(sc: Scoring) -> str:
    """Generate a one-line rationale for the decision."""
    strong = [name for name, score in [
        ("growth", sc.growth),
        ("profitability", sc.profitability),
        ("financial strength", sc.financial_strength),
        ("moat", sc.moat),
    ] if score >= 4]
    weak = [name for name, score in [
        ("valuation", 5 - sc.valuation_risk),
        ("geopolitical", 5 - sc.geopolitical_risk),
        ("momentum", sc.business_momentum),
    ] if score <= 2]

    parts = []
    if strong:
        parts.append(f"strengths: {', '.join(strong)}")
    if weak:
        parts.append(f"weaknesses: {', '.join(weak)}")
    return ". ".join(parts) if parts else "Balanced profile with no extreme strengths or weaknesses."


def analyze_ticker_fast(ticker: str, output_base: str = "analyses") -> AnalysisResult:
    """
    Fast-path analysis: returns result in <5s.
    Skips heavy file I/O (PDF/Excel/10-K conversion) — those run in background.
    
    Does:
      - Stock data (Yahoo Finance)
      - 10-K text extraction for management + risk scoring
      - Kimi K2.6 management analysis
      - Scoring + decision
      - Output directory creation (empty — filled by background dossier)
    
    Returns the AnalysisResult ready for API response.
    """
    import hashlib
    from backend.models import (
        AnalysisResult, FinancialData, SegmentInfo, ManagementTone,
        RiskItem, ValuationData, Scoring, Source, Claim
    )
    from backend.sources_collector import get_stock_data
    from backend.scorer import score_ticker
    
    retrieved_at = datetime.now(PARIS).isoformat()
    
    # ── Step 1: Identification ──
    logger.info(f"[{ticker}] Fast: Step 1 — stock data")
    yf_data = get_stock_data(ticker)
    price_native = yf_data.get("price")
    currency_fast = yf_data.get("currency", "USD")
    company_name = yf_data.get("company_name", ticker)
    
    # Compute output directory
    date_str = datetime.now(PARIS).strftime("%Y-%m-%d")
    ticker_clean = ticker.replace(".", "_")
    name_clean = company_name.replace(" ", "_").replace("/", "_")[:40]
    output_dir = os.path.join(output_base, f"{date_str}_{ticker_clean}_{name_clean}")
    
    # Create bare directory structure (files filled by background dossier)
    for subdir in [
        "01_official_company_sources",
        "02_sec_or_regulatory_filings",
        "03_financial_data_sources",
        "04_transcripts_and_management",
        "05_market_and_context",
        "06_extracted_data",
        "07_final_report",
    ]:
        os.makedirs(os.path.join(output_dir, subdir), exist_ok=True)
    
    # ── Financials ──
    fin = yf_data.get("financials", {})
    financials = FinancialData(
        revenue_quarterly=fin.get("revenue_quarterly"),
        revenue_yoy_growth=fin.get("revenue_yoy_growth"),
        revenue_annual=fin.get("revenue_annual"),
        revenue_annual_growth=fin.get("revenue_annual_growth"),
        gross_margin=fin.get("gross_margin"),
        operating_margin=fin.get("operating_margin"),
        net_income=fin.get("net_income"),
        free_cash_flow=fin.get("free_cash_flow"),
        net_debt=fin.get("net_debt"),
        guidance_official=fin.get("guidance_official"),
    )
    
    # ── Enrich with edgartools SEC XBRL data (replaces fragile HTML parsing) ──
    try:
        from backend.sources_collector import get_edgar_financials
        edgar = get_edgar_financials(ticker)
        if edgar:
            # Only fill gaps — don't overwrite existing yfinance data
            for attr, edgar_key in [
                ("revenue_annual", "revenue"),
                ("net_income", "net_income"),
                ("free_cash_flow", "free_cash_flow"),
            ]:
                current = getattr(financials, attr, None)
                edgar_val = edgar.get(edgar_key)
                if (current is None or current == 0) and edgar_val is not None:
                    setattr(financials, attr, edgar_val)
                    logger.info(f"[{ticker}] Enriched {attr} = {edgar_val:,.0f} from SEC XBRL")
            
            # Also enrich operating_margin if missing
            if (financials.operating_margin is None or financials.operating_margin == 0):
                rev = edgar.get("revenue")
                op_inc = edgar.get("operating_income")
                if rev and op_inc and rev > 0:
                    financials.operating_margin = round(op_inc / rev, 4)
                    logger.info(f"[{ticker}] Enriched operating_margin = {financials.operating_margin:.1%} from SEC XBRL")
    except Exception as e:
        logger.debug(f"[{ticker}] edgartools enrichment skipped: {e}")
    
    # ── Segments ──
    segments = SegmentInfo(
        primary_segment=yf_data.get("industry") or yf_data.get("sector"),
        revenue_share_pct=None,
        segment_growth=None,
        excessive_dependency="DATA NOT AVAILABLE"
    )
    
    # ── Management discourse + Risk extraction (Codex — single call) ──
    logger.info(f"[{ticker}] Fast: Management analysis (Codex)")
    from backend.sources_collector import extract_10k_sections, get_finnhub_data
    from backend.codex_provider import codex_analyze_management
    
    # Launch Finnhub fetch in parallel with 10-K extraction
    import concurrent.futures as _cf
    _fh_executor = _cf.ThreadPoolExecutor(max_workers=1)
    _fh_future = _fh_executor.submit(get_finnhub_data, ticker)
    
    try:
        sec_10k = extract_10k_sections(ticker, output_dir=output_dir)
        mda_text = sec_10k.get("mda", "")
        risk_text = sec_10k.get("risk_factors", "")
        has_10k = len(mda_text) > 500
    except Exception as e:
        logger.warning(f"[{ticker}] 10-K extraction failed: {e}")
        mda_text, risk_text, has_10k = "", "", False
    
    # Collect Finnhub result (should be ready by now)
    try:
        fh_data = _fh_future.result(timeout=5)
    except Exception:
        fh_data = {}
    _fh_executor.shutdown(wait=False)
    
    if has_10k:
        codex_data = codex_analyze_management(mda_text, risk_text)
        # Fallback to Kimi→DeepSeek if Codex returned empty
        if not codex_data or codex_data.get("tone", "").startswith("DATA NOT AVAILABLE"):
            from backend.kimi_provider import kimi_analyze_management
            codex_data = kimi_analyze_management(mda_text, risk_text)
        management_tone = ManagementTone(
            tone=codex_data.get("tone", ""),
            confidence=codex_data.get("confidence", ""),
            visibility=codex_data.get("visibility", ""),
            concrete_promises=codex_data.get("concrete_promises", []),
            defensive_signals=codex_data.get("defensive_signals", []),
        )
        risks_10k = codex_data.get("risks", [])
    else:
        management_tone = ManagementTone(
            tone="DATA NOT AVAILABLE",
            confidence="DATA NOT AVAILABLE",
            visibility="DATA NOT AVAILABLE",
            concrete_promises=[], defensive_signals=[],
        )
        risks_10k = []
    
    data_risks = _assess_risks(yf_data, {}, ticker)
    risks = risks_10k + data_risks
    if not risks:
        risks = [RiskItem(category="General", description="No major risks identified", severity="low", source="Analysis")]
    
    # ── Valuation ──
    valuation = ValuationData(
        pe_current=yf_data.get("pe_current"),
        pe_forward=yf_data.get("pe_forward"),
        peg_ratio=yf_data.get("peg_ratio"),
        expected_growth=yf_data.get("expected_growth"),
        margin_of_safety=_margin_of_safety_text(yf_data.get("pe_current"), yf_data.get("pe_forward"))
    )
    
    # ── Scoring ──
    scoring = score_ticker({
        "financials": fin,
        "valuation": {
            "pe_current": yf_data.get("pe_current"),
            "pe_forward": yf_data.get("pe_forward"),
            "peg_ratio": yf_data.get("peg_ratio"),
        },
        "sector": yf_data.get("sector"),
        "industry": yf_data.get("industry"),
        "market_cap": yf_data.get("market_cap"),
        "price": yf_data.get("price"),
        "52w_high": yf_data.get("52w_high"),
    }, tone_data=codex_data if has_10k else None)
    
    # ── Decision ──
    decision = scoring.decision()
    conviction = _conviction_text(scoring)
    
    # ── Build result ──
    result = AnalysisResult(
        ticker=ticker,
        company_name=company_name,
        retrieved_at=retrieved_at,
        price_native=price_native,
        price_eur=convert_to_eur(price_native) if (price_native and currency_fast == "USD") else None,
        currency=currency_fast,
        market_cap=yf_data.get("market_cap"),
        sector=yf_data.get("sector"),
        financials=financials,
        segments=segments,
        management_tone=management_tone,
        risks=risks,
        valuation=valuation,
        scoring=scoring,
        decision=decision,
        conviction=conviction,
        key_phrase=_key_phrase(decision, company_name, scoring.total),
        report_path=os.path.join(output_dir, "07_final_report", "report.md"),
        sources_manifest_path=os.path.join(output_dir, "06_extracted_data", "sources_manifest.json"),
    )
    
    # Save Yahoo Finance snapshot (lightweight)
    try:
        yf_local = os.path.join(output_dir, "03_financial_data_sources", f"yahoo_snapshot_{ticker}.json")
        with open(yf_local, "w") as f:
            json.dump(yf_data, f, indent=2, default=str)
    except Exception:
        pass
    
    # Save Finnhub snapshot (already fetched in parallel with 10-K above)
    try:
        if fh_data:
            fh_local = os.path.join(output_dir, "03_financial_data_sources", f"finnhub_{ticker}.json")
            with open(fh_local, "w") as f:
                json.dump(fh_data, f, indent=2, default=str)
    except Exception:
        pass
    
    # ── Synchronous dossier generation (all content written immediately) ──
    # Background thread on Render free tier is unreliable — generates everything here.
    
    # Place README.txt in ALL 7 directories (guarantees no empty dirs in ZIP)
    dossier_descriptions = {
        '01_official_company_sources': 'Company profile with business description, sector, and key facts.',
        '02_sec_or_regulatory_filings': '10-K annual report, 10-Q quarterly, 8-K filings (SEC EDGAR).',
        '03_financial_data_sources': 'Excel financial model, Yahoo Finance snapshot, Finnhub data.',
        '04_transcripts_and_management': 'Earnings call transcripts, management interviews, news.',
        '05_market_and_context': 'Sector analysis, peer comparison, macro indicators.',
        '06_extracted_data': 'Traceability matrix, extracted financials, claim verification.',
        '07_final_report': 'Final analysis report (PDF + Markdown), executive summary.',
    }
    for folder, description in dossier_descriptions.items():
        folder_path = os.path.join(output_dir, folder)
        os.makedirs(folder_path, exist_ok=True)
        placeholder = os.path.join(folder_path, 'README.txt')
        if not os.path.exists(placeholder):
            with open(placeholder, 'w') as f:
                f.write(f'{folder}\n{"=" * len(folder)}\n\n{description}\n\nTicker: {ticker}\n')
    
    # 1. Company profile (01) — from Yahoo Finance data
    try:
        from backend.company_profile import generate_company_profile
        profile_path = generate_company_profile(output_dir, ticker, yf_data)
        if profile_path and os.path.exists(profile_path):
            from backend.pdf_generator import md_to_pdf
            profile_pdf = os.path.join(os.path.dirname(profile_path), f"company_profile_{ticker}.pdf")
            md_to_pdf(profile_path, profile_pdf, title=f"{company_name} ({ticker}) — Company Profile")
    except Exception as e:
        logger.warning(f"[{ticker}] Company profile failed: {e}")
    
    # 2. Market context (05) — from Yahoo Finance (always available)
    try:
        market_dir = os.path.join(output_dir, "05_market_and_context")
        os.makedirs(market_dir, exist_ok=True)
        
        # Use already-fetched Finnhub peers (no re-fetch)
        peers = fh_data.get("peers", [])
        
        market_md = os.path.join(market_dir, f"market_context_{ticker}_{date_str}.md")
        with open(market_md, "w") as f:
            f.write(f"# Market Context — {ticker}\n\n")
            f.write(f"**Sector**: {yf_data.get('sector', 'N/A')}\n")
            f.write(f"**Industry**: {yf_data.get('industry', 'N/A')}\n")
            f.write(f"**Market Cap**: {yf_data.get('market_cap', 'N/A')}\n")
            f.write(f"**Currency**: {yf_data.get('currency', 'USD')}\n")
            f.write(f"**Country**: {yf_data.get('country', 'N/A')}\n")
            f.write(f"**Price**: {price_native} {yf_data.get('currency', 'USD')}\n")
            f.write(f"**P/E (trailing)**: {yf_data.get('pe_current', 'N/A')}\n")
            f.write(f"**P/E (forward)**: {yf_data.get('pe_forward', 'N/A')}\n")
            f.write(f"**52w High**: {yf_data.get('52w_high', 'N/A')}\n\n")
            if peers:
                f.write(f"**Peers** (Finnhub): {', '.join(peers[:10])}\n")
            else:
                f.write("**Peers**: Not available (Finnhub free tier limit)\n")
        from backend.pdf_generator import md_to_pdf
        md_to_pdf(market_md, market_md.replace('.md', '.pdf'),
                  title=f"{ticker} — Market Context")
    except Exception as e:
        logger.warning(f"[{ticker}] Market context failed: {e}")
    
    # 3. Transcripts/News (04) — from Yahoo Finance + Finnhub
    try:
        tx_dir = os.path.join(output_dir, "04_transcripts_and_management")
        os.makedirs(tx_dir, exist_ok=True)
        
        # Use already-fetched Finnhub news (no re-fetch)
        news_articles = fh_data.get("news", [])
        
        tx_md = os.path.join(tx_dir, f"earnings_news_{ticker}_{date_str}.md")
        with open(tx_md, "w") as f:
            f.write(f"# Earnings News & Management — {ticker}\n\n")
            f.write(f"**Generated**: {datetime.now(PARIS).isoformat()}\n")
            f.write(f"**Management Tone**: {management_tone.tone}\n")
            f.write(f"**Confidence**: {management_tone.confidence}\n")
            f.write(f"**Visibility**: {management_tone.visibility}\n\n")
            if management_tone.concrete_promises:
                f.write("## Concrete Promises\n")
                for p in management_tone.concrete_promises:
                    f.write(f"- {p}\n")
                f.write("\n")
            if management_tone.defensive_signals:
                f.write("## Defensive Signals\n")
                for s in management_tone.defensive_signals:
                    f.write(f"- {s}\n")
                f.write("\n")
            if news_articles:
                f.write(f"## Recent News ({len(news_articles)} articles)\n\n")
                for article in news_articles[:10]:
                    f.write(f"### {article.get('headline', 'N/A')}\n")
                    f.write(f"*{article.get('source', 'N/A')}*\n\n")
                    f.write(f"{article.get('summary', 'N/A')}\n\n")
            else:
                f.write("## Recent News\n\n")
                f.write("No news articles available (Finnhub free tier limit or API unavailable).\n")
        from backend.pdf_generator import md_to_pdf
        md_to_pdf(tx_md, tx_md.replace('.md', '.pdf'),
                  title=f"{ticker} — Earnings News & Management")
    except Exception as e:
        logger.warning(f"[{ticker}] Transcripts/news failed: {e}")
    
    # 4. Full report.md + report.pdf (07)
    try:
        report_dir = os.path.join(output_dir, "07_final_report")
        report_md = os.path.join(report_dir, "report.md")
        # Use the rich 9-section template
        sources = result.sources if hasattr(result, 'sources') and result.sources else []
        report_text = _generate_report(result, yf_data, sources)
        with open(report_md, "w") as f:
            f.write(report_text)
        # Convert to PDF
        from backend.pdf_generator import md_to_pdf
        report_pdf = os.path.join(report_dir, "report.pdf")
        md_to_pdf(report_md, report_pdf, title=f"{company_name} ({ticker}) — Analysis Report")
        logger.info(f"[{ticker}] Full report written (MD + PDF)")
    except Exception as e:
        logger.warning(f"[{ticker}] Report generation failed: {e}")

    # 4b. Optional earnings call deep-dive (07) — only when a full transcript is available
    _add_earnings_deep_dive_if_transcript(
        ticker=ticker,
        company_name=company_name,
        output_dir=output_dir,
        result=result,
        yf_data=yf_data,
        company_website=_company_website(yf_data, fh_data),
    )
    
    # 5. Excel financials (03)
    try:
        from backend.excel_generator import generate_excel
        excel_path = os.path.join(output_dir, "03_financial_data_sources", f"financials_{ticker}.xlsx")
        risks_data = [r.model_dump() if hasattr(r, 'model_dump') else r for r in result.risks]
        generate_excel(excel_path, ticker, company_name, yf_data, risks_data)
    except Exception as e:
        logger.warning(f"[{ticker}] Excel generation failed: {e}")
    
    # ── Write sources manifest with accurate source tracking ──
    try:
        actual_source = yf_data.get("_source", "yfinance")
        source_names = {
            "finnhub": ("Finnhub", "https://finnhub.io/", "financial_data_api"),
            "twelvedata": ("Twelve Data", "https://twelvedata.com/", "financial_data_api"),
            "yfinance": ("Yahoo Finance", f"https://finance.yahoo.com/quote/{ticker}/", "financial_aggregator"),
            "cache": ("Yahoo Finance (cache)", f"https://finance.yahoo.com/quote/{ticker}/", "financial_aggregator"),
        }
        name, url, stype = source_names.get(actual_source, source_names["yfinance"])
        manifest_sources = [{
            "id": "SRC-001",
            "category": "financial_data_sources",
            "title": f"{name} — {ticker} snapshot (source: {actual_source})",
            "url": url,
            "retrieved_at": retrieved_at,
            "source_type": stype,
            "publisher": name,
            "used_for": ["price", "financials", "valuation", "identification"]
        }]
        # Use already-fetched Finnhub data (no re-fetch)
        if fh_data.get("peers"):
            manifest_sources.append({
                "id": "SRC-002",
                "category": "financial_data_sources",
                "title": f"Finnhub — {ticker} metrics and peers",
                "url": f"https://finnhub.io/stock/{ticker}",
                "retrieved_at": retrieved_at,
                "source_type": "financial_data_api",
                "publisher": "Finnhub",
                "used_for": ["peer_analysis", "financials"]
            })
        manifest_path = os.path.join(output_dir, "06_extracted_data", "sources_manifest.json")
        os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
        with open(manifest_path, "w") as f:
            json.dump(manifest_sources, f, indent=2, default=str)
    except Exception as e:
        logger.warning(f"[{ticker}] Sources manifest write failed: {e}")
    
    # ── Background dossier generation (best-effort) ──
    # Only spawn if NOT already generated synchronously above
    # (avoids double work + race condition with ZIP — Codex R2 audit)
    from backend.async_dossier import generate_dossier_background
    if not os.path.exists(os.path.join(output_dir, "07_final_report", "report.md")):
        try:
            generate_dossier_background(ticker, company_name, yf_data, result, output_dir)
            logger.debug(f"[{ticker}] Background dossier thread spawned (best-effort)")
        except Exception as e:
            logger.debug(f"[{ticker}] Background dossier spawn skipped: {e}")
    
    return result
