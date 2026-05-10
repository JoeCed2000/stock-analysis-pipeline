"""Benchmark each step of the deep-dive pipeline."""
import sys, os, time, json

sys.path.insert(0, '.')
os.chdir('/mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline')

from backend.sources_collector import get_yahoo_data_for_quarter
from backend.pipeline import _deep_dive_metrics
from backend.models import AnalysisResult
from datetime import datetime, timezone

timings = {}

# STEP 1: Data collection
t0 = time.time()
q_data = get_yahoo_data_for_quarter('NVDA', '2026Q1')
timings['1_yfinance_quarter'] = round(time.time() - t0, 2)

t0 = time.time()
metrics = _deep_dive_metrics(AnalysisResult(
    ticker='NVDA', company_name=q_data.get('company_name','NVIDIA Corp'),
    retrieved_at=datetime.now(timezone.utc).isoformat(),
    price=q_data.get('price'), currency=q_data.get('currency','USD'),
), q_data)
timings['2_metrics_build'] = round(time.time() - t0, 2)

# STEP 2: Transcript search
t0 = time.time()
from backend.earnings_deep_dive.generator import _load_transcript
from backend.earnings_deep_dive.schemas import DeepDiveRequest
req = DeepDiveRequest(ticker='NVDA', company='NVIDIA Corp', quarter='2026Q1',
                      language='en', output_dir='/tmp', metrics=metrics)
try:
    tx_text, tx_meta = _load_transcript(req)
    timings['3_transcript_search'] = round(time.time() - t0, 2)
    timings['3_transcript_found'] = bool(tx_text)
    timings['3_transcript_source'] = tx_meta.get('primary_source', 'none')
except Exception as e:
    timings['3_transcript_search'] = round(time.time() - t0, 2)
    timings['3_transcript_error'] = str(e)[:80]

# STEP 3: LLM generation (1 section only for extrapolation)
t0 = time.time()
from backend.earnings_deep_dive.generator import build_prompt, system_prompt, _section_metrics, SECTION_ORDER
from backend.earnings_deep_dive.generator import kimi_chat

section = SECTION_ORDER[0]
sector = str(metrics.model_dump().get('sector', '') or '')
industry = str(metrics.model_dump().get('industry', '') or '')
sys_prompt = system_prompt('en', sector, industry)
prompt = build_prompt(section, 'en', 'NVDA', 'NVIDIA Corp', '2026Q1',
                      _section_metrics(section, metrics.model_dump()), '')
output = kimi_chat(prompt, system=sys_prompt, max_tokens=4000)
timings['4_llm_1section'] = round(time.time() - t0, 2)
timings['4_llm_1section_chars'] = len(output) if output else 0

# STEP 4: Markdown → PDF (from existing file)
from backend.main import _find_analysis_dirs
matches = _find_analysis_dirs('NVDA')
md_path = os.path.join(str(matches[0]), '07_final_report', 'earnings_deep_dive.md')
if os.path.exists(md_path):
    md_size = os.path.getsize(md_path)
    timings['5_markdown_size_kb'] = round(md_size / 1024, 1)
    
    # Measure PDF render
    t0 = time.time()
    from backend.earnings_deep_dive.mapper import build_earnings_deep_dive_report
    from backend.earnings_deep_dive.pdf_renderer import render_earnings_deep_dive_pdf
    import re
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
    pdf_path = os.path.join(str(matches[0]), '07_final_report', 'earnings_deep_dive_bench.pdf')
    render_earnings_deep_dive_pdf(report_model, pdf_path)
    timings['6_pdf_render'] = round(time.time() - t0, 2)
    timings['6_pdf_size_kb'] = round(os.path.getsize(pdf_path) / 1024, 1)

# REPORT
print(json.dumps(timings, indent=2, default=str))

avg_llm = timings['4_llm_1section']
n = len(SECTION_ORDER)
est_llm = avg_llm * n
total = (timings['1_yfinance_quarter'] + timings['2_metrics_build'] +
         timings['3_transcript_search'] + est_llm + timings.get('6_pdf_render', 5))

print(f'\n{"="*60}')
print(f'📊 DEEP-DIVE PIPELINE TIMING BREAKDOWN')
print(f'{"="*60}')
print(f'  {"Step":<30} {"Time":>8}  {"%":>6}')
print(f'  {"─"*30} {"─"*8}  {"─"*6}')
print(f'  {"1. Data collection (yfinance)":<30} {timings["1_yfinance_quarter"]:>6.1f}s  {timings["1_yfinance_quarter"]/total*100:>5.1f}%')
print(f'  {"2. Metrics build":<30} {timings["2_metrics_build"]:>6.1f}s  {timings["2_metrics_build"]/total*100:>5.1f}%')
print(f'  {"3. Transcript search":<30} {timings["3_transcript_search"]:>6.1f}s  {timings["3_transcript_search"]/total*100:>5.1f}%')
print(f'  {"4. LLM ({n} sections)":<30} {est_llm:>6.0f}s  {est_llm/total*100:>5.1f}%')
if '6_pdf_render' in timings:
    print(f'  {"6. PDF render":<30} {timings["6_pdf_render"]:>6.1f}s  {timings["6_pdf_render"]/total*100:>5.1f}%')
print(f'  {"─"*30} {"─"*8}  {"─"*6}')
print(f'  {"TOTAL":<30} {total:>6.0f}s  {"100%":>6}')
print(f'{"="*60}')
print(f'Transcript source: {timings.get("3_transcript_source", "?")} | Found: {timings.get("3_transcript_found", "?")}')
print(f'LLM chars/section: {timings.get("4_llm_1section_chars", "?")} | Markdown: {timings.get("5_markdown_size_kb", "?")}KB')
print(f'PDF: {timings.get("6_pdf_size_kb", "?")}KB')
