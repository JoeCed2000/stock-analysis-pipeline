import re, sys
from pathlib import Path
sys.path.insert(0, "/mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline")
from backend.earnings_deep_dive.mapper import _extract_markdown_table, _enrich_codex_table, _is_placeholder
from backend.earnings_deep_dive.template import get_earnings_template

md = Path("/mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline/analyses/2026-05-07_MSFT_Microsoft_Corp/07_final_report/earnings_deep_dive.md").read_text()

# Parse same as regenerate_jp_v2.py
HEADING_TO_KEY = {
    "📊 EPS & Revenue": "EPS & Revenue",
    "🌟 Highlights & ⚠️ Lowlights": "Highlights",
    "🧠 Operating Metrics": "Operating Metrics",
    "💰 Cash Flow": "Cash Flow",
    "🎯 Capital Efficiency": "Capital Efficiency",
    "🧩 Segments": "Segments",
    "📈 Forward P/E": "Forward P/E",
    "📦 Backlog Quality": "Backlog",
    "🔮 Guidance": "Guidance",
    "🏆 Verdict": "Verdict",
}

parts = re.split(r"\n##\s+", md)
section_analysis = {}
for part in parts[1:]:
    lines = part.split("\n", 1)
    heading = lines[0].strip()
    content = lines[1].strip() if len(lines) > 1 else ""
    key = HEADING_TO_KEY.get(heading)
    if key:
        section_analysis[key] = content

# Simulate build_earnings_deep_dive_report logic
template = get_earnings_template("jp")
for section in template:
    if section.key in ("Operating Metrics", "Cash Flow"):
        analysis_text = section_analysis.get(section.key) or section_analysis.get(section.title)
        print(f"\n{'='*60}")
        print(f"Section: {section.key}")
        print(f"  analysis_text found: {analysis_text is not None}")
        if analysis_text:
            print(f"  analysis_text starts with: {analysis_text[:80]}")
            print(f"  template table_columns: {section.table_columns}")
        
        codex_table = _extract_markdown_table(analysis_text, section.table_columns) if analysis_text else None
        print(f"  codex_table found: {codex_table is not None}")
        if codex_table:
            print(f"  codex_table rows: {len(codex_table.rows)}")
            for row in codex_table.rows[:3]:
                print(f"    {row.label}: {row.cells}")
        else:
            print(f"  → Would fall back to _rows_for_section")
