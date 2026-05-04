"""Main pipeline — executes the 9-step analysis for a single ticker."""
import os
import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from backend.models import (
    AnalysisResult, FinancialData, SegmentInfo, ManagementTone,
    RiskItem, ValuationData, Scoring, Source, Claim
)
from backend.sources_collector import get_yahoo_data, get_finnhub_data, get_sec_filings, convert_to_eur
from backend.scorer import score_ticker

logger = logging.getLogger(__name__)

# Paris timezone
PARIS = timezone(offset=datetime.now(timezone.utc).astimezone().utcoffset() or __import__("datetime").timedelta(hours=2))


def analyze_ticker(ticker: str, output_base: str = "analyses") -> AnalysisResult:
    """
    Execute the full 9-step pipeline for a single ticker.
    Returns AnalysisResult and writes files to analyses/{date}_{TICKER}_{NAME}/
    """
    retrieved_at = datetime.now(PARIS).isoformat()
    sources: List[Source] = []
    claims: List[Claim] = []
    src_id = 0
    claim_id = 0

    def next_src() -> str:
        nonlocal src_id
        src_id += 1
        return f"SRC-{src_id:03d}"

    def next_claim() -> str:
        nonlocal claim_id
        claim_id += 1
        return f"C-{claim_id:03d}"

    def add_claim(text: str, src: str, file_path: str = "", section: str = ""):
        claim_id = next_claim()
        sha = hashlib.sha256(f"{text}|{src}|{file_path}|{section}".encode()).hexdigest()[:16]
        claims.append(Claim(
            claim_id=claim_id, claim=text, source_id=src,
            file_path=file_path, page_or_section=section, confidence="high",
            sha256=sha
        ))

    # ── Step 1: Identification ──
    logger.info(f"[{ticker}] Step 1: Identification")
    yf_data = get_yahoo_data(ticker)
    price_native = yf_data.get("price")
    eur_rate = convert_to_eur(price_native) if price_native else None
    company_name = yf_data.get("company_name", ticker)

    # Compute output directory early
    date_str = datetime.now(PARIS).strftime("%Y-%m-%d")
    ticker_clean = ticker.replace(".", "_")
    name_clean = company_name.replace(" ", "_").replace("/", "_")[:40]
    output_dir = os.path.join(output_base, f"{date_str}_{ticker_clean}_{name_clean}")

    # Create full source directory structure
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

    # ── Populate dossiers 01 and 05 with README ──
    for folder, description in [
        ("01_official_company_sources",
         "Sources officielles de l'entreprise : rapports annuels, présentations investisseurs, "
         "communiqués de presse, lettres aux actionnaires, enregistrements SEC hors 10-K (8-K, DEF 14A)."),
        ("05_market_and_context",
         "Contexte de marché : données sectorielles, comparables, rapports d'analystes, "
         "indicateurs macroéconomiques, actualités du secteur, données de concurrence."),
    ]:
        readme_path = os.path.join(output_dir, folder, "README.txt")
        with open(readme_path, "w") as f:
            f.write(f"=== {folder} ===\n\n{description}\n\n"
                    f"Ticker: {ticker}\nDate: {date_str}\n"
                    "Ce dossier est destiné à recevoir les sources correspondantes.\n")
        logger.debug(f"README created: {readme_path}")

    # Save Yahoo Finance snapshot
    yf_local = os.path.join(output_dir, "03_financial_data_sources", f"yahoo_snapshot_{ticker}.json")
    try:
        with open(yf_local, "w") as f:
            json.dump(yf_data, f, indent=2, default=str)
    except Exception:
        yf_local = ""

    s1 = next_src()
    sources.append(Source(
        id=s1, category="financial_data_sources", title=f"Yahoo Finance — {ticker} snapshot",
        url=f"https://finance.yahoo.com/quote/{ticker}/",
        local_path=yf_local if yf_local else None,
        retrieved_at=retrieved_at, source_type="financial_aggregator",
        publisher="Yahoo Finance",
        used_for=["identification", "price", "market_cap", "sector"],
        reliability="medium"
    ))

    # ── Claims: Step 1 ──
    add_claim(f"Company name: {company_name}", s1, yf_local if yf_local else "", "info.longName")
    if price_native:
        add_claim(f"Stock price: {price_native} {yf_data.get('currency', 'USD')}", s1, yf_local if yf_local else "", "info.currentPrice")
    if yf_data.get("market_cap"):
        add_claim(f"Market cap: {yf_data['market_cap']/1e12:.2f}T {yf_data.get('currency', 'USD')}", s1, yf_local if yf_local else "", "info.marketCap")
    if yf_data.get("sector"):
        add_claim(f"Sector: {yf_data['sector']}", s1, yf_local if yf_local else "", "info.sector")

    # ── Step 2: Financials ──
    logger.info(f"[{ticker}] Step 2: Financial figures")
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

    # ── Claims: Step 2 ──
    if financials.revenue_quarterly:
        add_claim(f"Revenue Q: {financials.revenue_quarterly/1e9:.1f}B {yf_data.get('currency', 'USD')}", s1, yf_local if yf_local else "", "quarterly_financials")
    if financials.revenue_yoy_growth:
        add_claim(f"Revenue YoY growth: {financials.revenue_yoy_growth*100:.1f}%", s1, yf_local if yf_local else "", "quarterly_financials")
    if financials.revenue_annual:
        add_claim(f"Revenue annual: {financials.revenue_annual/1e9:.1f}B", s1, yf_local if yf_local else "", "financials")
    if financials.gross_margin:
        add_claim(f"Gross margin: {financials.gross_margin*100:.1f}%", s1, yf_local if yf_local else "", "info.grossMargins")
    if financials.operating_margin:
        add_claim(f"Operating margin: {financials.operating_margin*100:.1f}%", s1, yf_local if yf_local else "", "info.operatingMargins")
    if financials.net_income:
        add_claim(f"Net income: {financials.net_income/1e9:.1f}B", s1, yf_local if yf_local else "", "financials.Net Income")
    if financials.free_cash_flow:
        add_claim(f"Free cash flow: {financials.free_cash_flow/1e9:.1f}B", s1, yf_local if yf_local else "", "cashflow.Free Cash Flow")

    # ── Step 3: Segments ──
    logger.info(f"[{ticker}] Step 3: Segments")
    # YF doesn't give segment breakdown → mark as limited
    segments = SegmentInfo(
        primary_segment=yf_data.get("industry") or yf_data.get("sector"),
        revenue_share_pct=None,
        segment_growth=None,
        excessive_dependency="DONNÉE NON DISPONIBLE — segment breakdown requires company filings"
    )

    # ── Step 4: Management discourse ──
    logger.info(f"[{ticker}] Step 4: Management discourse")
    from backend.sources_collector import extract_10k_sections
    from backend.management_analyzer import analyze_management_tone

    sec_10k = extract_10k_sections(ticker, output_dir=output_dir)
    mda_text = sec_10k.get("mda", "")
    risk_text = sec_10k.get("risk_factors", "")
    has_10k_text = len(mda_text) > 500
    tenk_local = sec_10k.get("local_path", "")

    # Default fallback for management_tone (overridden below if data available)
    management_tone = ManagementTone(
        tone="DONNÉE NON DISPONIBLE — 10-K text extraction failed",
        confidence="DONNÉE NON DISPONIBLE",
        visibility="DONNÉE NON DISPONIBLE",
        concrete_promises=[],
        defensive_signals=[]
    )
    s4 = None  # Guard for risk claims loop when 10-K unavailable

    if has_10k_text:
        s4 = next_src()
        sources.append(Source(
            id=s4, category="sec_or_regulatory_filings",
            title=f"SEC EDGAR — {ticker} 10-K MD&A + Risk Factors",
            url=sec_10k.get("url", ""),
            local_path=tenk_local if tenk_local else None,
            retrieved_at=retrieved_at, source_type="sec_filing",
            publisher="SEC EDGAR",
            used_for=["management_discourse", "risk_factors"],
            reliability="high"
        ))

        tone_data = analyze_management_tone(mda_text, risk_text)
        management_tone = ManagementTone(
            tone=tone_data.get("tone", ""),
            confidence=tone_data.get("confidence", ""),
            visibility=tone_data.get("visibility", ""),
            concrete_promises=tone_data.get("concrete_promises", []),
            defensive_signals=tone_data.get("defensive_signals", []),
        )
        # ── Claims: Step 4 ──
        add_claim(f"Management tone: {tone_data.get('tone', '')}", s4, tenk_local, "Item 7 MD&A")
        add_claim(f"Management confidence: {tone_data.get('confidence', '')}", s4, tenk_local, "Item 7 MD&A")

    # ── Transcript search ──
    from backend.transcript_finder import find_transcripts
    transcript_data = find_transcripts(ticker, output_dir=output_dir)
    if transcript_data.get("found"):
        s_trans = next_src()
        sources.append(Source(
            id=s_trans, category="transcripts_and_management",
            title=f"Transcript sources — {ticker}",
            url=transcript_data["sources"][0]["url"] if transcript_data["sources"] else "",
            retrieved_at=retrieved_at, source_type="transcript_search",
            publisher="Seeking Alpha / Motley Fool",
            used_for=["management_discourse"],
            reliability="medium"
        ))

    # ── Step 5: Risks ──
    logger.info(f"[{ticker}] Step 5: Risks")
    from backend.management_analyzer import extract_risks_from_10k

    # Try 10-K risk factors first for real risks
    if risk_text and len(risk_text) > 500:
        risks_10k = extract_risks_from_10k(risk_text)
        risks_10k_source = "SEC 10-K Risk Factors"
    else:
        risks_10k = []
        risks_10k_source = ""

    # Supplement with data-driven risks
    data_risks = _assess_risks(yf_data, {}, ticker)

    # Merge: 10-K risks first (more reliable), then data risks
    risks = risks_10k + data_risks
    if not risks:
        risks.append(RiskItem(category="Général", description="Aucun risque majeur identifié", severity="low", source="Analysis"))

    # ── Claims: Step 5 ──
    for i, risk in enumerate(risks[:8]):
        risk_source = risk.get("source", "") if isinstance(risk, dict) else risk.source
        risk_desc = risk.get("description", "") if isinstance(risk, dict) else risk.description
        risk_cat = risk.get("category", "") if isinstance(risk, dict) else risk.category
        risk_sev = risk.get("severity", "") if isinstance(risk, dict) else risk.severity
        risk_src = s4 if (s4 and "10-K" in str(risk_source)) else s1
        risk_path = tenk_local if "10-K" in str(risk_source) else (yf_local if yf_local else "")
        add_claim(f"Risk: {risk_cat} ({risk_sev}): {risk_desc[:100]}", risk_src, risk_path, "Item 1A Risk Factors")

    # Finnhub news for context
    fh = get_finnhub_data(ticker)
    fh_local = ""
    if fh.get("news"):
        s5 = next_src()
        fh_local = os.path.join(output_dir, "03_financial_data_sources", f"finnhub_{ticker}.json")
        try:
            with open(fh_local, "w") as f:
                json.dump(fh, f, indent=2, default=str)
        except Exception:
            fh_local = ""
        sources.append(Source(
            id=s5, category="financial_data_sources",
            title=f"Finnhub — {ticker} recent news",
            url="https://finnhub.io/",
            local_path=fh_local if fh_local else None,
            retrieved_at=retrieved_at, source_type="news_aggregator",
            publisher="Finnhub", used_for=["risk_context"], reliability="medium"
        ))

    # ── Step 6: Valuation ──
    logger.info(f"[{ticker}] Step 6: Valuation")
    valuation = ValuationData(
        pe_current=yf_data.get("pe_current"),
        pe_forward=yf_data.get("pe_forward"),
        peg_ratio=yf_data.get("peg_ratio"),
        expected_growth=yf_data.get("expected_growth"),
        margin_of_safety=_margin_of_safety_text(yf_data.get("pe_current"), yf_data.get("pe_forward"))
    )

    # ── Claims: Step 6 ──
    if valuation.pe_current:
        add_claim(f"P/E trailing: {valuation.pe_current:.1f}", s1, yf_local if yf_local else "", "info.trailingPE")
    if valuation.pe_forward:
        add_claim(f"P/E forward: {valuation.pe_forward:.1f}", s1, yf_local if yf_local else "", "info.forwardPE")
    if valuation.peg_ratio:
        add_claim(f"PEG ratio: {valuation.peg_ratio:.2f}", s1, yf_local if yf_local else "", "info.pegRatio")

    # ── Step 7: Scoring ──
    logger.info(f"[{ticker}] Step 7: Scoring")
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
    }, tone_data=tone_data if has_10k_text else None)

    # ── Step 8: Decision ──
    decision = scoring.decision()
    conviction = _conviction_text(scoring)

    # ── Claims: Step 7-8 ──
    add_claim(f"Total score: {scoring.total}/40", s1, "", "Scoring model")
    add_claim(f"Decision: {decision} (conviction: {conviction})", s1, "", "Scoring model")

    # ── Step 9: Output ──
    # output_dir already computed in Step 1

    # Build result
    result = AnalysisResult(
        ticker=ticker,
        company_name=company_name,
        retrieved_at=retrieved_at,
        price_native=price_native,
        price_eur=eur_rate,
        currency=yf_data.get("currency", "USD"),
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

    # Write output files
    _write_output_files(output_dir, result, yf_data, fin, sources, claims)

    return result


def _assess_risks(yf_data: Dict, fh_data: Dict, ticker: str) -> List[RiskItem]:
    """Identify risks from available data."""
    risks = []

    # Sector-specific risks
    sector = str(yf_data.get("sector", "")).lower()
    industry = str(yf_data.get("industry", "")).lower()

    if "technology" in sector or "semiconductor" in industry:
        risks.append(RiskItem(category="Sector", description="Cyclicalité tech / semi-conducteurs", severity="medium", source="Yahoo Finance sector classification"))
    if "china" in yf_data.get("description", "").lower() or "china" in industry:
        risks.append(RiskItem(category="Geopolitique", description="Exposition Chine / tensions commerciales", severity="high", source="Company description analysis"))

    # Concentration risk
    if yf_data.get("market_cap") and yf_data.get("market_cap", 0) > 5e11:
        risks.append(RiskItem(category="Taille", description="Mega-cap → croissance plus difficile à maintenir", severity="low", source="Market cap analysis"))

    # Debt risk
    fin = yf_data.get("financials", {})
    if fin.get("net_debt") is not None and fin.get("net_debt", 0) > 1e10:
        risks.append(RiskItem(category="Financier", description=f"Dette nette significative ({fin['net_debt']/1e9:.1f}B)", severity="medium", source="Yahoo Finance balance sheet"))

    # Valuation risk
    pe = yf_data.get("pe_current")
    if pe is not None and pe > 50:
        risks.append(RiskItem(category="Valorisation", description=f"PE élevé ({pe:.1f}) → prime de croissance importante", severity="high", source="Yahoo Finance valuation"))

    # No risks found
    if not risks:
        risks.append(RiskItem(category="Général", description="Aucun risque majeur identifié avec les données disponibles", severity="low", source="Analysis"))

    return risks


def _margin_of_safety_text(pe: Any, fpe: Any) -> str:
    pe_val = fpe if fpe else pe
    if pe_val is None:
        return "DONNÉE NON DISPONIBLE"
    if pe_val < 15:
        return "Marge de sécurité confortable (PE < 15)"
    if pe_val < 25:
        return "Marge de sécurité modérée (PE 15-25)"
    if pe_val < 40:
        return "Marge de sécurité faible (PE 25-40)"
    return "Absence de marge de sécurité (PE > 40)"


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
