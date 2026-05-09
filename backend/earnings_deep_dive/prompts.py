"""PDF-aligned prompt templates for earnings call deep-dive sections."""
from typing import Any, Callable, Dict, List


class SectionName(str):
    """Canonical section key that renders as the report heading."""

    def __new__(cls, canonical: str, title: str) -> "SectionName":
        obj = str.__new__(cls, canonical)
        obj.title = title
        return obj

    def __str__(self) -> str:
        return self.title

    def __repr__(self) -> str:
        return repr(self.title)

    def __contains__(self, item: object) -> bool:
        return item in self.title

    def translate(self, table: Any) -> str:
        return self.title.translate(table)


SECTION_TITLES: Dict[str, str] = {
    "EPS & Revenue": "📊 EPS & Revenue",
    "Highlights": "🌟 Highlights & ⚠️ Lowlights",
    "Operating Metrics": "🧠 Operating Metrics",
    "Cash Flow": "💰 Cash Flow",
    "Capital Efficiency": "🎯 Capital Efficiency",
    "Segments": "🧩 Segments",
    "Forward P/E": "📈 Forward P/E",
    "Backlog": "📦 Backlog Quality",
    "Guidance": "🔮 Guidance",
    "Verdict": "🏆 Verdict",
}

SECTION_ORDER: List[str] = [
    SectionName("EPS & Revenue", SECTION_TITLES["EPS & Revenue"]),
    SectionName("Highlights", SECTION_TITLES["Highlights"]),
    SectionName("Operating Metrics", SECTION_TITLES["Operating Metrics"]),
    SectionName("Cash Flow", SECTION_TITLES["Cash Flow"]),
    SectionName("Capital Efficiency", SECTION_TITLES["Capital Efficiency"]),
    SectionName("Segments", SECTION_TITLES["Segments"]),
    SectionName("Forward P/E", SECTION_TITLES["Forward P/E"]),
    SectionName("Backlog", SECTION_TITLES["Backlog"]),
    SectionName("Guidance", SECTION_TITLES["Guidance"]),
    SectionName("Verdict", SECTION_TITLES["Verdict"]),
]

SECTION_KEYWORDS: Dict[str, List[str]] = {
    "EPS & Revenue": ["eps", "earnings per share", "revenue", "sales", "estimate", "actual"],
    "Highlights": ["highlight", "record", "growth", "demand", "margin", "risk", "concern"],
    "Operating Metrics": ["operating", "gross profit", "gross margin", "opex", "net income", "margin"],
    "Cash Flow": ["cash flow", "operating cash", "free cash flow", "capex", "buyback", "dividend"],
    "Capital Efficiency": ["roe", "rote", "rotce", "roa", "roic", "return", "capital"],
    "Segments": ["segment", "division", "product", "category", "geography", "region"],
    "Forward P/E": ["valuation", "forward", "earnings", "multiple", "pe", "p/e"],
    "Backlog": ["backlog", "remaining performance", "bookings", "orders", "contract", "pipeline"],
    "Guidance": ["guidance", "outlook", "forecast", "next quarter", "full year", "medium term"],
    "Verdict": ["priority", "risk", "opportunity", "guidance", "demand", "margin", "cash"],
}

TABLE_SECTIONS = set(s for s in SECTION_ORDER if s[0] != "Backlog")  # Backlog is optional — not all companies report it

TABLE_REQUIREMENTS: Dict[str, str] = {
    "EPS & Revenue": "| Metric | Estimate | Actual | vs Estimate | YoY Change | Source |",
    "Highlights": "| Type | Number | Point | Evidence | Investor implication | Severity |",
    "Operating Metrics": "| Metric | Actual | Prior Year | YoY | Source |",
    "Cash Flow": "| Metric | Actual | Prior Year | YoY | Quality read-through | Source |",
    "Capital Efficiency": "| Metric | Value | Evaluation | Driver | Source |",
    "Segments": "| Segment / Region | Revenue / KPI | Prior Year | YoY | Mix / Risk | Source |",
    "Forward P/E": "| Metric | Current | Context | Growth Support | Source |",
    "Backlog": "| Backlog Dimension | Quantity / Coverage | Quality | Contract firmness | Source |",
    "Guidance": "| Metric | Guidance | QoQ | Medium-term Signal | Source |",
    "Verdict": "| Dimension | Positive evidence | Negative evidence | Net assessment | Source |",
}

