"""DeepSeek repetition-loop mitigation in per-section generation.

Regression context: DeepSeek v4 Pro intermittently enters a repetition loop
on long sections (observed on Segments). Both attempts then failed
'Repetition loop detected' and the section shipped as a placeholder, which
later failed markdown validation ('Missing table in section: ...').

Mitigation contract:
- attempt 1 repetitive -> retry with defensive params (higher temperature +
  explicit anti-loop instruction)
- attempt 2 repetitive too -> salvage: truncate the output at the start of
  the loop; accept only if the salvaged section still passes validation
- salvage impossible -> existing clean placeholder fallback, unchanged
- every salvage is recorded as an explicit warning in section metadata
- valid sections are never penalized
"""
import tempfile
from pathlib import Path

from backend.earnings_deep_dive.generator import generate_deep_dive
from backend.earnings_deep_dive.schemas import DeepDiveRequest, FinancialMetrics
from backend.earnings_deep_dive.validators import detect_repetition_loop

ANALYSES_DIR = Path(__file__).parent.parent / "analyses"

VALID_SECTION = (
    "## {heading}\n\n"
    "| Metric | Current | Prior |\n|---|---|---|\n| Revenue | $10B | $9B |\n\n"
    "Steady quarter with broad-based demand."
)

# Trailing loop AFTER valid content — salvageable by truncation.
TRAILING_LOOP_SECTION = (
    "## {heading}\n\n"
    "| Segment | Revenue | YoY |\n|---|---|---|\n| Cloud | $4.0B | +18% |\n\n"
    "Cloud led the quarter with enterprise adoption.\n"
    + "The segment momentum continued into next quarter.\n" * 30
)

# Loop BEFORE any table — truncation leaves no table, salvage must fail.
UNSALVAGEABLE_LOOP_SECTION = (
    "## {heading}\n\n"
    + "Loading segment data for the quarter.\n" * 30
    + "\n| Segment | Revenue |\n|---|---|\n| Cloud | $4.0B |\n"
)


def _heading_of(prompt: str) -> str:
    return prompt.split("Required heading: ## ", 1)[1].splitlines()[0]


def _fake_transcripts(ticker, output_dir=""):
    return {
        "found": True,
        "sources": [{
            "source": "Test Source",
            "type": "earnings_transcript",
            "quarter": "2026Q1",
            "url": "https://example.com/acme-transcript",
            "text": (
                "Revenue exceeded expectations. EPS was strong. "
                "Cloud segment growth improved. Guidance was raised. "
                "Free cash flow and backlog were discussed."
            ),
        }],
    }


def _run(monkeypatch, chat_fn):
    monkeypatch.setattr("backend.earnings_deep_dive.generator.find_transcripts", _fake_transcripts)
    monkeypatch.setattr("backend.earnings_deep_dive.generator.primary_chat", chat_fn)
    out_dir = tempfile.mkdtemp(dir=ANALYSES_DIR)
    return generate_deep_dive(DeepDiveRequest(
        ticker="ACME",
        company="Acme Corp",
        quarter="2026Q1",
        language="en",
        output_dir=out_dir,
        metrics=FinancialMetrics(eps_actual=2.10, revenue_actual=10_000_000_000, pe_forward=18.0),
        transcript_url="https://example.com/acme-transcript",
    ))


def _status_of(response, name):
    return next(s for s in response.statuses if s.name == name)


def test_persistent_trailing_loop_is_salvaged_not_placeholdered(monkeypatch):
    """Both attempts loop on one long section: the section must be salvaged
    by truncating the loop, keep its heading + table, and carry an explicit
    warning in metadata — not ship as a placeholder."""
    def chat_fn(prompt, system=None, max_tokens=400, temperature=0.0):
        heading = _heading_of(prompt)
        if heading.startswith("Segments"):
            return TRAILING_LOOP_SECTION.format(heading=heading)
        return VALID_SECTION.format(heading=heading)

    response = _run(monkeypatch, chat_fn)

    status = _status_of(response, "Segments")
    assert status.status == "salvaged", f"got {status.status} ({status.error})"
    assert status.warnings, "salvage must leave an explicit warning in metadata"
    content = response.sections["Segments"]
    assert not detect_repetition_loop(content)
    assert "| Cloud | $4.0B | +18% |" in content, "valid table must survive salvage"
    assert "placeholder" not in content.lower()


