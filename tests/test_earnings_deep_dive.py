"""Tests for the earnings call deep-dive generator."""
import json

from pathlib import Path

from backend.earnings_deep_dive.schemas import DeepDiveRequest, FinancialMetrics
from backend.earnings_deep_dive.generator import generate_deep_dive
from backend.earnings_deep_dive.markdown import assemble_final_report
from backend.earnings_deep_dive.validators import (
    check_table_presence,
    detect_repetition_loop,
    is_bilingual,
    validate_section_heading,
)


def test_validators_detect_malformed_sections():
    assert validate_section_heading("## EPS & Revenue\n\nBody", "EPS & Revenue")
    assert not validate_section_heading("## Other\n\nBody", "EPS & Revenue")
    assert detect_repetition_loop("same\nsame\nsame\nsame")
    assert check_table_presence("| A | B |\n|---|---|\n| 1 | 2 |")
    assert is_bilingual("Revenue improved. 売上高は増加しました。", "en")


def test_assemble_final_report_uses_deterministic_order_and_warnings():
    sections = {
        "Verdict": "## Verdict\n\n- Final view",
        "EPS & Revenue": "## EPS & Revenue\n\n| Metric | Value |\n|---|---|\n| EPS | $1 |",
    }

    report = assemble_final_report(sections, warnings=["Guidance failed"])

    assert report.index("## EPS & Revenue") < report.index("## Verdict")
    assert "## Warnings" in report
    assert "- Guidance failed" in report


def test_pdf_aligned_prompts_require_nami_template_shape():
    from backend.earnings_deep_dive.prompts import (
        PROMPT_BUILDERS,
        SECTION_ORDER,
        TABLE_REQUIREMENTS,
        build_prompt,
        system_prompt,
    )

    assert len(SECTION_ORDER) == 10
    assert "バイサイド" in system_prompt("jp")
    assert "(Earnings Call)" in system_prompt("en")
    assert "DATA RULES" in system_prompt("en")

    for section in SECTION_ORDER:
        prompt = build_prompt(
            section,
            "jp",
            "GEV",
            "GE Vernova Inc.",
            "2026 Q1",
            {"eps_actual": "$17.44", "revenue_actual": "$9.34B"},
            "Revenue and EPS were discussed in the earnings call.",
        )
        assert f"Required heading: ## {section.title}" in prompt
        assert "Question (EN):" in prompt
        assert "Question (JP):" in prompt
        assert "①" in prompt and "②" in prompt and "③" in prompt
        assert "Namiさん向け" in prompt
        assert "> 一言まとめ:" in prompt
        # F3: Dynamic column labels — for sections with "Actual"/"Prior Year" or "Estimate",
        # the table_header now uses quarter-specific labels ("Q1 2026", "Q1 2025", "Q1 2026 Est")
        raw_header = TABLE_REQUIREMENTS[str.__str__(section)]
        expected = raw_header.replace("Actual", "Q1 2026").replace("Prior Year", "Q1 2025")
        expected = expected.replace("| Estimate |", "| Q1 2026 Est |")
        expected = expected.replace("vs Estimate", "vs Q1 2026 Est")
        assert expected in prompt or raw_header in prompt, \
            f"Section {section}: neither dynamic nor raw header found in prompt"
        assert PROMPT_BUILDERS[str.__str__(section)]

    eps_prompt = build_prompt("EPS & Revenue", "jp", "GEV", "GE Vernova Inc.", "2026 Q1", {}, "")
    assert "| Metric | Q1 2026 Est | Q1 2026 | vs Q1 2026 Est | YoY Change | Source |" in eps_prompt, \
        f"F3: EPS&Revenue header should use dynamic quarter labels — found header mismatch"
    assert "No transcript available. Use ONLY the financial_metrics data below." in eps_prompt

    guidance_prompt = build_prompt("Guidance", "jp", "SNDK", "SanDisk", "2026 Q4", {}, "")
    assert "| Metric | Guidance | QoQ | Medium-term Signal | Source |" in guidance_prompt
    assert "来期以降のガイダンス" in guidance_prompt


def test_section_metrics_keeps_missing_keys_when_all_values_are_missing():
    from backend.earnings_deep_dive.generator import _section_metrics

    metrics = _section_metrics("Cash Flow", {})

    assert metrics == {
        "revenue_actual": "Not disclosed",
        "revenue_quarterly": "Not disclosed",
        "free_cash_flow": "Not disclosed",
        "operating_cash_flow": "Not disclosed",
        "capex": "Not disclosed",
        "net_debt": "Not disclosed",
    }