SECTION_QUESTIONS: Dict[str, Dict[str, str]] = {
    "EPS & Revenue": {
        "en": (
            "Please summarize the estimated and actual figures for EPS (earnings per share) "
            "and revenue of {company} ({ticker}) for {quarter} in a table, including the "
            "variance versus estimates and the year-over-year change."
        ),
        "jp": "{company} ({ticker}) の{quarter}決算のEPS（1株当たり利益）と売上高の予想値、実績値、予想比、前年同期比をまとめて下さい。",
    },
    "Highlights": {
        "en": "What are the highlights and lowlights (key concerns) of this earnings report?",
        "jp": "今回の決算のハイライト、ローライトを教えてください。",
    },
    "Operating Metrics": {
        "en": (
            "How were operating income, operating margin, gross profit, gross margin, "
            "operating expenses, and net income? Please provide a summary of the key "
            "metrics first, followed by an explanation and analysis."
        ),
        "jp": "営業利益、営業利益率、粗利益、粗利益率、営業費用、純利益などは前年同期比と比べてどうでしたか？最初に指標の一覧を出して、その後説明・分析をしてください。",
    },
    "Cash Flow": {
        "en": "Please share any available figures for operating cash flow, CapEx, and free cash flow.",
        "jp": "営業キャッシュフロー、CapEx、フリーキャッシュフローの数値についてもわかることを教えてください。",
    },
    "Capital Efficiency": {
        "en": "How were ROE, ROTCE (ROTE), ROA, and ROIC?",
        "jp": "ROE / ROTCE（ROTE）/ ROA / ROICなどはどうでしたか？",
    },
    "Segments": {
        "en": "What were the results by segment?",
        "jp": "セグメント別の業績はどうでしたか？",
    },
    "Forward P/E": {
        "en": (
            "What is the forward P/E ratio for {company} ({ticker})? "
            "State the current multiple, compare it to the sector and historical range, "
            "and explain whether growth, margins, and cash flows justify this valuation level."
        ),
        "jp": "{company} ({ticker}) のForward P/Eはどうなっていますか？現在の倍率、セクターや過去との比較、成長・利益率・キャッシュフローがバリュエーションを正当化するか説明してください。",
    },
    "Backlog": {
        "en": (
            "How is the quality and quantity of the order backlog for {company} ({ticker})? "
            "If the company does not disclose a backlog (common for consumer/tech companies), "
            "state 'Not applicable' and explain why."
        ),
        "jp": "{company} ({ticker}) の受注残の質と量はどうですか？開示がない場合は「該当なし」と明記し、理由を説明してください。",
    },
    "Guidance": {
        "en": "What is the guidance for the upcoming quarters and beyond?",
        "jp": "来期以降のガイダンスをおしえてください。",
    },
    "Verdict": {
        "en": "What is the overall earnings verdict for Nami-san after weighing growth, margins, cash flow, valuation, backlog, and guidance?",
        "jp": "成長、利益率、キャッシュフロー、バリュエーション、バックログ、ガイダンスを踏まえて、Namiさん向けの総合評価を教えてください。",
    },
}

