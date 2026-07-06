# -*- coding: utf-8 -*-
"""技術指標與評分（純 pandas 實作，不吃 API 額度）。"""
import numpy as np
import pandas as pd

WEIGHTS = {"trend": 0.25, "momentum": 0.20, "fundamental": 0.20,
           "volume": 0.15, "volatility": 0.10, "rel_strength": 0.10}


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    diff = close.diff()
    up = diff.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-diff.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def macd_hist(close: pd.Series) -> pd.Series:
    macd = close.ewm(span=12).mean() - close.ewm(span=26).mean()
    return macd - macd.ewm(span=9).mean()


def atr_pct(df: pd.DataFrame, n: int = 14) -> pd.Series:
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - df["close"].shift()).abs(),
                    (df["low"] - df["close"].shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean() / df["close"] * 100


def position_score(close: pd.Series, lookback: int = 252) -> float:
    """位階溫度計 0-100：越低越便宜。價格百分位 + 200MA乖離百分位 + 回檔深度。"""
    s = close.tail(lookback)
    if len(s) < 60:
        return 50.0
    pctile = (s < s.iloc[-1]).mean() * 100
    ma200 = close.rolling(min(200, len(close))).mean()
    bias = (close / ma200 - 1) * 100
    b = bias.tail(lookback).dropna()
    bias_pct = (b < b.iloc[-1]).mean() * 100 if len(b) else 50
    drawdown = (1 - s.iloc[-1] / s.max()) * 100  # 距高點回檔%
    dd_score = max(0.0, 100 - drawdown * 4)      # 回檔越深位階越低
    return round(pctile * 0.4 + bias_pct * 0.4 + dd_score * 0.2, 1)


def tech_scores(df: pd.DataFrame, bench_ret60: float,
                intraday_frac: float = 1.0) -> dict:
    """對含今日臨時K棒的日線 df 計算各因子分數（0-100）。
    intraday_frac: 盤中掃描時，今日已進行的交易時間比例（用來年化當日量）。"""
    c = df["close"]
    price = float(c.iloc[-1])
    ma20 = c.rolling(20).mean().iloc[-1]
    ma60 = c.rolling(60).mean().iloc[-1]

    # 趨勢
    if price > ma20 > ma60:
        trend = 100
    elif price > ma20:
        trend = 50
    else:
        trend = 0

    # 動能
    r = float(rsi(c).iloc[-1])
    if 50 <= r <= 70:
        momentum = 90
    elif 40 <= r < 50 or 70 < r <= 80:
        momentum = 55
    else:
        momentum = 20
    if float(macd_hist(c).iloc[-1]) > 0:
        momentum = min(100, momentum + 10)

    # 量能（盤中要把當日量年化再比）
    vol_today = df["volume"].iloc[-1] / max(intraday_frac, 0.2)
    vol_ma20 = df["volume"].iloc[-21:-1].mean()
    vr = vol_today / vol_ma20 if vol_ma20 > 0 else 0
    if 1.5 <= vr <= 3:
        volume = 100
    elif 1.0 <= vr < 1.5:
        volume = 60
    elif vr > 3:
        volume = 40
    else:
        volume = 30

    # 波動定位
    ap = atr_pct(df).dropna()
    if len(ap) > 60:
        vp = (ap.tail(252) < ap.iloc[-1]).mean() * 100
        volatility = 100 if 30 <= vp <= 70 else 40
    else:
        volatility = 50

    # 相對強度（近60日 vs 大盤）
    if len(c) > 61:
        ret60 = c.iloc[-1] / c.iloc[-61] - 1
        excess = (ret60 - bench_ret60) * 100
        rel = float(np.clip(50 + excess * 2.5, 0, 100))
    else:
        rel = 50

    return {"trend": trend, "momentum": momentum, "volume": volume,
            "volatility": volatility, "rel_strength": rel,
            "rsi": round(r, 1), "vol_ratio": round(vr, 2), "price": price}


def total_score(tech: dict, fundamental: float, regime: str) -> float:
    """加權總分；依市場溫度微調權重。"""
    w = dict(WEIGHTS)
    if regime == "bull":       # 多頭：動能加重
        w["momentum"] += 0.05
        w["volatility"] -= 0.05
    elif regime == "bear":     # 空頭/震盪：趨勢與波動加重
        w["trend"] += 0.05
        w["momentum"] -= 0.05
    parts = {k: tech[k] for k in ("trend", "momentum", "volume", "volatility", "rel_strength")}
    parts["fundamental"] = fundamental
    return round(sum(parts[k] * w[k] for k in w), 1)


def reason_text(tech: dict, fundamental: float) -> str:
    """一句話推薦理由。"""
    bits = []
    if tech["trend"] == 100:
        bits.append("多頭排列")
    elif tech["trend"] == 50:
        bits.append("站上20MA")
    bits.append(f"RSI {tech['rsi']}")
    if tech["vol_ratio"] >= 1.5:
        bits.append(f"量增{tech['vol_ratio']}倍")
    if fundamental >= 70:
        bits.append("基本面強")
    return "、".join(bits)
