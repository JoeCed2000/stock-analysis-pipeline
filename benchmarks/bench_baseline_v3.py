"""Performance baseline v3: 3 scenarios × 3 iterations.

Scenarios:
  S1 — Full ticker analysis via analyze_ticker_fast (NVDA + AAPL)
  S2 — Earnings deep-dive generation (NVDA, transcript-dependent)
  S3 — PDF report generation (render + filesize)

Captures: wall-clock time, CPU %, peak RSS, API call counts, file I/O volumes.

NO OPTIMIZATION CHANGES. MEASURE ONLY.

Usage:
  cd /home/ced/codex-projects/stock-analysis-pipeline
  .venv/bin/python3 benchmarks/bench_baseline_v3.py
"""

import os
import sys
import json
import time
import shutil
import tempfile
import resource
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict

# ── Setup ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

N_RUNS = 3
TICKERS_S1 = ["NVDA", "AAPL"]
DEEP_DIVE_TICKER = "NVDA"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_JSON = PROJECT_ROOT / "benchmarks" / f"baseline_v3_{TIMESTAMP}.json"


# ── Helpers ──────────────────────────────────────────────────────────────

def cpu_usage() -> float:
    """Current process CPU usage as percentage (0-100)."""
    try:
        # /proc/self/stat fields: utime(14) + stime(15) in clock ticks
        with open("/proc/self/stat") as f:
            parts = f.read().split()
        utime = int(parts[13])
        stime = int(parts[14])
        ticks = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
        # Approximate: since process start, not per-interval. Better than nothing.
        return (utime + stime) / ticks
    except Exception:
        return -1.0


def peak_rss_mb() -> float:
    """Peak RSS in MB."""
    try:
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except Exception:
        return -1.0


def api_call_count_marker() -> Dict[str, int]:
    """Read API call counters from marker files if they exist."""
    result = {}
    marker_dir = PROJECT_ROOT / ".api_markers"
    if marker_dir.exists():
        for f in marker_dir.iterdir():
            if f.is_file():
                try:
                    result[f.name] = int(f.read_text().strip())
                except Exception:
                    pass
    return result


class BenchmarkResult:
    """Holds results for one scenario iteration."""
    def __init__(self, scenario: str, ticker: str, run: int):
        self.scenario = scenario
        self.ticker = ticker
        self.run = run
        self.wall_s: float = 0.0
        self.cpu_pct: float = 0.0
        self.peak_rss_mb: float = 0.0
        self.output_size_kb: float = 0.0
        self.api_calls: Dict[str, int] = {}
        self.file_count: int = 0
        self.notes: str = ""
        self.success: bool = False

    def to_dict(self) -> Dict:
        return {
            "scenario": self.scenario,
            "ticker": self.ticker,
            "run": self.run,
            "wall_s": round(self.wall_s, 2),
            "cpu_pct": round(self.cpu_pct, 1),
            "peak_rss_mb": round(self.peak_rss_mb, 1),
            "output_size_kb": round(self.output_size_kb, 1),
            "api_calls": self.api_calls,
            "file_count": self.file_count,
            "notes": self.notes,
            "success": self.success,
        }


def count_output_files(d: str) -> int:
    """Count files in directory tree."""
    c = 0
    try:
        for root, dirs, files in os.walk(d):
            c += len(files)
    except Exception:
        pass
    return c


def dir_size_kb(d: str) -> float:
    """Total size of directory tree in KB."""
    total = 0
    try:
        for root, dirs, files in os.walk(d):
            for fn in files:
                fp = os.path.join(root, fn)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
    except Exception:
        pass
    return total / 1024.0


# ── Scenario Runners ─────────────────────────────────────────────────────

