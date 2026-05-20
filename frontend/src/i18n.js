// i18n.js — Translations for Stock Analysis Pipeline
// EN (default) + JA (Japanese)
// UI strings only. Document content translated via NVIDIA free tier.

const translations = {
  en: {
    // Header
    siteTitle: "📈 Stock Analysis",
    siteSubtitle: "Automated fundamental analysis — BUY / HOLD / SELL based on 6 weighted categories",
    
    // Mode tabs
    quickAnalysis: "🔍 Quick Analysis",
    batchAnalysis: "📦 Batch (Upload + ZIP)",
    whatIsThis: "▸ What is this? How does it work?",
    
    // Quick Analysis
    tickerPlaceholder: "Type tickers or ISINs (comma, space, or line separated)…",
    analyze: "Analyze",
    analyzing: "Analyzing…",
    
    // Batch Analysis
    batchTitle: "📦 Batch Analysis",
    batchSubtitle: "Upload a CSV or paste tickers. Get individual + consolidated ZIP.",
    uploadCSV: "Upload CSV",
    orPaste: "or paste tickers below",
    csvFormat: "CSV format: ticker column required, optional weight/notes columns",
    pastePlaceholder: "AAPL, MSFT, GOOGL…",
    startBatch: "Start Batch Analysis",
    processing: "Processing…",
    
    // Progress
    buildingDossier: "📊 Building dossier…",
    sections: "sections",
    of: "of",
    estimatedBilingual: "Bilingual EN+JP package — estimated ~2 min",
    estimatedSingle: "Single language — estimated ~1 min",
    
    // Scoring
    conviction: "Conviction",
    verdict: "Verdict",
    scoringBreakdown: "Scoring Breakdown",
    detailedScoring: "Detailed Scoring",
    viewFullReport: "📄 Deep-Dive PDF",
    downloadDossier: "📥 Download Dossier",
    downloadingDossier: "⏳ Downloading...",
    downloadComplete: "✅ Download complete!",
    downloadFailed: "❌ Download failed",
    downloadReport: "📄 Download Report",
    
    // Scoring labels
    businessMomentum: "Business Momentum",
    valuationRisk: "Valuation Risk",
    financialStrength: "Financial Strength",
    profitability: "Profitability",
    moat: "Competitive Moat",
    management: "Management Quality",
    growth: "Growth",
    geopoliticalRisk: "Geopolitical Risk",
    
    // Verdicts
    BUY: "BUY",
    HOLD: "HOLD",
    SELL: "SELL",
    "HOLD / BUY ON PULLBACK": "HOLD / BUY ON PULLBACK",
    "HOLD fragile": "HOLD (fragile)",
    "SELL or AVOID": "SELL / AVOID",
    
    // Conviction
    High: "High",
    Moderate: "Moderate",
    Low: "Low",
    
    // Messages
    loading: "Loading…",
    searchMonitorTitle: "🔍 Live Searches",
    analysisDuration: "This takes 3-5 minutes — fetching financials, SEC filings, and deep-dive scoring. Please wait…",
    step_fetching: "Fetching financial data…",
    step_ratios: "Processing ratios & metrics…",
    step_scoring: "Scoring fundamentals…",
    step_insights: "Generating insights…",
    stepLabel: "Step {step} of {total}",
    currentTicker: "Current ticker",
    tickersProcessed: "tickers processed",
    estimatedDuration: "Est. 3–5 min",
    activityLog: "Activity log",
    sourcesIncluded: "Sources and calculations will be included in the final report",
    // Activity log entries
    act_init: "Analysis initialized",
    act_fetch_is: "Fetching income statement",
    act_fetch_bs: "Fetching balance sheet",
    act_fetch_cf: "Fetching cash flow statement",
    act_fetch_filings: "Fetching regulatory filings & source documents",
    act_fetch_estimates: "Fetching analyst estimates",
    act_fetch_sources: "Collecting source documents",
    act_calc_ratios: "Calculating financial ratios",
    act_compare_peers: "Comparing against sector peers",
    act_score_growth: "Scoring growth metrics",
    act_score_value: "Scoring value & valuation",
    act_score_profit: "Scoring profitability",
    act_prep_insights: "Preparing final insights",
    act_parse_docs: "Parsing regulatory filings",
    act_score_momentum: "Scoring momentum indicators",
    act_finalize: "Finalizing analysis report",
    error: "Error",
    noResults: "No results",
    tryExample: "Try e.g. AAPL, MSFT, GOOGL",
    comingSoon: "Coming soon",
    
    // About
    aboutTitle: "📊 How it works",
    aboutDescription: "This pipeline analyzes stocks using 6 weighted categories. Each ticker gets a BUY / HOLD / SELL verdict with detailed scoring. The full dossier includes financial data, SEC filings analysis, management evaluation, and market context.",
    aboutMainTitle: "About the Stock Analysis Pipeline",
    aboutIntro: "This tool performs automated fundamental analysis on any publicly traded stock. For each ticker, it fetches data from multiple sources, scores the company across 6 weighted categories, and produces a BUY, HOLD, or SELL decision with full traceability.",
    aboutDataSources: "📊 Data Sources",
    aboutSources: [
      ["SEC EDGAR", "10-K / 10-Q filings — Items 1, 1A, 7, 7A, 8 (business, risks, MD&A, financials)"],
      ["Yahoo Finance", "Real-time price, market cap, sector, company description"],
      ["Finnhub", "Financial statements, valuation ratios (P/E, PEG), analyst estimates"],
      ["Alpha Vantage", "Earnings call transcripts — management tone & sentiment analysis"],
      ["The Motley Fool", "Fallback transcript source for US-listed stocks"],
    ],
    aboutScoring: "⚖️ Scoring Criteria (6 categories = /40)",
    aboutCriteria: [
      ["Financial Health", "Profitability, cash flow, balance sheet strength (max 10)"],
      ["Growth", "Revenue growth YoY, guidance trajectory, market expansion (max 10)"],
      ["Valuation", "P/E, forward P/E, PEG ratio — attractiveness vs growth (max 8)"],
      ["Management", "Tone, confidence, execution quality from earnings calls (max 5)"],
      ["Moat", "Competitive advantage, barriers to entry, market position (max 4)"],
      ["Sentiment", "Market momentum, analyst sentiment, macro context (max 3)"],
    ],
    aboutDecisionRules: "📋 Decision Rules",
    aboutRules: [
      ["BUY", "Score ≥ 32/40 — strong fundamentals across most criteria"],
      ["HOLD", "Score 26-31 — good quality, wait for a better entry point"],
      ["HOLD (fragile)", "Score 18-25 — mixed signals, hold but do not add"],
      ["SELL", "Score < 18 — too many risks, avoid or exit"],
    ],
    aboutDisclaimer: "⚠️ Disclaimer: This is an automated research tool, not financial advice. All data is sourced from public records. Every claim in the report is traceable to a stored source file (10-K HTML, API snapshots, transcripts). Always verify before making investment decisions.",
    
    // Language
    language: "Language",
    
    // Insights
    insight_momentum: "🚀 Strong momentum detected",
    insight_undervalued: "📈 Undervalued vs sector",
    insight_fundamentals: "🏛️ Stable fundamentals",
    insight_moat: "🛡️ Strong competitive moat",
    insight_management: "👔 Quality management signals",
    insight_growth: "📊 Consistent growth pattern",
    insight_valuation_concern: "⚠️ Valuation concerns",
    insight_geopolitical: "🌍 Geopolitical exposure flagged",
    insight_mixed: "🔍 Mixed signals — review full report",
  },
  
  ja: {
    // Header
    siteTitle: "📈 株式分析",
    siteSubtitle: "6つの加重カテゴリーに基づく自動ファンダメンタル分析 — BUY / HOLD / SELL",
    
    // Mode tabs
    quickAnalysis: "🔍 クイック分析",
    batchAnalysis: "📦 バッチ分析 (CSV + ZIP)",
    whatIsThis: "▸ これは何？使い方は？",
    
    // Quick Analysis
    tickerPlaceholder: "ティッカーまたはISINを入力（カンマ、スペース、改行区切り）…",
    analyze: "分析する",
    analyzing: "分析中…",
    
    // Batch Analysis
    batchTitle: "📦 バッチ分析",
    batchSubtitle: "CSVをアップロードするか、ティッカーを貼り付けてください。個別＋統合ZIP。",
    uploadCSV: "CSVアップロード",
    orPaste: "または下にティッカーを貼り付け",
    csvFormat: "CSV形式: ticker列必須、weight/notes列は任意",
    pastePlaceholder: "AAPL, MSFT, GOOGL…",
    startBatch: "バッチ分析を開始",
    processing: "処理中…",
    
    // Progress
    buildingDossier: "📊 ドシエ作成中…",
    sections: "セクション",
    of: "/",
    estimatedBilingual: "バイリンガルEN+JPパッケージ — 推定約2分",
    estimatedSingle: "単一言語 — 推定約1分",
    
    // Scoring
    conviction: "確信度",
    verdict: "判定",
    scoringBreakdown: "スコア内訳",
    detailedScoring: "詳細スコア",
    viewFullReport: "📄 詳細レポート (PDF)",
    downloadDossier: "📥 ドシエをダウンロード",
    downloadingDossier: "⏳ ダウンロード中...",
    downloadComplete: "✅ ダウンロード完了!",
    downloadFailed: "❌ ダウンロード失敗",
    downloadReport: "📄 レポートをダウンロード",
    
    // Scoring labels
    businessMomentum: "ビジネスモメンタム",
    valuationRisk: "バリュエーションリスク",
    financialStrength: "財務力",
    profitability: "収益性",
    moat: "競争優位性",
    management: "経営品質",
    growth: "成長性",
    geopoliticalRisk: "地政学リスク",
    
    // Verdicts
    BUY: "買い",
    HOLD: "ホールド",
    SELL: "売り",
    "HOLD / BUY ON PULLBACK": "ホールド / 押し目買い",
    "HOLD fragile": "ホールド（脆弱）",
    "SELL or AVOID": "売り / 回避",
    
    // Conviction
    High: "高い",
    Moderate: "中程度",
    Low: "低い",
    
    // Messages
    loading: "読み込み中…",
    searchMonitorTitle: "🔍 リアルタイム検索",
    analysisDuration: "分析には3〜5分かかります — 財務データ、SEC提出書類、詳細スコアリングを実行中です。しばらくお待ちください…",
    step_fetching: "財務データ取得中…",
    step_ratios: "比率・指標を処理中…",
    step_scoring: "ファンダメンタルズ評価中…",
    step_insights: "インサイト生成中…",
    stepLabel: "ステップ {step} / {total}",
    currentTicker: "現在のティッカー",
    tickersProcessed: "ティッカー処理済み",
    estimatedDuration: "推定 3〜5分",
    activityLog: "アクティビティログ",
    sourcesIncluded: "ソースと計算は最終レポートに含まれます",
    // Activity log entries
    act_init: "分析を初期化しました",
    act_fetch_is: "損益計算書を取得中",
    act_fetch_bs: "貸借対照表を取得中",
    act_fetch_cf: "キャッシュフロー計算書を取得中",
    act_fetch_filings: "規制当局への提出書類・ソース文書を取得中",
    act_fetch_estimates: "アナリスト予想を取得中",
    act_fetch_sources: "ソース文書を収集中",
    act_calc_ratios: "財務比率を計算中",
    act_compare_peers: "セクター平均と比較中",
    act_score_growth: "成長性を評価中",
    act_score_value: "バリュー・バリュエーションを評価中",
    act_score_profit: "収益性を評価中",
    act_prep_insights: "最終インサイトを準備中",
    act_parse_docs: "規制当局への提出書類を解析中",
    act_score_momentum: "モメンタム指標を評価中",
    act_finalize: "分析レポートを最終処理中",
    error: "エラー",
    noResults: "結果なし",
    tryExample: "例: AAPL, MSFT, GOOGL",
    comingSoon: "近日公開",
    
    // About
    aboutTitle: "📊 仕組み",
    aboutDescription: "このパイプラインは6つの加重カテゴリーを使用して株式を分析します。各ティッカーにBUY / HOLD / SELLの判定と詳細なスコアリングが付与されます。完全なドシエには財務データ、SEC提出書類の分析、経営陣の評価、市場コンテキストが含まれます。",
    aboutMainTitle: "株式分析パイプラインについて",
    aboutIntro: "このツールは上場株式の自動ファンダメンタル分析を行います。各ティッカーについて複数のソースからデータを取得し、6つの加重カテゴリーでスコアリングし、完全なトレーサビリティ付きでBUY、HOLD、SELLの判断を下します。",
    aboutDataSources: "📊 データソース",
    aboutSources: [
      ["SEC EDGAR", "10-K / 10-Q 提出書類 — Items 1, 1A, 7, 7A, 8（事業、リスク、MD&A、財務）"],
      ["Yahoo Finance", "リアルタイム株価、時価総額、セクター、企業概要"],
      ["Finnhub", "財務諸表、バリュエーション指標（P/E、PEG）、アナリスト予想"],
      ["Alpha Vantage", "決算説明会トランスクリプト — 経営陣のトーンとセンチメント分析"],
      ["The Motley Fool", "米国株向けフォールバックトランスクリプトソース"],
    ],
    aboutScoring: "⚖️ スコアリング基準（6カテゴリー = /40）",
    aboutCriteria: [
      ["財務健全性", "収益性、キャッシュフロー、バランスシートの強さ（最大10）"],
      ["成長性", "収益成長率（前年比）、ガイダンスの軌道、市場拡大（最大10）"],
      ["バリュエーション", "P/E、フォワードP/E、PEGレシオ — 成長に対する割安度（最大8）"],
      ["経営品質", "決算説明会からのトーン、自信、実行力（最大5）"],
      ["競争優位性", "競争優位、参入障壁、市場ポジション（最大4）"],
      ["センチメント", "市場モメンタム、アナリストセンチメント、マクロ環境（最大3）"],
    ],
    aboutDecisionRules: "📋 判断ルール",
    aboutRules: [
      ["買い", "スコア ≥ 32/40 — ほとんどの基準で強固なファンダメンタルズ"],
      ["ホールド", "スコア 26-31 — 良好な品質、より良いエントリーポイントを待つ"],
      ["ホールド（脆弱）", "スコア 18-25 — 混在シグナル、保有継続だが追加購入しない"],
      ["売り", "スコア < 18 — リスクが多すぎる、回避または売却"],
    ],
    aboutDisclaimer: "⚠️ 免責事項：これは自動調査ツールであり、財務アドバイスではありません。すべてのデータは公的記録から取得されています。レポート内のすべての主張は、保存されたソースファイル（10-K HTML、APIスナップショット、トランスクリプト）まで追跡可能です。投資判断の前に必ずご自身で確認してください。",
    
    // Language
    language: "言語",
    
    // Insights
    insight_momentum: "🚀 強いモメンタム検出",
    insight_undervalued: "📈 セクター比で割安",
    insight_fundamentals: "🏛️ 安定したファンダメンタルズ",
    insight_moat: "🛡️ 強い競争優位性",
    insight_management: "👔 質の高い経営陣のシグナル",
    insight_growth: "📊 一貫した成長パターン",
    insight_valuation_concern: "⚠️ バリュエーション懸念",
    insight_geopolitical: "🌍 地政学的リスクあり",
    insight_mixed: "🔍 混在シグナル — 詳細レポートを確認",
  }
};

export default translations;
