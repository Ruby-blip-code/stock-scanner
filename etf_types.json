# -*- coding: utf-8 -*-
"""Flask 網站：每日前10推薦 + ETF 位階溫度計（部署在 Render）。

資料來源優先序：
1. GITHUB_RAW 環境變數（例：https://raw.githubusercontent.com/帳號/stock-scanner/main/data）
   → 永遠抓 repo 裡最新的名單，網站不用重新部署
2. 本地 data/ 資料夾（本機測試用）
"""
import json
import os
import requests
from flask import Flask, render_template_string

app = Flask(__name__)
DATA = os.path.join(os.path.dirname(__file__), "data")
RAW = os.getenv("GITHUB_RAW", "").rstrip("/")


def load(name):
    if RAW:
        try:
            r = requests.get(f"{RAW}/{name}", timeout=10)
            if r.ok:
                return r.json()
        except Exception:
            pass
    p = os.path.join(DATA, name)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return None


REGIME = {"bull": ("🟢 多頭", "#16a34a"), "neutral": ("🟡 震盪", "#ca8a04"),
          "bear": ("🔴 空頭", "#dc2626")}

TPL = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>每日前10選股</title>
<style>
 body{font-family:"Microsoft JhengHei",system-ui,sans-serif;margin:0;background:#f8fafc;color:#0f172a}
 .wrap{max-width:1100px;margin:0 auto;padding:16px}
 h1{font-size:1.5rem} h2{font-size:1.15rem;margin-top:28px}
 .note{background:#fef9c3;border:1px solid #fde047;border-radius:8px;padding:10px 14px;font-size:.9rem}
 .badge{display:inline-block;padding:2px 10px;border-radius:99px;color:#fff;font-size:.85rem}
 table{border-collapse:collapse;width:100%;background:#fff;font-size:.9rem;margin-top:8px}
 th,td{border:1px solid #e2e8f0;padding:6px 8px;text-align:left}
 th{background:#f1f5f9} tr:nth-child(even){background:#f8fafc}
 .etf{background:#ecfdf5} .cheap{color:#16a34a;font-weight:700}
 .mid{color:#ca8a04} .rich{color:#dc2626;font-weight:700}
 .meta{color:#64748b;font-size:.85rem}
 a{color:#2563eb;text-decoration:none}
</style></head><body><div class="wrap">
<h1>📈 每日前10推薦（台股＋美股）</h1>
<p class="note">技術面＋基本面<b>觀察清單，非投資建議</b>。名單為盤中掃描產生，
發布後至收盤價格仍會變動，下單前請自行確認即時報價；請自行控管停損與部位。</p>

{% for m, title, quote_url in markets %}
<h2>{{ title }}</h2>
{% if m %}
 <p class="meta">市場溫度：<span class="badge" style="background:{{ m.regime_color }}">{{ m.regime_label }}</span>
 ｜產生時間：{{ m.generated_at.replace("T"," ") }}</p>
 <table><tr><th>#</th><th>代號</th><th>名稱</th><th>類型</th><th>總分</th>
 <th>掃描價</th><th>位階<br><span class="meta">(低=便宜)</span></th><th>理由</th><th>看盤</th></tr>
 {% for r in m.top10 %}
 <tr class="{{ 'etf' if r.is_etf else '' }}">
  <td>{{ r.rank }}</td><td><b>{{ r.id }}</b></td><td>{{ r.name }}</td>
  <td>{{ r.category }}</td><td><b>{{ r.score }}</b></td><td>{{ r.price }}</td>
  <td>{{ r.position }}</td><td>{{ r.reason }}</td>
  <td><a href="{{ quote_url.format(id=r.id) }}" target="_blank">即時價↗</a></td>
 </tr>{% endfor %}
 </table>
{% else %}
 <p class="meta">尚無名單（等第一次掃描完成後就會出現）。</p>
{% endif %}
{% endfor %}

<h2>📊 ETF 位階溫度計</h2>
{% if etf %}
 <p class="meta">位階 &lt;30 = 歷史相對便宜區、30–70 = 中性、&gt;70 = 相對昂貴區
 （相對自己的歷史，非預測）｜更新：{{ etf.generated_at.replace("T"," ") }}</p>
 <table><tr><th>市場</th><th>代號</th><th>名稱</th><th>類型</th><th>現價</th><th>位階</th><th>判定</th></tr>
 {% for e in etf.etfs %}
 <tr><td>{{ e.market }}</td><td><b>{{ e.id }}</b></td><td>{{ e.name }}</td><td>{{ e.type }}</td>
 <td>{{ e.price }}</td><td>{{ e.position }}</td>
 <td class="{{ 'cheap' if e.position < 30 else 'mid' if e.position <= 70 else 'rich' }}">
 {{ '🟢 便宜區' if e.position < 30 else '🟡 中性' if e.position <= 70 else '🔴 昂貴區' }}</td>
 </tr>{% endfor %}
 </table>
{% else %}
 <p class="meta">尚無資料（夜間更新跑過一次後就會出現）。</p>
{% endif %}
<p class="meta" style="margin-top:24px">資料來源：FinMind／證交所／Yahoo Finance（免費方案，
台股報價為準即時）。本站僅供學習研究。</p>
</div></body></html>"""


def prep(d):
    if not d:
        return None
    label, color = REGIME.get(d.get("regime", "neutral"), REGIME["neutral"])
    d["regime_label"], d["regime_color"] = label, color
    return d


@app.route("/")
def index():
    markets = [
        (prep(load("top10_tw.json")), "🇹🇼 台股前10",
         "https://tw.stock.yahoo.com/quote/{id}"),
        (prep(load("top10_us.json")), "🇺🇸 美股前10",
         "https://finance.yahoo.com/quote/{id}"),
    ]
    return render_template_string(TPL, markets=markets,
                                  etf=load("etf_positions.json"))


@app.route("/healthz")   # 給 keep-alive 服務打的輕量端點
def healthz():
    return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
