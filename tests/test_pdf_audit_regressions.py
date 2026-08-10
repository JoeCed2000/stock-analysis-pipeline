"""Regression gates for defects found in the real AAPL client PDF."""

from pathlib import Path
from types import SimpleNamespace

from backend.earnings_deep_dive.mapper import (
    _build_data_quality,
    _build_valuation_context,
    _compute_peer_labels,
    _ensure_section_commentary,
    _rows_for_section,
    build_earnings_deep_dive_report,
    render_report_markdown,
    _cash_flow_quality_note,
)
from backend.earnings_deep_dive.report_model import SourceRef
from backend.earnings_deep_dive.schemas import FinancialMetrics
from backend.earnings_deep_dive.deep_dive_validator import validate_deep_dive
from backend.models import Scoring
from backend.pipeline import _deep_dive_metrics


def _section(report, key):
    return next(section for section in report.sections if section.key == key)


def test_forward_pe_uses_provider_annual_eps_not_quarterly_estimate_times_four():
    metrics = FinancialMetrics(
        eps_estimate=1.94,
        forward_eps=8.54,
        pe_forward=31.14,
        pe_trailing=37.80,
    )

    rows = _rows_for_section(
        "Forward P/E",
        ("Forward P/E", "Forward EPS"),
        metrics,
    )

    assert rows[0][1] == "31.14x"
    assert "Yahoo" in rows[0][4]
    assert rows[1][1] == "$8.54"
    assert "$7.76" not in str(rows)


def test_forward_pe_does_not_leak_internal_validation_marker():
    report = build_earnings_deep_dive_report(
        ticker="AAPL",
        company="Apple Inc.",
        quarter="FY2026 Q2",
        language="en",
        metrics=FinancialMetrics(forward_eps=8.54, pe_forward=31.14),
        section_analysis={"Forward P/E": "The valuation remains elevated."},
    )

    forward = _section(report, "Forward P/E")
    assert "[Validated:" not in "\n".join(forward.analysis)


def test_capital_efficiency_change_is_recomputed_from_displayed_values():
    metrics = FinancialMetrics(
        roe=1.20,
        roe_prior_year=0.371,
        roe_yoy=210.3,
        rotce=1.40,
        rotce_prior_year=0.371,
        rotce_yoy=288.0,
    )

    rows = _rows_for_section(
        "Capital Efficiency",
        ("ROE", "ROTCE", "ROA", "ROIC"),
        metrics,
    )

    assert rows[0][1] == "+120.0%"
    assert rows[0][3] == "+82.9 pts"
    assert rows[0][4] == "improvement"
    assert rows[1][1] == "+140.0%"
    assert rows[1][3] == "+102.9 pts"
    assert rows[1][4] == "improvement"


def test_garbled_xbrl_segment_names_are_not_rendered_or_relabelled_as_products():
    metrics = FinancialMetrics(
        revenue_actual=111.2e9,
        segments={
            "Mar": {"revenue": 28e6, "source": "SEC XBRL"},
            "March": {"revenue": 19e6, "source": "SEC XBRL"},
            "the Company expects": {"revenue": 64e6, "source": "SEC XBRL"},
            "year": {"revenue": 200e3, "source": "SEC XBRL"},
            "total_revenue_quarterly": 111.2e9,
        },
    )

    rows = _rows_for_section(
        "Segments",
        ("Product 1", "Product 2", "Product 3", "Product 4", "Total"),
        metrics,
    )
    rendered = " ".join(str(cell) for row in rows for cell in row)

    assert "Mar" not in rendered
    assert "March" not in rendered
    assert "the Company expects" not in rendered
    assert "year" not in rendered
    assert "$28.0M" not in rendered
    assert "$64.0M" not in rendered
    assert any(row[0] == "Total" and "$111.2B" in row[1] for row in rows)


def test_missing_aapl_segments_do_not_fall_back_to_nvidia_product_names():
    metrics = FinancialMetrics(
        revenue_actual=111.18e9,
        revenue_yoy=16.6,
        segments={"total_revenue_quarterly": 111.18e9},
    )

    rows = _rows_for_section(
        "Segments",
        ("Data Center", "Gaming", "Professional Visualization", "Automotive", "OEM & Other", "Total"),
        metrics,
    )
    rendered = " ".join(str(cell) for row in rows for cell in row)

    assert "Data Center" not in rendered
    assert "Gaming" not in rendered
    assert "Professional Visualization" not in rendered
    assert "Segment breakdown not disclosed" in rendered
    assert any(row[0] == "Total" and "$111.2B" in row[1] for row in rows)


