"""Map sourced earnings metrics into the structured PDF render model."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import re

from backend.earnings_deep_dive.report_model import (
    EarningsDeepDiveReport,
    RenderedSection,
    RenderedTable,
    RenderedTableRow,
    SourceRef,
)
from backend.earnings_deep_dive.schemas import FinancialMetrics
from backend.earnings_deep_dive.template import TemplateLanguage, get_earnings_template


MISSING = "データ未取得"
MISSING_EN = "Not available"
NOT_DISCLOSED = "開示なし"
NOT_DISCLOSED_EN = "Not disclosed"
NOT_APPLICABLE = "該当なし"
NOT_APPLICABLE_EN = "N/A"
NOT_CALCULABLE = "計算不可"
NOT_CALCULABLE_EN = "Not calculable"


def _language(value: str) -> TemplateLanguage:
    return "jp" if value in ("jp", "ja") else "en"


def _metric_url(metrics: FinancialMetrics, *keys: str) -> str | None:
    extra = getattr(metrics, "model_extra", {}) or {}
    for key in keys:
        value = getattr(metrics, key, None)
        if value is None:
            value = extra.get(key)
        if isinstance(value, str) and value.strip().startswith(("http://", "https://")):
            return value.strip()
    return None


def _seeking_alpha_transcripts_url(ticker: str) -> str:
    return f"https://seekingalpha.com/symbol/{ticker.strip().upper()}/earnings/transcripts"


def _metric_text(metrics: FinancialMetrics, *keys: str) -> str | None:
    extra = getattr(metrics, "model_extra", {}) or {}
    for key in keys:
        value = getattr(metrics, key, None)
        if value is None:
            value = extra.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _has(value: Any) -> bool:
    return value is not None and value != ""


def _source(*values: Any) -> str:
    return "会社開示 / 計算ベース" if any(_has(value) for value in values) else MISSING


def _money(value: Any) -> str:
    if not _has(value):
        return MISSING
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    if amount >= 1_000_000_000_000:
        return f"{sign}${amount / 1_000_000_000_000:.2f}T"
    if amount >= 1_000_000_000:
        return f"{sign}${amount / 1_000_000_000:.1f}B"
    if amount >= 1_000_000:
        return f"{sign}${amount / 1_000_000:.1f}M"
    return f"{sign}${amount:,.0f}"


def _eps(value: Any) -> str:
    if not _has(value):
        return MISSING
    try:
        return f"${float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _pct(value: Any) -> str:
    if not _has(value):
        return MISSING
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number) <= 1:
        number *= 100
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.1f}%"


def _multiple(value: Any) -> str:
    if not _has(value):
        return MISSING
    try:
        return f"{float(value):.2f}x"
    except (TypeError, ValueError):
        return str(value)


def _yoy_pct(value: Any) -> str:
    """Format a YoY percentage value that is already in percentage points (e.g., -4.4, 9.5)."""
    if not _has(value):
        return MISSING
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.1f}%"


def _yoy_comment(value: Any) -> str:
    if not _has(value):
        return MISSING
    try:
        number = float(value)
    except (TypeError, ValueError):
        return MISSING
    if number > 0:
        return "improvement"
    if number < 0:
        return "decline"
    return "flat"


def _variance(actual: Any, estimate: Any, explicit: Any = None) -> str:
    if _has(explicit):
        return _pct(explicit)
    if not (_has(actual) and _has(estimate)):
        return MISSING
    try:
        actual_number = float(actual)
        estimate_number = float(estimate)
    except (TypeError, ValueError):
        return MISSING
    if estimate_number == 0:
        return NOT_CALCULABLE
    return _pct((actual_number - estimate_number) / abs(estimate_number))


def _clean_markdown_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().strip("`")).strip()


def _is_markdown_separator(cells: list[str]) -> bool:
    clean_cells = [cell.strip() for cell in cells if cell.strip()]
    return bool(clean_cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in clean_cells)


def _extract_markdown_table(markdown: str, expected_columns: tuple[str, ...]) -> RenderedTable | None:
    lines = [line.strip() for line in markdown.splitlines() if line.strip().startswith("|")]
    if len(lines) < 3:
        return None

    for index in range(len(lines) - 2):
        header = [_clean_markdown_cell(cell) for cell in lines[index].strip("|").split("|")]
        separator = [_clean_markdown_cell(cell) for cell in lines[index + 1].strip("|").split("|")]
        if len(header) < 2 or not _is_markdown_separator(separator):
            continue

        rows: list[RenderedTableRow] = []
        for raw in lines[index + 2:]:
            cells = [_clean_markdown_cell(cell) for cell in raw.strip("|").split("|")]
            if len(cells) != len(header):
                break
            if _is_markdown_separator(cells):
                continue
            rows.append(RenderedTableRow(label=cells[0], cells=cells[1:]))

        if rows:
            return RenderedTable(columns=header or list(expected_columns), rows=rows)

    return None


def _analysis_without_table(markdown: str) -> str:
    kept: list[str] = []
    in_table = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            in_table = True
            continue
        if in_table and not stripped:
            in_table = False
            continue
        if stripped.startswith("## "):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def _extract_segment_rows(metrics: FinancialMetrics, labels: tuple[str, ...]) -> list[list[str]]:
    rows: list[list[str]] = []
    segments = metrics.segments if isinstance(metrics.segments, dict) else {}
    segment_items = list(segments.items())[: len(labels)]

    for index, row_label in enumerate(labels):
        if index >= len(segment_items):
            rows.append([row_label, MISSING, MISSING, MISSING, MISSING])
            continue

        name, raw = segment_items[index]
        data = raw if isinstance(raw, dict) else {}
        revenue = data.get("revenue") if isinstance(data, dict) else None
        yoy = data.get("yoy") if isinstance(data, dict) else None
        driver = data.get("driver") if isinstance(data, dict) else None
        rows.append([
            str(name) if name else row_label,
            _money(revenue),
            _pct(yoy),
            str(driver) if _has(driver) else MISSING,
            _source(raw),
        ])
    return rows


def _rows_for_section(section_key: str, row_labels: tuple[str, ...], metrics: FinancialMetrics) -> list[list[str]]:
    if section_key == "EPS & Revenue":
        return [
            [
                row_labels[0],
                _eps(metrics.eps_estimate),
                _eps(metrics.eps_actual),
                _variance(metrics.eps_actual, metrics.eps_estimate, getattr(metrics, "eps_vs_estimate", None)),
                _yoy_pct(getattr(metrics, "eps_yoy", None)),
                _source(metrics.eps_estimate, metrics.eps_actual, getattr(metrics, "eps_vs_estimate", None), getattr(metrics, "eps_yoy", None)),
            ],
            [
                row_labels[1],
                _money(getattr(metrics, "revenue_estimate", None)),
                _money(getattr(metrics, "revenue_actual", None)),
                _variance(getattr(metrics, "revenue_actual", None), getattr(metrics, "revenue_estimate", None)),
                _yoy_pct(getattr(metrics, "revenue_yoy", None)),
                _source(getattr(metrics, "revenue_estimate", None), getattr(metrics, "revenue_actual", None), getattr(metrics, "revenue_yoy", None)),
            ],
        ]

    if section_key == "Highlights":
        return [
            [row_labels[0], MISSING, MISSING, MISSING, MISSING],
            [row_labels[1], MISSING, MISSING, MISSING, MISSING],
            [row_labels[2], MISSING, MISSING, MISSING, MISSING],
        ]

    if section_key == "Operating Metrics":
        rows = (
            (
                row_labels[0],
                _money(metrics.gross_profit),
                _money(getattr(metrics, "gross_profit_prior_year", None)),
                _yoy_pct(getattr(metrics, "gross_profit_yoy", None)),
                metrics.gross_profit,
            ),
            (
                row_labels[1],
                _pct(metrics.gross_margin),
                _pct(getattr(metrics, "gross_margin_prior_year", None)),
                _yoy_pct(getattr(metrics, "gross_margin_yoy", None)),
                metrics.gross_margin,
            ),
            (
                row_labels[2],
                _money(metrics.opex),
                _money(getattr(metrics, "opex_prior_year", None)),
                _yoy_pct(getattr(metrics, "opex_yoy", None)),
                metrics.opex,
            ),
            (
                row_labels[3],
                _money(metrics.operating_income),
                _money(getattr(metrics, "operating_income_prior_year", None)),
                _yoy_pct(getattr(metrics, "operating_income_yoy", None)),
                metrics.operating_income,
            ),
            (
                row_labels[4],
                _pct(metrics.operating_margin),
                _pct(getattr(metrics, "operating_margin_prior_year", None)),
                _yoy_pct(getattr(metrics, "operating_margin_yoy", None)),
                metrics.operating_margin,
            ),
            (
                row_labels[5],
                _money(getattr(metrics, "net_income_quarterly", None)),
                _money(getattr(metrics, "net_income_quarterly_prior_year", None)),
                _yoy_pct(getattr(metrics, "net_income_yoy", None)),
                getattr(metrics, "net_income_quarterly", None),
            ),
        )
        return [[label, value, prior, yoy, _source(raw)] for label, value, prior, yoy, raw in rows]

    if section_key == "Cash Flow":
        def cash_flow_quality() -> str:
            if not (_has(metrics.free_cash_flow) and _has(metrics.operating_cash_flow)):
                return MISSING
            try:
                operating_cash_flow = float(metrics.operating_cash_flow)
                ratio = float(metrics.free_cash_flow) / operating_cash_flow if operating_cash_flow else None
            except (TypeError, ValueError):
                return MISSING
            if ratio is None:
                return MISSING
            if ratio > 0.8:
                return "good"
            if ratio >= 0.5:
                return "watch"
            return "weak"

        quality = cash_flow_quality()
        rows = (
            (
                row_labels[0],
                _money(metrics.operating_cash_flow),
                _money(getattr(metrics, "operating_cash_flow_prior_year", None)),
                _yoy_pct(getattr(metrics, "operating_cash_flow_yoy", None)),
                MISSING,
                metrics.operating_cash_flow,
            ),
            (
                row_labels[1],
                _money(metrics.capex),
                _money(getattr(metrics, "capex_prior_year", None)),
                _yoy_pct(getattr(metrics, "capex_yoy", None)),
                MISSING,
                metrics.capex,
            ),
            (
                row_labels[2],
                _money(metrics.free_cash_flow),
                _money(getattr(metrics, "free_cash_flow_prior_year", None)),
                _yoy_pct(getattr(metrics, "free_cash_flow_yoy", None)),
                quality,
                metrics.free_cash_flow,
            ),
            (
                row_labels[3],
                _money(metrics.net_debt),
                _money(getattr(metrics, "net_debt_prior_year", None)),
                _yoy_pct(getattr(metrics, "net_debt_yoy", None)),
                MISSING,
                metrics.net_debt,
            ),
        )
        return [[label, value, prior, yoy, q, _source(raw)] for label, value, prior, yoy, q, raw in rows]

    if section_key == "Capital Efficiency":
        rows = (
            (
                row_labels[0],
                _pct(metrics.roe),
                _pct(getattr(metrics, "roe_prior_year", None)),
                _yoy_pct(getattr(metrics, "roe_yoy", None)),
                _yoy_comment(getattr(metrics, "roe_yoy", None)),
                metrics.roe,
            ),
            (
                row_labels[1],
                _pct(metrics.rotce),
                _pct(getattr(metrics, "rotce_prior_year", None)),
                _yoy_pct(getattr(metrics, "rotce_yoy", None)),
                _yoy_comment(getattr(metrics, "rotce_yoy", None)),
                metrics.rotce,
            ),
            (
                row_labels[2],
                _pct(metrics.roa),
                _pct(getattr(metrics, "roa_prior_year", None)),
                _yoy_pct(getattr(metrics, "roa_yoy", None)),
                _yoy_comment(getattr(metrics, "roa_yoy", None)),
                metrics.roa,
            ),
            (
                row_labels[3],
                _pct(metrics.roic),
                _pct(getattr(metrics, "roic_prior_year", None)),
                _yoy_pct(getattr(metrics, "roic_yoy", None)),
                _yoy_comment(getattr(metrics, "roic_yoy", None)),
                metrics.roic,
            ),
            (
                row_labels[4],
                _money(metrics.buybacks),
                _money(getattr(metrics, "buybacks_prior_year", None)),
                _yoy_pct(getattr(metrics, "buybacks_yoy", None)),
                _yoy_comment(getattr(metrics, "buybacks_yoy", None)),
                metrics.buybacks,
            ),
            (
                row_labels[5],
                _money(metrics.dividends),
                _money(getattr(metrics, "dividends_prior_year", None)),
                _yoy_pct(getattr(metrics, "dividends_yoy", None)),
                _yoy_comment(getattr(metrics, "dividends_yoy", None)),
                metrics.dividends,
            ),
        )
        result = [[label, value, prior, yoy, comment, _source(raw)] for label, value, prior, yoy, comment, raw in rows]
        # If ALL metrics are unavailable (Finnhub free tier limitation), show 1 informative row
        if all(not _has(raw) for _, _, _, _, _, raw in rows):
            return [["Capital Efficiency metrics", "Finnhub free tier limit", MISSING, MISSING, MISSING, MISSING]]
        return result

    if section_key == "Segments":
        return _extract_segment_rows(metrics, row_labels)

    if section_key == "Forward P/E":
        trailing_pe = getattr(metrics, "pe_trailing", None)
        if trailing_pe is None:
            trailing_pe = getattr(metrics, "pe_current", None)
        return [
            [row_labels[0], _multiple(metrics.pe_forward), _multiple(trailing_pe), MISSING, _source(metrics.pe_forward)],
            [row_labels[1], MISSING, MISSING, MISSING, MISSING],
        ]

    if section_key == "Backlog":
        backlog_value = _money(metrics.backlog) if _has(metrics.backlog) else NOT_APPLICABLE
        backlog_source = _source(metrics.backlog) if _has(metrics.backlog) else "事業特性 / 開示資料"
        return [
            [row_labels[0], backlog_value, MISSING, "受注残が主要KPIでない場合は該当なし", backlog_source],
            [row_labels[1], NOT_DISCLOSED if _has(metrics.backlog) else NOT_APPLICABLE, MISSING, MISSING, backlog_source],
        ]

    if section_key == "Guidance":
        guidance = metrics.guidance if _has(metrics.guidance) else MISSING
        guidance_source = _source(metrics.guidance)
        rows = [
            [row_labels[0], guidance, MISSING, MISSING, guidance_source],
            [row_labels[1], MISSING, MISSING, MISSING, MISSING],
            [row_labels[2], MISSING, MISSING, MISSING, MISSING],
        ]
        # Filter out rows with no data at all (common with Finnhub free tier)
        return [r for r in rows if r[1] != MISSING] if len([r for r in rows if r[1] != MISSING]) > 0 else rows[:1]

    if section_key == "Verdict":
        return [[label, MISSING, MISSING, MISSING, MISSING] for label in row_labels]

    return [[label, *([MISSING] * 4)] for label in row_labels]


def _summary(language: TemplateLanguage, ticker: str, section_key: str, metrics: FinancialMetrics) -> str:
    revenue = _money(metrics.revenue_actual)
    revenue_yoy = _pct(metrics.revenue_yoy)
    eps = _eps(metrics.eps_actual)
    fcf = _money(metrics.free_cash_flow)
    pe = _multiple(metrics.pe_forward)

    if language == "jp":
        summaries = {
            "EPS & Revenue": f"👉 EPSは{eps}、売上高は{revenue}。予想比と前年比の両方を見て、成長の質を判断する局面です。",
            "Highlights": "👉 良い点と懸念点を分けて見ると、数字で確認できる成長が最重要です。",
            "Operating Metrics": f"👉 売上高は{revenue}、前年比は{revenue_yoy}。利益率の変化が次の評価ポイントです。",
            "Cash Flow": f"👉 FCFは{fcf}。利益が現金に変わっているかを最優先で確認します。",
            "Capital Efficiency": "👉 ROE/ROICは資本効率を見る指標です。高い数値でもレバレッジや自社株買いの影響を分けて評価します。",
            "Segments": "👉 どのセグメントが成長を支えているかを見ると、次の四半期の注目点が見えます。",
            "Forward P/E": f"👉 予想PERは{pe}。成長率で正当化できるかが投資判断の分かれ目です。",
            "Backlog": "👉 受注残は事業によって重要度が違います。該当なし・開示なしの場合は無理に評価しません。",
            "Guidance": "👉 ガイダンスは次の期待値です。売上、利益率、EPSを分けて確認します。",
            "Verdict": "👉 最終判断は、成長率・利益率・キャッシュ創出・バリュエーションのバランスで見ます。",
        }
        return summaries.get(section_key, f"👉 {ticker}の決算は、確認できる数字と未開示項目を分けて評価します。")

    summaries = {
        "EPS & Revenue": f"{ticker} reported EPS of {eps} and revenue of {revenue}; the key investor question is whether the beat/miss is broad-based or one-off.",
        "Highlights": f"{ticker}'s quarter should be read through specific positives and risks, each tied to reported numbers or management commentary.",
        "Operating Metrics": f"Revenue was {revenue} with YoY growth of {revenue_yoy}; margin direction determines the quality of the growth.",
        "Cash Flow": f"Free cash flow was {fcf}; cash conversion and capex intensity show whether earnings are translating into owner cash.",
        "Capital Efficiency": "ROE, ROIC, and related returns indicate whether growth is creating value or simply consuming capital.",
        "Segments": "Segment trends identify which business lines are driving the quarter and where risk is concentrated.",
        "Forward P/E": f"Forward P/E is {pe}; valuation only works if growth and margin durability support it.",
        "Backlog": "Backlog is evaluated only when economically relevant and disclosed; otherwise it is marked not applicable or not disclosed.",
        "Guidance": "Guidance matters because it resets expectations for revenue, margin, EPS, and medium-term demand.",
        "Verdict": "The investor verdict weighs earnings quality, growth durability, cash generation, and valuation risk together.",
    }
    return summaries.get(section_key, f"{ticker}'s section conclusion is based on concrete reported metrics and source traceability.")


def _default_highlights_analysis(language: TemplateLanguage, metrics: FinancialMetrics) -> list[str]:
    revenue = _money(metrics.revenue_actual)
    revenue_yoy = _pct(metrics.revenue_yoy)
    fcf = _money(metrics.free_cash_flow)
    margin = _pct(metrics.operating_margin)
    if language == "jp":
        return [
            "\n".join(
                [
                    "🌟 ハイライト（良かった点）",
                    "",
                    "① 売上成長の確認",
                    f"● 売上高: {revenue} / 前年比: {revenue_yoy}",
                    "👉 成長が数字で確認できる場合、投資家は持続性と利益率への波及を見ます。",
                    "",
                    "② キャッシュ創出力",
                    f"● フリーキャッシュフロー: {fcf}",
                    "👉 利益が現金に変わっているかは、決算の質を見る重要ポイントです。",
                    "",
                    "⚠️ ローライト（懸念点）",
                    "",
                    "① 利益率の確認",
                    f"● 営業利益率: {margin}",
                    "👉 売上が伸びても利益率が弱い場合、株価評価は伸びにくくなります。",
                    "",
                    "② 未開示データ",
                    "● 未取得または未開示の項目は表で明示しています。",
                    "👉 空欄でごまかさず、次に確認すべき資料を明確にします。",
                    "",
                    "🧠 総合評価（Namiさん向け）",
                    "👉 まず売上、利益率、キャッシュの3点を見れば、この決算が本当に強いか判断しやすいです。",
                    "",
                    "🎯 投資視点の一言",
                    "👉 良い決算でも、次のガイダンスとバリュエーションが合わなければ追いかけすぎに注意です。",
                ]
            )
        ]
    return [
        "\n".join(
            [
                "Highlights / Lowlights",
                f"① Revenue signal: {revenue} with YoY growth of {revenue_yoy}.",
                f"● Free cash flow: {fcf}.",
                "👉 Investor read: focus on whether growth converts into durable cash and margin expansion.",
            ]
        )
    ]


def build_earnings_deep_dive_report(
    *,
    ticker: str,
    company: str | None,
    quarter: str,
    metrics: FinancialMetrics,
    transcript_url: str | None = None,
    language: str = "en",
    section_analysis: dict[str, str] | None = None,
    generated_at: str | None = None,
) -> EarningsDeepDiveReport:
    """Build the deterministic report model used by the PDF renderer."""
    report_language = _language(language)
    ticker_clean = ticker.strip().upper()
    company_name = company.strip() if isinstance(company, str) and company.strip() else ticker_clean
    template = get_earnings_template(report_language)
    analysis_by_key = section_analysis or {}

    sections: list[RenderedSection] = []
    for section in template:
        analysis_text = analysis_by_key.get(section.key) or analysis_by_key.get(section.title)
        codex_table = _extract_markdown_table(analysis_text, section.table_columns) if analysis_text else None
        if codex_table:
            table = codex_table
            analysis_items = [text for text in (_analysis_without_table(analysis_text),) if text]
        else:
            rows = _rows_for_section(section.key, section.table_rows, metrics)
            table = RenderedTable(
                columns=list(section.table_columns),
                rows=[RenderedTableRow(label=str(row[0]), cells=[str(cell) for cell in row[1:]]) for row in rows],
            )
            if analysis_text:
                analysis_items = [analysis_text]
            elif section.key == "Highlights":
                analysis_items = _default_highlights_analysis(report_language, metrics)
            else:
                analysis_items = []
        sections.append(
            RenderedSection(
                key=section.key,
                title=section.title,
                question=section.question,
                table=table,
                analysis=analysis_items,
                summary_label=section.summary_label,
                summary=_summary(report_language, ticker_clean, section.key, metrics),
            )
        )

    investor_relations_url = _metric_url(
        metrics,
        "investor_relations_url",
        "investors_url",
        "ir_url",
    )
    company_website_url = _metric_url(metrics, "company_website", "website", "weburl", "official_website")
    transcript_source = _metric_text(metrics, "transcript_source", "transcript_provider") or "Transcript"
    # Build transcript source entry — use the real source name and URL.
    # If no transcript was actually obtained, omit this source row entirely.
    sources = []
    if transcript_url or transcript_source not in ("Transcript", ""):
        transcript_label = f"Earnings Transcript — {transcript_source}"
        transcript_display_url = transcript_url or (
            f"https://seekingalpha.com/symbol/{ticker_clean}/earnings/transcripts"
            if "seeking alpha" in transcript_source.lower() else None
        )
        sources.append(SourceRef(
            label=transcript_label,
            url=transcript_display_url,
            note="Primary earnings transcript source" if transcript_display_url else MISSING,
        ))
    sources.append(SourceRef(
        label="Official Investor Relations",
        url=investor_relations_url,
        note="Press release / earnings presentation source" if investor_relations_url else MISSING,
    ))
    if company_website_url and company_website_url != investor_relations_url:
        sources.append(SourceRef(label="Official Website", url=company_website_url))
    press_release_url = _metric_url(metrics, "press_release_url")
    if press_release_url:
        sources.append(SourceRef(label="Press Release", url=press_release_url))
    presentation_url = _metric_url(metrics, "earnings_presentation_url", "presentation_url")
    if presentation_url:
        sources.append(SourceRef(label="Earnings Call Presentation", url=presentation_url))

    return EarningsDeepDiveReport(
        ticker=ticker_clean,
        company=company_name,
        quarter=quarter.strip() if quarter else "latest quarter",
        language=report_language,
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
        title=f"{company_name} ({ticker_clean}) - Earnings Deep-Dive",
        sections=sections,
        sources=sources,
    )
