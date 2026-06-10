# HAR Export Guide — Chrome DevTools

> **Why this exists:** The web tutorial that originally described HAR export used HAR specification terminology ("Request List") which doesn't match Chrome DevTools UI labels. This guide uses Chrome-visible language throughout.

## What is HAR?

HAR (HTTP Archive) is a JSON file format that captures network requests made by a browser. The Stock Analysis Pipeline uses HAR files to extract Seeking Alpha API response data that isn't available through public endpoints.

**Important:** The "Request List" you see in HAR documentation is the **network request table** in Chrome DevTools. Chrome does not label this table anywhere — it's just the list of requests visible on the Network tab.

## Step-by-Step (EN)

1. **Press F12 (or Ctrl+Shift+I) to open Chrome DevTools.**
2. **Go to the "Network" tab.**
3. **Keep the Network tab open, then navigate to seekingalpha.com and log in.**  
   DevTools records all network activity while the Network tab is open.
4. **In the filter box, type "seekingalpha" to filter requests.**  
   This narrows the list to only Seeking Alpha API calls.
5. **Right-click anywhere in the network request table → "Save all as HAR with content".**  
   Chrome saves a `.har` file containing all request/response data.

> 💡 **Note:** The table of network requests IS what HAR documentation calls the "Request List" — it's called that in the HAR file format (log.entries), but Chrome doesn't label it that way. If you see "Request List" in other documentation, it means this table.

## ステップバイステップ (JP)

1. **F12キー（またはCtrl+Shift+I）を押してChrome DevToolsを開く。**
2. **"Network"タブに移動する。**
3. **Networkタブを開いたまま、seekingalpha.comにアクセスしてログインする。**  
   DevToolsはNetworkタブが開いている間、すべてのネットワークアクティビティを記録します。
4. **フィルターボックスに"seekingalpha"と入力してリクエストを絞り込む。**  
   Seeking AlphaのAPI呼び出しのみが表示されます。
5. **ネットワークリクエストテーブル内で右クリック → "Save all as HAR with content"。**  
   すべてのリクエスト・レスポンスデータを含む`.har`ファイルが保存されます。

> 💡 **補足:** "Request List"は技術的なHAR用語です — 表示されているリクエストテーブルのことを指しています。Chromeにラベルはありませんが、このテーブルがRequest Listです。

## Key differences from the web tutorial

| Term in tutorial | Chrome DevTools reality | Why it matters |
|---|---|---|
| "Request List" | The network request table (has no Chrome label) | Users scanned for "Request List" as a UI label and couldn't find it |
| Implied as a visible panel | It's just the default table view on the Network tab | Users expected a labeled section that doesn't exist |

## Troubleshooting

| Problem | Solution |
|---|---|
| No requests appear | Make sure the Network tab was open before navigating to seekingalpha.com |
| HAR file is empty or tiny | The filter may be too strict — try clearing the filter box and re-recording |
| "Save as HAR with content" is greyed out | Right-click **inside** the request table, not on header/blank space |
| Can't find ".har" file | Check your browser's default download folder or the download bar at the bottom of Chrome |
