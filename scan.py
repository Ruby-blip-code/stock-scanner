# -*- coding: utf-8 -*-
"""盤中掃描：即時報價 + 快取基本面 → 每日前10推薦（含 ETF 與個股）。

用法：
  python scan.py tw    # 台股盤中掃描（建議台北 12:10 跑，12:40 前出名單，遠早於 13:25 收盤撮合）
  python scan.py us    # 美股盤中掃描（建議美東 15:00 跑，15:30 前出名單）
  python scan.py auto  # 依 UTC 時間自動判斷（給 GitHub Actions 用）
"""
import sys
import datetime as dt
import pandas as pd
import data_fetch as dfe
import history
from indicators import tech_scores, total_score, position_score, reason_text

MIN_BARS = 80          # 至少要有80根日K才評分
GUARANTEED_ETFS = 2    # 前10保底 ETF 檔數


def market_regime(bench_ticker: str, vix: bool = False) -> str:
    """市場溫度：大盤 vs 60MA（美股加看 VIX）。"""
    import yfinance as yf
    try:
        px = yf.download(bench_ticker, period="6mo", progress=False,
                         auto_adjust=True)["Close"].dropna()
        above = float(px.iloc[-1]) > float(px.rolling(60).mean().iloc[-1])
        if vix:
            v = yf.download("^VIX", period="5d", progress=False)["Close"].dropna()
            calm = float(v.iloc[-1]) < 20
            return "bull" if above and calm else "bear" if not above else "neutral"
        return "bull" if above else "bear"
    except Exception as e:
        print(f"regime error: {e}")
        return "neutral"


def intraday_fraction(market: str) -> float:
    """今日交易時間已進行比例（量能年化用）。"""
    now = dt.datetime.utcnow()
    if market == "tw":   # 01:00–05:30 UTC
        start, total = now.replace(hour=1, minute=0), 270
    else:                # 13:30–20:00 UTC（夏令）
        start, total = now.replace(hour=13, minute=30), 390
    return min(1.0, max(0.2, (now - start).total_seconds() / 60 / total))


def build_provisional(hist: pd.DataFrame, quote: dict) -> pd.DataFrame:
    """歷史日K + 今日盤中臨時K棒。"""
    row = {"date": pd.Timestamp.today().normalize(),
           "open": quote["price"], "high": quote["price"],
           "low": quote["price"], "close": quote["price"],
           "volume": quote["volume"]}
    if hist["date"].iloc[-1].normalize() == row["date"]:
        hist = hist.iloc[:-1]
    return pd.concat([hist, pd.DataFrame([row])], ignore_index=True)


