#!/usr/bin/env python3
"""Deterministic proof for t_e4cbec09 Quality scope decision."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "feedback-audits" / "quality-section-scope.md"
PDF_RENDERER = ROOT / "backend" / "earnings_deep_dive" / "pdf_renderer.py"
PROMPTS = ROOT / "backend" / "earnings_deep_dive" / "prompts.py"
TEMPLATE = ROOT / "backend" / "earnings_deep_dive" / "template.py"
VALIDATOR = ROOT / "backend" / "earnings_deep_dive" / "deep_dive_validator.py"

required_doc_phrases = [
    "Remove the client-visible `Quality` block only from Earnings Deep-Dive PDF output",
    "Peer Benchmark `Quality` dimension",
    "Do not remove or rename",
    "`Data Quality`",
    "`Backlog Quality`",
    "`Capital Efficiency`",
    "no runtime implementation in this card",
    "WIKI_EVIDENCE",
    "GRAPH_EVIDENCE",
    "SYMBOL_PLAN",
    "Child-card rule",
]

for path in (DOC, PDF_RENDERER, PROMPTS, TEMPLATE, VALIDATOR):
    if not path.exists():
        raise SystemExit(f"missing required file: {path.relative_to(ROOT)}")

text = DOC.read_text(encoding="utf-8")
missing = [phrase for phrase in required_doc_phrases if phrase not in text]
if missing:
    raise SystemExit(f"decision doc missing required phrases: {missing}")

renderer = PDF_RENDERER.read_text(encoding="utf-8")
if 'translate("Quality", lang), pb.relative_quality_label' not in renderer:
    raise SystemExit("expected current Peer Benchmark Quality renderer anchor not found")
if 'def render_data_quality(' not in renderer or 'translate("Data Quality", lang)' not in renderer:
    raise SystemExit("expected Data Quality renderer anchor not found")

prompts = PROMPTS.read_text(encoding="utf-8")
for section in ('"Capital Efficiency"', '"Backlog": "Backlog Quality"'):
    if section not in prompts:
        raise SystemExit(f"expected prompts section anchor missing: {section}")

template = TEMPLATE.read_text(encoding="utf-8")
if 'TEMPLATE_SECTION_KEYS' not in template or '"Capital Efficiency"' not in template:
    raise SystemExit("expected template section anchors missing")

validator = VALIDATOR.read_text(encoding="utf-8")
if 'FORBIDDEN_QUALITY_PATTERNS' not in validator or 'Backlog Quality' not in validator:
    raise SystemExit("expected validator quality guard anchors missing")

print("VERIFY_T_E4CBEC09_READY")