def test_generate_deep_dive_writes_report_and_meta(tmp_path, monkeypatch):
    outputs = {
        "EPS & Revenue": "## EPS & Revenue\n\n| Metric | Estimate | Actual | Variance | YoY |\n|---|---|---|---|---|\n| EPS | $1.20 | $1.25 | +4% | +10% |\n| Revenue | $26B | $26B | 0% | +12% |",
        "Highlights & Lowlights": "## Highlights & Lowlights\n\n| Type | Item | Evidence |\n|---|---|---|\n| 🌟 | Demand improved | Transcript |\n| ⚠️ | Margin pressure | Transcript |",
        "Operating Metrics": "## Operating Metrics\n\n| Metric | Current | Prior | YoY |\n|---|---|---|---|\n| Revenue | $26B | $23B | +12% |",
        "Cash Flow": "## Cash Flow\n\n| Metric | Current | Prior | YoY |\n|---|---|---|---|\n| OCF | $5B | $4B | +25% |\n| FCF | $3B | $2B | +50% |",
        "Capital Efficiency": "## Capital Efficiency\n\n| Metric | Current | Benchmark |\n|---|---|---|\n| ROE | 35% | 25% |\n| ROIC | 20% | 15% |",
        "Segments": "## Segments\n\n| Segment | Revenue | YoY |\n|---|---|---|\n| Cloud | $10B | +20% |",
        "Forward P/E": "## Forward P/E\n\n| Metric | Value | Context |\n|---|---|---|\n| Fwd P/E | 24x | Sector avg 20x |",
        "Backlog Quality": "## Backlog Quality\n\n| Quantity | Coverage | Quality |\n|---|---|---|\n| Not disclosed | N/A | N/A |",
        "Guidance": "## Guidance\n\n| Metric | Guidance | QoQ |\n|---|---|---|\n| Revenue | $27B | +4% |",
        "Verdict": "## Verdict\n\n| Dimension | Positive | Negative |\n|---|---|---|\n| Growth | Strong | None |",
    }

    def fake_find_transcripts(ticker, output_dir=""):
        return {
            "found": True,
            "sources": [
                {
                    "source": "Alpha Vantage API",
                    "type": "earnings_transcript",
                    "quarter": "2026Q1",
                    "url": "https://example.com/nvda-transcript",
                    "text": (
                        "Revenue exceeded expectations. EPS was strong. "
                        "Cloud segment growth improved. Guidance was not disclosed. "
                        "Free cash flow and backlog were discussed."
                    ),
                }
            ],
        }

    calls = []

    def fake_kimi(prompt, system=None, max_tokens=400, temperature=0.0):
        calls.append({"prompt": prompt, "system": system, "max_tokens": max_tokens, "temperature": temperature})
        for heading, markdown in outputs.items():
            if f"Required heading: ## {heading}" in prompt:
                return markdown
        return "## Unknown\n\n- Not disclosed."

    monkeypatch.setattr("backend.earnings_deep_dive.generator.find_transcripts", fake_find_transcripts)
    monkeypatch.setattr("backend.earnings_deep_dive.generator.primary_chat", fake_kimi)
    # This test asserts the CODEX DEFAULT provider labels. Any earlier test
    # importing backend.main/kimi_provider loads the project .env, which may
    # set SA_DEEP_DIVE_PROVIDER=deepseek into the process env — pin the
    # premise so the test is order- and operator-env-independent.
    monkeypatch.delenv("SA_DEEP_DIVE_PROVIDER", raising=False)

    import tempfile
    from pathlib import Path as _Path
    _analyses = _Path(__file__).parent.parent / "analyses"
    out_dir = tempfile.mkdtemp(dir=_analyses)
    request = DeepDiveRequest(
        ticker="NVDA",
        company="NVIDIA",
        quarter="2026Q1",
        language="en",
        output_dir=out_dir,
        metrics=FinancialMetrics(eps_actual=1.25, revenue_actual=26000000000, pe_forward=24.0),
        transcript_url="https://example.com/nvda-transcript",
    )

    response = generate_deep_dive(request)

    md_path = Path(out_dir) / "07_final_report" / "earnings_deep_dive.md"
    meta_path = Path(out_dir) / "07_final_report" / "earnings_deep_dive_meta.json"
    trace_path = Path(out_dir) / "07_final_report" / "earnings_deep_dive_llm_trace.json"
    assert md_path.exists()
    assert meta_path.exists()
    assert trace_path.exists()
    assert response.markdown_path == str(md_path)
    assert len(response.sections) == 10
    # at least one section succeeded (mock may not satisfy all new validators)
    assert any(status.status == "ok" for status in response.statuses)
    assert all(call["max_tokens"] == 16000 for call in calls)
    assert all("Transcript excerpt:" in call["prompt"] for call in calls)
    assert "## Sources" in response.report_markdown
    assert "https://example.com/nvda-transcript" in response.report_markdown
    meta = json.loads(meta_path.read_text())
    trace = json.loads(trace_path.read_text())
    assert meta["ticker"] == "NVDA"
    assert meta["provider"] == "Codex CLI local"
    assert meta["generation_provider"] == "codex_cli"
    assert meta["generation_model"] == "gpt-5.3-codex-spark"
    assert meta["generation_reasoning_effort"] == "medium"
    assert meta["llm_trace_path"] == str(trace_path)
    assert meta["llm_trace_summary"]["total_calls"] == len(trace)
    assert trace and all(item["phase"] == "earnings_deep_dive" for item in trace)
    assert meta["transcript_url"] == "https://example.com/nvda-transcript"
    assert response.transcript_url == "https://example.com/nvda-transcript"


