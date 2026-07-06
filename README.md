# -*- coding: utf-8 -*-
"""夜間基本面更新：算好每檔「基本面分數」(0-100) 存快取，盤中掃描直接用。

台股：月營收 YoY + EPS 成長（FinMind）
美股：revenueGrowth + earningsGrowth（yfinance）
ETF ：不在這裡算，盤中掃描時用位階溫度計代替基本面分數。
"""
import sys
import time
import datetime as dt
import pandas as pd
import data_fetch as dfe


def score_tw_stock(stock_id: str) -> float:
    score = 50.0
    try:
        rev = dfe.tw_monthly_revenue(stock_id, start_date="2024-01-01")
        if not rev.empty and len(rev) >= 13:
            yoy = rev["revenue"].iloc[-1] / rev["revenue"].iloc[-13] - 1
            score = 90 if yoy > 0.2 else 65 if yoy > 0 else 25
    except Exception:
        pass
    try:
        fin = dfe.tw_financials(stock_id, start_date="2024-01-01")
        eps = fin[fin["type"] == "EPS"].sort_values("date")["value"]
        if len(eps) >= 5 and eps.iloc[-1] > eps.iloc[-5]:  # 近四季 EPS 優於去年同期
            score = min(100, score + 10)
    except Exception:
        pass
    return score


def run_tw():
    """每晚只更新 1/5 的股票（依星期輪替），一週輪完一圈。
    財報是月更/季更，不需要每天全掃；這樣單晚約 400 次呼叫，
    配 6 秒間隔剛好貼在免費 token 600次/hr 的額度內。"""
    uni = dfe.tw_universe()
    stocks = sorted(s for s in uni["stock_id"] if not s.startswith("00"))
    slot = dt.date.today().weekday() % 5           # 週一0 ... 週五4
    todays = stocks[slot::5]
    out = dfe.load_json("fundamentals_tw.json")    # 保留其他 4/5 的舊分數
    for i, sid in enumerate(todays):
        out[sid] = score_tw_stock(sid)
        if i % 50 == 0:
            print(f"tw fundamentals {i}/{len(todays)} (slot {slot})")
        time.sleep(6)  # 600/hr 額度：每 6 秒 1 次
    dfe.save_json("fundamentals_tw.json", out)
    print(f"saved {len(out)} tw fundamental scores (updated {len(todays)} today)")


def run_us():
    """美股同樣依星期輪替更新 1/5（yfinance 免 key，但放慢避免被擋）。"""
    import yfinance as yf
    tickers = dfe.us_universe()
    etfs = set(dfe.load_etf_types()["us"].keys())
    slot = dt.date.today().weekday() % 5
    todays = [t for t in tickers if t not in etfs][slot::5]
    out = dfe.load_json("fundamentals_us.json")
    for i, t in enumerate(todays):
        try:
            info = yf.Ticker(t).info
            rg = info.get("revenueGrowth")
            eg = info.get("earningsGrowth")
            s = 50.0
            if rg is not None:
                s = 90 if rg > 0.15 else 65 if rg > 0 else 25
            if eg is not None and eg > 0:
                s = min(100, s + 10)
            out[t] = s
        except Exception:
            out.setdefault(t, 50.0)
        if i % 50 == 0:
            print(f"us fundamentals {i}/{len(todays)} (slot {slot})")
        time.sleep(0.5)
    dfe.save_json("fundamentals_us.json", out)
    print(f"saved {len(out)} us fundamental scores (updated {len(todays)} today)")


if __name__ == "__main__":
    market = sys.argv[1] if len(sys.argv) > 1 else "all"
    if market in ("tw", "all"):
        run_tw()
    if market in ("us", "all"):
        run_us()
