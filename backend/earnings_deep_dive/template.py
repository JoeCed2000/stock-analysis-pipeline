"""Executable templates for earnings deep-dive PDF reports."""
from dataclasses import dataclass
from typing import Literal


TemplateLanguage = Literal["en", "jp"]

TEMPLATE_LANGUAGE_CODES: tuple[TemplateLanguage, ...] = ("en", "jp")
TEMPLATE_SECTION_KEYS = (
    "EPS & Revenue",
    "Highlights",
    "Operating Metrics",
    "Cash Flow",
    "Capital Efficiency",
    "Segments",
    "Forward P/E",
    "Backlog",
    "Guidance",
    "Verdict",
)


@dataclass(frozen=True)
class ReportSectionTemplate:
    key: str
    title: str
    question: str
    table_columns: tuple[str, ...]
    table_rows: tuple[str, ...]
    summary_label: str


EARNINGS_TEMPLATE: tuple[ReportSectionTemplate, ...] = (
    ReportSectionTemplate(
        key="EPS & Revenue",
        title="EPS & Revenue",
        question="Please summarize EPS and revenue performance versus consensus and prior year.",
        table_columns=("Metric", "Estimate", "Actual", "vs Estimate", "YoY Change", "Source"),
        table_rows=("EPS", "Revenue"),
        summary_label="One-line summary",
    ),
    ReportSectionTemplate(
        key="Highlights",
        title="Highlights",
        question="Please identify the main positive and negative points from the quarter.",
        table_columns=("Type", "Point", "Source"),
        table_rows=("Highlight 1", "Highlight 2", "Lowlight 1", "Lowlight 2"),
        summary_label="Nami takeaway",
    ),
    ReportSectionTemplate(
        key="Operating Metrics",
        title="Operating Metrics",
        question="Please compare the operating metrics that explain the quarter's earnings quality.",
        table_columns=("Metric", "Actual", "Prior Year", "YoY", "Source"),
        table_rows=("Revenue", "Gross profit", "Gross margin", "OpEx", "Operating income", "Operating margin", "Net income"),
        summary_label="Operating takeaway",
    ),
    ReportSectionTemplate(
        key="Cash Flow",
        title="Cash Flow",
        question="Please assess cash conversion, capex intensity, and free cash flow quality.",
        table_columns=("Metric", "Actual", "Prior Year", "YoY", "Quality", "Source"),
        table_rows=("Operating cash flow", "CapEx", "Free cash flow", "Net debt"),
        summary_label="Cash flow takeaway",
    ),
    ReportSectionTemplate(
        key="Capital Efficiency",
        title="Capital Efficiency",
        question="Please evaluate capital efficiency and shareholder return metrics.",
        table_columns=("Metric", "Actual", "Prior Year", "YoY", "Comment", "Source"),
        table_rows=("ROE", "ROTCE / ROTE", "ROA", "ROIC", "Buybacks", "Dividends"),
        summary_label="Capital efficiency takeaway",
    ),
    ReportSectionTemplate(
        key="Segments",
        title="Segments",
        question="Please summarize segment revenue, growth, and the main business drivers.",
        table_columns=("Segment", "Revenue", "Prior Year", "YoY", "% of Total", "Driver", "Source"),
        table_rows=("Data Center", "Gaming", "Professional Visualization", "Automotive", "OEM & Other", "Total"),
        summary_label="Segment takeaway",
    ),
    ReportSectionTemplate(
        key="Forward P/E",
        title="Forward P/E",
        question="Please explain the forward P/E and valuation signal implied by the quarter.",
        table_columns=("Metric", "Value", "Reference", "Interpretation", "Source"),
        table_rows=("Forward P/E", "Forward EPS basis"),
        summary_label="Valuation takeaway",
    ),
    ReportSectionTemplate(
        key="Backlog",
        title="Backlog",
        question="Please state whether backlog or contracted revenue changes the medium-term visibility.",
        table_columns=("Metric", "Value", "Change", "Visibility Signal", "Source"),
        table_rows=("Backlog", "Book-to-bill / demand"),
        summary_label="Backlog takeaway",
    ),
    ReportSectionTemplate(
        key="Guidance",
        title="Guidance",
        question="Please summarize guidance and compare it with the recent run-rate.",
        table_columns=("Metric", "Guidance", "QoQ", "Medium-term Signal", "Source"),
        table_rows=("Revenue guidance", "Margin guidance", "EPS guidance", "OpEx guidance", "Diluted shares"),
        summary_label="Guidance takeaway",
    ),
    ReportSectionTemplate(
        key="Verdict",
        title="Verdict / Overall Assessment",
        question="Please provide a balanced final assessment based only on sourced data.",
        table_columns=("Dimension", "Positive evidence", "Negative evidence", "Net assessment", "Source"),
        table_rows=("Earnings quality", "Growth durability", "Valuation", "Overall verdict"),
        summary_label="Final verdict",
    ),
)


