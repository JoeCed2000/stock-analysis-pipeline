"""Performance baseline: instrument analyze_ticker_fast with per-step timing.

Runs 3 iterations and reports per-step + total timing.
Outputs: benchmarks/baseline_YYYYMMDD_HHMMSS.json

Usage: cd /mnt/c/Users/cedon/Documents/Codex/stock-analysis-pipeline && python3 benchmarks/bench_baseline.py
"""

import os
import sys
import json
import time
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List
from collections import defaultdict

# Ensure we're in the project root
project_root = Path(__file__).parent.parent.absolute()
os.chdir(project_root)
sys.path.insert(0, str(project_root))
os.environ["PYTHONPATH"] = str(project_root)

# Load .env
env_path = project_root / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

PARIS = datetime.now(timezone.utc).astimezone().tzinfo  # approximate

TICKERS = ["NVDA"]  # Use a single ticker with full data
N_RUNS = 3

class StepTimer:
    """Context manager that records elapsed wall-clock time."""
    def __init__(self, timings: Dict[str, List[float]], step_name: str):
        self.timings = timings
        self.step_name = step_name
    
    def __enter__(self):
        self.start = time.perf_counter()
        return self
    
    def __exit__(self, *args):
        elapsed = time.perf_counter() - self.start
        self.timings[self.step_name].append(elapsed)
        print(f"  [{self.step_name}] {elapsed:.2f}s")

timings: Dict[str, List[float]] = defaultdict(list)
all_total_times = []

for run in range(1, N_RUNS + 1):
    print(f"\n{'='*60}")
    print(f"RUN {run}/{N_RUNS}")
    print(f"{'='*60}")
    
    ticker = "NVDA"
    
    # Use a temp output dir to avoid polluting analyses/
    tmpdir = tempfile.mkdtemp(prefix=f"bench_run{run}_")
    
    t0 = time.perf_counter()
    
    # === Step 1: get_stock_data ===
    with StepTimer(timings, "1_get_stock_data"):
        from backend.sources_collector import get_stock_data
        yf_data = get_stock_data(ticker)
    
    currency = yf_data.get("currency", "USD")
    company_name = yf_data.get("company_name", ticker)
    price_native = yf_data.get("price")
    
    # === Step 2: get_edgar_financials ===
    with StepTimer(timings, "2_get_edgar_financials"):
        try:
            from backend.sources_collector import get_edgar_financials
            edgar = get_edgar_financials(ticker)
        except Exception as e:
            print(f"  edgar skipped: {e}")
            edgar = None
    
    # === Step 3: extract_10k + finnhub (parallel) ===
    import concurrent.futures as cf
    with StepTimer(timings, "3a_extract_10k"):
        try:
            from backend.sources_collector import extract_10k_sections
            sec_10k = extract_10k_sections(ticker, output_dir=tmpdir)
            mda_text = sec_10k.get("mda", "")
            risk_text = sec_10k.get("risk_factors", "")
            has_10k = len(mda_text) > 500
        except Exception as e:
            print(f"  10k failed: {e}")
            mda_text, risk_text, has_10k = "", "", False
    
    with StepTimer(timings, "3b_get_finnhub"):
        try:
            from backend.sources_collector import get_finnhub_data
            fh_data = get_finnhub_data(ticker)
        except Exception as e:
            print(f"  finnhub failed: {e}")
            fh_data = {}
    
    # === Step 4: Management analysis (Codex/Kimi) ===
    with StepTimer(timings, "4_management_analysis"):
        if has_10k:
            from backend.codex_provider import codex_analyze_management
            codex_data = codex_analyze_management(mda_text, risk_text)
            if not codex_data or codex_data.get("tone", "").startswith("DATA NOT AVAILABLE"):
                from backend.kimi_provider import kimi_analyze_management
                codex_data = kimi_analyze_management(mda_text, risk_text)
        else:
            codex_data = {"tone": "DATA NOT AVAILABLE", "confidence": "", "visibility": "", "risks": []}
    
    # === Step 5: Scoring ===
    with StepTimer(timings, "5_scoring"):
        from backend.scorer import score_ticker
        scoring = score_ticker({
            "financials": yf_data.get("financials", {}),
            "valuation": {
                "pe_current": yf_data.get("pe_current"),
                "pe_forward": yf_data.get("pe_forward"),
                "peg_ratio": yf_data.get("peg_ratio"),
            },
            "sector": yf_data.get("sector"),
            "industry": yf_data.get("industry"),
            "market_cap": yf_data.get("market_cap"),
            "price": yf_data.get("price"),
            "52w_high": yf_data.get("52w_high"),
        }, tone_data=codex_data if has_10k else None)
    
    # === Step 6: Transcripts ===
    with StepTimer(timings, "6_transcripts"):
        try:
            from backend.transcript_finder import find_transcripts
            transcript_results = find_transcripts(ticker, output_dir=tmpdir, company=company_name)
        except Exception as e:
            print(f"  transcripts skipped: {e}")
            transcript_results = {}
    
    # === Step 7: Deep Dive (Kimi + mapper + render) ===
    with StepTimer(timings, "7_deep_dive"):
        try:
            from backend.earnings_deep_dive.generator import generate_deep_dive
            from backend.earnings_deep_dive.mapper import build_earnings_deep_dive_report
            from backend.earnings_deep_dive.pdf_renderer import render_earnings_deep_dive_pdf
            from backend.earnings_deep_dive.schemas import DeepDiveRequest
            
            transcript_sources = transcript_results.get("sources", []) if isinstance(transcript_results, dict) else []
            best_text = ""
            best_source = {}
            for s in transcript_sources:
                text = s.get("text") or s.get("content") or ""
                if isinstance(text, str) and len(text) > len(best_text or ""):
                    best_text = text
                    best_source = s
            
            # Build metrics
            from backend.pipeline import _deep_dive_metrics
            
            # Mock AnalysisResult for metrics
            class FakeResult:
                pass
            fake_result = FakeResult()
            fake_result.financials = type('obj', (object,), {
                'revenue_quarterly': yf_data.get("financials", {}).get("revenue_quarterly"),
                'revenue_yoy_growth': yf_data.get("financials", {}).get("revenue_yoy_growth"),
                'gross_margin': yf_data.get("financials", {}).get("gross_margin"),
                'operating_margin': yf_data.get("financials", {}).get("operating_margin"),
                'net_income': yf_data.get("financials", {}).get("net_income"),
                'free_cash_flow': yf_data.get("financials", {}).get("free_cash_flow"),
            })()
            fake_result.scoring = scoring
            
            metrics = _deep_dive_metrics(fake_result, yf_data)
            
            if best_text:
                response = generate_deep_dive(
                    DeepDiveRequest(
                        ticker=ticker,
                        company=company_name,
                        quarter=best_source.get("quarter", "latest quarter"),
                        language="en",
                        output_dir=tmpdir,
                        metrics=metrics,
                        transcript_text=best_text,
                        transcript_url="",
                    )
                )
                
                pdf_path = os.path.join(tmpdir, "deep_dive.pdf")
                report_model = build_earnings_deep_dive_report(
                    ticker=ticker,
                    company=company_name,
                    quarter=best_source.get("quarter", "latest quarter"),
                    language="en",
                    metrics=metrics,
                    transcript_url="",
                    section_analysis=response.sections,
                )
                render_earnings_deep_dive_pdf(report_model, pdf_path)
                print(f"  deep_dive PDF: {os.path.getsize(pdf_path)} bytes")
            else:
                print("  deep_dive skipped: no transcript")
        except Exception as e:
            print(f"  deep_dive failed: {e}")
            import traceback
            traceback.print_exc()
    
    # === Step 8: Report + PDF generation ===
    with StepTimer(timings, "8_report_pdf"):
        try:
            from backend.pdf_generator import md_to_pdf
            report_md = os.path.join(tmpdir, "report.md")
            with open(report_md, "w") as f:
                f.write(f"# {ticker} Analysis Report\n\nScore: {scoring.total}/40\nDecision: {scoring.decision()}\n")
            md_to_pdf(report_md, report_md.replace(".md", ".pdf"), title=f"{ticker} Report")
        except Exception as e:
            print(f"  report failed: {e}")
    
    # === Step 9: ZIP packaging ===
    with StepTimer(timings, "9_zip"):
        try:
            import zipfile
            zip_path = os.path.join(tmpdir, "dossier.zip")
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(tmpdir):
                    for fn in files:
                        if fn != "dossier.zip":
                            fp = os.path.join(root, fn)
                            arcname = os.path.relpath(fp, tmpdir)
                            zf.write(fp, arcname)
            zip_size = os.path.getsize(zip_path)
            print(f"  ZIP: {zip_size} bytes")
        except Exception as e:
            print(f"  zip failed: {e}")
    
    total = time.perf_counter() - t0
    all_total_times.append(total)
    print(f"\n  >>> RUN {run} TOTAL: {total:.2f}s")
    
    # Cleanup temp dir
    shutil.rmtree(tmpdir, ignore_errors=True)