def test_cash_flow_quality_note_labels_fcf_ocf_and_capex_in_the_right_order():
    note = _cash_flow_quality_note(
        "en",
        FinancialMetrics(
            operating_cash_flow=28.70e9,
            capex=-1.97e9,
            free_cash_flow=26.73e9,
        ),
    )

    assert "FCF $26.7B = OCF $28.7B − CapEx $2.0B" in note
    assert "FCF = $28.7B OCF" not in note


def test_backlog_proxy_does_not_assume_a_data_center_business():
    rows = _rows_for_section(
        "Backlog",
        ("Backlog", "Book-to-bill / demand"),
        FinancialMetrics(),
    )

    rendered = " ".join(str(cell) for row in rows for cell in row)
    assert "Data Center" not in rendered
    assert "revenue guidance and disclosed demand indicators" in rendered


def test_yfinance_run_does_not_label_quantitative_rows_as_sec_filings():
    metrics = FinancialMetrics(
        source_form="yfinance",
        revenue_actual=111.18e9,
        revenue_quarterly_prior_year=95.36e9,
        revenue_yoy=16.6,
        gross_profit=54.85e9,
        gross_margin=0.493,
        operating_income=35.87e9,
        operating_margin=0.323,
        net_income=30.00e9,
    )

    rows = _rows_for_section(
        "Operating Metrics",
        ("Revenue", "Gross profit", "Gross margin", "OpEx", "Operating income", "Operating margin", "Net income"),
        metrics,
    )
    populated_sources = [row[-1] for row in rows if row[1] != "Not disclosed"]

    assert populated_sources
    assert all("Yahoo Finance" in source for source in populated_sources)
    assert all("SEC" not in source for source in populated_sources)


def test_revenue_actual_without_consensus_is_labeled_as_yahoo_not_sec():
    rows = _rows_for_section(
        "EPS & Revenue",
        ("EPS", "Revenue"),
        FinancialMetrics(
            financial_source_form="yfinance",
            revenue_actual=111.18e9,
            revenue_yoy=16.6,
        ),
    )

    revenue = next(row for row in rows if row[0] == "Revenue")
    assert "Yahoo Finance" in revenue[-1]
    assert "SEC" not in revenue[-1]


def test_financial_metric_provenance_is_not_overwritten_by_segment_filing_source():
    metrics = FinancialMetrics(
        source_form="10-Q",
        financial_source_form="yfinance",
        roe=1.151,
        rotce=1.439,
        roa=0.330,
        roic=0.641,
    )

    rows = _rows_for_section(
        "Capital Efficiency",
        ("ROE", "ROTCE / ROTE", "ROA", "ROIC", "Capital Allocation - Buybacks", "Capital Allocation - Dividends"),
        metrics,
    )
    populated_sources = [row[-1] for row in rows if row[1] != "Not disclosed"]

    assert populated_sources
    assert all("Yahoo Finance" in source for source in populated_sources)
    assert all("SEC" not in source for source in populated_sources)


def test_missing_guidance_rows_do_not_claim_an_sec_source():
    rows = _rows_for_section(
        "Guidance",
        ("Revenue", "GAAP Gross Margin", "Non-GAAP Gross Margin", "GAAP OpEx", "EPS (non-GAAP)", "Diluted Shares"),
        FinancialMetrics(
            financial_source_form="yfinance",
            gross_margin=0.493,
            revenue_estimate=112.0e9,
            eps_estimate=1.94,
        ),
    )

    rendered = {row[0]: row for row in rows}
    assert "Yahoo Finance" in rendered["Revenue"][-1]
    assert "Yahoo Finance" in rendered["GAAP Gross Margin"][-1]
    assert rendered["Non-GAAP Gross Margin"][-1] == "Not disclosed"
    assert rendered["GAAP OpEx"][-1] == "Not disclosed"
    assert rendered["Diluted Shares"][-1] == "Not disclosed"