SECTION_FORMATS: Dict[str, str] = {
    "EPS & Revenue": """Required table:
{table_header}
|---|---|---|---|---|---|
| EPS | ... | ... | ... | ... | ... |
| Revenue | ... | ... | ... | ... | ... |

Required analysis format:
① EPS: beat/miss, YoY direction, and exact source.
② Revenue: beat/miss, YoY direction, and exact source.
③ Quality of the beat/miss: explain whether both top line and profit moved together.
👉 Namiさん向け解釈: explain in plain Japanese-investor terms whether this is a high-quality surprise or not.""",
    "Highlights": """Required table:
{table_header}
|---|---|---|---|---|---|
| 🌟 Highlight | ① | ... | ... | ... | Low / Medium / High |
| ⚠️ Lowlight | ① | ... | ... | ... | Low / Medium / High |

Required analysis format:
🌟 ハイライト（良かった点）
① ...
● Metric / transcript evidence
👉 Why it matters
② ...
③ ...

⚠️ ローライト（懸念点）
① ...
● Evidence and severity
👉 Investor concern
② ...
③ ...

🧠 総合評価（Namiさん向け）: grade the quarter in one concise line.
🎯 投資視点の一言: state the core takeaway without investment advice.""",
    "Operating Metrics": """Required table:
{table_header}
|---|---|---|---|---|
| Revenue | ... | ... | ... | ... |
| Gross Profit | ... | ... | ... | ... |
| Gross Margin | ... | ... | ... | ... |
| OpEx | ... | ... | ... | ... |
| Operating Income | ... | ... | ... | ... |
| Operating Margin | ... | ... | ... | ... |
| Net Income | ... | ... | ... | ... |

Required analysis format:
🧠 説明・分析
① Gross profit / gross margin: expansion or compression, with drivers.
② Operating income / operating margin: whether scale benefits offset OpEx.
③ OpEx and net income: cost investment, tax/other effects, and sustainability.
🎯 全体構造（超重要）: summarize the revenue growth x margins x cost structure.
🧩 Namiさん向けの本質理解: explain whether the earnings quality is high or fragile.
⚠️ 今後のチェックポイント: list the next 2 checks.""",
    "Cash Flow": """Required table:
{table_header}
|---|---|---|---|---|---|
| Operating Cash Flow (OCF) | ... | ... | ... | ... | ... |
| CapEx | ... | ... | ... | ... | ... |
| Free Cash Flow (FCF) | ... | ... | ... | ... | ... |

Required analysis format:
🧠 説明・分析
① Operating cash flow: cash earnings quality and working-capital effect.
② CapEx: whether investment intensity is rising or falling.
③ Free cash flow: conversion from earnings to cash and sustainability.
🎯 Cash structure（超重要）: compare cash generation versus reinvestment needs.
🧩 Namiさん向け解釈: explain whether the company creates cash efficiently or burns cash.
💰 Cash use: buybacks, dividends, debt paydown — state actual amounts.
⚠️ 注意点（Namiさん向け）: mention one-off working-capital or future investment risks.""",
    "Capital Efficiency": """Required table:
{table_header}
|---|---|---|---|---|
| ROE | ... | ... | ... | ... |
| ROTCE / ROTE | ... | ... | ... | ... |
| ROA | ... | ... | ... | ... |
| ROIC | ... | ... | ... | ... |

Required analysis format:
🧾 補足データ（計算ベース）: list net income, assets, equity, invested capital if available.
🧠 指標ごとの解説
① ROE: why high/low and whether buybacks distort it.
② ROTCE / ROTE and ROA: core efficiency and asset productivity.
③ ROIC: the most important capital-return read-through versus cost of capital.
🎯 総合評価（Namiさん向け）: state whether capital efficiency is excellent, normal, or weak.
⚠️ 注意点（かなり重要）: distinguish financial engineering from business-model strength.""",
    "Segments": """Required tables:
{table_header}
|---|---|---|---|---|---|
| Product / Category 1 | ... | ... | ... | ... | ... |
| Product / Category 2 | ... | ... | ... | ... | ... |

{table_header}
|---|---|---|---|---|---|
| Region 1 | ... | ... | ... | ... | ... |
| Region 2 | ... | ... | ... | ... | ... |

Required analysis format:
🧠 セグメント別の解説・分析
① Lead product/category segment: growth, mix, and driver.
② Profit engine or recurring segment: margin relevance and durability.
③ Stable / weak segments: recovery, maturity, or pressure.
🌍 地域別の重要ポイント
① Strongest region
② Emerging growth region
③ Mature-market stability or weakness
🎯 全体構造（超重要）: revenue mix and concentration.
🧩 Namiさん向け本質理解: short / medium / long-term segment thesis.
⚠️ 注意ポイント: concentration and future segment dependency.""",
    "Forward P/E": """Required table:
{table_header}
|---|---|---|---|---|
| Forward P/E | ... | Sector / history / peers | ... | ... |
| Forward EPS basis | ... | Consensus / company guide | ... | ... |
| Growth support | ... | Revenue / margin / guidance | ... | ... |

Required analysis format:
📈 Forward P/Eの確認
① Current multiple: state the value from supplied metrics.
② Comparison: sector, history, peers — use available context.
③ Justification: whether growth, margins, cash, backlog, or guidance support the multiple.
👉 Namiさん向け解釈: explain if valuation looks supported, stretched, or not assessable.
⚠️ 注意点: do not invent consensus numbers; mark missing data.""",
    "Backlog": """Required table:
{table_header}
|---|---|---|---|---|
| Quantity | ... | ... | ... | ... |
| Coverage | ... | ... | ... | ... |
| Quality | ... | ... | ... | ... |
| Conversion risk | ... | ... | ... | ... |

Required analysis format:
■ 結論: quantity and quality in one line.
■ ① 量（どれくらいあるのか）: backlog amount and quarters of coverage.
■ ② 質（ここがもっと重要）: firm commitments versus cancellable pipeline.
■ ③ なぜ質が高い/低いのか？: demand duration, customer commitment, supply constraints.
■ ④ ただし注意点（重要）: pricing, cancellation, coverage, and burn-down risk.
■ ⑤ バックログの“質”を一言でいうと: one direct phrase.
■ Namiさん向けの本質: explain what visibility changed and list next questions.""",
    "Guidance": """Required table:
{table_header}
|---|---|---|---|---|
| Revenue | ... | ... | ... | ... |
| Gross Margin | ... | ... | ... | ... |
| OpEx | ... | ... | ... | ... |
| EPS | ... | ... | ... | ... |
| Diluted Shares | ... | ... | ... | ... |

Required analysis format:
■ 来期ガイダンス: present the table first.
■ 一言でいうと: concise direction such as strong growth, high profitability, or cautious.
■ 分析（かなり重要）
① Revenue: acceleration/deceleration and demand drivers.
② Profitability: gross margin and OpEx implications.
③ EPS: QoQ / YoY direction.
④ Structural signals: customer mix, long-term contracts, pricing, product cycle, or macro.
■ 中期（来期以降）の示唆
① Revenue direction
② Margin direction
③ Stabilizing or risk factors
■ ただし注意点（かなり重要）: whether guidance is too strong, price dependent, or cyclical.
■ Namiさん向けの本質: what the guide means and what to monitor next.""",
    "Verdict": """Required table:
{table_header}
|---|---|---|---|---|
| Growth | ... | ... | ... | ... |
| Margins | ... | ... | ... | ... |
| Cash Flow | ... | ... | ... | ... |
| Capital Efficiency | ... | ... | ... | ... |
| Segments | ... | ... | ... | ... |
| Valuation / Forward P/E | ... | ... | ... | ... |
| Backlog / Guidance | ... | ... | ... | ... |

Required analysis format:
🏆 総合評価（Namiさん向け）
① What was strongest: growth, margins, cash, backlog, or guidance.
② What was weakest: costs, concentration, valuation, cyclicality, or missing data.
③ What matters next: the 2-3 monitor items for the next quarter.
🎯 投資視点の一言: summarize the thesis without making buy/sell advice.
⚠️ リスク: cite only sourced risks.
🧩 本質理解: explain the quality of the quarter in simple terms.""",
}

