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
    "EPS & Revenue": "EPS & Revenue",
    "Highlights": "Highlights & Lowlights",
    "Operating Metrics": "Operating Metrics",
    "Cash Flow": "Cash Flow",
    "Capital Efficiency": "Capital Efficiency",
    "Segments": "Segments",
    "Forward P/E": "Forward P/E",
    "Backlog": "Backlog Quality",
    "Guidance": "Guidance",
    "Verdict": "Verdict",
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

TABLE_SECTIONS = set(s for s in SECTION_ORDER if s != "Backlog")  # Backlog is optional — not all companies report it

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
            "and revenue of {company} ({ticker}) for {quarter} in a detailed table "
            "(Estimate|Actual|vs Estimate|YoY|Source). "
            "Include the 3-quarter EPS trend to show trajectory and velocity. "
            "Explain beat/miss quality: was this a high-quality surprise (both top and bottom line beat) "
            "or a mixed result? Provide variance versus estimates and year-over-year change "
            "with specific dollar amounts and percentages."
        ),
        "jp": "{company} ({ticker}) の{quarter}決算のEPS（1株当たり利益）と売上高の予想値、実績値、予想比、前年同期比をまとめて下さい。3四半期のEPSトレンドも含めてください。",
    },
    "Highlights": {
        "en": (
            "What are the highlights and lowlights (key concerns) of this earnings report? "
            "Categorize each by theme (Operational, Strategic, Macro, Competitive) "
            "with a severity rating (High/Medium/Low). For each, provide the specific transcript "
            "or data evidence, explain WHY it matters to investors, and assess whether "
            "it represents a durable shift or a one-quarter event."
        ),
        "jp": (
            "今回の決算のハイライト、ローライトを、テーマ別（オペレーション/戦略/マクロ/競合）に分類し、"
            "重要度（高/中/低）を付けて教えてください。それぞれに具体的な証拠を示してください。"
        ),
    },
    "Operating Metrics": {
        "en": (
            "How were operating income, operating margin, gross profit, gross margin, "
            "operating expenses, and net income? Provide a summary table of the key "
            "metrics (Current|Prior Qtr|YoY|Source), followed by detailed analysis. "
            "Show the 3-quarter trend to explain margin trajectory. "
            "Compare to sector peers where possible.\n\n"
            "MANDATORY HEADING: Write the section title as exactly '## Operating Metrics' "
            "(do not rewrite it as 'Key Operating Metrics', 'Operational Performance', "
            "'Profitability', etc. — the downstream validator is strict on this exact string). "
            "If the company has unusual financials (negative operating margin, pre-revenue, "
            "aerospace/defense, biotech, etc.), STILL keep the heading 'Operating Metrics' and "
            "populate it with whatever operating-level data is available (e.g. for aerospace: "
            "revenue, gross margin if applicable, operating loss, operating expense breakdown, "
            "net loss, and a note explaining the negative operating margin trajectory). "
            "For pre-revenue companies, fill the table with 'N/M' (not meaningful) rows rather "
            "than skipping the section entirely."
        ),
        "jp": (
            "営業利益、営業利益率、粗利益、粗利益率、営業費用、純利益などは前年同期比と比べてどうでしたか？"
            "指標の一覧（当期|前期|前年同期比|ソース）を出して、3四半期のトレンド分析とセクター比較を含めて説明してください。\n\n"
            "【必須】見出しは必ず『## Operating Metrics』の文字列で出力してください。"
            "『主要営業指標』『業績概要』などの言い換えは不可です（バリデーターが厳格にチェックします）。"
            "航空宇宙・防衛、バイオ、プレレベニュー企業など通常の営業指標が該当しない場合でも、"
            "見出しは『Operating Metrics』のまま、使用可能なデータ（売上、適用可能な粗利率、営業損失、"
            "営業費の内訳、純損失など）を表に埋めてください。N/M（not meaningful）の行も許容されます。"
        ),
    },
    "Cash Flow": {
        "en": (
            "Please share any available figures for operating cash flow, CapEx, and free cash flow. "
            "Include a table (Current|Prior Qtr|YoY|Source) followed by analysis. "
            "Show 3-quarter cash flow trajectory. Discuss cash conversion quality "
            "and compare reinvestment intensity to sector norms."
        ),
        "jp": "営業キャッシュフロー、CapEx、フリーキャッシュフローの数値について、3四半期のトレンドを含めて教えてください。",
    },
    "Capital Efficiency": {
        "en": (
            "How were ROE, ROTCE (ROTE), ROA, and ROIC? Provide a table with values and sources. "
            "Explain whether efficiency is driven by business-model strength or financial engineering. "
            "Compare to sector and historical norms."
        ),
        "jp": "ROE / ROTCE（ROTE）/ ROA / ROICなどはどうでしたか？ビジネスモデルの強さと財務エンジニアリングを区別し、セクター比較も含めてください。",
    },
    "Segments": {
        "en": (
            "What were the results by segment? Provide tables for product/category segments AND "
            "regional segments (Segment|Revenue Q|YoY|Mix%|Source). Explain which segments "
            "are driving growth, which are stable, and which are under pressure. "
            "Compare segment mix to sector peers."
        ),
        "jp": "セグメント別の業績はどうでしたか？製品別・地域別の表を作成し、どのセグメントが成長を牽引しているか、セクターと比較して説明してください。",
    },
    "Forward P/E": {
        "en": (
            "What is the forward P/E ratio for {company} ({ticker})? "
            "State the current multiple with exact source, compare it to the sector and historical range, "
            "and explain whether growth, margins, and cash flows justify this valuation level. "
            "Discuss whether the multiple looks supported, stretched, or not assessable."
        ),
        "jp": "{company} ({ticker}) のForward P/Eはどうなっていますか？現在の倍率、セクターや過去との比較、成長・利益率・キャッシュフローがバリュエーションを正当化するか、支持されるか/割高か/判断不能かを説明してください。",
    },
    "Backlog": {
        "en": (
            "How is the quality and quantity of the order backlog for {company} ({ticker})? "
            "If the company does not disclose a backlog (common for consumer/tech companies), "
            "state 'Not applicable' and explain why in 2-3 sentences with business-model context. "
            "If backlog data exists, assess quantity (quarters of coverage), quality (firm vs cancellable), "
            "and conversion risk."
        ),
        "jp": "{company} ({ticker}) の受注残の質と量はどうですか？開示がない場合は「該当なし」と明記し、2-3文で理由を説明してください。データがある場合は量・質・変換リスクを評価してください。",
    },
    "Guidance": {
        "en": "What is the guidance for the upcoming quarters and beyond?",
        "jp": "来期以降のガイダンスをおしえてください。",
    },
    "Verdict": {
        "en": (
            "What is the overall earnings verdict for Nami-san after weighing each dimension? "
            "Rate each dimension (Growth, Margins, Cash Flow, Capital Efficiency, Valuation, "
            "Backlog/Guidance) on a simple scale: Strong / Neutral / Weak. "
            "Then produce an integrated verdict explaining how these dimensions interact — "
            "e.g., strong growth offset by weak margins, or improving cash flow despite "
            "valuation concerns. End with the 2-3 most critical monitor items for next quarter."
        ),
        "jp": (
            "成長、利益率、キャッシュフロー、資本効率、バリュエーション、バックログ/ガイダンスの"
            "各次元を「強い/普通/弱い」で評価し、Namiさん向けの総合評価を教えてください。"
            "これらの次元がどのように相互作用するかも説明してください。"
        ),
    },
}