def rank_market(market: str):
    etf_meta = dfe.load_etf_types()[market]
    frac = intraday_fraction(market)

    if market == "tw":
        hist_all = history.load(history.TW_PATH)
        uni = dfe.tw_universe()
        rows = list(uni[["stock_id", "type"]].itertuples(index=False, name=None))
        quotes = dfe.tw_intraday_quotes(rows)
        names = dict(zip(uni["stock_id"], uni["stock_name"]))
        inds = dict(zip(uni["stock_id"], uni["industry_category"]))
        fundamentals = dfe.load_json("fundamentals_tw.json")
        regime = market_regime("^TWII")
        bench_id = "0050"
        min_price, min_avg_vol = 10, 500 * 1000  # 10元、500張
    else:
        hist_all = history.load(history.US_PATH)
        tickers = sorted(hist_all["stock_id"].unique())
        quotes = dfe.us_intraday_quotes(tickers)
        names, inds = {}, {}
        fundamentals = dfe.load_json("fundamentals_us.json")
        regime = market_regime("SPY", vix=True)
        bench_id = "SPY" if "SPY" in quotes else "VOO"
        min_price, min_avg_vol = 5, 300000

    hist_all["date"] = pd.to_datetime(hist_all["date"])
    grouped = {k: v.sort_values("date").reset_index(drop=True)
               for k, v in hist_all.groupby("stock_id")}

    # 大盤基準的60日報酬
    bench = grouped.get(bench_id)
    bench_ret60 = (bench["close"].iloc[-1] / bench["close"].iloc[-61] - 1) \
        if bench is not None and len(bench) > 61 else 0.0

    results = []
    for sid, q in quotes.items():
        hist = grouped.get(sid)
        if hist is None or len(hist) < MIN_BARS:
            continue
        if q["price"] < min_price or hist["volume"].tail(20).mean() < min_avg_vol:
            continue
        df = build_provisional(hist, q)
        try:
            tech = tech_scores(df, bench_ret60, intraday_frac=frac)
        except Exception:
            continue
        is_etf = sid in etf_meta
        if is_etf:
            pos = position_score(df["close"])
            fund = 100 - pos          # ETF：位階越低（越便宜）分數越高
            category = etf_meta[sid]["type"] + " ETF"
            name = etf_meta[sid]["name"]
            if "避開" in category:    # 槓桿/反向不進推薦
                continue
        else:
            pos = position_score(df["close"])
            fund = float(fundamentals.get(sid, 50))
            category = "個股-" + str(inds.get(sid, ""))
            name = names.get(sid, sid)
        results.append({
            "id": sid, "name": name, "category": category, "is_etf": is_etf,
            "score": total_score(tech, fund, regime),
            "price": tech["price"], "position": pos,
            "reason": reason_text(tech, fund),
            "factors": {k: round(v, 1) for k, v in tech.items()
                        if k in ("trend", "momentum", "volume", "volatility", "rel_strength")}
                       | {"fundamental": round(fund, 1)},
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    top10 = results[:10]

    # 保底：前10至少含 GUARANTEED_ETFS 檔 ETF
    n_etf = sum(r["is_etf"] for r in top10)
    if n_etf < GUARANTEED_ETFS:
        best_etfs = [r for r in results if r["is_etf"] and r not in top10]
        need = GUARANTEED_ETFS - n_etf
        for etf in best_etfs[:need]:
            for i in range(len(top10) - 1, -1, -1):
                if not top10[i]["is_etf"]:
                    top10[i] = etf
                    break
        top10.sort(key=lambda x: x["score"], reverse=True)

    for i, r in enumerate(top10, 1):
        r["rank"] = i

    heat = None
    # 台股加做「產業熱力圖」資料（方塊=成交值、顏色=漲跌）
    if market == "tw":
        agg = {}
        for sid, q in quotes.items():
            hist = grouped.get(sid)
            if hist is None or len(hist) < 2:
                continue
            prev = float(hist["close"].iloc[-1])
            if prev <= 0 or q["volume"] <= 0:
                continue
            ind = str(inds.get(sid, "")).strip() or "其他"
            chg = q["price"] / prev - 1
            val = q["price"] * q["volume"]
            a = agg.setdefault(ind, {"value": 0.0, "wsum": 0.0})
            a["value"] += val
            a["wsum"] += chg * val
        heat = [{"name": k, "value": round(v["value"] / 1e8, 2),  # 億元
                 "chg": round(v["wsum"] / v["value"] * 100, 2)}
                for k, v in agg.items() if v["value"] > 0]
        heat.sort(key=lambda x: -x["value"])
        dfe.save_json("heatmap_tw.json", {
            "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
            "industries": heat})
        print(f"heatmap: {len(heat)} industries")

    build_focus(market, quotes, grouped, names, etf_meta, heat, regime, frac)

    out = {"market": market, "regime": regime,
           "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
           "note": "技術面+基本面觀察清單，非投資建議；盤中價格仍會變動，下單前請再確認。",
           "top10": top10}
    dfe.save_json(f"top10_{market}.json", out)
    print(f"[{market}] regime={regime}, scanned={len(results)}, saved top10")
    for r in top10:
        print(f"  {r['rank']:2d}. {r['id']} {r['name']} [{r['category']}] "
              f"{r['score']}分 @{r['price']} — {r['reason']}")


def build_focus(market, quotes, grouped, names, etf_meta, heat, regime, frac):
    """每日焦點（完整欄位）：漲幅/跌幅/爆量各前5 + 強弱勢產業 → focus_{market}.json"""
    min_val = 1e8 if market == "tw" else 5e7   # 成交值門檻，過濾殭屍股
    rows = []
    for sid, q in quotes.items():
        hist = grouped.get(sid)
        if hist is None or len(hist) < 21:
            continue
        prev = float(hist["close"].iloc[-1])
        val = q["price"] * q["volume"]
        if prev <= 0 or val < min_val:
            continue
        vma = hist["volume"].tail(20).mean()
        rows.append({
            "id": sid,
            "name": names.get(sid) or etf_meta.get(sid, {}).get("name", sid),
            "price": round(q["price"], 2),
            "chg": round((q["price"] / prev - 1) * 100, 2),
            "vr": round((q["volume"] / max(frac, 0.2)) / vma, 1) if vma > 0 else 0.0,
            "value": round(val / 1e8, 1),   # 成交值（億）
        })
    by_chg = sorted(rows, key=lambda x: -x["chg"])
    by_vr = sorted(rows, key=lambda x: -x["vr"])
    dfe.save_json(f"focus_{market}.json", {
        "regime": regime,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "gainers": by_chg[:5],
        "losers": by_chg[-5:][::-1],
        "volume": by_vr[:5],
        "industries": sorted(heat, key=lambda x: -x["chg"])[:3] if heat else [],
        "weak_industries": sorted(heat, key=lambda x: x["chg"])[:3] if heat else []})
    print(f"focus_{market}: {len(rows)} candidates")


def build_etf_positions():
    """算所有 ETF 的位階，存成 etf_positions.json 給網站顯示（夜間更新時呼叫）。"""
    etf_meta = dfe.load_etf_types()
    rows = []
    for market, path, label in (("tw", history.TW_PATH, "台股"),
                                ("us", history.US_PATH, "美股")):
        hist = history.load(path)
        if hist.empty:
            continue
        hist["date"] = pd.to_datetime(hist["date"])
        for sid, meta in etf_meta[market].items():
            h = hist[hist["stock_id"] == sid].sort_values("date")
            if len(h) < 120:
                continue
            pos = position_score(h["close"].reset_index(drop=True))
            rows.append({"market": label, "id": sid, "name": meta["name"],
                         "type": meta["type"], "position": pos,
                         "price": round(float(h["close"].iloc[-1]), 2)})
    rows.sort(key=lambda x: x["position"])
    dfe.save_json("etf_positions.json", {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "etfs": rows})
    print(f"etf positions: {len(rows)} etfs saved")


def auto_mode() -> str:
    h = dt.datetime.utcnow().hour
    if 1 <= h <= 6:
        return "tw"
    if 13 <= h <= 21:
        return "us"
    return "fundamentals"


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
    if mode == "auto":
        mode = auto_mode()
    if mode == "fundamentals":
        import fundamentals
        history.update_tw()
        history.update_us()
        build_etf_positions()
        fundamentals.run_tw()
        fundamentals.run_us()
    else:
        rank_market(mode)