# === Summary ===
print(f"\n{'='*60}")
print("BASELINE SUMMARY")
print(f"{'='*60}")

for step in sorted(timings.keys()):
    vals = timings[step]
    avg = sum(vals) / len(vals)
    mn, mx = min(vals), max(vals)
    print(f"  {step:30s} avg={avg:6.2f}s  min={mn:6.2f}s  max={mx:6.2f}s  (n={len(vals)})")

avg_total = sum(all_total_times) / len(all_total_times) if all_total_times else 0
print(f"\n  {'TOTAL (avg)':30s} {avg_total:.2f}s  over {N_RUNS} runs")
print(f"  {'TOTAL (min)':30s} {min(all_total_times):.2f}s")
print(f"  {'TOTAL (max)':30s} {max(all_total_times):.2f}s")

# Save to JSON
output = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "ticker": TICKERS[0],
    "n_runs": N_RUNS,
    "total_avg_s": round(avg_total, 2),
    "total_min_s": round(min(all_total_times), 2),
    "total_max_s": round(max(all_total_times), 2),
    "per_step": {step: {
        "avg": round(sum(vals) / len(vals), 2),
        "min": round(min(vals), 2),
        "max": round(max(vals), 2),
        "n": len(vals),
    } for step, vals in sorted(timings.items())},
}

os.makedirs("benchmarks", exist_ok=True)
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
report_path = f"benchmarks/baseline_{ts}.json"
with open(report_path, "w") as f:
    json.dump(output, f, indent=2)

print(f"\nReport saved: {report_path}")
