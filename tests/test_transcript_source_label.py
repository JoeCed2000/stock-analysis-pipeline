"""Regression test for transcript source label / URL mismatch.

Bug fixed 2026-06-05: the PDF deep-dive rendered the label "Seeking Alpha"
in the transcript sources appendix even when the actual fetched URL was
stockanalysis.com (fallback). This breaks the audit trail: a user clicks
the "Seeking Alpha" link in the PDF and lands on stockanalysis.com.

Ced rule: SA cookies/auth → "Seeking Alpha"; StockAnalysis fallback →
"Seeking Alpha via StockAnalysis". Source label MUST match the actual URL.
"""
from backend.stockanalysis import search_transcripts, fetch_transcript


def test_stockanalysis_search_returns_via_label_not_plain_sa():
    """stockanalysis.search_transcripts() must label its results with
    'Seeking Alpha via StockAnalysis' (not 'Seeking Alpha'), because
    StockAnalysis is a distinct source, not a SA republisher.
    """
    # Search for NVDA — actual data, no mock. We just inspect the source label.
    results = search_transcripts("NVDA", limit=1)
    if not results:
        # No transcripts indexed for NVDA — that's OK, skip the test
        return
    first = results[0]
    url = (first.get("url") or "").lower()
    assert "stockanalysis.com" in url, f"Expected stockanalysis URL, got {url}"
    assert first.get("source") == "Seeking Alpha via StockAnalysis", (
        f"StockAnalysis search result must use 'via StockAnalysis' label, "
        f"got {first.get('source')!r}"
    )


def test_stockanalysis_fetch_returns_via_label_for_stockanalysis_url():
    """stockanalysis.fetch_transcript() called on a StockAnalysis URL must
    return source='Seeking Alpha via StockAnalysis'. Only when a parallel
    SA article URL is provided should the source be plain 'Seeking Alpha'.
    """
    results = search_transcripts("NVDA", limit=1)
    if not results:
        return
    url = results[0].get("url") or ""
    if not url:
        return
    data = fetch_transcript(url)
    assert data is not None
    src = (data.get("source") or "").lower()
    assert "via stockanalysis" in src, (
        f"StockAnalysis fetch must produce 'via StockAnalysis' label, got {data.get('source')!r}"
    )


def test_generator_domain_map_marks_stockanalysis_as_via():
    """The generator.py domain_map must classify stockanalysis.com as
    'Seeking Alpha via StockAnalysis', not plain 'Seeking Alpha'.
    """
    import re
    from pathlib import Path
    src = Path("backend/earnings_deep_dive/generator.py").read_text()
    # Find the domain_map block
    m = re.search(r'domain_map\s*=\s*\{(.*?)\}', src, re.DOTALL)
    assert m, "domain_map not found in generator.py"
    block = m.group(1)
    # Must contain "Seeking Alpha via StockAnalysis" mapping for stockanalysis.com
    assert '"stockanalysis.com": "Seeking Alpha via StockAnalysis"' in block, (
        "generator.py domain_map must map stockanalysis.com → 'Seeking Alpha via StockAnalysis'"
    )
    # Must NOT have a plain "Seeking Alpha" mapping for stockanalysis.com
    assert '"stockanalysis.com": "Seeking Alpha"' not in block, (
        "generator.py domain_map still maps stockanalysis.com → plain 'Seeking Alpha' (bug)"
    )


def test_mapper_domain_map_marks_stockanalysis_as_via():
    """The mapper.py DOMAIN_NAMES must classify stockanalysis.com as
    'Seeking Alpha via StockAnalysis', not plain 'Seeking Alpha'.
    """
    import re
    from pathlib import Path
    src = Path("backend/earnings_deep_dive/mapper.py").read_text()
    m = re.search(r'DOMAIN_NAMES\s*=\s*\{(.*?)\}', src, re.DOTALL)
    assert m, "DOMAIN_NAMES not found in mapper.py"
    block = m.group(1)
    assert '"stockanalysis.com": "Seeking Alpha via StockAnalysis"' in block, (
        "mapper.py DOMAIN_NAMES must map stockanalysis.com → 'Seeking Alpha via StockAnalysis'"
    )
    assert '"stockanalysis.com": "Seeking Alpha"' not in block, (
        "mapper.py DOMAIN_NAMES still maps stockanalysis.com → plain 'Seeking Alpha' (bug)"
    )


def test_requirements_txt_contains_patchright():
    """requirements.txt must declare patchright, the SA anti-bot dependency.
    Without it, `pip install -r requirements.txt` produces a venv that
    silently skips the SA transcript-fetch path (ModuleNotFoundError caught
    by try/except → logger.warning only).
    """
    from pathlib import Path
    reqs = Path("requirements.txt").read_text().lower()
    assert "patchright" in reqs, (
        "requirements.txt must declare patchright (SA anti-bot Playwright fork)"
    )
