// i18n.js — Translations for Stock Analysis Pipeline
// EN (default) + JA (Japanese)
// UI strings only. Document content translated via NVIDIA free tier.

const translations = {
  en: {
    // Header
    siteTitle: "📈 Stock Analysis",
    siteSubtitle: "Automated fundamental analysis — BUY / HOLD / SELL based on 8 criteria",
    
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
    viewFullReport: "View Full Report →",
    downloadDossier: "📥 Download Dossier",
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
    analysisDuration: "This takes 3-5 minutes — fetching financials, SEC filings, and deep-dive scoring. Please wait…",
    step_fetching: "Fetching financial data…",
    step_ratios: "Processing ratios & metrics…",
    step_scoring: "Scoring fundamentals…",
    step_insights: "Generating insights…",
    error: "Error",
    noResults: "No results",
    tryExample: "Try e.g. AAPL, MSFT, GOOGL",
    comingSoon: "Coming soon",
    
    // About
    aboutTitle: "📊 How it works",
    aboutDescription: "This pipeline analyzes stocks using 8 fundamental criteria. Each ticker gets a BUY / HOLD / SELL verdict with detailed scoring. The full dossier includes financial data, SEC filings analysis, management evaluation, and market context.",
    aboutMainTitle: "About the Stock Analysis Pipeline",
    aboutIntro: "This tool performs automated fundamental analysis on any publicly traded stock. For each ticker, it fetches data from multiple sources, scores the company across 8 weighted criteria, and produces a BUY, HOLD, or SELL decision with full traceability.",
    aboutDataSources: "📊 Data Sources",
    aboutSources: [
      ["SEC EDGAR", "10-K / 10-Q filings — Items 1, 1A, 7, 7A, 8 (business, risks, MD&A, financials)"],
      ["Yahoo Finance", "Real-time price, market cap, sector, company description"],
      ["Finnhub", "Financial statements, valuation ratios (P/E, PEG), analyst estimates"],
      ["Alpha Vantage", "Earnings call transcripts — management tone & sentiment analysis"],
      ["The Motley Fool", "Fallback transcript source for US-listed stocks"],
    ],
    aboutScoring: "⚖️ Scoring Criteria (8 × /5 = /40)",
    aboutCriteria: [
      ["Growth", "Revenue growth (YoY + annual), guidance trajectory"],
      ["Profitability", "Gross margin, operating margin, net income"],
      ["Financial Strength", "Free cash flow, net debt, balance sheet health"],
      ["Moat", "Competitive advantage, market position, barriers to entry"],
      ["Management", "Tone, confidence, visibility from earnings calls"],
      ["Valuation Risk", "P/E, forward P/E, PEG ratio vs. growth"],
      ["Geopolitical Risk", "Tariff exposure, supply chain, regulatory pressure"],
      ["Business Momentum", "Segment trends, product cycles, market demand"],
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
    siteSubtitle: "8つの基準に基づく自動ファンダメンタル分析 — BUY / HOLD / SELL",
    
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
    viewFullReport: "詳細レポートを見る →",
    downloadDossier: "📥 ドシエをダウンロード",
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
    analysisDuration: "分析には3〜5分かかります — 財務データ、SEC提出書類、詳細スコアリングを実行中です。しばらくお待ちください…",
    step_fetching: "財務データ取得中…",
    step_ratios: "比率・指標を処理中…",
    step_scoring: "ファンダメンタルズ評価中…",
    step_insights: "インサイト生成中…",
    error: "エラー",
    noResults: "結果なし",
    tryExample: "例: AAPL, MSFT, GOOGL",
    comingSoon: "近日公開",
    
    // About
    aboutTitle: "📊 仕組み",
    aboutDescription: "このパイプラインは8つのファンダメンタル基準を使用して株式を分析します。各ティッカーにBUY / HOLD / SELLの判定と詳細なスコアリングが付与されます。完全なドシエには財務データ、SEC提出書類の分析、経営陣の評価、市場コンテキストが含まれます。",
    aboutMainTitle: "株式分析パイプラインについて",
    aboutIntro: "このツールは上場株式の自動ファンダメンタル分析を行います。各ティッカーについて複数のソースからデータを取得し、8つの加重基準でスコアリングし、完全なトレーサビリティ付きでBUY、HOLD、SELLの判断を下します。",
    aboutDataSources: "📊 データソース",
    aboutSources: [
      ["SEC EDGAR", "10-K / 10-Q 提出書類 — Items 1, 1A, 7, 7A, 8（事業、リスク、MD&A、財務）"],
      ["Yahoo Finance", "リアルタイム株価、時価総額、セクター、企業概要"],
      ["Finnhub", "財務諸表、バリュエーション指標（P/E、PEG）、アナリスト予想"],
      ["Alpha Vantage", "決算説明会トランスクリプト — 経営陣のトーンとセンチメント分析"],
      ["The Motley Fool", "米国株向けフォールバックトランスクリプトソース"],
    ],
    aboutScoring: "⚖️ スコアリング基準（8項目 × /5 = /40）",
    aboutCriteria: [
      ["成長性", "収益成長率（前年比 + 年間）、ガイダンスの軌道"],
      ["収益性", "粗利益率、営業利益率、純利益"],
      ["財務力", "フリーキャッシュフロー、純負債、バランスシートの健全性"],
      ["競争優位性", "競争優位、市場ポジション、参入障壁"],
      ["経営品質", "決算説明会からのトーン、自信、可視性"],
      ["バリュエーションリスク", "P/E、フォワードP/E、PEGレシオ対成長率"],
      ["地政学リスク", "関税エクスポージャー、サプライチェーン、規制圧力"],
      ["ビジネスモメンタム", "セグメント動向、製品サイクル、市場需要"],
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