def test_repetition_retry_uses_defensive_temperature(monkeypatch):
    """Attempt 1 loops, attempt 2 is clean: the retry call must use a higher
    temperature than the first call, and the section ends retry_ok."""
    calls = []

    def chat_fn(prompt, system=None, max_tokens=400, temperature=0.0):
        heading = _heading_of(prompt)
        calls.append({"heading": heading, "temperature": temperature, "retry": "Retry instruction" in prompt})
        if heading.startswith("Segments") and "Retry instruction" not in prompt:
            return TRAILING_LOOP_SECTION.format(heading=heading)
        return VALID_SECTION.format(heading=heading)

    response = _run(monkeypatch, chat_fn)

    status = _status_of(response, "Segments")
    assert status.status == "retry_ok"
    seg_calls = [c for c in calls if c["heading"].startswith("Segments")]
    assert len(seg_calls) == 2
    assert seg_calls[1]["retry"] is True
    assert seg_calls[1]["temperature"] > seg_calls[0]["temperature"], \
        "repetition retry must use more defensive (higher) temperature"


def test_unsalvageable_loop_falls_back_to_clean_placeholder(monkeypatch):
    """When truncating the loop destroys the section (no table left), the
    existing placeholder fallback applies — no silent failure."""
    def chat_fn(prompt, system=None, max_tokens=400, temperature=0.0):
        heading = _heading_of(prompt)
        if heading.startswith("Segments"):
            return UNSALVAGEABLE_LOOP_SECTION.format(heading=heading)
        return VALID_SECTION.format(heading=heading)

    response = _run(monkeypatch, chat_fn)

    status = _status_of(response, "Segments")
    assert status.status == "failed"
    assert "Repetition loop" in (status.error or "")
    assert any(w.startswith("Segments") for w in response.warnings), \
        "placeholder fallback must surface a top-level warning"


def test_valid_sections_are_not_penalized(monkeypatch):
    """Clean outputs everywhere: every section is accepted on attempt 1 with
    the normal temperature, no salvage, no extra warnings."""
    calls = []

    def chat_fn(prompt, system=None, max_tokens=400, temperature=0.0):
        calls.append(temperature)
        return VALID_SECTION.format(heading=_heading_of(prompt))

    response = _run(monkeypatch, chat_fn)

    assert all(s.status == "ok" for s in response.statuses), \
        [(s.name, s.status, s.error) for s in response.statuses]
    assert all(s.attempts == 1 for s in response.statuses)
    assert all(not s.warnings for s in response.statuses)
    assert all(t == 0.3 for t in calls), "normal generation temperature must stay 0.3"


def test_clean_section_output_normalizes_unrenderable_punctuation():
    """DeepSeek emits typographic punctuation with no glyph in the PDF body
    font: U+2011 NON-BREAKING HYPHEN rendered as a box (274 of them in the
    2026-06-12 NVDA report: 'near□monopoly', 'data□center'). Normalize to
    renderable ASCII equivalents at section-cleaning time."""
    from backend.earnings_deep_dive.generator import _clean_section_output

    raw = (
        "## Segments\n\nNVIDIA's near‑monopoly in data‑center GPUs "
        "(supply‐chain, −5% move, 12 GW, 3 9nm)."
    )
    cleaned = _clean_section_output(raw, 6000)
    assert "‑" not in cleaned
    assert "‐" not in cleaned
    assert "−" not in cleaned
    assert " " not in cleaned
    assert " " not in cleaned
    assert "near-monopoly" in cleaned and "data-center" in cleaned