EN_SECTION_FORMATS: Dict[str, str] = {
    "EPS & Revenue": """Required table:
{table_header}
|---|---|---|---|---|---|
| EPS | ... | ... | ... | ... | ... |
| Revenue | ... | ... | ... | ... | ... |

Required analysis format:
① EPS: beat/miss, YoY direction, and exact source.
② Revenue: beat/miss, YoY direction, and exact source.
③ Quality of the beat/miss: explain whether both top line and profit moved together.
For Nami-san: explain in plain investor terms whether this is a high-quality surprise or not.
> One-line summary: [your one-line summary here]""",
    "Highlights": """Required table:
{table_header}
|---|---|---|---|---|---|
| 🌟 Highlight | ① | ... | ... | ... | Low / Medium / High |
| ⚠️ Lowlight | ① | ... | ... | ... | Low / Medium / High |

Required analysis format:
🌟 Highlights
① ...
* Metric / transcript evidence
* Why it matters
② ...
③ ...

⚠️ Lowlights
① ...
* Evidence and severity
* Investor concern
② ...
③ ...

Essential insight for Nami-san: grade the quarter in one concise line.
Investment takeaway: state the core takeaway without investment advice.
> One-line summary: [your one-line summary here]""",
    "Operating Metrics": """Required table:
{table_header}
|---|---|---|---|---|
| Revenue | ... | ... | ... | ... |
| Gross Profit | ... | ... | ... | ... |
| Gross Margin | ... | ... | ... | ... |
| OpEx | ... | ... | ... | ... |
| Operating Income | ... | ... | ... | ... |
| Operating Margin | ... | ... | ... | ... |
| Net Income | ... | ... | ... | ... |

Required analysis format:
🧠 Explanation and analysis
① Gross profit / gross margin: expansion or compression, with drivers.
② Operating income / operating margin: whether scale benefits offset OpEx.
③ OpEx and net income: cost investment, tax/other effects, and sustainability.
Operating structure: summarize revenue growth x margins x cost structure.
Essential insight for Nami-san: explain whether earnings quality is high or fragile.
Caution: list the next 2 checks.
> One-line summary: [your one-line summary here]""",
    "Cash Flow": """Required table:
{table_header}
|---|---|---|---|---|---|
| Operating Cash Flow (OCF) | ... | ... | ... | ... | ... |
| CapEx | ... | ... | ... | ... | ... |
| Free Cash Flow (FCF) | ... | ... | ... | ... | ... |

Required analysis format:
🧠 Explanation and analysis
① Operating cash flow: cash earnings quality and working-capital effect.
② CapEx: whether investment intensity is rising or falling.
③ Free cash flow: conversion from earnings to cash and sustainability.
Cash structure: compare cash generation versus reinvestment needs.
Essential insight for Nami-san: explain whether the company creates cash efficiently or burns cash.
💰 Cash use: buybacks, dividends, debt paydown — state actual amounts.
Caution for Nami-san: mention one-off working-capital or future investment risks.
> One-line summary: [your one-line summary here]""",
    "Capital Efficiency": """Required table:
{table_header}
|---|---|---|---|---|
| ROE | ... | ... | ... | ... |
| ROTCE / ROTE | ... | ... | ... | ... |
| ROA | ... | ... | ... | ... |
| ROIC | ... | ... | ... | ... |

Required analysis format:
Supporting calculation data: list net income, assets, equity, invested capital if available.
🧠 Metric-by-metric explanation
① ROE: why high/low and whether buybacks distort it.
② ROTCE / ROTE and ROA: core efficiency and asset productivity.
③ ROIC: the most important capital-return read-through versus cost of capital.
For Nami-san: state whether capital efficiency is excellent, normal, or weak.
Caution: distinguish financial engineering from business-model strength.
> One-line summary: [your one-line summary here]""",
    "Segments": """Required tables:
{table_header}
|---|---|---|---|---|---|
| Product / Category 1 | ... | ... | ... | ... | ... |
| Product / Category 2 | ... | ... | ... | ... | ... |

{table_header}
|---|---|---|---|---|---|
| Region 1 | ... | ... | ... | ... | ... |
| Region 2 | ... | ... | ... | ... | ... |

Required analysis format:
🧠 Segment explanation and analysis
① Lead product/category segment: growth, mix, and driver.
② Profit engine or recurring segment: margin relevance and durability.
③ Stable / weak segments: recovery, maturity, or pressure.
Regional points:
① Strongest region
② Emerging growth region
③ Mature-market stability or weakness
Overall structure: revenue mix and concentration.
Essential insight for Nami-san: short / medium / long-term segment thesis.
Caution: concentration and future segment dependency.
> One-line summary: [your one-line summary here]""",
    "Forward P/E": """Required table:
{table_header}
|---|---|---|---|---|
| Forward P/E | ... | Sector / history / peers | ... | ... |
| Forward EPS basis | ... | Consensus / company guide | ... | ... |
| Growth support | ... | Revenue / margin / guidance | ... | ... |

Required analysis format:
📈 Forward P/E check
① Current multiple: state the value from supplied metrics.
② Comparison: sector, history, peers — use available context.
③ Justification: whether growth, margins, cash, backlog, or guidance support the multiple.
For Nami-san: explain if valuation looks supported, stretched, or not assessable.
Caution: do not invent consensus numbers; mark missing data.
> One-line summary: [your one-line summary here]""",
    "Backlog": """Required table:
{table_header}
|---|---|---|---|---|
| Quantity | ... | ... | ... | ... |
| Coverage | ... | ... | ... | ... |
| Quality | ... | ... | ... | ... |
| Conversion risk | ... | ... | ... | ... |

Required analysis format:
Conclusion: quantity and quality in one line.
① Quantity: backlog amount and quarters of coverage.
② Quality: firm commitments versus cancellable pipeline.
③ Why quality is high/low: demand duration, customer commitment, supply constraints.
④ Caution: pricing, cancellation, coverage, and burn-down risk.
⑤ Backlog quality in one phrase.
Essential insight for Nami-san: explain what visibility changed and list next questions.
> One-line summary: [your one-line summary here]""",
    "Guidance": """Required table:
{table_header}
|---|---|---|---|---|
| Revenue | ... | ... | ... | ... |
| Gross Margin | ... | ... | ... | ... |
| OpEx | ... | ... | ... | ... |
| EPS | ... | ... | ... | ... |
| Diluted Shares | ... | ... | ... | ... |

Required analysis format:
Next-quarter guidance: present the table first.
In one line: concise direction such as strong growth, high profitability, or cautious.
Analysis:
① Revenue: acceleration/deceleration and demand drivers.
② Profitability: gross margin and OpEx implications.
③ EPS: QoQ / YoY direction.
④ Structural signals: customer mix, long-term contracts, pricing, product cycle, or macro.
Medium-term implications:
① Revenue direction
② Margin direction
③ Stabilizing or risk factors
Caution: whether guidance is too strong, price dependent, or cyclical.
Essential insight for Nami-san: what the guide means and what to monitor next.
> One-line summary: [your one-line summary here]""",
    "Verdict": """Required table:
{table_header}
|---|---|---|---|---|
| Strengths | ... | ... | ... | ... |
| Weaknesses | ... | ... | ... | ... |
| Opportunities | ... | ... | ... | ... |
| Risks | ... | ... | ... | ... |

Required analysis format:
🏆 Overall assessment for Nami-san
① What was strongest: growth, margins, cash, backlog, or guidance.
② What was weakest: costs, concentration, valuation, cyclicality, or missing data.
③ What matters next: the 2-3 monitor items for the next quarter.
Investment takeaway: summarize the thesis without making buy/sell advice.
Caution: cite only sourced risks.
Essential insight: explain the quality of the quarter in simple terms.
> One-line summary: [your one-line summary here]""",
}


