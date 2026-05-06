"""Generate deterministic earnings deep-dive PDFs for local validation."""
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.earnings_deep_dive.mapper import build_earnings_deep_dive_report
from backend.earnings_deep_dive.pdf_renderer import render_earnings_deep_dive_pdf
from backend.earnings_deep_dive.schemas import FinancialMetrics


def _sample_metrics() -> FinancialMetrics:
    return FinancialMetrics(
        eps_estimate=3.10,
        eps_actual=3.46,
        eps_vs_estimate=0.116,
        eps_yoy=0.22,
        revenue_estimate=80_000_000_000,
        revenue_actual=82_900_000_000,
        revenue_yoy=0.183,
        gross_profit=56_000_000_000,
        gross_margin=0.676,
        opex=18_000_000_000,
        operating_income=38_400_000_000,
        operating_margin=0.463,
        net_income=101_800_000_000,
        operating_cash_flow=95_000_000_000,
        capex=23_400_000_000,
        free_cash_flow=71_600_000_000,
        net_debt=12_000_000_000,
        roe=0.35,
        roic=0.28,
        pe_forward=21.19,
        guidance="Revenue growth expected to remain double-digit.",
        segments={"Cloud": {"revenue": 45_000_000_000, "yoy": 0.26, "driver": "AI demand"}},
    )


def main() -> None:
    output_dir = Path("reports/generated")
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics = _sample_metrics()

    for language in ("en", "jp"):
        report = build_earnings_deep_dive_report(
            ticker="MSFT",
            company="Microsoft Corporation",
            quarter="FY2026 Q1",
            language=language,
            metrics=metrics,
            transcript_url="https://example.com/msft-transcript",
            generated_at="2026-05-06T00:00:00+00:00",
        )
        output_path = output_dir / f"final-report-{language}.pdf"
        render_earnings_deep_dive_pdf(report, output_path)

    (output_dir / "final-report.pdf").write_bytes((output_dir / "final-report-en.pdf").read_bytes())
    print(f"Generated {output_dir / 'final-report-en.pdf'}")
    print(f"Generated {output_dir / 'final-report-jp.pdf'}")
    print(f"Generated {output_dir / 'final-report.pdf'}")


if __name__ == "__main__":
    main()
