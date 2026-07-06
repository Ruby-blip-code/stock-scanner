# -*- coding: utf-8 -*-
"""歷史日K資料庫（parquet）：首次建庫 + 每日增量更新。

台股：FinMind 依「日期」整市場抓（一天一次 API call，超省額度）
美股：yfinance 批次下載
"""
import os
import sys
import time
import pandas as pd
import data_fetch as dfe

TW_PATH = os.path.join(dfe.DATA_DIR, "history_tw.parquet")
US_PATH = os.path.join(dfe.DATA_DIR, "history_us.parquet")
LOOKBACK_DAYS = 550  # 約2年交易日 + buffer


def load(path: str) -> pd.DataFrame:
    if os.path.exists(path):
        return pd.read_parquet(path)
    return pd.DataFrame(columns=["stock_id", "date", "open", "high", "low", "close", "volume"])


def update_tw():
    os.makedirs(dfe.DATA_DIR, exist_ok=True)
    hist = load(TW_PATH)
    last = pd.to_datetime(hist["date"]).max() if not hist.empty else \
        pd.Timestamp.today() - pd.Timedelta(days=LOOKBACK_DAYS)
    dates = pd.bdate_range(last + pd.Timedelta(days=1), pd.Timestamp.today())
    frames = [hist]
    for d in dates:
        ds = d.strftime("%Y-%m-%d")
        try:
            df = dfe.finmind("TaiwanStockPrice", start_date=ds, end_date=ds)
            if df.empty:
                continue
            df = df.rename(columns={"max": "high", "min": "low", "Trading_Volume": "volume"})
            frames.append(df[["stock_id", "date", "open", "high", "low", "close", "volume"]])
            print(f"tw {ds}: {len(df)} rows")
        except Exception as e:
            print(f"tw {ds} error: {e}")
        time.sleep(0.5)
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    out = out.drop_duplicates(["stock_id", "date"]).sort_values(["stock_id", "date"])
    # 只留兩年
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