def system_prompt(language: str, sector: str = "", industry: str = "") -> str:
    sector_line = ""
    if sector:
        sector_line = f" You specialize in the {sector} sector"
        if industry:
            sector_line += f" ({industry})"
        sector_line += "."

    sector_guidance = _sector_guidance(sector, industry)

    en_system = (
        f"You are a senior buy-side equity analyst writing an earnings deep-dive for Nami-san, "
        f"a fund manager who needs actionable, sector-specific insight.{sector_line}\n"
        f"{sector_guidance}\n\n"
        "THINK LIKE AN ANALYST — NOT A FORM FILLER:\n"
        "- Identify the 3-5 metrics that truly matter for THIS company in THIS sector. "
        "Do not mechanically list every metric in the supplied data.\n"
        "- When the company does NOT report a metric (e.g., backlog for Apple), "
        "say so clearly instead of forcing a table.\n"
        "- Adapt your analysis depth to what the transcript reveals.\n"
        "- Use markdown tables where they add clarity, with columns that make sense for the sector.\n\n"
        "STRUCTURE:\n"
        "- Start each section with ## Section Name\n"
        "- Use numbered analysis ①②③ for key points\n"
        "- Include a 'Nami-san takeaway' line\n"
        "- End with > One-line summary: [concise verdict]\n\n"
        "DATA RULES:\n"
        "- Every number must be sourced: (Transcript, CEO remarks) or (yfinance, quarterly data)\n"
        "- Never invent data. When a number is unavailable, explain WHY.\n"
        "- Do NOT use 'Not available' or 'Supplied metrics' as filler sources.\n"
        "- Write in ENGLISH only. No Japanese characters, no CJK."
    )

    jp_system = (
        f"あなたはバイサイドのシニアアナリストで、Namiさん向けに決算分析を書いています。{sector_line}\n"
        f"{sector_guidance}\n\n"
        "型にはまったフォーム記入ではなく、アナリストとして考えてください：\n"
        "- この企業・このセクターで本当に重要な3〜5の指標を特定してください。\n"
        "- 企業が指標を開示していない場合、「該当なし」と明確に述べてください。\n"
        "- 決算トランスクリプトで経営陣が強調しているテーマに合わせて分析の深さを調整。\n\n"
        "構造：## セクション名, ①②③, Namiさん向け解釈, > 一言まとめ\n\n"
        "データルール：すべての数字に出所を明記。数値が入手できない場合は理由を説明。\n"
        "埋め草（Not available/Supplied metrics）を使用しない。日本語で記述。"
    )

    if language == "en":
        return en_system
    return jp_system


