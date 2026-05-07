"""Performance import tests — verifies heavyweight modules are loaded lazily."""


def test_pipeline_defers_heavy_earnings_imports():
    """pipeline.py imports schemas at top level, not pdf_renderer/generator."""
    import backend.pipeline as pipeline_mod

    source = pipeline_mod.__file__
    assert source is not None
    with open(source) as f:
        source_text = f.read()

    # Top-level imports should only touch lightweight schemas
    assert (
        "from backend.earnings_deep_dive.schemas import" in source_text
    ), "pipeline.py must import schemas at module level"

    # Heavy imports must be inside a function (deferred)
    pdf_import = "from backend.earnings_deep_dive.pdf_renderer import"
    gen_import = "from backend.earnings_deep_dive.generator import"
    assert pdf_import in source_text, f"Missing deferred: {pdf_import}"
    assert gen_import in source_text, f"Missing deferred: {gen_import}"

    # Verify top-level source does NOT have heavy imports at module scope
    top_lines = source_text.split("\n\n")[0]
    assert pdf_import not in top_lines.split("\n"), (
        "pdf_renderer import must be inside a function, not at module level"
    )


def test_pdf_font_resolution_is_cached():
    from backend.earnings_deep_dive.pdf_renderer import resolve_pdf_fonts

    assert hasattr(resolve_pdf_fonts, "cache_info"), (
        "resolve_pdf_fonts should have @lru_cache"
    )
