# -*- coding: utf-8 -*-
"""資料抓取模組：台股 FinMind + 證交所 MIS、美股 yfinance。"""
import os
import time
import json
import requests
import pandas as pd

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_TOKEN = os.getenv("FINMIND_TOKEN", "")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def finmind(dataset: str, **params) -> pd.DataFrame:
    """呼叫 FinMind API，回傳 DataFrame。
    沒設 FINMIND_TOKEN 也能跑（匿名 300次/hr），但建議免費註冊拿 token（600次/hr）。"""
    p = {"dataset": dataset, **params}
    if FINMIND_TOKEN:
        p["token"] = FINMIND_TOKEN
    r = requests.get(FINMIND_URL, params=p, timeout=30)
    r.raise_for_status()
    return pd.DataFrame(r.json().get("data", []))


# ---------- 台股 ----------

def tw_universe() -> pd.DataFrame:
    """台股選股池：上市+上櫃普通股與 ETF（含市場別，MIS 報價需要）。"""
    info = finmind("TaiwanStockInfo")
    info = info[info["type"].isin(["twse", "tpex"])]
    mask = info["stock_id"].str.fullmatch(r"\d{4}") | info["stock_id"].str.startswith("00")
    return info[mask][["stock_id", "stock_name", "type", "industry_category"]].drop_duplicates("stock_id")


def tw_daily_history(stock_id: str, start_date: str) -> pd.DataFrame:
    """單檔台股日K。"""
    df = finmind("TaiwanStockPrice", data_id=stock_id, start_date=start_date)
    if df.empty:
        return df
    df = df.rename(columns={"max": "high", "min": "low", "Trading_Volume": "volume"})
    df["date"] = pd.to_datetime(df["date"])
    return df[["date", "open", "high", "low", "close", "volume"]]


def tw_intraday_quotes(stock_rows: list) -> dict:
    """證交所 MIS 盤中報價，每批 50 檔。
    stock_rows: [(stock_id, market)]，market 為 'twse' 或 'tpex'。
    回傳 {stock_id: {"price": float, "volume": int(股)}}
    """
    out = {}
    prefix = {"twse": "tse", "tpex": "otc"}
    for i in range(0, len(stock_rows), 50):
        batch = stock_rows[i:i + 50]
        ch = "|".join(f"{prefix.get(m, 'tse')}_{s}.tw" for s, m in batch)
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ch}&json=1&delay=0"
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            for item in r.json().get("msgArray", []):
                price = item.get("z") or item.get("y")  # 最新成交價，沒有就用昨收
                if price and price != "-":
                    out[item["c"]] = {
                        "price": float(price),
                        "volume": int(float(item.get("v", 0) or 0)) * 1000,  # 張→股
                    }
        except Exception as e:
            print(f"MIS batch {i} error: {e}")
        time.sleep(1.5)  # 禮貌性間隔，避免被擋
    return out


def tw_monthly_revenue(stock_id: str, start_date: str) -> pd.DataFrame:
    return finmind("TaiwanStockMonthRevenue", data_id=stock_id, start_date=start_date)


def tw_financials(stock_id: str, start_date: str) -> pd.DataFrame:
    return finmind("TaiwanStockFinancialStatements", data_id=stock_id, start_date=start_date)


# ---------- 美股 ----------

def us_universe() -> list:
    """S&P 500 + Nasdaq 100 成分股（從 Wikipedia 抓）+ 主要 ETF。"""
    import io
    headers = {"User-Agent": "Mozilla/5.0"}
    tickers = set()
    try:
        html = requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            headers=headers, timeout=30).text
        sp500 = pd.read_html(io.StringIO(html))[0]
        tickers |= set(sp500["Symbol"].str.replace(".", "-", regex=False))
    except Exception as e:
        print(f"SP500 list error: {e}")
    try:
        html = requests.get("https://en.wikipedia.org/wiki/Nasdaq-100",
                            headers=headers, timeout=30).text
        for t in pd.read_html(io.StringIO(html)):
            if "Ticker" in t.columns:
                tickers |= set(t["Ticker"])
                break
    except Exception as e:
        print(f"NDX list error: {e}")
    etfs = load_etf_types()["us"].keys()
    return sorted(tickers | set(etfs))


def us_history(tickers: list, period: str = "2y") -> dict:
    """批次抓美股日K，回傳 {ticker: DataFrame(date, open..volume)}。"""
    import yfinance as yf
    raw = yf.download(tickers, period=period, group_by="ticker",
                      auto_adjust=True, threads=True, progress=False)
    out = {}
    for t in tickers:
        try:
            df = raw[t].dropna().reset_index()
            df.columns = [c.lower() for c in df.columns]
            out[t] = df[["date", "open", "high", "low", "close", "volume"]]
        except Exception:
            continue
    return out


def us_intraday_quotes(tickers: list) -> dict:
    """盤中近即時價：抓當日 5 分 K 取最後一根。"""
    import yfinance as yf
    raw = yf.download(tickers, period="1d", interval="5m", group_by="ticker",
                      threads=True, progress=False)
    out = {}
    for t in tickers:
        try:
            df = raw[t].dropna()
            out[t] = {"price": float(df["Close"].iloc[-1]),
                      "volume": int(df["Volume"].sum())}
        except Exception:
            continue
    return out


# ---------- 共用 ----------

def load_etf_types() -> dict:
    path = os.path.join(os.path.dirname(__file__), "etf_types.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(name: str, obj) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, default=str)


def load_json(name: str, default=None):
    path = os.path.join(DATA_DIR, name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}