def _sector_guidance(sector: str, industry: str) -> str:
    """Return sector-specific analysis guidance."""
    s = sector.lower() if sector else ""
    i = (industry or "").lower()
    if "technology" in s or "electronic" in s or "semiconductor" in i:
        return ("For tech/electronics: focus on product cycles, gross margins by segment, "
                "Services/software mix, installed base growth, supply chain constraints, R&D intensity.")
    if "financial" in s or "bank" in s:
        return ("For financials: focus on NIM, loan/deposit growth, credit quality, "
                "CET1 ratio, ROE/ROTCE, and rate sensitivity.")
    if "healthcare" in s or "pharma" in s or "biotech" in s:
        return ("For healthcare/pharma: focus on drug pipeline, patent cliffs, "
                "R&D efficiency, regulatory catalysts, pricing power.")
    if "consumer" in s or "retail" in s:
        return ("For consumer/retail: focus on same-store sales, e-commerce growth, "
                "inventory turns, gross margin, customer acquisition cost.")
    if "industrial" in s or "aerospace" in s or "defense" in s:
        return ("For industrials/aerospace/defense: focus on backlog/book-to-bill, "
                "operating leverage, aftermarket revenue mix, long-term contracts.")
    if "energy" in s:
        return ("For energy: focus on production volumes, realized prices, "
                "capex discipline, FCF yield, reserve replacement, break-even costs.")
    return ""


def _fmt_metrics(metrics: Dict[str, Any]) -> str:
    if not metrics:
        return ""
    parts = []
    for key in sorted(metrics):
        value = metrics[key]
        if value is None or value == "" or value == "Not disclosed":
            continue  # skip missing values
        parts.append(f"{key}={value}")
    return " | ".join(parts) if parts else ""


def _canonical_section(section: str) -> str:
    return str.__str__(section) if isinstance(section, SectionName) else str(section)


def _section_title(section: str) -> str:
    return SECTION_TITLES.get(_canonical_section(section), str(section))


def _format_question(section: str, language: str, ticker: str, company: str, quarter: str) -> str:
    question = SECTION_QUESTIONS[section]
    values = {"ticker": ticker, "company": company, "quarter": quarter}
    en = question["en"].format(**values)
    jp = question["jp"].format(**values)
    normalized = language.lower()

    if normalized in {"jp", "ja", "bilingual"}:
        return f"Question (EN): {en}\nQuestion (JP): {jp}"
    return f"Question (EN): {en}"


def _language_rules(language: str) -> str:
    normalized = language.lower()
    if normalized in {"ja", "jp"}:
        return (
            "Use Japanese for the answer body. Keep important English financial terms in parentheses "
            "when helpful, for example 売上高 (Revenue), 営業キャッシュフロー (OCF), "
            "フリーキャッシュフロー (FCF), 投下資本利益率 (ROIC)."
        )
    if normalized == "bilingual":
        return (
            "Use the English question followed by the Japanese question, then write the analysis in "
            "Japanese with concise English financial terms in parentheses. Do not add facts in one "
            "language that are absent in the other."
        )
    return (
        "Use English ONLY for the entire answer — no Japanese characters, no CJK. "
        "Use English labels only: 'For Nami-san:', 'Caution:', 'Essential insight:', "
        "and '> One-line summary:'. "
        "Every table cell must contain a sourced value or —. "
        "Compute a metric only when all formula inputs are supplied; otherwise write —. "
        "Never leave a cell empty and never invent missing values."
    )


def _base_prompt(
    *,
    section: str,
    language: str,
    ticker: str,
    company: str,
    quarter: str,
    metrics: Dict[str, Any],
    transcript_excerpt: str,
) -> str:
    canonical = _canonical_section(section)
    title = _section_title(section)
    table_header = TABLE_REQUIREMENTS[canonical]
    is_jp = language.lower() in {"jp", "ja"}
    format_source = SECTION_FORMATS if is_jp else EN_SECTION_FORMATS
    section_format = format_source[canonical].format(table_header=table_header)
    question = _format_question(canonical, language, ticker, company, quarter)
    transcript_context = (
        transcript_excerpt
        if transcript_excerpt
        else (
            "No transcript available. Use ONLY the financial_metrics data below. "
            "Do NOT invent qualitative commentary. Use Data not available in transcript "
            "for management commentary, business drivers, and other call discussion that "
            "requires transcript evidence."
        )
    )

    nami_label = "Namiさん向け解釈 / Namiさん向けの本質理解" if is_jp else "For Nami-san / Essential insight"
    missing_label = "—"
    summary_label = "> 一言まとめ: [one-line summary]" if is_jp else "> One-line summary: [one-line summary]"

    return f"""Required heading: ## {title}
Language: {language}
Language rule: {_language_rules(language)}
Ticker: {ticker}
Company: {company}
Quarter: {quarter}
Metrics: {_fmt_metrics(metrics)}
Transcript excerpt: {transcript_context}

Analysis question for context only; do not print it in the output:
{question}

Section output contract:
- Start with exactly: ## {title}
- Use strict markdown only.
- Use the PDF visual markers where applicable: 📊 🌟 ⚠️ 🧠 🎯 🧩 💰 📈 📦 🔮 🏆.
- Include the required table header exactly: {table_header}
- Put every numeric financial claim in a table first, then explain it below.
- Use numbered analysis markers ①②③. Use ④⑤⑥ only when the PDF section calls for more points.
- Include {nami_label} where specified.
- Use direct transcript or supplied-metric evidence. Never invent financial data.
- If the transcript excerpt says no transcript is available, use only Metrics and mark qualitative call evidence as Data not available in transcript.
- Every table cell must contain a sourced value or —. Never leave cells empty and never invent missing values.
- CRITICAL: Never write \"Section unavailable\" or similar placeholder text. If specific data is missing, use — in table cells and provide qualitative analysis based on the company's known business model, sector position, and total revenue/growth trends from Metrics.
- End with exactly one final blockquote line: {summary_label}

PDF-aligned section skeleton:
{section_format}
"""