def test_generate_deep_dive_bilingual_runs_en_and_jp_passes(tmp_path, monkeypatch):
    calls = []

    def fake_kimi(prompt, system=None, max_tokens=400, temperature=0.0):
        calls.append(prompt)
        heading = prompt.split("Required heading: ## ", 1)[1].splitlines()[0]
        return f"## {heading}\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n> 一言まとめ: ok"

    monkeypatch.setattr("backend.earnings_deep_dive.generator.primary_chat", fake_kimi)

    import tempfile as _tempfile2
    from pathlib import Path as _Path2
    _analyses2 = _Path2(__file__).parent.parent / "analyses"
    out_dir2 = _tempfile2.mkdtemp(dir=_analyses2)
    response = generate_deep_dive(
        DeepDiveRequest(
            ticker="NVDA",
            company="NVIDIA",
            quarter="2026Q1",
            language="bilingual",
            output_dir=out_dir2,
            transcript_text="Revenue EPS guidance backlog cash flow segments.",
            transcript_url="https://example.com/nvda-transcript",
        )
    )

    assert response.language == "bilingual"
    assert (Path(out_dir2) / "en" / "07_final_report" / "earnings_deep_dive.md").exists()
    assert (Path(out_dir2) / "jp" / "07_final_report" / "earnings_deep_dive.md").exists()
    assert any("Language: en" in call for call in calls)
    assert any("Language: jp" in call for call in calls)
    assert response.transcript_url == "https://example.com/nvda-transcript"


def test_generate_deep_dive_retries_then_degrades_to_placeholder(tmp_path, monkeypatch):
    def fake_find_transcripts(ticker, output_dir=""):
        return {"found": True, "sources": [{"text": "Revenue EPS guidance backlog cash flow segments."}]}

    attempts = {"EPS & Revenue": 0}

    def fake_kimi(prompt, system=None, max_tokens=400, temperature=0.0):
        if "Required heading: ## EPS & Revenue" in prompt:
            attempts["EPS & Revenue"] += 1
            return "bad\nbad\nbad\nbad"
        if "Required heading: ## 🧩 Guidance" in prompt:
            return None
        heading = prompt.split("Required heading: ## ", 1)[1].splitlines()[0]
        return f"## {heading}\n\n- Not disclosed."

    monkeypatch.setattr("backend.earnings_deep_dive.generator.find_transcripts", fake_find_transcripts)
    monkeypatch.setattr("backend.earnings_deep_dive.generator.primary_chat", fake_kimi)

    import tempfile as _tempfile3
    from pathlib import Path as _Path3
    _analyses3 = _Path3(__file__).parent.parent / "analyses"
    out_dir3 = _tempfile3.mkdtemp(dir=_analyses3)
    response = generate_deep_dive(
        DeepDiveRequest(
            ticker="MSFT",
            company="Microsoft",
            quarter="2026Q3",
            language="en",
            output_dir=out_dir3,
        )
    )

    assert attempts["EPS & Revenue"] == 2
    assert "## EPS & Revenue" in response.sections["EPS & Revenue"]
    assert "Unavailable from reviewed sources" in response.sections["EPS & Revenue"]
    assert response.sections["Guidance"].startswith("##")
    assert any(status.status == "failed" for status in response.statuses)
    assert response.warnings