def run_s1_full_analysis(ticker: str, run_idx: int) -> BenchmarkResult:
    """S1: Full ticker analysis via analyze_ticker_fast."""
    result = BenchmarkResult("S1_full_analysis", ticker, run_idx)

    # Clear __pycache__ for cold run measurement accuracy
    cache_dirs = list(PROJECT_ROOT.rglob("__pycache__"))
    for cd in cache_dirs:
        try:
            shutil.rmtree(cd)
        except Exception:
            pass

    tmpdir = tempfile.mkdtemp(prefix=f"bench_s1_{ticker}_run{run_idx}_")

    api_before = api_call_count_marker()
    t0 = time.perf_counter()
    cpu_before = cpu_usage()
    rss_before = peak_rss_mb()

    try:
        from backend.pipeline import analyze_ticker_fast

        analysis = analyze_ticker_fast(
            ticker=ticker,
            output_base=tmpdir,
            language="en",
            force_refresh=(run_idx == 1),  # cold first run only
        )

        result.wall_s = time.perf_counter() - t0
        result.cpu_pct = cpu_usage() - cpu_before
        result.peak_rss_mb = peak_rss_mb()
        result.file_count = count_output_files(tmpdir)
        result.output_size_kb = dir_size_kb(tmpdir)
        result.success = True

        api_after = api_call_count_marker()
        result.api_calls = {
            k: api_after.get(k, 0) - api_before.get(k, 0)
            for k in set(api_before) | set(api_after)
        }

        notes_parts = []
        if hasattr(analysis, 'scoring') and analysis.scoring:
            notes_parts.append(f"Score={analysis.scoring.total}/40")
        if hasattr(analysis, 'scoring') and hasattr(analysis.scoring, 'decision'):
            notes_parts.append(str(analysis.scoring.decision()))
        result.notes = " | ".join(notes_parts) if notes_parts else "OK"

    except Exception as e:
        result.wall_s = time.perf_counter() - t0
        result.notes = f"FAILED: {e}"
        result.success = False

    shutil.rmtree(tmpdir, ignore_errors=True)
    return result


def run_s2_deep_dive(ticker: str, run_idx: int) -> BenchmarkResult:
    """S2: Earnings deep-dive generation (LLM + mapper + render)."""
    result = BenchmarkResult("S2_deep_dive", ticker, run_idx)

    tmpdir = os.path.join(PROJECT_ROOT, "analyses", f"bench_s2_{ticker}_run{run_idx}_{int(time.time())}")
    os.makedirs(tmpdir, exist_ok=True)

    api_before = api_call_count_marker()
    t0 = time.perf_counter()
    cpu_before = cpu_usage()

    try:
        from backend.sources_collector import get_stock_data
        from backend.pipeline import _deep_dive_metrics
        from backend.transcript_finder import find_transcripts
        from backend.earnings_deep_dive.generator import generate_deep_dive
        from backend.earnings_deep_dive.mapper import build_earnings_deep_dive_report
        from backend.earnings_deep_dive.pdf_renderer import render_earnings_deep_dive_pdf
        from backend.earnings_deep_dive.schemas import DeepDiveRequest

        # 2a: Get stock data
        yf_data = get_stock_data(ticker)

        # 2b: Find transcripts
        company = yf_data.get("company_name", ticker)
        transcript_results = find_transcripts(ticker, output_dir=tmpdir, company=company)

        # Find best transcript
        transcript_sources = transcript_results.get("sources", []) if isinstance(transcript_results, dict) else []
        best_text = ""
        best_source = {}
        for s in transcript_sources:
            text = s.get("text") or s.get("content") or ""
            if isinstance(text, str) and len(text) > len(best_text or ""):
                best_text = text
                best_source = s

        if not best_text or len(best_text) < 200:
            result.wall_s = time.perf_counter() - t0
            result.notes = "fast-fail: no transcript available (ALPHA_VANTAGE not set, no free source)"
            result.success = True  # Valid measurement
            result.file_count = count_output_files(tmpdir)
            shutil.rmtree(tmpdir, ignore_errors=True)
            return result

        # 2c: Build metrics
        from backend.pipeline import AnalysisResult

        class FakeResult:
            pass

        fake = FakeResult()
        fake.financials = type('obj', (object,), {
            'revenue_quarterly': yf_data.get("financials", {}).get("revenue_quarterly"),
            'revenue_yoy_growth': yf_data.get("financials", {}).get("revenue_yoy_growth"),
            'gross_margin': yf_data.get("financials", {}).get("gross_margin"),
            'operating_margin': yf_data.get("financials", {}).get("operating_margin"),
            'net_income': yf_data.get("financials", {}).get("net_income"),
            'free_cash_flow': yf_data.get("financials", {}).get("free_cash_flow"),
        })()
        fake.scoring = None  # Not used in deep-dive

        metrics = _deep_dive_metrics(fake, yf_data)

        # 2d: Generate deep dive
        quarter = best_source.get("quarter", "latest quarter")
        request = DeepDiveRequest(
            ticker=ticker,
            company=company,
            quarter=quarter,
            language="en",
            output_dir=tmpdir,
            metrics=metrics,
            transcript_text=best_text,
            transcript_url="",
        )

        response = generate_deep_dive(request)

        # 2e: Build report + render PDF
        report_model = build_earnings_deep_dive_report(
            ticker=ticker,
            company=company,
            quarter=quarter,
            language="en",
            metrics=metrics,
            transcript_url="",
            section_analysis=response.sections,
        )

        pdf_path = os.path.join(tmpdir, "deep_dive.pdf")
        render_earnings_deep_dive_pdf(report_model, pdf_path)

        result.wall_s = time.perf_counter() - t0
        result.output_size_kb = os.path.getsize(pdf_path) / 1024.0 if os.path.exists(pdf_path) else 0
        result.file_count = count_output_files(tmpdir)
        result.peak_rss_mb = peak_rss_mb()
        result.success = True
        result.notes = f"PDF={result.output_size_kb:.0f}KB | sections={len(response.sections)} | {quarter}"

    except Exception as e:
        result.wall_s = time.perf_counter() - t0
        result.notes = f"FAILED: {e}"
        result.success = False

    api_after = api_call_count_marker()
    result.api_calls = {
        k: api_after.get(k, 0) - api_before.get(k, 0)
        for k in set(api_before) | set(api_after)
    }

    shutil.rmtree(tmpdir, ignore_errors=True)
    return result