SECTION_FORMATS: Dict[str, str] = {
    "EPS & Revenue": """Required table:
{table_header}
|---|---|---|---|---|---|
| EPS | ... | ... | ... | ... | ... |
| Revenue | ... | ... | ... | ... | ... |

Required analysis format（簡潔に — 合計120語以内、長い段落は禁止）:
① EPS: 実績 vs コンセンサス予想（予想の出所を明記）、サプライズ%、前年同期比の方向。
② 売上高: 実績 vs コンセンサス予想、サプライズ%、前年同期比の方向。
③ その後、1行の箇条書き2〜3点のみ: 今四半期の主なポジティブとネガティブ。
詳細はハイライト/ローライトのセクションに任せ、ここでは繰り返さないこと。""",
    "Highlights": """Required table:
{table_header}
|---|---|---|---|---|---|
| 🌟 Highlight | ① | ... | ... | ... | Low / Medium / High |
| ⚠️ Lowlight | ① | ... | ... | ... | Low / Medium / High |

Required analysis format（簡潔に — 短い見出し + 箇条書きのみ、段落は禁止）:
Highlights（ハイライト）
1. <最重要ポジティブの短い見出し>
   • 具体的な指標またはトランスクリプト根拠つきの1行箇条書きを2〜3点。
2. <2番目のポジティブ — 短い見出し>
   • 1行箇条書き2〜3点。
3. <3番目のポジティブ — 短い見出し>
   • 1行箇条書き2〜3点。

Lowlights（ローライト）
1. <最重要懸念 — 短い見出し>
   • 具体的根拠つきの1行箇条書き2〜3点。
2. <2番目の懸念 — 短い見出し>
   • 1行箇条書き2〜3点。
3. <3番目の懸念 — 短い見出し>
   • 1行箇条書き2〜3点。

各箇条書きは1行。項目ごとに3〜5文の段落を書かないこと。
""",
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

Required analysis format — Key Takeaways only (max 5 bullets, one line each):
• Gross margin level and what it signals vs sector norms.
• Operating leverage: revenue growth vs expense growth.
• Operating margin level in context (e.g. comparable to leading software peers, only if true).
• Net income vs operating income — name the driver (e.g. unrealized investment gains) ONLY if supported by source data.
• Core message: revenue growth AND margin direction together (growth quality).
The table carries the detail — no multi-paragraph analysis, no INFERRED paragraphs.
""",
    "Cash Flow": """Required table:
{table_header}
|---|---|---|---|---|---|
| Operating Cash Flow (OCF) | ... | ... | ... | ... | ... |
| CapEx | ... | ... | ... | ... | ... |
| Free Cash Flow (FCF) | ... | ... | ... | ... | ... |

Required analysis format — Key Takeaways形式のみ（最大5点、各1行）:
• 粗利益率の水準とセクター水準との比較が示す意味。
• 営業レバレッジ: 売上成長 vs 費用成長。
• 営業利益率の水準（例: 大手ソフトウェア企業並み — 事実の場合のみ）。
• 純利益 vs 営業利益 — 要因（例: 投資有価証券の未実現評価益）はソースで裏付けられる場合のみ明記。
• 核心メッセージ: 売上成長とマージン改善の同時達成（成長の質）。
表が詳細を担う — 複数段落の分析やINFERRED段落は書かないこと。
""",
    "Capital Efficiency": """Required table:
{table_header}
|---|---|---|---|---|
| ROE | ... | ... | ... | ... |
| ROTCE / ROTE | ... | ... | ... | ... |
| ROA | ... | ... | ... | ... |
| ROIC | ... | ... | ... | ... |
| Net Cash / (Net Debt) | ... | ... | ... | ... |

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
🧠 セグメント別の解説・分析（各3〜5文）
① 主要製品/カテゴリセグメント: 収益、成長率、全体に占める割合。成長の要因 — 価格、数量、新製品？成長率をセクター平均と比較。
② 利益エンジン/経常収益セグメント: マージン貢献と持続性。これはキャッシュカウか？経常収益の特性。
③ 安定/弱含みのセグメント: 回復シグナル、成熟圧力、構造的衰退。3四半期の収益軌道。
④⑤ 追加セグメントまたはトランスクリプトで強調されたテーマ。

🌍 地域別の重要ポイント（各3〜5文）
① 最強の地域: 収益と成長。地域のアウトパフォーマンス要因は？
② 新興成長地域: 次の成長の波はどこか？初期シグナル。
③ 成熟市場: 安定性、飽和、マクロ経済エクスポージャー。

競合コンテキスト: セクター平均と比較したセグメントミックス — より多様化/集中？より高い/低い成長セグメント？

🎯 全体構造（超重要）: 収益集中リスク。顧客または製品依存度の分析。

🧩 Namiさん向け本質理解: 短期/中期/長期のセグメントテーゼ — どのセグメントが勝ち、どれが衰えるか。

⚠️ リスク: 1〜2のセグメント固有リスク（集中、競合代替、景気循環性）。

⚠️ 注意ポイント: 集中と将来のセグメント依存。""",
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
■ Namiさん向けの本質: what the guide means and what to monitor next.
■ 一言まとめ: [your one-line summary here]

⚠️ 重要: 会社ガイダンス（経営陣が発表した会社の見通し）とコンセンサス/アナリスト予想（外部予測）を常に明確に区別してください。外部予想を「ガイダンス」と表記しないこと。「会社ガイダンス：…」または「経営陣のガイダンス：…」のように正確に表記すること。""",
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
🏆 総合評価（Namiさん向け、各次元3〜5文）
① 成長: 強い/普通/弱いで評価。収益とEPSの軌道。成長の質（オーガニックvs買収、経常的vs一時的）。セクター成長との比較。
② マージン: 強い/普通/弱いで評価。粗利益率と営業利益率のトレンド。価格決定力とコスト管理。セクター平均との比較。
③ キャッシュフロー: 強い/普通/弱いで評価。FCF生成と変換率。現金使途の質（自社株買い、再投資、債務）。FCF利回りの文脈。
④ 資本効率: 強い/普通/弱いで評価。ROIC vs 資本コスト。バランスシートの強さ。財務エンジニアリング vs ビジネスモデルのリターン。
⑤ バリュエーション: 強い/普通/弱いで評価。Forward P/E vs 成長率（PEG文脈）。過去レンジとの比較。セクターとの比較。支持されるか/割高か？
⑥ バックログ/ガイダンス: 強い/普通/弱いで評価。収益の可視性。ガイダンスの方向性（上方修正/維持/下方修正）。バックログの質（該当する場合）。

統合的評価: これらの次元がどのように相互作用するかを説明。強い成長 + 弱いマージン ≠ 強い成長 + 強いマージン。緊張はどこに？整合性はどこに？

次に重要なこと: 来四半期の最も重要な2〜3のモニタリング項目。具体的で実用的なシグナル。

🎯 明示的な投資アクション（必須）: Write exactly one line using this format: `Recommendation: BUY`, `Recommendation: HOLD`, or `Recommendation: SELL`. Choose one only, consistent with the score and evidence above. This is a client-facing action label, not generic investment advice.

⚠️ リスク: Cite only sourced risks from the analysis above. Not generic.

🧩 本質理解: Explain the quality of the quarter in simple terms — clean operational beat or noisy quarter with asterisks?""",
}

EN_SECTION_FORMATS: Dict[str, str] = {
    "EPS & Revenue": """Required table:
{table_header}
|---|---|---|---|---|---|
| EPS | ... | ... | ... | ... | ... |
| Revenue | ... | ... | ... | ... | ... |

Required analysis format (CONCISE — max ~120 words total, ONE short paragraph only):
① EPS beat/miss vs consensus estimate (name the consensus source EXACTLY as given in the consensus_provider metric — never invent a vendor name like FactSet/Refinitiv/Bloomberg), with surprise % and YoY direction. One sentence only.
② Revenue beat/miss vs consensus estimate, with surprise % and YoY direction. One sentence only.
③ Then 2-3 one-line bullets only: the key positives and negatives of the quarter. No ⚠️ Risk/Implications block.

Detailed discussion belongs in Highlights & Lowlights below — do not repeat it here.
> One-line summary: [your one-line summary here]""",
    "Highlights": """Required table:
{table_header}
|---|---|---|---|---|---|
| 🌟 Highlight | ① | ... | ... | ... | Low / Medium / High |
| ⚠️ Lowlight | ① | ... | ... | ... | Low / Medium / High |

Required analysis format (CONCISE — short numbered headings + bullets ONLY, NO paragraphs, each bullet is ONE line):
Highlights
1. <Short heading for the most important positive>
   • 2-3 one-line bullets with the specific metric or transcript evidence.
2. <Second positive — short heading>
   • 2-3 one-line bullets.
3. <Third positive — short heading>
   • 2-3 one-line bullets.

Lowlights
1. <Most important concern — short heading>
   • 2-3 one-line bullets with specific evidence.
2. <Second concern — short heading>
   • 2-3 one-line bullets.
3. <Third concern — short heading>
   • 2-3 one-line bullets.

STRICT RULES — VIOLATION WILL BE FLAGGED:
- Each bullet is MAXIMUM ONE LINE (not 3-5 sentences).
- NO prose paragraphs under any heading. Each bullet must start with "•".
- NO detailed explanations, NO multi-sentence analysis, NO "For the investor" prose blocks.
- The table carries the key evidence. Bullets add ONE line of context per point.
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

Required analysis format — Key Takeaways only (max 5 bullets, one line each):
• Gross margin level and what it signals vs sector norms.
• Operating leverage: revenue growth vs expense growth.
• Operating margin level in context (e.g. comparable to leading software peers, only if true).
• Net income vs operating income — name the driver (e.g. unrealized investment gains) ONLY if supported by source data.
• Core message: revenue growth AND margin direction together (growth quality).

The table carries the detail — no multi-paragraph analysis, no INFERRED paragraphs, no competitive context essay, no 3-quarter margin trend narrative, no risk/caution section. Each bullet is ONE sentence only. Total: max ~120 words.
> One-line summary: [your one-line summary here]""",
    "Cash Flow": """Required table:
{table_header}
|---|---|---|---|---|---|
| Operating Cash Flow (OCF) | ... | ... | ... | ... | ... |
| CapEx | ... | ... | ... | ... | ... |
| Free Cash Flow (FCF) | ... | ... | ... | ... | ... |

Required analysis format:
🧠 Explanation and analysis (3-5 sentences each)
① Operating Cash Flow: OCF amount with exact source. Cash earnings quality — how much of net income converts to cash? Working capital effect (positive or negative drag). 3-quarter OCF trend. Compare to sector cash conversion norms.
② CapEx: CapEx amount and intensity (CapEx/Revenue %). Whether investment is rising or falling. What is the company investing in? Compare reinvestment rate to sector and growth rate justification.
③ Free Cash Flow: FCF = OCF - CapEx with exact calculation. FCF yield if meaningful. 3-quarter FCF trend. Sustainability of current FCF generation.
④⑤ Additional analysis: Buybacks, dividends, debt paydown — actual amounts and trajectory.

Cash structure: Compare cash generation versus reinvestment needs. Is the company a cash compounder or cash consumer?

Competitive context: FCF conversion and CapEx intensity vs sector peers.

Essential insight for Nami-san: Explain whether the company creates cash efficiently or burns cash, and whether current cash usage (buybacks, investment, debt) is value-accretive.

⚠️ Risk/Implications: 1-2 working-capital or reinvestment risks. Not generic.

Caution for Nami-san: Mention one-off working-capital or future investment risks.
> One-line summary: [your one-line summary here]""",
    "Capital Efficiency": """Required table:
{table_header}
|---|---|---|---|---|
| ROE | ... | ... | ... | ... |
| ROTCE / ROTE | ... | ... | ... | ... |
| ROA | ... | ... | ... | ... |
| ROIC | ... | ... | ... | ... |
| Net Cash / (Net Debt) | ... | ... | ... | ... |

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
🧠 Segment explanation and analysis (3-5 sentences each)
① Lead product/category segment: Revenue, growth rate, and mix % of total. What drove the growth — pricing, volume, new products? Compare growth rate to sector peers.
② Profit engine or recurring segment: Margin contribution and durability. Is this the cash cow? Recurring revenue characteristics.
③ Stable/weak segments: Recovery signals, maturity pressure, or structural decline. Revenue trajectory over 3 quarters.
④⑤ Additional segments or transcript-emphasized themes.

Regional analysis (3-5 sentences each):
① Strongest region: Revenue and growth. What is driving regional outperformance?
② Emerging growth region: Where is the next growth wave? Early signals.
③ Mature-market: Stability, saturation, or macroeconomic exposure.

Competitive context: Segment mix positioning vs sector peers — more/less diversified? Higher/lower growth segments?

Overall structure: Revenue concentration risk. Customer or product dependency analysis.

Essential insight for Nami-san: Short/medium/long-term segment thesis — which segments win, which fade.

⚠️ Risk/Implications: 1-2 segment-specific risks (concentration, competitive displacement, cyclicality).

Caution: Concentration and future segment dependency.
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
> One-line summary: [your one-line summary here]

⚠️ CRITICAL: Always distinguish company guidance (company-issued forward outlook from management) from consensus/analyst estimates (external predictions). Never label external estimates as "guidance." Use precise language: "Company guidance: ..." or "Management guides: ..." when discussing company-issued outlooks.""",
    "Verdict": """Required table:
{table_header}
|---|---|---|---|---|
| Strengths | ... | ... | ... | ... |
| Weaknesses | ... | ... | ... | ... |
| Opportunities | ... | ... | ... | ... |
| Risks | ... | ... | ... | ... |

Required analysis format:
🏆 Overall assessment for Nami-san (3-5 sentences each dimension)
① Growth: Rate Strong/Neutral/Weak. Revenue and EPS trajectory. Quality of growth (organic vs acquired, recurring vs one-time). Compare to sector growth.
② Margins: Rate Strong/Neutral/Weak. Gross and operating margin trend. Pricing power and cost control. Margin vs sector peers.
③ Cash Flow: Rate Strong/Neutral/Weak. FCF generation and conversion. Cash usage quality (buybacks, reinvestment, debt). FCF yield context.
④ Capital Efficiency: Rate Strong/Neutral/Weak. ROIC vs cost of capital. Balance sheet strength. Financial engineering vs business-model returns.
⑤ Valuation: Rate Strong/Neutral/Weak. Forward P/E vs growth rate (PEG context). vs historical range. vs sector. Supported/stretched?
⑥ Backlog/Guidance: Rate Strong/Neutral/Weak. Revenue visibility. Guidance direction (raise/maintain/cut). Backlog quality if applicable.

Integrated verdict: Explain how these dimensions interact. Strong growth + weak margins = different story than strong growth + strong margins. Where is the tension? Where is the alignment?

What matters next: 2-3 most critical monitor items for next quarter. Specific, actionable signals.

Explicit action label (mandatory): Write exactly one line using this format: `Recommendation: BUY`, `Recommendation: HOLD`, or `Recommendation: SELL`. Choose one only, consistent with the score and evidence above. This is a client-facing action label, not generic investment advice.

⚠️ Risk: Cite only sourced risks from the analysis above. Not generic.

Essential insight: Explain the quality of the quarter in simple terms — was this a clean beat on operational strength or a noisy quarter with asterisks?
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
        "- Each analysis point must be 3-5 substantive sentences with specific data evidence, "
        "competitive context, and investor implications. Single-line answers are UNACCEPTABLE.\n"
        "- Identify the 3-5 metrics that truly matter for THIS company in THIS sector. "
        "Do not mechanically list every metric in the supplied data.\n"
        "- When the company does NOT report a metric (e.g., backlog for Apple), "
        "say so clearly instead of forcing a table.\n"
        "- Adapt your analysis depth to what the transcript reveals, and add ④⑤ analysis points "
        "on themes management emphasized in the call.\n"
        "- Provide competitive context — compare to sector peers where data allows. "
        "State whether performance appears above, at, or below sector average.\n"
        "- Show QoQ trend alongside YoY — discuss what CHANGED this quarter vs the trajectory.\n"
        "- Use markdown tables where they add clarity, with columns that make sense for the sector.\n\n"
        "STRUCTURE:\n"
        "- Start each section with ## Section Name\n"
        "- Use numbered analysis ①②③ for key points (3-5 sentences each minimum)\n"
        "- Include a 'Nami-san takeaway' line\n"
        "- End with > One-line summary: [concise verdict]\n"
        "- Every section must include a ⚠️ Risk/Implications paragraph with 1-2 specific, sourced risks\n\n"
        "DATA RULES:\n"
        "CRITICAL — SUPPLIED METRICS ARE THE SINGLE SOURCE OF TRUTH:\n"
        "- The 'supplied_metrics' in each section prompt contains VERIFIED data from yfinance and SEC.\n"
        "- These numbers ARE the authoritative source. Use them for ALL numerical values, tables, and comparisons.\n"
        "- The transcript may mention different numbers (annual vs quarterly revenue, GAAP vs non-GAAP EPS,\n"
        "  analyst consensus estimates vs actuals, segment revenue vs total). When there is ANY discrepancy\n"
        "  between the transcript and supplied metrics, the supplied metrics ALWAYS take precedence.\n"
        "- Example: if the transcript says '$164B' but supplied_metrics shows revenue_actual=$109.9B,\n"
        "  use $109.9B. The transcript number may be annual revenue or an analyst estimate.\n"
        "- Every supplied number must appear in your output AS-IS. Do not round, convert, or approximate.\n\n"
        "SOURCING:\n"
        "- Source every number: use (yfinance) for supplied metrics, (Earnings Call) for qualitative claims.\n"
        "- Never invent data. When a number is unavailable, explain WHY.\n"
        "- Do NOT use 'Not available', 'Not retrieved', 'N/A' or 'Supplied metrics' as filler sources.\n"
        "  Instead: 'Not disclosed in quarterly filing', 'Not reported', or '—'.\n\n"
        "FORBIDDEN in output:\n"
        "- Tool/provider names ('Codex CLI', 'DeepSeek', 'Spark', 'LLM analysis', 'pipeline',\n"
        "  'pre_render', 'RapidAPI'), internal markers ('DATA NOT AVAILABLE',\n"
        "  'DONNÉE NON DISPONIBLE', 'CRITICAL OVERRIDE'), and placeholder text\n"
        "  ('Section unavailable', 'primary returned no content').\n"
        "- Write in ENGLISH only. No Japanese characters, no CJK."
    )

    jp_system = (
        f"あなたはバイサイドのシニアアナリストで、Namiさん向けに決算分析を書いています。{sector_line}\n"
        f"{sector_guidance}\n\n"
        "型にはまったフォーム記入ではなく、アナリストとして考えてください：\n"
        "- 各分析ポイントは3〜5文の実質的な内容で、具体的なデータ証拠、競合コンテキスト、投資家への示唆を含めてください。1行の回答は不十分です。\n"
        "- この企業・このセクターで本当に重要な3〜5の指標を特定してください。\n"
        "- 企業が指標を開示していない場合、「該当なし」と明確に述べてください。\n"
        "- 決算トランスクリプトで経営陣が強調しているテーマに合わせて分析の深さを調整し、④⑤の追加分析ポイントを加えてください。\n"
        "- 可能な場合はセクター平均との比較を含めてください。\n"
        "- QoQトレンドをYoYと併せて示し、単なるスナップショットではなく変化を論じてください。\n\n"
        "構造：## セクション名, ①②③, Namiさん向け解釈, ⚠️ リスク, > 一言まとめ\n\n"
        "データルール：すべての数字に出所を明記。数値が入手できない場合は理由を説明。\n"
        "埋め草（Not available / Not retrieved / N/A / Supplied metrics）を使用しない。\n"
        "  代わりに「四半期報告書で非開示」「報告されず」「—」を使用。\n"
        "禁止出力：ツール名（Codex CLI、DeepSeek、Spark、LLM分析、pipeline、pre_render、RapidAPI）、\n"
        "  内部マーカー（DATA NOT AVAILABLE、DONNÉE NON DISPONIBLE、CRITICAL OVERRIDE）、\n"
        "  プレースホルダー（Section unavailable、primary returned no content）。\n"
        "日本語で記述。"
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
    # EXCLUDE annual metrics to prevent quarterly/annual confusion.
    # Sections that need annual data (Segments, full-year context) use raw SEC XBRL.
    _ANNUAL_KEYS = {
        "revenue_annual", "revenue_annual_growth", "net_income_annual",
        "gross_profit_annual", "operating_income_annual",
    }
    for key in sorted(metrics):
        if key in _ANNUAL_KEYS:
            continue  # skip — sections that need these pull from SEC XBRL directly
        value = metrics[key]
        if value is None or value == "" or value == "Not disclosed":
            continue  # skip missing values
        parts.append(f"{key}={_fmt_value(value)}")
    return " | ".join(parts) if parts else ""


def _fmt_value(value: Any) -> str:
    """Format a metric value for LLM prompt — round floats to prevent regurgitation."""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        abs_val = abs(value)
        if abs_val >= 1e9:
            return f"{value / 1e9:.2f}B"
        if abs_val >= 1e6:
            return f"{value / 1e6:.2f}M"
        if abs_val < 1:
            return f"{value:.4f}"
        return f"{value:.2f}"
    return str(value)


def _canonical_section(section: str) -> str:
    return str.__str__(section) if isinstance(section, SectionName) else str(section)


def _section_title(section: str) -> str:
    return SECTION_TITLES.get(_canonical_section(section), str(section))


def _parse_quarter(quarter: Any) -> tuple[str, str] | None:
    """Parse YYYYQn or YYYY Qn into current/prior-year labels for prompt table headers."""
    if not isinstance(quarter, str):
        return None
    normalized = quarter.strip().upper().replace(" ", "")
    if len(normalized) != 6:
        return None
    year_part = normalized[:4]
    q_marker = normalized[4]
    q_part = normalized[5]
    if q_marker != "Q" or not year_part.isdigit() or q_part not in {"1", "2", "3", "4"}:
        return None
    year = int(year_part)
    return f"Q{q_part} {year}", f"Q{q_part} {year - 1}"


def _period_table_header(section: str, quarter: str) -> str:
    """Replace generic period columns with concrete quarter labels."""
    header = TABLE_REQUIREMENTS[section]
    labels = _parse_quarter(quarter)
    if not labels:
        return header
    current_label, prior_label = labels
    if section == "EPS & Revenue":
        estimate_label = f"{current_label} Est"
        return (
            header
            .replace("| Estimate |", f"| {estimate_label} |")
            .replace("vs Estimate", f"vs {estimate_label}")
            .replace("Actual", current_label)
        )
    if section in {"Operating Metrics", "Cash Flow"}:
        return header.replace("Actual", current_label).replace("Prior Year", prior_label)
    return header


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
        "Every table cell must contain a sourced value or a placeholder dash. "
        "Compute a metric only when all formula inputs are supplied; otherwise use a dash. "
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
    table_header = _period_table_header(canonical, quarter)
    is_jp = language.lower() in {"jp", "ja"}
    format_source = SECTION_FORMATS if is_jp else EN_SECTION_FORMATS
    section_format = format_source[canonical].format(table_header=table_header)
    question = _format_question(canonical, language, ticker, company, quarter)
    transcript_context = (
        transcript_excerpt
        if transcript_excerpt
        else (
            "No transcript available. Use ONLY the financial_metrics data below. "
            "Do NOT invent qualitative commentary. For management commentary, "
            "business drivers, and other call discussions that require transcript "
            "evidence, state 'Not discussed in the available transcript' — "
            "do NOT write 'Not available', 'Not retrieved', 'N/A' or 'DATA NOT AVAILABLE'."
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

🔴 DATA CONTRACT — READ BEFORE WRITING:
The Metrics above are the SINGLE SOURCE OF TRUTH extracted from yfinance and SEC filings.
The PDF renderer will validate your table against these exact values and replace
any hallucinated numbers with data-driven corrections.
- Every number in your table MUST come from Metrics. If a metric is missing → write —.
- Every number in your PROSE must match the table. Do not write "$4.91 EPS" if the table says "$1.76".
- Never convert, annualize, or TTM-adjust the Metrics values. Use them as-is.
- If you need a number that is not in Metrics, write — in the table and
  "Not disclosed in this filing" in prose for that SPECIFIC metric only.
  NEVER write "Not available", "Not retrieved", "N/A", or "DATA NOT AVAILABLE"
  in ANY cell, prose, or heading. PROHIBITED FORMATS: "Not available", "N/A".
  Instead: "Not disclosed in quarterly filing" for missing data, "—" in cells.
🔴 CROSS-SECTION CONSISTENCY — ALL sections MUST agree on these facts:
- If any CRITICAL OVERRIDE in this prompt states EPS/Revenue BEAT or MISSED,
  you MUST use that exact direction. Do not contradict it.
- The EPS & Revenue section is the single source of truth for beat/miss status.
  All other sections (Highlights, Verdict) must echo the SAME direction.
- Never write "EPS did not beat" if the override says EPS BEAT.

Analysis question for context only; do not print it in the output:
{question}

Section output contract:
- Start with exactly: ## {title}
- Use strict markdown only.
- Use the ◆ marker for numbered analysis points (①②③ ◆ text).
- Include the required table header exactly: {table_header}
- CRITICAL: Tables are quick reference only. ALL substantive analysis goes in prose below. Every table cell value MUST appear AGAIN in prose with detailed analysis, sourcing, competitive context, and implications. Tables provide the numbers — prose provides the ANALYSIS.
- ALL detailed analysis, explanations, and interpretations go BELOW the table as structured prose.
- Use numbered analysis markers ①②③. Use ④⑤⑥ only when the PDF section calls for more points.
- Under each ①②③ item, use ● for data bullets and 👉 for investor implications.
- Include {nami_label} where specified.
- Use direct transcript or supplied-metric evidence. Never invent financial data.
- If the transcript excerpt says no transcript is available, use only Metrics and mark qualitative call evidence as "Not discussed in available transcript." Do NOT write "Not available" or "Not retrieved."
- Every table cell must contain a sourced value or a dash. Never leave cells empty and never invent missing values.
- CRITICAL Source column format: Every source cell MUST identify the real data origin with client-safe specificity. Use human-readable provenance — SEC 10-Q page and line number, Yahoo Finance/company metrics snapshot, transcript quote with timestamp, or calculation formula with inputs. Do NOT print raw provider keys or internal row IDs. Generic labels like \"Company filing\" or \"Calculated\" are INSUFFICIENT.
- CRITICAL: Never write \"Section unavailable\" or similar placeholder text. If specific data is missing, use — in table cells and provide qualitative analysis based on the company's known business model, sector position, and total revenue/growth trends from Metrics.
🔴 CLAIM SOURCE GROUNDING — Every analytical claim in your prose MUST fall into one of these categories:
  1. SOURCED — backed by a specific number from Metrics, a transcript quote, or an SEC filing fact. When sourced, cite the evidence inline with client-safe labels: (source: company metrics) or (source: 10-Q p.42). Never cite raw provider keys such as yfinance eps_actual.
  2. INFERRED — analyst interpretation based on sourced data. Label explicitly: \"Based on the metrics above, we infer that...\" or \"Model interpretation: ...\"
  3. UNSUPPORTED — do NOT emit. If you lack data to support an analytical claim, omit the claim entirely rather than inventing reasoning. A missing claim is better than a fabricated one.
🔴 FORBIDDEN CLAIM PATTERNS — These are BLOCKED at PDF generation:
  - Sector-specific language applied to wrong sectors (e.g. \"hyperscaler capex\" for non-tech companies)
  - Consensus estimates presented as company guidance
  - LLM output presented as source data (e.g. \"source: LLM analysis\")
  - Price targets, investment recommendations, or forward-looking predictions not explicitly requested
  - "Not available", "Not retrieved", or "DATA NOT AVAILABLE" applied to an entire section. If individual metrics are missing, mark only those specific cells with — and use "Not disclosed in this filing" for each.
- End with exactly one final blockquote line: {summary_label}

PDF-aligned section skeleton:
{section_format}
"""


def eps_revenue_prompt(language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str) -> str:
    # 🔴 CRITICAL OVERRIDE: inject exact EPS & Revenue values so the LLM
    # cannot invent conflicting numbers. This section is the single source
    # of truth that all other sections cross-reference against.
    eps_actual = metrics.get("eps_actual")
    eps_est = metrics.get("eps_estimate")
    rev_actual = metrics.get("revenue_actual")
    rev_est = metrics.get("revenue_estimate")
    rev_q = metrics.get("revenue_quarterly")
    eps_yoy = metrics.get("eps_yoy")
    rev_yoy = metrics.get("revenue_yoy")
    extra = ""
    def _vs(actual, estimate):
        try:
            return (float(actual) - float(estimate)) / float(estimate)
        except (TypeError, ValueError, ZeroDivisionError):
            return None
    # EPS
    eps_vs = _vs(eps_actual, eps_est) if eps_actual is not None and eps_est is not None else None
    if eps_vs is not None:
        pct = eps_vs * 100
        direction = "BEAT" if pct > 0 else "MISSED"
        try: eps_actual_f = float(eps_actual); eps_est_f = float(eps_est)
        except (TypeError, ValueError): eps_actual_f = eps_actual; eps_est_f = eps_est
        extra += f"\n\n🔴 CRITICAL OVERRIDE — EPS: {direction} consensus by {abs(pct):.1f}% (actual=${eps_actual_f:.2f}, estimate=${eps_est_f:.2f}). USE THESE EXACT VALUES in the EPS row of the table. State '{direction}' in prose."
    elif eps_actual is not None:
        try: extra += f"\n⚠️  EPS actual = ${float(eps_actual):.2f}. Use in table. Estimate unavailable — mark vs Estimate as —."
        except (TypeError, ValueError): pass
    # EPS YoY
    if eps_yoy is not None:
        try: extra += f"\n⚠️  EPS YoY change = {float(eps_yoy):+.1f}%. Use in YoY Change column."
        except (TypeError, ValueError): pass
    # Revenue
    rev_vs = _vs(rev_actual, rev_est) if rev_actual is not None and rev_est is not None else None
    if rev_vs is not None:
        pct = rev_vs * 100
        direction = "BEAT" if pct > 0 else "MISSED"
        try: rev_f = float(rev_actual) / 1e9; rev_est_f = float(rev_est) / 1e9
        except (TypeError, ValueError): rev_f = rev_actual; rev_est_f = rev_est
        extra += f"\n🔴 CRITICAL OVERRIDE — Revenue: {direction} consensus by {abs(pct):.1f}% (actual=${rev_f:.2f}B, estimate=${rev_est_f:.2f}B). USE THESE EXACT VALUES in the Revenue row. State '{direction}' in prose."
    # Use revenue_quarterly if revenue_actual is missing
    if rev_actual is None and rev_q is not None:
        try: extra += f"\n⚠️  Revenue (quarterly) = ${float(rev_q)/1e9:.2f}B. Use in Revenue row."
        except (TypeError, ValueError): pass
    elif rev_actual is None and rev_q is None:
        extra += (
            "\n🔴 CRITICAL OVERRIDE — Revenue Actual is not present in supplied_metrics. "
            "In the Revenue row, the Actual cell MUST be —. Do NOT copy a transcript revenue "
            "number (for example '$22.2B') into the Actual cell unless it also appears as "
            "supplied_metrics.revenue_actual or supplied_metrics.revenue_quarterly. You may "
            "mention transcript revenue only in prose, explicitly labeled as Earnings Call evidence, "
            "and it must not contradict the Operating Metrics table."
        )
    # Revenue YoY
    if rev_yoy is not None:
        try: extra += f"\n⚠️  Revenue YoY change = {float(rev_yoy):+.1f}%. Use in YoY Change column."
        except (TypeError, ValueError): pass
    # 3-quarter EPS trend
    eps_quarterly = metrics.get("eps_quarterly")
    if isinstance(eps_quarterly, list) and len(eps_quarterly) >= 3:
        vals = [f"${float(e):.2f}" for e in eps_quarterly[-3:]]
        extra += f"\n⚠️  EPS 3-quarter trend: {' → '.join(vals)}. Include in trend analysis."
    base = _base_prompt(
        section="EPS & Revenue",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=metrics,
        transcript_excerpt=transcript_excerpt,
    )
    return base + extra


def highlights_prompt(language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str) -> str:
    # CRITICAL OVERRIDE: the LLM must know whether EPS/Revenue beat or missed
    # before classifying highlights. Without this it will hallucinate "Revenue beat"
    # when the EPS & Revenue table shows a miss.
    eps_actual = metrics.get("eps_actual")
    eps_est = metrics.get("eps_estimate")
    rev_actual = metrics.get("revenue_actual")
    rev_est = metrics.get("revenue_estimate")
    extra = ""
    # Compute vs_estimate from actual/estimate (revenue_vs_estimate not in schema)
    def _vs(actual, estimate):
        try:
            return (float(actual) - float(estimate)) / float(estimate)
        except (TypeError, ValueError, ZeroDivisionError):
            return None
    eps_vs = _vs(eps_actual, eps_est) if eps_actual is not None and eps_est is not None else None
    if eps_vs is not None:
        pct = eps_vs * 100
        direction = "BEAT" if pct > 0 else "MISSED"
        try: eps_actual_f = float(eps_actual); eps_est_f = float(eps_est)
        except (TypeError, ValueError): eps_actual_f = eps_actual; eps_est_f = eps_est
        extra += f"\n\n🔴 CRITICAL OVERRIDE: EPS {direction} consensus estimates by {abs(pct):.1f}% (actual=${eps_actual_f:.2f}, estimate=${eps_est_f:.2f}). Frame highlights consistent with this result."
    rev_vs = _vs(rev_actual, rev_est) if rev_actual is not None and rev_est is not None else None
    if rev_vs is not None:
        pct = rev_vs * 100
        direction = "BEAT" if pct > 0 else "MISSED"
        try: rev_b = float(rev_actual) / 1e9
        except (TypeError, ValueError): rev_b = rev_actual
        try: rev_est_b = float(rev_est) / 1e9
        except (TypeError, ValueError): rev_est_b = rev_est
        extra += f"\n⚠️  Revenue {direction} consensus estimates by {abs(pct):.1f}% (actual=${rev_b:.2f}B, estimate=${rev_est_b:.2f}B). Frame highlights consistent with this result."
    base = _base_prompt(
        section="Highlights",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=metrics,
        transcript_excerpt=transcript_excerpt,
    )
    return base + extra


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
            extra += f"\n\n🔴 CRITICAL OVERRIDE: Revenue (current quarter) = ${rev_b:.2f}B. USE THIS EXACT VALUE in the Revenue row of the table. Do NOT invent a different revenue number."
        except (TypeError, ValueError):
            pass
    if rev_prior is not None:
        try:
            rp_b = float(rev_prior) / 1e9
            extra += f"\n⚠️  Revenue prior year = ${rp_b:.2f}B. Use in Prior Year column."
        except (TypeError, ValueError):
            pass
    if gross_margin is not None:
        try:
            extra += f"\n⚠️  Gross Margin = {float(gross_margin):.2f}% (already a percentage — DO NOT multiply). Use in Gross Margin row."
        except (TypeError, ValueError):
            pass
    if op_margin is not None:
        try:
            extra += f"\n⚠️  Operating Margin = {float(op_margin):.2f}% (already a percentage — DO NOT multiply). Use in Operating Margin row."
        except (TypeError, ValueError):
            pass
    if op_income is not None:
        try:
            oi_b = float(op_income) / 1e9
            extra += f"\n⚠️  Operating Income = ${oi_b:.2f}B. Use in Operating Income row."
        except (TypeError, ValueError):
            pass
    if net_income is not None:
        try:
            ni_b = float(net_income) / 1e9
            extra += f"\n⚠️  Net Income = ${ni_b:.2f}B. Use in Net Income row."
        except (TypeError, ValueError):
            pass
    if opex is not None:
        try:
            ox_b = float(opex) / 1e9
            extra += f"\n⚠️  OpEx = ${ox_b:.2f}B. Use in OpEx row."
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
    # 🔴 CRITICAL OVERRIDE: surface exact cash flow numbers to prevent hallucination.
    ocf = metrics.get("operating_cash_flow")
    capex = metrics.get("capex")
    fcf = metrics.get("free_cash_flow")
    extra = ""
    if ocf is not None:
        try: extra += f"\n\n🔴 CRITICAL OVERRIDE: Operating Cash Flow = ${float(ocf)/1e9:.2f}B. USE THIS EXACT VALUE in the OCF row of the table."
        except (TypeError, ValueError): pass
    if capex is not None:
        try: extra += f"\n⚠️  CapEx = ${float(capex)/1e9:.2f}B. Use in CapEx row."
        except (TypeError, ValueError): pass
    if fcf is not None:
        try: extra += f"\n⚠️  Free Cash Flow (FCF) = ${float(fcf)/1e9:.2f}B (= OCF - CapEx). Use in FCF row."
        except (TypeError, ValueError): pass
    if ocf is not None and capex is not None:
        try:
            calculated_fcf = float(ocf) - float(capex)
            if calculated_fcf >= 0: qual = "positive"
            else: qual = "negative"
            extra += f"\n⚠️  FCF is {qual} (${calculated_fcf/1e9:.2f}B). Frame cash analysis accordingly."
        except (TypeError, ValueError): pass
    base = _base_prompt(
        section="Cash Flow",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=metrics,
        transcript_excerpt=transcript_excerpt,
    )
    return base + extra


def capital_efficiency_prompt(language: str, ticker: str, company: str, quarter: str, metrics: Dict[str, Any], transcript_excerpt: str) -> str:
    # 🔴 CRITICAL OVERRIDE: surface exact capital efficiency ratios to prevent hallucination.
    roe = metrics.get("roe")
    roa = metrics.get("roa")
    roic = metrics.get("roic")
    rotce = metrics.get("rotce") or metrics.get("rote")
    net_income = metrics.get("net_income") or metrics.get("net_income_quarterly")
    extra = ""
    if roe is not None:
        try: extra += f"\n\n🔴 CRITICAL OVERRIDE: ROE = {float(roe):.1f}%. USE THIS EXACT VALUE in the ROE row of the table."
        except (TypeError, ValueError): pass
    if rotce is not None:
        try: extra += f"\n⚠️  ROTCE/ROTE = {float(rotce):.1f}%. Use in ROTCE/ROTE row."
        except (TypeError, ValueError): pass
    if roa is not None:
        try: extra += f"\n⚠️  ROA = {float(roa):.1f}%. Use in ROA row."
        except (TypeError, ValueError): pass
    if roic is not None:
        try: extra += f"\n⚠️  ROIC = {float(roic):.1f}%. Use in ROIC row."
        except (TypeError, ValueError): pass
    if net_income is not None:
        try: extra += f"\n⚠️  Net Income = ${float(net_income)/1e9:.2f}B. Reference in capital efficiency analysis."
        except (TypeError, ValueError): pass
    # 🔴 CRITICAL OVERRIDE: net_debt is the authoritative net cash/debt position.
    # The consensus_overrides provide the exact filing-derived value. Do NOT recompute
    # Net Cash from individual cash/marketable_securities/total_debt components —
    # yfinance may have incomplete marketable securities and wrong total_debt.
    net_debt = metrics.get("net_debt")
    if net_debt is not None:
        try:
            abs_val = abs(float(net_debt)) / 1e9
            if float(net_debt) < 0:
                extra += f"\n\n🔴 CRITICAL OVERRIDE: Net Cash / (Net Debt) = ${abs_val:.1f}B (net cash position, from net_debt={float(net_debt)/1e9:.2f}B). USE THIS EXACT VALUE in the Net Cash / (Net Debt) row. Do NOT recalculate from cash_and_equivalents or total_debt components — the net_debt metric IS the authoritative filing-derived net position."
            else:
                extra += f"\n\n🔴 CRITICAL OVERRIDE: Net Cash / (Net Debt) = -${abs_val:.1f}B (net debt position, from net_debt={float(net_debt)/1e9:.2f}B). USE THIS EXACT VALUE in the Net Cash / (Net Debt) row. Do NOT recalculate from cash_and_equivalents or total_debt components."
        except (TypeError, ValueError): pass
    base = _base_prompt(
        section="Capital Efficiency",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=metrics,
        transcript_excerpt=transcript_excerpt,
    )
    return base + extra


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
    # Surface eps_estimate and revenue_estimate for the guidance section.
    # CRITICAL: These are ANALYST CONSENSUS estimates, NOT management guidance.
    # The guidance table must clearly distinguish:
    #   - Management guidance: what the company explicitly guided (from transcript)
    #   - Analyst consensus: what analysts estimate (from yfinance)
    # Never conflate the two. Never present consensus as guidance.
    eps_q = metrics.get("eps_estimate")
    rev = metrics.get("revenue_estimate")
    extra = ""
    if eps_q is not None:
        try:
            eps_q_f = float(eps_q)
            eps_annual = eps_q_f * 4.0
            extra += (
                f"\n\n🔴 ANALYST CONSENSUS (NOT management guidance): "
                f"EPS consensus estimate is ${eps_q_f:.2f}/quarter "
                f"(${eps_annual:.2f} annualized). "
                f"Use in the EPS row of the Guidance table. "
                f"Label as 'Analyst consensus' — do NOT label as 'Management guidance' "
                f"unless the company explicitly guided this number."
            )
        except (TypeError, ValueError):
            pass
    if rev is not None:
        try:
            rev_f = float(rev)
            rev_b = rev_f / 1e9
            extra += (
                f"\n⚠️  Revenue analyst consensus is ${rev_b:.2f}B. "
                f"Use in the Revenue row of the Guidance table. "
                f"Label as 'Analyst consensus' — do NOT label as 'Management guidance' "
                f"unless the company explicitly guided this number."
            )
        except (TypeError, ValueError):
            pass
    # Add instruction to separate management guidance and analyst consensus
    extra += (
        "\n\n🔴 GUIDANCE TABLE FORMAT: "
        "The Guidance table MUST have separate rows for:\n"
        "  | Metric | Management Guidance | Analyst Consensus | Source |\n"
        "If management did NOT provide guidance for a metric, write "
        "'Not guided by management' in the Management Guidance column "
        "and fill the Consensus column with the analyst estimate. "
        "Never leave the consensus column empty if an estimate exists."
    )
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
    # CRITICAL OVERRIDE: the Verdict MUST be consistent with EPS & Revenue results.
    # Without this the LLM will contradict its own earlier sections (e.g. "EPS beat"
    # in Highlights then "EPS did not beat consensus" in Verdict).
    eps_actual = metrics.get("eps_actual")
    eps_est = metrics.get("eps_estimate")
    rev_actual = metrics.get("revenue_actual")
    rev_est = metrics.get("revenue_estimate")
    gross_margin = metrics.get("gross_margin")
    op_margin = metrics.get("operating_margin")
    extra = ""
    def _vs(actual, estimate):
        try:
            return (float(actual) - float(estimate)) / float(estimate)
        except (TypeError, ValueError, ZeroDivisionError):
            return None
    eps_vs = _vs(eps_actual, eps_est) if eps_actual is not None and eps_est is not None else None
    if eps_vs is not None:
        pct = eps_vs * 100
        direction = "BEAT" if pct > 0 else "MISSED"
        try: eps_actual_f = float(eps_actual); eps_est_f = float(eps_est)
        except (TypeError, ValueError): eps_actual_f = eps_actual; eps_est_f = eps_est
        extra += f"\n\n🔴 VERDICT DATA: EPS {direction} consensus by {abs(pct):.1f}% (${eps_actual_f:.2f} vs ${eps_est_f:.2f}). Your Verdict MUST state this direction. NEVER contradict beat/miss status."
    rev_vs = _vs(rev_actual, rev_est) if rev_actual is not None and rev_est is not None else None
    if rev_vs is not None:
        pct = rev_vs * 100
        direction = "BEAT" if pct > 0 else "MISSED"
        try: rev_b = float(rev_actual) / 1e9
        except (TypeError, ValueError): rev_b = rev_actual
        try: rev_est_b = float(rev_est) / 1e9
        except (TypeError, ValueError): rev_est_b = rev_est
        extra += f"\n⚠️  Revenue {direction} consensus by {abs(pct):.1f}% (${rev_b:.2f}B vs ${rev_est_b:.2f}B). Verdict MUST state this direction."
    if gross_margin is not None:
        try: extra += f"\n⚠️  Gross Margin = {float(gross_margin):.1f}% — do NOT say margins are missing or unavailable."
        except (TypeError, ValueError): pass
    if op_margin is not None:
        try: extra += f"\n⚠️  Operating Margin = {float(op_margin):.1f}% — do NOT say margins are missing or unavailable."
        except (TypeError, ValueError): pass
    # 🔴 CRITICAL OVERRIDE (2026-06-10): The recommendation line MUST be emitted FIRST in
    # the Verdict section, before the table or any dimension analysis. Previously this
    # requirement lived at the end of the EN/JP section formats, so a low-effort or
    # truncated LLM (e.g. gpt-5.3-codex-spark effort=low, observed on NVDA 12:59) would
    # cut the response mid-section and silently drop the only BUY/HOLD/SELL token,
    # tripping pre_render_validator (verdict_missing_recommendation) and blocking the PDF.
    # Emitting the recommendation first guarantees it survives any downstream truncation.
    extra += (
        "\n\n🔴 CRITICAL OVERRIDE — RECOMMENDATION FIRST: Begin the section content with "
        "EXACTLY this line (no other text before it, no `Recommendation:` prefix variant):\n"
        "**Recommendation: BUY**   OR   **Recommendation: HOLD**   OR   **Recommendation: SELL**\n"
        "Then a blank line, then the Strengths/Weaknesses/Opportunities/Risks table, then the "
        "five-dimension assessment. The orchestrator's score (FH/G/V/M/Mo/S) and the evidence "
        "above MUST drive the choice: FH>=9 + strong G/M/Mo + supportive V → BUY; mixed signals "
        "or stretched valuation → HOLD; FH<=4 OR deteriorating fundamentals → SELL."
    )
    base = _base_prompt(
        section="Verdict",
        language=language,
        ticker=ticker,
        company=company,
        quarter=quarter,
        metrics=metrics,
        transcript_excerpt=transcript_excerpt,
    )
    return base + extra


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
