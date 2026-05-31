#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const appPath = path.join(__dirname, 'App.jsx');
const source = fs.readFileSync(appPath, 'utf8');

assert(
  source.includes("testSeekingAlphaAccess"),
  'App must use the live Seeking Alpha connectivity probe, not only cookie presence.'
);

assert(
  !source.includes('if (!showAdmin && !showFeedback)'),
  'Homepage SA badge must not skip the Seeking Alpha probe; the main page is where the badge is rendered.'
);

assert(
  source.includes('if (show404)') && source.includes('}, [show404]);'),
  'Seeking Alpha polling may be skipped only for the 404 route, not for the homepage.'
);

assert(
  source.includes("saAccess.ok && saAccess.authenticated") && source.includes("SA: connected ✅"),
  'Badge must display connected when the live probe returns ok+authenticated.'
);

console.log('✅ App Seeking Alpha homepage badge guard passed');
