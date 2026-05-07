"""Regenerate EN+JP PDFs with proper section_analysis key mapping."""
import json, re, sys
sys.path.insert(0, '.')
from pathlib import Path
from backend.pipeline import _extract_quarterly_comparison
from backend.earnings_deep_dive.mapper import build_earnings_deep_dive_report
from backend.earnings_deep_dive.pdf_renderer import render_earnings_deep_dive_pdf
from backend.earnings_deep_dive.schemas import FinancialMetrics
from backend.earnings_deep_dive.template import JAPANESE_EARNINGS_TEMPLATE, EARNINGS_TEMPLATE
import fitz

def build_section_key_map(template):
    key_map = {}
    for section in template:
        key_map[section.key] = section.key
        key_map[section.title] = section.key
    return key_map

def parse_markdown_to_sections(md_text, key_map):
    sections = {}
    current_key = None
    current_text = []
    for line in md_text.split('\n'):
        if line.startswith('## '):
            if current_key and current_text:
                sections[current_key] = '\n'.join(current_text)
            heading = line[3:].strip()
            current_key = None
            current_text = [line]
            for map_key, section_key in key_map.items():
                if map_key.lower() in heading.lower():
                    current_key = section_key
                    break
            if current_key is None:
                simple = re.sub(r'[^\w\s&]', '', heading).strip()
                for map_key, section_key in key_map.items():
                    if map_key.lower() in simple.lower():
                        current_key = section_key
                        break
        elif current_key:
            current_text.append(line)
    if current_key and current_text:
        sections[current_key] = '\n'.join(current_text)
    return sections

quarterly = _extract_quarterly_comparison('MSFT')
metrics = FinancialMetrics(**quarterly)

# ---- JP version ----
jp_md = Path('analyses/2026-05-07_MSFT_Microsoft_Corp/07_final_report/earnings_deep_dive.md').read_text()
jp_key_map = build_section_key_map(JAPANESE_EARNINGS_TEMPLATE)
jp_sections = parse_markdown_to_sections(jp_md, jp_key_map)

jp_report = build_earnings_deep_dive_report(
    ticker='MSFT', company='Microsoft Corporation', quarter='FY2026 Q3',
    metrics=metrics,
    transcript_url='https://stockanalysis.com/stocks/msft/transcripts/547930-q3-2026/',
    language='jp',
    section_analysis=jp_sections,
)
jp_pdf = Path('analyses/2026-05-07_MSFT_Microsoft_Corp/07_final_report/earnings_deep_dive_jp_v2.pdf')
render_earnings_deep_dive_pdf(jp_report, str(jp_pdf))
jp_missing = sum(page.get_text().count('データ未取得') for page in fitz.open(jp_pdf))
print(f'JP: {jp_pdf.stat().st_size} bytes, {jp_missing} データ未取得')

# ---- EN version ----
en_resp = json.loads(Path('/tmp/deep_dive_en_response.json').read_text())
en_md = en_resp.get('report_markdown', '')
en_key_map = build_section_key_map(EARNINGS_TEMPLATE)
en_sections = parse_markdown_to_sections(en_md, en_key_map)
print(f'EN sections: {list(en_sections.keys())}')

en_report = build_earnings_deep_dive_report(
    ticker='MSFT', company='Microsoft Corporation', quarter='FY2026 Q3',
    metrics=metrics,
    transcript_url='https://stockanalysis.com/stocks/msft/transcripts/547930-q3-2026/',
    language='en',
    section_analysis=en_sections,
)
en_pdf = Path('analyses/2026-05-07_MSFT_Microsoft_Corp/07_final_report/earnings_deep_dive_en_v2.pdf')
render_earnings_deep_dive_pdf(en_report, str(en_pdf))
en_missing = sum(page.get_text().count('DATA NOT AVAILABLE') + page.get_text().count('Not disclosed') for page in fitz.open(en_pdf))
print(f'EN: {en_pdf.stat().st_size} bytes, {en_missing} DATA NOT AVAILABLE/Not disclosed')

# Show remaining JP data missing
doc = fitz.open(jp_pdf)
for page in doc:
    text = page.get_text()
    if 'データ未取得' in text:
        for line in text.split('\n'):
            if 'データ未取得' in line:
                print(f'  JP: {line.strip()[:100]}')