def test_verdict_rows_are_labeled_as_synthesis_not_sec_filing():
    rows = _rows_for_section(
        "Verdict",
        ("Earnings quality", "Growth durability", "Valuation", "Overall verdict"),
        FinancialMetrics(
            financial_source_form="yfinance",
            eps_actual=2.01,
            eps_estimate=1.94,
            revenue_actual=111.2e9,
            revenue_yoy=16.6,
            operating_cash_flow=28.7e9,
            free_cash_flow=26.7e9,
            pe_forward=31.14,
        ),
    )

    assert all("SEC" not in row[-1] for row in rows)
    assert all(row[-1] == "Model + metrics" for row in rows)


def test_canonical_scoring_is_the_only_client_facing_verdict():
    scoring = Scoring(
        financial_health=8,
        growth=7,
        valuation=5,
        management=4,
        moat=3,
        sentiment=1,
    )
    report = build_earnings_deep_dive_report(
        ticker="AAPL",
        company="Apple Inc.",
        quarter="FY2026 Q2",
        language="en",
        metrics=FinancialMetrics(
            eps_actual=2.01,
            eps_estimate=1.94,
            revenue_actual=111.2e9,
            revenue_yoy=17.0,
            free_cash_flow=26.7e9,
            pe_forward=31.14,
        ),
        scoring=scoring,
        section_analysis={
            "Verdict": "Recommendation: HOLD. This is a hold-grade setup."
        },
    )

    verdict = _section(report, "Verdict")
    client_text = "\n".join([*verdict.analysis, verdict.summary])
    assert scoring.decision() == "BUY"
    assert "Recommendation: BUY" in client_text
    assert "HOLD" not in client_text
    assert "hold-grade" not in client_text.lower()
    assert "0-5 score" not in client_text
    assert "Risk/reward is favorable" in client_text


def test_canonical_scoring_replaces_fallback_verdict_when_llm_verdict_failed():
    scoring = Scoring(
        financial_health=8,
        growth=7,
        valuation=5,
        management=4,
        moat=3,
        sentiment=1,
    )
    report = build_earnings_deep_dive_report(
        ticker="AAPL",
        company="Apple Inc.",
        quarter="FY2026 Q2",
        language="en",
        metrics=FinancialMetrics(
            eps_actual=2.01,
            eps_estimate=1.94,
            revenue_actual=111.2e9,
            revenue_yoy=16.6,
            free_cash_flow=26.7e9,
            pe_forward=31.14,
        ),
        scoring=scoring,
    )

    verdict = _section(report, "Verdict")
    client_text = "\n".join([*verdict.analysis, verdict.summary])
    assert "BUY" in client_text
    assert "HOLD" not in client_text


def test_obtained_transcript_is_not_reported_as_unused_when_timestamp_is_missing():
    generated_at = "2026-07-12T13:25:39Z"
    dq = _build_data_quality(
        ticker="AAPL",
        yf_info={"forwardPE": 31.14},
        company_overview={"ticker": "AAPL"},
        metrics=FinancialMetrics(
            eps_actual=2.01,
            revenue_actual=111.2e9,
            free_cash_flow=26.7e9,
            gross_margin=49.3,
        ),
        sources=[
            SourceRef(
                source_id="S1",
                source_type="transcript",
                label="Transcript - StockAnalysis",
                url="https://stockanalysis.com/stocks/aapl/earnings-call-transcripts/q2-2026/",
            )
        ],
        generated_at=generated_at,
    )
    assert dq.transcript_freshness == generated_at
    assert dq.transcript_source_label == "Earnings Call Transcript"


def test_deep_dive_prefers_canonical_result_forward_pe_over_stale_snapshot(monkeypatch):
    monkeypatch.setattr(
        "backend.pipeline._extract_quarterly_comparison",
        lambda _ticker: {"pe_forward": 32.82},
    )
    result = SimpleNamespace(
        ticker="AAPL",
        financials=None,
        valuation=SimpleNamespace(pe_forward=31.14, pe_current=37.80, peg_ratio=2.65),
    )

    metrics = _deep_dive_metrics(result, {"ticker": "AAPL", "financials": {}})

    assert metrics.pe_forward == 31.14
    assert metrics.peg_ratio == 2.65