def eps_revenue_prompt(language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str) -> str:
    return _base_prompt(
        section="EPS & Revenue",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=metrics,
        transcript_excerpt=transcript_excerpt,
    )


def highlights_prompt(language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str) -> str:
    return _base_prompt(
        section="Highlights",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=metrics,
        transcript_excerpt=transcript_excerpt,
    )


def operating_metrics_prompt(language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str) -> str:
    # CRITICAL OVERRIDE: the LLM frequently hallucinates the revenue value
    # (e.g. writing $2,025,000,000 instead of $111.18B). Surface the real
    # numbers explicitly to prevent this.
    rev_q = metrics.get("revenue_quarterly")
    rev_prior = metrics.get("revenue_quarterly_prior_year")
    gross_margin = metrics.get("gross_margin")
    op_margin = metrics.get("operating_margin")
    op_income = metrics.get("operating_income")
    net_income = metrics.get("net_income_quarterly") or metrics.get("net_income")
    opex = metrics.get("opex")
    extra = ""
    if rev_q is not None:
        try:
            rev_b = float(rev_q) / 1e9
            extra += f"\n\n🔴 CRITICAL OVERRIDE: Revenue (current quarter) = ${rev_b:.2f}B (raw={rev_q}). USE THIS EXACT VALUE in the Revenue row of the table. Do NOT invent a different revenue number."
        except (TypeError, ValueError):
            pass
    if rev_prior is not None:
        try:
            rp_b = float(rev_prior) / 1e9
            extra += f"\n⚠️  Revenue prior year = ${rp_b:.2f}B (raw={rev_prior}). Use in Prior Year column."
        except (TypeError, ValueError):
            pass
    if gross_margin is not None:
        try:
            extra += f"\n⚠️  Gross Margin = {float(gross_margin)*100:.2f}% (raw={gross_margin}). Use in Gross Margin row."
        except (TypeError, ValueError):
            pass
    if op_margin is not None:
        try:
            extra += f"\n⚠️  Operating Margin = {float(op_margin)*100:.2f}% (raw={op_margin}). Use in Operating Margin row."
        except (TypeError, ValueError):
            pass
    if op_income is not None:
        try:
            oi_b = float(op_income) / 1e9
            extra += f"\n⚠️  Operating Income = ${oi_b:.2f}B (raw={op_income}). Use in Operating Income row."
        except (TypeError, ValueError):
            pass
    if net_income is not None:
        try:
            ni_b = float(net_income) / 1e9
            extra += f"\n⚠️  Net Income = ${ni_b:.2f}B (raw={net_income}). Use in Net Income row."
        except (TypeError, ValueError):
            pass
    if opex is not None:
        try:
            ox_b = float(opex) / 1e9
            extra += f"\n⚠️  OpEx = ${ox_b:.2f}B (raw={opex}). Use in OpEx row."
        except (TypeError, ValueError):
            pass
    base = _base_prompt(
        section="Operating Metrics",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=metrics,
        transcript_excerpt=transcript_excerpt,
    )
    return base + extra


def cash_flow_prompt(language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str) -> str:
    return _base_prompt(
        section="Cash Flow",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=metrics,
        transcript_excerpt=transcript_excerpt,
    )


def capital_efficiency_prompt(language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str) -> str:
    return _base_prompt(
        section="Capital Efficiency",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=metrics,
        transcript_excerpt=transcript_excerpt,
    )


def segments_prompt(language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str) -> str:
    # Enrich with formatted segment table if XBRL data is available
    enriched = dict(metrics)
    seg_data = metrics.get("segments", {})
    if isinstance(seg_data, dict) and seg_data.get("product_segments"):
        lines = ["Segment revenue (from SEC 10-Q XBRL):",
                 f"Total quarterly revenue: ${seg_data.get('total_revenue_quarterly', 0) / 1e9:.2f}B",
                 "| Segment | Revenue (Q) |"]
        lines.append("|---|---|")
        for seg in seg_data["product_segments"]:
            rev = seg.get("revenue_quarterly", 0)
            name = seg.get("name", "?")
            lines.append(f"| {name} | ${rev / 1e9:.2f}B |")
        enriched["_segment_table"] = "\n".join(lines)
    return _base_prompt(
        section="Segments",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=enriched,
        transcript_excerpt=transcript_excerpt,
    )


