#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const component = fs.readFileSync(path.join(__dirname, 'BatchAnalysis.jsx'), 'utf8');
const i18n = fs.readFileSync(path.join(__dirname, '..', 'i18n.js'), 'utf8');

const keys = [
  'batchPageTitle', 'batchHelpShow', 'batchHelpHide', 'batchAcceptedFormats',
  'batchTickerHelp', 'batchIsinHelp', 'batchSteps', 'batchStepUpload',
  'batchStepSelect', 'batchStepRun', 'batchStepDownload', 'batchDropPrompt',
  'batchDropHint', 'batchParse', 'batchSelectAll', 'batchDeselectAll',
  'batchSelectedSummary', 'batchNoTickers', 'batchRun', 'batchRunning',
  'batchUploadFailed', 'batchError', 'batchTimeout', 'batchAcceptedError',
];

for (const key of keys) {
  assert(component.includes(`t('${key}')`), `BatchAnalysis must use t('${key}')`);
  const occurrences = i18n.split(`${key}:`).length - 1;
  assert(occurrences === 2, `${key} must exist in both EN and JP translations`);
}

assert(i18n.includes('バッチ分析 (TXT/CSV + ZIP)'), 'Japanese tab must describe the actual TXT/CSV upload flow');
console.log('✅ BatchAnalysis i18n contract passed');