def test_deep_dive_reads_canonical_top_level_peg_when_result_omits_it(monkeypatch):
    monkeypatch.setattr(
        "backend.pipeline._extract_quarterly_comparison",
        lambda _ticker: {"pe_forward": 32.82},
    )
    result = SimpleNamespace(
        ticker="AAPL",
        financials=None,
        valuation=SimpleNamespace(pe_forward=31.14, pe_current=37.80, peg_ratio=None),
    )

    metrics = _deep_dive_metrics(
        result,
        {"ticker": "AAPL", "peg_ratio": 2.65, "financials": {}},
    )

    assert metrics.peg_ratio == 2.65


def test_provider_peg_is_used_before_mixing_trailing_growth_bases():
    metrics = FinancialMetrics(peg_ratio=2.65)

    context = _build_valuation_context(
        yf_info={
            "pegRatio": 2.65,
            "trailingPE": 37.80,
            "forwardPE": 32.82,
            "earningsGrowth": 0.216,
        },
        metrics=metrics,
        generated_at="2026-07-12T13:25:39Z",
    )

    assert context.peg_signal == 2.65
    assert context.peg_signal_label == "Expensive (>2x)"
    assert "provider" in context.peg_signal_detail.lower()


def test_raw_provider_fcf_is_not_labeled_as_canonical_ttm_yield():
    context = _build_valuation_context(
        yf_info={
            "marketCap": 4_630_000_000_000,
            "freeCashflow": 101_000_000_000,
            "pegRatio": 2.65,
            "priceToSalesTrailing12Months": 10.3,
            "enterpriseToEbitda": 29.2,
            "revenueGrowth": 0.166,
        },
        metrics=FinancialMetrics(peg_ratio=2.65),
        generated_at="2026-07-12T17:45:15Z",
    )

    assert context.pfcf_vs_growth_signal is None
    assert context.fcf_yield_signal is None
    assert "FCF Yield" not in (context.valuation_support or "")


def test_structured_valuation_uses_same_provider_peg_as_context_and_ui():
    report = build_earnings_deep_dive_report(
        ticker="AAPL",
        company="Apple Inc.",
        quarter="FY2026 Q2",
        language="en",
        metrics=FinancialMetrics(
            pe_trailing=37.80,
            pe_forward=31.14,
            peg_ratio=2.65,
        ),
        yf_info={
            "pegRatio": 2.55,
            "trailingPE": 38.17,
            "forwardPE": 32.82,
            "earningsGrowth": 0.218,
        },
    )

    assert report.valuation.peg_ratio == 2.65
    assert report.valuation_context.peg_signal == 2.65


def test_data_sensitive_sections_replace_unsourced_llm_claims():
    metrics = FinancialMetrics(roe=0.012, roic=0.641, net_debt=39.14e9)

    capital = _ensure_section_commentary(
        "en",
        "AAPL",
        "Capital Efficiency",
        metrics,
        ["ROIC is 60.0%; net cash is not supplied and ROA is undisclosed."],
    )
    segments = _ensure_section_commentary(
        "en",
        "AAPL",
        "Segments",
        metrics,
        ["iPhone revenue was $99B and Services was $88B."],
    )
    forward = _ensure_section_commentary(
        "en",
        "AAPL",
        "Forward P/E",
        metrics,
        ["Forward EPS is 7.77 because quarterly EPS 1.94 is multiplied by four."],
    )

    joined = " ".join([*capital, *segments, *forward])
    assert "60.0%" not in joined
    assert "net cash is not supplied" not in joined
    assert "$99B" not in joined
    assert "$88B" not in joined
    assert "multiplied by four" not in joined
    assert "7.77" not in joined


def test_concise_sections_use_one_short_table_backed_commentary_block():
    metrics = FinancialMetrics(
        eps_actual=2.01,
        eps_estimate=1.94,
        revenue_actual=111.2e9,
        revenue_yoy=16.6,
        gross_margin=49.3,
        operating_margin=32.3,
    )
    verbose = [
        "word " * 140,
        "second " * 10,
    ]

    eps = _ensure_section_commentary("en", "AAPL", "EPS & Revenue", metrics, verbose)
    operating = _ensure_section_commentary("en", "AAPL", "Operating Metrics", metrics, verbose)

    assert len(eps) == 1
    assert len(operating) == 1
    assert len(operating[0].split()) <= 120


