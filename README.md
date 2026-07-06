# 每日前10選股系統（台股＋美股，全免費資源）

收盤撮合**前**產出「前10值得關注」名單（含 ETF＋個股、帶類型標籤），
結合技術面、財報基本面與市場環境，並附 ETF 位階溫度計。

## 檔案結構

```
stock-scanner/
├── data_fetch.py        # 資料抓取（FinMind / 證交所MIS / yfinance）
├── history.py           # 歷史日K資料庫（首次建庫＋每日增量）
├── fundamentals.py      # 夜間基本面分數快取（月營收/EPS，每晚輪替更新1/5）
├── indicators.py        # 技術指標＋評分模型＋位階溫度計
├── scan.py              # 盤中掃描 → data/top10_tw.json / top10_us.json
├── app.py               # Flask 網站（部署到 Render）
├── etf_types.json       # ETF 類型對照表（顯示用標籤）
├── cloudflare-worker.js # Cloudflare Worker 觸發器（貼到 CF 儀表板用）
├── 部署設定教學.md       # 從零開始的完整設定步驟（含 Cloudflare 精準觸發）
└── .github/workflows/scan.yml  # 自動排程
```

## 安裝與首次啟動

```bash
# 1. 安裝套件
pip install -r requirements.txt

# 2. 設定 FinMind token（finmindtrade.com 免費註冊取得；不設也能跑但額度減半）
export FINMIND_TOKEN=你的token        # Windows: set FINMIND_TOKEN=你的token

# 3. 首次建歷史資料庫（台股約 20-30 分鐘、美股約 5 分鐘，之後每天只增量）
python history.py

# 4. 建基本面快取（每次只更新 1/5 股票，一週輪完；首週資料會逐日補齊）
python fundamentals.py

# 5. 盤中跑一次掃描（台股開盤時間跑 tw、美股開盤時間跑 us）
python scan.py tw
python scan.py us

# 6. 啟動網站（本機測試）
python app.py     # 開 http://localhost:10000
```

## 自動化部署（免費）

完整步驟見 **部署設定教學.md**。摘要：

1. 把整個資料夾推上 GitHub（公開 repo 的 Actions 完全免費）
2. repo Settings → Secrets and variables → Actions → 新增 `FINMIND_TOKEN`
3. 用 Cloudflare Worker Cron 精準觸發（主要）＋ GitHub 內建 cron（備援）：
   - 台北 12:10 掃台股 → **12:40 前出名單（遠早於 13:25 收盤撮合）**
   - 美東 15:00 掃美股 → 15:30 前出名單，16:00 收盤前有半小時下單
   - 台北 22:00 更新歷史庫＋基本面快取
4. 網站部署：Render 免費 Web Service（gunicorn + Flask），設 `GITHUB_RAW` 環境變數
   讓網站直接讀 repo 最新名單，每日更新不需重新部署；用 keep-alive 打 `/healthz` 防休眠

## 排程時間注意事項

- Cloudflare Cron 觸發準到秒級；GitHub Actions 開機器＋跑腳本約 3~8 分鐘，
  所以 12:10 觸發 → 名單約 12:15~12:18 出來
- GitHub 內建 cron（備援）尖峰時可能延遲 5–15 分鐘
- 美股夏令冬令由 cloudflare-worker.js 自動判斷切換，不用手動改；
  GitHub 備援 cron 冬令時請把 `15 19` 改成 `15 20`
- 台股於 13:25–13:30 進行收盤撮合，名單出來後你有約 1 小時可下單

## 評分模型（總分 0–100）

趨勢 25%（多頭排列）＋ 動能 20%（RSI/MACD）＋ 基本面 20%（個股：月營收YoY/EPS成長；
ETF：位階溫度計反轉分）＋ 量能 15% ＋ 波動定位 10% ＋ 相對強度 10%。
市場溫度（大盤 vs 60MA、VIX）會動態微調權重：多頭加重動能、空頭加重趨勢與防禦。

前10保底至少 2 檔 ETF；槓桿/反向 ETF 一律排除。

## 已知限制（誠實告知）

- 台股盤中報價來自證交所 MIS（約 5 秒~1 分鐘延遲的準即時），非逐筆
- yfinance 屬非官方介面，偶爾會失效需等社群更新
- 免費 API 均限個人非商業使用
- **本系統輸出為技術面觀察清單，不是投資建議**。掃描後到收盤前價格仍會變動，
  下單前請確認即時價；過往統計不保證未來績效，請自行控管停損與部位大小
