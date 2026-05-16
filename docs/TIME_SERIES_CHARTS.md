# Time-Series Charts — Feature Flag

## Status: DISABLED (waiting for reliable time-series data)

### Current state
- ChartData model exists in `report_model.py` with EPS/Revenue comparison chart support
- `_build_chart_data()` in `mapper.py` extracts point-in-time metrics
- PDF renderer can render basic comparison charts (EPS actual vs estimate, Revenue actual vs estimate)
- These are already deployed in production

### What's missing for time-series charts
The pipeline currently fetches **single-quarter snapshots** (yfinance + SEC EDGAR).
Time-series charts (sparklines, margin trends, revenue/EPS trends) require **multi-period data**
that is not yet available in the pipeline.

### Required data for each chart type

| Chart | Data Needed | Source | Status |
|---|---|---|---|
| **Price sparkline** | 1-year daily closing prices | yfinance `.history()` | ❌ Not fetched |
| **Margin trends** | 4-8 quarters of gross/operating margin | yfinance quarterly financials | ❌ Not fetched |
| **Revenue/EPS trend** | 4-8 quarters of revenue/EPS | yfinance quarterly financials | ❌ Not fetched |

### Feature flag

```python
# In pipeline.py or mapper.py
ENABLE_TIME_SERIES_CHARTS = False  # TODO: enable when multi-period data is available

if ENABLE_TIME_SERIES_CHARTS:
    chart_data = _build_time_series_charts(metrics)
    report.charts = chart_data
else:
    # Existing behavior — single-quarter comparison chart only
    report.charts = _build_chart_data(metrics)
```

### Implementation plan (when ready)

1. Add `yfinance.Ticker.history(period="1y")` call for price data
2. Add `yfinance.Ticker.quarterly_financials` for multi-quarter metrics
3. Implement `_build_time_series_charts()` in mapper.py
4. Add sparkline + trend chart rendering in pdf_renderer.py
5. Add tests with mock yfinance data
6. Set `ENABLE_TIME_SERIES_CHARTS = True`

### Guardrails
- Charts MUST NOT be rendered with fake/placeholder data
- If yfinance returns incomplete data, charts degrade gracefully (show "Data unavailable")
- Lazy imports for matplotlib (already done in pdf_renderer.py)
- Chart style must match existing premium PDF aesthetic

### Related
- Commit 7b7179f: "feat: metrics comparison chart and PDF chart support"
- `backend/earnings_deep_dive/report_model.py::ChartData`
- `backend/earnings_deep_dive/mapper.py::_build_chart_data()`