def run_s3_pdf_render(ticker: str, run_idx: int) -> BenchmarkResult:
    """S3: PDF report generation from markdown (local, no API calls)."""
    result = BenchmarkResult("S3_pdf_render", ticker, run_idx)

    tmpdir = tempfile.mkdtemp(prefix=f"bench_s3_{ticker}_run{run_idx}_")

    t0 = time.perf_counter()

    try:
        from backend.pdf_generator import md_to_pdf

        # Create a realistic markdown report
        md_content = f"""# {ticker} Stock Analysis Report

## Summary
- **Ticker:** {ticker}
- **Date:** {datetime.now().strftime('%Y-%m-%d')}
- **Score:** 34/40 — BUY

## Financial Highlights
| Metric | Value |
|--------|-------|
| Revenue (TTM) | $130.5B |
| Net Income | $72.9B |
| Gross Margin | 75.9% |
| P/E (TTM) | 38.5 |
| Market Cap | $3.2T |

## Scoring Breakdown
| Pillar | Score | Max |
|--------|-------|-----|
| Finance | 14 | 16 |
| Momentum | 7 | 8 |
| Risk | 6 | 8 |
| Management | 7 | 8 |
| **Total** | **34** | **40** |

## Segment Analysis
### Data Center
Revenue: $47.5B (+217% YoY). Strong growth driven by Hopper and Blackwell.

### Gaming
Revenue: $2.6B (-8% YoY). Consumer GPU demand softening.

## Risk Factors
1. **Supply Chain Concentration** — TSMC single-source for advanced nodes
2. **Export Controls** — China restrictions impact ~15% of Data Center revenue
3. **Competition** — AMD MI300X, custom ASICs (Google TPU, Amazon Trainium)

## Recommendation: BUY
NVIDIA remains the dominant AI infrastructure provider.
"""

        md_path = os.path.join(tmpdir, "report.md")
        with open(md_path, "w") as f:
            f.write(md_content)

        pdf_path = os.path.join(tmpdir, "report.pdf")
        md_to_pdf(md_path, pdf_path, title=f"{ticker} Analysis Report")

        result.wall_s = time.perf_counter() - t0
        result.output_size_kb = os.path.getsize(pdf_path) / 1024.0 if os.path.exists(pdf_path) else 0
        result.peak_rss_mb = peak_rss_mb()
        result.file_count = count_output_files(tmpdir)
        result.success = True
        result.notes = f"PDF={result.output_size_kb:.0f}KB | {len(md_content)} chars markdown"

    except Exception as e:
        result.wall_s = time.perf_counter() - t0
        result.notes = f"FAILED: {e}"
        result.success = False

    shutil.rmtree(tmpdir, ignore_errors=True)
    return result


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    all_results: List[BenchmarkResult] = []

    print("=" * 70)
    print("PERFORMANCE BASELINE V3")
    print(f"Start: {datetime.now().isoformat()}")
    print(f"Project: {PROJECT_ROOT}")
    print(f"Runs per scenario: {N_RUNS}")
    print("=" * 70)

    # ── S1: Full analysis ──
    for ticker in TICKERS_S1:
        print(f"\n── S1: Full Analysis — {ticker} ──")
        for run in range(1, N_RUNS + 1):
            print(f"  Run {run}/{N_RUNS}...", end=" ", flush=True)
            r = run_s1_full_analysis(ticker, run)
            all_results.append(r)
            status = "✓" if r.success else "✗"
            print(f"{status} {r.wall_s:.2f}s | {r.notes}")

    # ── S2: Deep Dive ──
    print(f"\n── S2: Deep Dive — {DEEP_DIVE_TICKER} ──")
    for run in range(1, N_RUNS + 1):
        print(f"  Run {run}/{N_RUNS}...", end=" ", flush=True)
        r = run_s2_deep_dive(DEEP_DIVE_TICKER, run)
        all_results.append(r)
        status = "✓" if r.success else "✗"
        print(f"{status} {r.wall_s:.2f}s | {r.notes}")

    # ── S3: PDF Render ──
    print(f"\n── S3: PDF Render — {TICKERS_S1[0]} ──")
    for run in range(1, N_RUNS + 1):
        print(f"  Run {run}/{N_RUNS}...", end=" ", flush=True)
        r = run_s3_pdf_render(TICKERS_S1[0], run)
        all_results.append(r)
        status = "✓" if r.success else "✗"
        print(f"{status} {r.wall_s:.2f}s | {r.notes}")

    # ── Summary ──
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")

    by_scenario = defaultdict(list)
    for r in all_results:
        by_scenario[(r.scenario, r.ticker)].append(r)

    for (scenario, ticker), results in sorted(by_scenario.items()):
        successful = [r for r in results if r.success]
        if not successful:
            print(f"  {scenario:25s} {ticker:5s}  ALL FAILED (n={len(results)})")
            continue
        walls = [r.wall_s for r in successful]
        avg_w = sum(walls) / len(walls)
        min_w = min(walls)
        max_w = max(walls)
        sz = max((r.output_size_kb for r in successful), default=0)
        print(f"  {scenario:25s} {ticker:5s}  avg={avg_w:.2f}s  min={min_w:.2f}s  max={max_w:.2f}s  "
              f"size={sz:.0f}KB  n={len(successful)}/{len(results)}")

    # ── Save JSON ──
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "project_root": str(PROJECT_ROOT),
        "python_version": sys.version,
        "n_runs": N_RUNS,
        "environment": {
            "hostname": os.uname().nodename,
            "os": f"{os.uname().sysname} {os.uname().release}",
            "cpu_count": os.cpu_count(),
        },
        "results": [r.to_dict() for r in all_results],
        "summary": {
            f"{r.scenario}_{r.ticker}": {
                "avg_s": round(
                    sum(x.wall_s for x in [rr for rr in all_results if rr.scenario == r.scenario and rr.ticker == r.ticker and rr.success]) /
                    max(len([rr for rr in all_results if rr.scenario == r.scenario and rr.ticker == r.ticker and rr.success]), 1), 2
                )
            }
            for r in all_results
        },
    }

    os.makedirs(PROJECT_ROOT / "benchmarks", exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nRaw data: {OUT_JSON}")
    print("Done.")


if __name__ == "__main__":
    main()