def forward_pe_prompt(language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str) -> str:
    # Explicitly surface pe_forward to prevent LLM hallucination.
    # Despite being present in the Metrics line, the LLM often claims
    # "not provided in supplied metrics" and fills the table with —.
    pe_val = metrics.get("pe_forward")
    eps_val = metrics.get("eps_estimate")
    extra = ""
    if pe_val is not None:
        try:
            pe_str = f"{float(pe_val):.2f}x"
        except (TypeError, ValueError):
            pe_str = str(pe_val)
        extra += (
            f"\n\n🔴 CRITICAL OVERRIDE: The forward P/E ratio IS {pe_str} "
            f"(from yfinance, key=pe_forward). This value EXISTS in the Metrics line above. "
            f"Your FIRST sentence MUST state: \"The forward P/E is {pe_str}.\" "
            f"Do NOT claim it is missing, not provided, not disclosed, or unavailable — "
            f"that would be factually incorrect. "
            f"Put {pe_str} in the Current column of the table."
        )
    if eps_val is not None:
        try:
            eps_annual = float(eps_val) * 4.0
            extra += f"\n⚠️  Forward EPS basis (annualized consensus): ${eps_annual:.2f} ({float(eps_val):.2f} × 4 quarters). Use this in the Forward EPS basis row."
        except (TypeError, ValueError):
            pass
    base = _base_prompt(
        section="Forward P/E",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=metrics,
        transcript_excerpt=transcript_excerpt,
    )
    return base + extra


def backlog_prompt(language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str) -> str:
    # If the company does not report backlog data (e.g., Apple, most tech),
    # explicitly instruct the LLM to write a short "Not applicable" response
    # instead of creating a — filled table.
    backlog_val = metrics.get("backlog")
    if backlog_val is None or backlog_val == "" or backlog_val == "Not disclosed":
        extra = (
            f"\n\n⚠️  NOT APPLICABLE: {company} does NOT report backlog data. "
            f"Do NOT create a table. Write exactly one sentence: "
            f"\"Backlog is not applicable for {company} — the company does not report backlog or order book data.\" "
            f"Then briefly explain why in 1-2 sentences (e.g., consumer electronics business model, direct sales). "
            f"End with > One-line summary: Not applicable for {company}."
        )
        return _base_prompt(
            section="Backlog",
            language=language,
            ticker=ticker,
            company=company,
            quarter=quarter,
            metrics=metrics,
            transcript_excerpt=transcript_excerpt,
        ) + extra
    return _base_prompt(
        section="Backlog",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=metrics,
        transcript_excerpt=transcript_excerpt,
    )


def guidance_prompt(language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str) -> str:
    # Surface eps_estimate and revenue_estimate as guidance values.
    # Without this override, the LLM fills the guidance table with — because
    # the raw 'guidance' field is just a growth rate (e.g. 0.218).
    eps_q = metrics.get("eps_estimate")
    rev = metrics.get("revenue_estimate")
    extra = ""
    if eps_q is not None:
        try:
            eps_q_f = float(eps_q)
            eps_annual = eps_q_f * 4.0
            extra += (
                f"\n\n🔴 GUIDANCE OVERRIDE: EPS estimate (consensus) is ${eps_q_f:.2f}/quarter "
                f"(${eps_annual:.2f} annualized). "
                f"Use ${eps_q_f:.2f} in the EPS row of the Guidance table. "
                f"Do NOT leave EPS as —."
            )
        except (TypeError, ValueError):
            pass
    if rev is not None:
        try:
            rev_f = float(rev)
            rev_b = rev_f / 1e9
            extra += (
                f"\n⚠️  Revenue estimate (consensus) is ${rev_b:.2f}B. "
                f"Use ${rev_b:.2f}B in the Revenue row of the Guidance table. "
                f"Do NOT leave Revenue as —."
            )
        except (TypeError, ValueError):
            pass
    base = _base_prompt(
        section="Guidance",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=metrics,
        transcript_excerpt=transcript_excerpt,
    )
    return base + extra


def verdict_prompt(language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str) -> str:
    return _base_prompt(
        section="Verdict",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=metrics,
        transcript_excerpt=transcript_excerpt,
    )


PROMPT_BUILDERS: Dict[str, Callable[[str, str, str, str, Dict[str, Any], str], str]] = {
    "EPS & Revenue": eps_revenue_prompt,
    "Highlights": highlights_prompt,
    "Operating Metrics": operating_metrics_prompt,
    "Cash Flow": cash_flow_prompt,
    "Capital Efficiency": capital_efficiency_prompt,
    "Segments": segments_prompt,
    "Forward P/E": forward_pe_prompt,
    "Backlog": backlog_prompt,
    "Guidance": guidance_prompt,
    "Verdict": verdict_prompt,
}


def build_prompt(section: str, language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str, **kwargs: Any) -> str:
    """Build a PDF-aligned prompt for one earnings deep-dive section.
    
    Accepts optional sector/industry kwargs for forward-compatibility;
    sector context is primarily delivered via the system prompt.
    """
    return PROMPT_BUILDERS[_canonical_section(section)](language, ticker, company, quarter, metrics, transcript_excerpt)
