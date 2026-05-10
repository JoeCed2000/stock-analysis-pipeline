"""Full deep-dive pipeline benchmark — Gemini Flash + parallelized LLM."""
import sys, os, time, json
sys.path.insert(0, '.')
os.chdir('/mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline')

from backend.sources_collector import get_yahoo_data_for_quarter
from backend.pipeline import _deep_dive_metrics
from backend.models import AnalysisResult
from backend.earnings_deep_dive.schemas import DeepDiveRequest
from backend.earnings_deep_dive.generator import generate_deep_dive
from datetime import datetime, timezone

timings = {}
TOTAL_START = time.time()

# Step 1+2: Data collection
t0 = time.time()
q_data = get_yahoo_data_for_quarter('NVDA', '2026Q1')
timings['data_collection'] = round(time.time() - t0, 1)

t0 = time.time()
metrics = _deep_dive_metrics(AnalysisResult(
    ticker='NVDA', company_name=q_data.get('company_name','NVIDIA Corp'),
    retrieved_at=datetime.now(timezone.utc).isoformat(),
    price=q_data.get('price'), currency=q_data.get('currency','USD'),
), q_data)
timings['metrics_build'] = round(time.time() - t0, 1)

# Step 3: Full deep-dive generation (LLM + PDF)
t0 = time.time()
from backend.main import _find_analysis_dirs
matches = _find_analysis_dirs('NVDA')
out_dir = str(matches[0])

req = DeepDiveRequest(
    ticker='NVDA', company=q_data.get('company_name','NVIDIA Corp'),
    quarter='2026Q1', language='en', output_dir=out_dir, metrics=metrics,
)
result = generate_deep_dive(req)
timings['llm_generation'] = round(time.time() - t0, 1)

# Step 4: PDF render
t0 = time.time()
from backend.earnings_deep_dive.mapper import build_earnings_deep_dive_report
from backend.earnings_deep_dive.pdf_renderer import render_earnings_deep_dive_pdf
import re

md_path = os.path.join(out_dir, '07_final_report', 'earnings_deep_dive.md')
with open(md_path) as f:
    md = f.read()
section_md = {}
cur = None
cur_text = []
for line in md.split('\n'):
    if line.startswith('## '):
        if cur:
            section_md[cur] = '\n'.join(cur_text)
        cur = line[3:].strip()
        cur_text = [line]
    elif cur:
        cur_text.append(line)
if cur:
    section_md[cur] = '\n'.join(cur_text)

report_model = build_earnings_deep_dive_report(
    ticker='NVDA', company='NVIDIA Corp', quarter='2026Q1',
    language='en', metrics=metrics, transcript_url='',
    section_analysis=section_md,
)
pdf_path = os.path.join(out_dir, '07_final_report', 'earnings_deep_dive_bench2.pdf')
render_earnings_deep_dive_pdf(report_model, pdf_path)
timings['pdf_render'] = round(time.time() - t0, 1)
timings['pdf_size_kb'] = round(os.path.getsize(pdf_path) / 1024, 1)

TOTAL = round(time.time() - TOTAL_START, 1)

# Report
print(json.dumps(timings, indent=2))
print(f'\n{"="*60}')
print(f'📊 FULL PIPELINE BENCHMARK (Gemini Flash + 3 workers)')
print(f'{"="*60}')
for label, t in timings.items():
    if isinstance(t, (int, float)):
        print(f'  {label:<25} {t:>6.1f}s  ({t/TOTAL*100:>5.1f}%)')
print(f'  {"─"*25} {"─"*6}  {"─"*6}')
print(f'  {"TOTAL":<25} {TOTAL:>6.1f}s  (100%)')
print(f'{"="*60}')
print(f'PDF: {timings.get("pdf_size_kb","?")}KB')
