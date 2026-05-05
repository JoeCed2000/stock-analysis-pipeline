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
    error: "Error",
    noResults: "No results",
    tryExample: "Try e.g. AAPL, MSFT, GOOGL",
    comingSoon: "Coming soon",
    
    // About
    aboutTitle: "📊 How it works",
    aboutDescription: "This pipeline analyzes stocks using 8 fundamental criteria. Each ticker gets a BUY / HOLD / SELL verdict with detailed scoring. The full dossier includes financial data, SEC filings analysis, management evaluation, and market context.",
    
    // Language
    language: "Language",
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
    error: "エラー",
    noResults: "結果なし",
    tryExample: "例: AAPL, MSFT, GOOGL",
    comingSoon: "近日公開",
    
    // About
    aboutTitle: "📊 仕組み",
    aboutDescription: "このパイプラインは8つのファンダメンタル基準を使用して株式を分析します。各ティッカーにBUY / HOLD / SELLの判定と詳細なスコアリングが付与されます。完全なドシエには財務データ、SEC提出書類の分析、経営陣の評価、市場コンテキストが含まれます。",
    
    // Language
    language: "言語",
  }
};

export default translations;