JAPANESE_EARNINGS_TEMPLATE: tuple[ReportSectionTemplate, ...] = (
    ReportSectionTemplate(
        key="EPS & Revenue",
        title="EPS・売上高",
        question="以下のEPSと売上高について、コンセンサスおよび前年同期比との差異を要約してください。",
        table_columns=("指標", "予想", "実績", "予想比", "前年同期比", "出所"),
        table_rows=("EPS", "売上高"),
        summary_label="一行要約",
    ),
    ReportSectionTemplate(
        key="Highlights",
        title="ハイライト",
        question="以下の四半期について、主なポジティブ要因とリスク要因を整理してください。",
        table_columns=("テーマ", "シグナル", "根拠", "影響", "出所"),
        table_rows=("主なポジティブ要因", "主なリスク", "経営陣トーン"),
        summary_label="Namiコメント",
    ),
    ReportSectionTemplate(
        key="Operating Metrics",
        title="営業指標",
        question="以下の営業指標を比較し、収益品質を説明してください。",
        table_columns=("指標", "実績", "前年", "前年同期比", "出所"),
        table_rows=("売上高", "粗利益", "粗利益率", "営業費用", "営業利益", "営業利益率", "純利益"),
        summary_label="営業面の要点",
    ),
    ReportSectionTemplate(
        key="Cash Flow",
        title="キャッシュフロー",
        question="以下のキャッシュ創出力、設備投資、フリーキャッシュフローの質を評価してください。",
        table_columns=("指標", "実績", "前年", "前年同期比", "品質", "出所"),
        table_rows=("営業キャッシュフロー", "設備投資", "フリーキャッシュフロー", "純負債"),
        summary_label="キャッシュフロー要点",
    ),
    ReportSectionTemplate(
        key="Capital Efficiency",
        title="資本効率",
        question="以下の資本効率と株主還元指標を評価してください。",
        table_columns=("指標", "実績", "前年", "前年同期比", "コメント", "出所"),
        table_rows=("ROE", "ROTCE / ROTE", "ROA", "ROIC", "自社株買い", "配当"),
        summary_label="資本効率要点",
    ),
    ReportSectionTemplate(
        key="Segments",
        title="セグメント",
        question="以下のセグメント別売上高、成長率、主要ドライバーを要約してください。",
        table_columns=("セグメント", "売上高", "前年", "前年同期比", "構成比", "ドライバー", "出所"),
        table_rows=("主要セグメント", "第二セグメント", "その他セグメント"),
        summary_label="セグメント要点",
    ),
    ReportSectionTemplate(
        key="Forward P/E",
        title="予想PER",
        question="以下の予想PERとバリュエーション上の示唆を説明してください。",
        table_columns=("指標", "値", "参照", "解釈", "出所"),
        table_rows=("予想PER", "Forward EPS basis"),
        summary_label="バリュエーション要点",
    ),
    ReportSectionTemplate(
        key="Backlog",
        title="受注残",
        question="以下の受注残または契約済み売上が中期的な見通しに与える影響を示してください。",
        table_columns=("指標", "値", "変化", "見通しシグナル", "出所"),
        table_rows=("受注残", "需要シグナル"),
        summary_label="受注残要点",
    ),
    ReportSectionTemplate(
        key="Guidance",
        title="ガイダンス",
        question="以下のガイダンスを要約し、直近のランレートと比較してください。",
        table_columns=("指標", "ガイダンス", "前四半期比", "中期シグナル", "出所"),
        table_rows=("売上高ガイダンス", "利益率ガイダンス", "EPSガイダンス", "営業費用ガイダンス", "希薄化後株式数"),
        summary_label="ガイダンス要点",
    ),
    ReportSectionTemplate(
        key="Verdict",
        title="総合評価",
        question="以下のソース済みデータだけに基づき、バランスの取れた総合評価をしてください。",
        table_columns=("観点", "ポジティブ要因", "ネガティブ要因", "総合評価", "出所"),
        table_rows=("収益品質", "成長持続性", "バリュエーション", "総合判断"),
        summary_label="最終判断",
    ),
)

_TEMPLATES: dict[TemplateLanguage, tuple[ReportSectionTemplate, ...]] = {
    "en": EARNINGS_TEMPLATE,
    "jp": JAPANESE_EARNINGS_TEMPLATE,
}


def get_earnings_template(language: str) -> tuple[ReportSectionTemplate, ...]:
    """Return the language-specific executable template."""
    if language not in _TEMPLATES:
        raise ValueError(f"Unsupported earnings template language: {language}")
    return _TEMPLATES[language]  # type: ignore[index]
