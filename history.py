# -*- coding: utf-8 -*-
"""歷史日K資料庫（parquet）：首次建庫 + 每日增量更新。

台股：證交所官方 MI_INDEX 每日全市場行情（一天一個請求、免註冊）
      ※ v1 先涵蓋上市股票；上櫃之後再擴充
美股：yfinance 批次下載
"""
import os
import sys
import time
import requests
import pandas as pd
import data_fetch as dfe

TW_PATH = os.path.join(dfe.DATA_DIR, "history_tw.parquet")
US_PATH = os.path.join(dfe.DATA_DIR, "history_us.parquet")
LOOKBACK_DAYS = 550  # 約2年交易日 + buffer
UA = {"User-Agent": "Mozilla/5.0"}


def load(path: str) -> pd.DataFrame:
    if os.path.exists(path):
        return pd.read_parquet(path)
    return pd.DataFrame(columns=["stock_id", "date", "open", "high", "low", "close", "volume"])


def twse_daily_all(date: pd.Timestamp) -> pd.DataFrame:
    """證交所官方：某日全部上市股票收盤行情（一天一個請求）。"""
    ds = date.strftime("%Y%m%d")
    url = ("https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
           f"?date={ds}&type=ALLBUT0999&response=json")
    try:
        j = requests.get(url, headers=UA, timeout=30).json()
    except Exception as e:
        print(f"twse {ds} fetch error: {e}")
        return pd.DataFrame()
    target = None
    for t in j.get("tables") or []:
        f = t.get("fields") or []
        if f and f[0] == "證券代號":
            target = t
    if not target:
        return pd.DataFrame()  # 非交易日或格式變動
    idx = {name: i for i, name in enumerate(target["fields"])}

    def num(x):
        return float(str(x).replace(",", ""))

    rows = []
    for r in target["data"]:
        try:
            rows.append({
                "stock_id": str(r[idx["證券代號"]]).strip(),
                "date": date,
                "open": num(r[idx["開盤價"]]),
                "high": num(r[idx["最高價"]]),
                "low": num(r[idx["最低價"]]),
                "close": num(r[idx["收盤價"]]),
                "volume": num(r[idx["成交股數"]]),
            })
        except (ValueError, KeyError, IndexError):
            continue  # '--' = 當日無成交，跳過
    return pd.DataFrame(rows)


def update_tw():
    os.makedirs(dfe.DATA_DIR, exist_ok=True)
    hist = load(TW_PATH)
    last = pd.to_datetime(hist["date"]).max() if not hist.empty else \
        pd.Timestamp.today() - pd.Timedelta(days=LOOKBACK_DAYS)
    dates = pd.bdate_range(last + pd.Timedelta(days=1), pd.Timestamp.today())
    frames = [hist]
    for d in dates:
        df = twse_daily_all(d)
        if not df.empty:
            frames.append(df)
            print(f"tw {d.date()}: {len(df)} rows")
        time.sleep(3)  # 對官方站禮貌性間隔，首次建庫約 25 分鐘
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    out = out.drop_duplicates(["stock_id", "date"]).sort_values(["stock_id", "date"])
    out = out[out["date"] >= pd.Timestamp.today() - pd.Timedelta(days=LOOKBACK_DAYS + 200)]
    out.to_parquet(TW_PATH, index=False)
    print(f"tw history: {out['stock_id'].nunique()} stocks, {len(out)} rows")


def update_us():
    os.makedirs(dfe.DATA_DIR, exist_ok=True)
    tickers = dfe.us_universe()
    data = dfe.us_history(tickers, period="2y")
    frames = []
    for t, df in data.items():
        df = df.copy()
        df["stock_id"] = t
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out.to_parquet(US_PATH, index=False)
    print(f"us history: {len(data)} tickers, {len(out)} rows")


if __name__ == "__main__":
    market = sys.argv[1] if len(sys.argv) > 1 else "all"
    if market in ("tw", "all"):
        update_tw()
    if market in ("us", "all"):
        update_us()