def test_guidance_ignores_llm_tables_that_relabel_current_actuals_as_guidance():
    metrics = FinancialMetrics(
        revenue_actual=111.2e9,
        guidance="No forward revenue guidance disclosed.",
    )
    report = build_earnings_deep_dive_report(
        ticker="AAPL",
        company="Apple Inc.",
        quarter="FY2026 Q2",
        language="en",
        metrics=metrics,
        section_analysis={
            "Guidance": (
                "| Metric | Guidance | QoQ | Medium-term Signal | Source |\n"
                "|---|---|---|---|---|\n"
                "| Revenue | $111.2 billion March quarter actual | — | strong | transcript |\n\n"
                "The current quarter actual proves guidance was strong."
            )
        },
    )

    guidance = _section(report, "Guidance")
    rendered = " ".join(
        str(cell)
        for row in guidance.table.rows
        for cell in row.cells
    ) + " " + " ".join(guidance.analysis)
    assert "$111.2 billion March quarter actual" not in rendered
    assert "current quarter actual proves guidance" not in rendered.lower()
    assert "No forward revenue guidance disclosed" in rendered


def test_peer_summary_understands_premium_and_discount_labels():
    labels = _compute_peer_labels(
        {
            "pe_ttm": {"status": "available", "label": "pe_ttm trades at a premium vs peers"},
            "pe_forward": {"status": "available", "label": "pe_forward trades at a premium vs peers"},
            "peg_ratio": {"status": "available", "label": "peg_ratio trades at a discount vs peers"},
        }
    )

    assert labels["val_label"] == "Above Peer Median (2/3)"


def test_configured_but_unused_finnhub_is_not_listed_as_a_report_source(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "configured-but-unused")

    report = build_earnings_deep_dive_report(
        ticker="AAPL",
        company="Apple Inc.",
        quarter="FY2026 Q2",
        language="en",
        metrics=FinancialMetrics(eps_actual=2.01, revenue_actual=111.2e9),
    )

    assert all(source.source_type != "finnhub" for source in report.sources)


def test_pdf_methodology_does_not_claim_an_unused_finnhub_source():
    source = (
        Path(__file__).resolve().parents[1]
        / "backend"
        / "earnings_deep_dive"
        / "pdf_renderer.py"
    ).read_text(encoding="utf-8")

    assert "via yfinance/Finnhub" not in source


def test_pipeline_passes_canonical_scoring_into_both_report_models():
    source = (
        Path(__file__).resolve().parents[1] / "backend" / "pipeline.py"
    ).read_text(encoding="utf-8")

    assert source.count('scoring=getattr(result, "scoring", None)') >= 2


def test_normalized_markdown_matches_the_content_rendered_in_the_pdf(tmp_path):
    report = build_earnings_deep_dive_report(
        ticker="AAPL",
        company="Apple Inc.",
        quarter="FY2026 Q2",
        language="en",
        metrics=FinancialMetrics(
            eps_actual=2.01,
            eps_estimate=1.94,
            revenue_actual=111.2e9,
            revenue_yoy=16.6,
        ),
        section_analysis={"EPS & Revenue": "raw-llm-word " * 300},
    )

    markdown = render_report_markdown(report)

    assert markdown.startswith("# Earnings Call Deep-Dive")
    assert "## EPS & Revenue" in markdown
    assert "## Highlights & Lowlights" in markdown
    assert "raw-llm-word" not in markdown
    assert "| Metric |" in markdown
    assert "## Sources" in markdown
    eps_body = markdown.split("## EPS & Revenue", 1)[1].split("## Highlights & Lowlights", 1)[0]
    assert "One-line summary" not in eps_body
    markdown_path = tmp_path / "earnings_deep_dive.md"
    markdown_path.write_text(markdown, encoding="utf-8")
    _, issues = validate_deep_dive(str(markdown_path))
    target_issues = [
        issue for issue in issues
        if "Highlights & Lowlights" in issue or "EDP-007" in issue or "EDP-009" in issue
    ]
    assert target_issues == []


def test_pipeline_persists_normalized_markdown_before_terminal_validation():
    source = (
        Path(__file__).resolve().parents[1] / "backend" / "pipeline.py"
    ).read_text(encoding="utf-8")

    assert "render_report_markdown(en_report_model)" in source
