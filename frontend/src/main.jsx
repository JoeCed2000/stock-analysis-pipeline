import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';

// Build stamp — visible in browser console (F12) for cache verification
const commit = typeof __BUILD_COMMIT__ !== 'undefined' ? __BUILD_COMMIT__ : 'dev';
const date = typeof __BUILD_DATE__ !== 'undefined' ? __BUILD_DATE__ : new Date().toISOString().slice(0, 10);
console.log(`%c📈 SA Pipeline %c${commit} %c${date}`,
  'color:#58a6ff;font-weight:bold', 'color:#238636', 'color:#8b949e');

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
