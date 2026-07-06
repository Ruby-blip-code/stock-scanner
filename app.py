# -*- coding: utf-8 -*-
"""Flask 網站：每日前10 + ETF 位階 + K線 + 產業熱力圖 + 產業鏈地圖 + PWA。"""
import json
import os
import requests
from flask import Flask, render_template_string, Response

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
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


REGIME = {"bull": ("🟢 多頭", "#16a34a"), "neutral": ("🟡 震盪", "#ca8a04"),
          "bear": ("🔴 空頭", "#dc2626")}

HEAD = """<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<link rel="manifest" href="/manifest.json">
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/icon.svg">
<meta name="theme-color" content="#0f172a">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="每日前10">
<style>
 body{font-family:"Microsoft JhengHei",system-ui,sans-serif;margin:0;background:#f8fafc;color:#0f172a}
 .wrap{max-width:1100px;margin:0 auto;padding:16px}
 h1{font-size:1.5rem} h2{font-size:1.15rem;margin-top:28px}
 .nav{background:#0f172a;padding:10px 16px;position:sticky;top:0;z-index:9}
 .nav a{color:#e2e8f0;text-decoration:none;margin-right:18px;font-size:.95rem}
 .nav a.on{color:#38bdf8;font-weight:700}
 .note{background:#fef9c3;border:1px solid #fde047;border-radius:8px;padding:10px 14px;font-size:.9rem}
 .badge{display:inline-block;padding:2px 10px;border-radius:99px;color:#fff;font-size:.85rem}
 table{border-collapse:collapse;width:100%;background:#fff;font-size:.9rem;margin-top:8px}
 th,td{border:1px solid #e2e8f0;padding:6px 8px;text-align:left}
 th{background:#f1f5f9} tr:nth-child(even){background:#f8fafc}
 .etf{background:#ecfdf5} .cheap{color:#16a34a;font-weight:700}
 .mid{color:#ca8a04} .rich{color:#dc2626;font-weight:700}
 .meta{color:#64748b;font-size:.85rem}
 a{color:#2563eb;text-decoration:none}
</style>
<script>
if ('serviceWorker' in navigator) { navigator.serviceWorker.register('/sw.js'); }
</script>"""

NAV = """<div class="nav">
 <a href="/" class="{{ 'on' if page=='home' else '' }}">📈 每日前10</a>
 <a href="/heatmap" class="{{ 'on' if page=='heat' else '' }}">🔥 產業熱力圖</a>
 <a href="/map" class="{{ 'on' if page=='map' else '' }}">🗺️ 產業鏈地圖</a>
</div>"""

TPL = """<!doctype html>
<html lang="zh-Hant"><head><title>每日前10選股</title>""" + HEAD + "</head><body>" + NAV + """
<div class="wrap">
<h1>📈 每日前10推薦（台股＋美股）</h1>
<p class="note">技術面＋基本面<b>觀察清單，非投資建議</b>。名單為盤中掃描產生，
發布後至收盤價格仍會變動，下單前請自行確認即時報價；請自行控管停損與部位。</p>

{% for m, title, quote_url, mkt in markets %}
<h2>{{ title }}</h2>
{% if m %}
 <p class="meta">市場溫度：<span class="badge" style="background:{{ m.regime_color }}">{{ m.regime_label }}</span>
 ｜產生時間：{{ m.generated_at.replace("T"," ") }}</p>
 <table><tr><th>#</th><th>代號</th><th>名稱</th><th>類型</th><th>總分</th>
 <th>掃描價</th><th>位階<br><span class="meta">(低=便宜)</span></th><th>理由</th><th>K線</th><th>看盤</th></tr>
 {% for r in m.top10 %}
 <tr class="{{ 'etf' if r.is_etf else '' }}">
  <td>{{ r.rank }}</td><td><b>{{ r.id }}</b></td><td>{{ r.name }}</td>
  <td>{{ r.category }}</td><td><b>{{ r.score }}</b></td><td>{{ r.price }}</td>
  <td>{{ r.position }}</td><td>{{ r.reason }}</td>
  <td><a href="/chart/{{ mkt }}/{{ r.id }}">📊 K線</a></td>
  <td><a href="{{ quote_url.format(id=r.id) }}" target="_blank">即時價↗</a></td>
 </tr>{% endfor %}
 </table>
{% else %}
 <p class="meta">尚無名單（等第一次掃描完成後就會出現）。</p>
{% endif %}
{% endfor %}

<h2>📊 ETF 位階溫度計</h2>
{% if etf %}
 <p class="meta">位階 = 現在相對自己過去一年「貴或便宜」的程度（價格百分位＋均線乖離＋回檔深度綜合）。
 &lt;30 = 歷史相對便宜區、30–70 = 中性、&gt;70 = 相對昂貴區。是相對位置，不是漲跌預測。
 ｜更新：{{ etf.generated_at.replace("T"," ") }}</p>
 <table><tr><th>市場</th><th>代號</th><th>名稱</th><th>類型</th><th>現價</th><th>位階</th><th>判定</th><th>K線</th></tr>
 {% for e in etf.etfs %}
 <tr><td>{{ e.market }}</td><td><b>{{ e.id }}</b></td><td>{{ e.name }}</td><td>{{ e.type }}</td>
 <td>{{ e.price }}</td><td>{{ e.position }}</td>
 <td class="{{ 'cheap' if e.position < 30 else 'mid' if e.position <= 70 else 'rich' }}">
 {{ '🟢 便宜區' if e.position < 30 else '🟡 中性' if e.position <= 70 else '🔴 昂貴區' }}</td>
 <td><a href="/chart/{{ 'tw' if e.market == '台股' else 'us' }}/{{ e.id }}">📊 K線</a></td>
 </tr>{% endfor %}
 </table>
{% else %}
 <p class="meta">尚無資料（夜間更新跑過一次後就會出現）。</p>
{% endif %}
<p class="meta" style="margin-top:24px">📱 手機安裝：用 Chrome/Safari 開本站 → 瀏覽器選單 →
「加入主畫面」，就能像 App 一樣使用。<br>
資料來源：FinMind／證交所／Yahoo Finance（免費方案，台股報價為準即時）。本站僅供學習研究。</p>
</div></body></html>"""

CHART_TPL = """<!doctype html>
<html lang="zh-Hant"><head><title>{{ sym }} K線</title>""" + HEAD + "</head><body>" + NAV + """
<div style="padding:6px 10px;font-size:.9rem;background:#f1f5f9">
 <b>{{ sym }}</b> 日K（含 20/60MA、RSI、MACD，圖上「指標」可再加 KD、布林等）
</div>
<div id="tv" style="height:82vh"></div>
<script src="https://s3.tradingview.com/tv.js"></script>
<script>
new TradingView.widget({
  container_id: "tv", symbol: "{{ sym }}", interval: "D",
  timezone: "Asia/Taipei", locale: "zh_TW", theme: "light", autosize: true,
  studies: [
    {id: "MASimple@tv-basicstudies", inputs: {length: 20}},
    {id: "MASimple@tv-basicstudies", inputs: {length: 60}},
    "RSI@tv-basicstudies",
    "MACD@tv-basicstudies"
  ]
});
</script>
<p class="meta" style="padding:4px 10px">圖表由 TradingView 提供。</p>
</body></html>"""

HEAT_TPL = """<!doctype html>
<html lang="zh-Hant"><head><title>產業熱力圖</title>""" + HEAD + "</head><body>" + NAV + """
<div class="wrap">
<h1>🔥 台股產業熱力圖</h1>
{% if heat %}
<p class="meta">方塊大小 = 產業成交值（億元）、顏色 = 加權漲跌幅（紅漲綠跌）。
資料時間：{{ heat.generated_at.replace("T"," ") }}（每個交易日 12:10 盤中掃描時更新）</p>
<div id="hm" style="height:75vh;background:#fff;border:1px solid #e2e8f0"></div>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<script>
const data = {{ heat.industries | tojson }};
const chart = echarts.init(document.getElementById('hm'));
chart.setOption({
  tooltip: { formatter: p => p.name + '<br>成交值 ' + p.value[0] + ' 億<br>漲跌 ' + p.value[1] + '%' },
  visualMap: { min: -3, max: 3, dimension: 1, show: true, orient: 'horizontal',
    left: 'center', bottom: 0, text: ['漲', '跌'],
    inRange: { color: ['#16a34a', '#e2e8f0', '#dc2626'] } },
  series: [{ type: 'treemap', roam: false, nodeClick: false,
    breadcrumb: { show: false },
    label: { show: true, formatter: p => p.name + '\\n' + p.value[1] + '%' },
    data: data.map(d => ({ name: d.name, value: [d.value, d.chg] })) }]
});
window.addEventListener('resize', () => chart.resize());
</script>
{% else %}
<p class="meta">尚無資料——熱力圖在每個交易日 12:10 台股盤中掃描時產生，明天中午後再來看。</p>
{% endif %}
</div></body></html>"""

# 精選產業鏈地圖（v1 靜態版，可自行增修；僅含上市股票）
CHAINS = {
    "半導體": [
        ("上游：IC設計/材料設備", [("2454", "聯發科"), ("3034", "聯詠"), ("2379", "瑞昱"),
                                   ("3532", "台勝科"), ("2338", "光罩"), ("3413", "京鼎")]),
        ("中游：晶圓製造", [("2330", "台積電"), ("2303", "聯電"), ("6770", "力積電")]),
        ("下游：封測/通路", [("3711", "日月光投控"), ("2449", "京元電子"), ("8150", "南茂"),
                             ("3702", "大聯大")]),
    ],
    "AI 伺服器": [
        ("晶片/矽智財", [("2330", "台積電"), ("2454", "聯發科"), ("3661", "世芯-KY")]),
        ("零組件：電源/散熱/板卡", [("2308", "台達電"), ("3017", "奇鋐"), ("3324", "雙鴻"),
                                     ("3653", "健策"), ("3037", "欣興")]),
        ("整機組裝", [("2317", "鴻海"), ("2382", "廣達"), ("3231", "緯創"),
                      ("2356", "英業達"), ("6669", "緯穎")]),
    ],
    "電動車": [
        ("關鍵零組件", [("2308", "台達電"), ("1536", "和大"), ("3665", "貿聯-KY"),
                        ("1533", "車王電")]),
        ("車電/感測", [("2454", "聯發科"), ("3034", "聯詠"), ("2327", "國巨")]),
        ("整車/組裝", [("2317", "鴻海"), ("2201", "裕隆"), ("2204", "中華")]),
    ],
}

MAP_TPL = """<!doctype html>
<html lang="zh-Hant"><head><title>產業鏈地圖</title>""" + HEAD + "</head><body>" + NAV + """
<div class="wrap">
<h1>🗺️ 產業鏈地圖（精選版）</h1>
<p class="meta">點任一股票直接看K線。此為入門示意版，供應鏈歸類力求常見共識、僅供學習參考。</p>
{% for chain, stages in chains.items() %}
<h2>{{ chain }}</h2>
<div style="display:flex;gap:12px;flex-wrap:wrap">
 {% for stage, stocks in stages %}
 <div style="flex:1;min-width:240px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:10px">
  <div style="font-weight:700;margin-bottom:8px;color:#334155">{{ stage }}</div>
  {% for sid, name in stocks %}
  <a href="/chart/tw/{{ sid }}" style="display:inline-block;margin:3px;padding:4px 10px;
     background:#eff6ff;border:1px solid #bfdbfe;border-radius:99px;font-size:.85rem">
   {{ sid }} {{ name }}</a>
  {% endfor %}
 </div>
 {% endfor %}
</div>
{% endfor %}
</div></body></html>"""

ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
<rect width="100" height="100" rx="20" fill="#0f172a"/>
<polyline points="15,70 35,50 50,60 85,25" fill="none" stroke="#38bdf8" stroke-width="8"
 stroke-linecap="round" stroke-linejoin="round"/>
<polyline points="63,25 85,25 85,47" fill="none" stroke="#38bdf8" stroke-width="8"
 stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""

MANIFEST = {
    "name": "每日前10選股", "short_name": "每日前10",
    "start_url": "/?source=pwa", "display": "standalone",
    "background_color": "#f8fafc", "theme_color": "#0f172a",
    "icons": [{"src": "/icon.svg", "sizes": "any",
               "type": "image/svg+xml", "purpose": "any"}],
}

SW_JS = "self.addEventListener('install',e=>self.skipWaiting());" \
        "self.addEventListener('fetch',()=>{});"


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
         "https://tw.stock.yahoo.com/quote/{id}", "tw"),
        (prep(load("top10_us.json")), "🇺🇸 美股前10",
         "https://finance.yahoo.com/quote/{id}", "us"),
    ]
    return render_template_string(TPL, markets=markets,
                                  etf=load("etf_positions.json"), page="home")


@app.route("/heatmap")
def heatmap():
    return render_template_string(HEAT_TPL, heat=load("heatmap_tw.json"), page="heat")


@app.route("/map")
def industry_map():
    return render_template_string(MAP_TPL, chains=CHAINS, page="map")


@app.route("/chart/<market>/<sid>")
def chart(market, sid):
    sid = "".join(c for c in sid if c.isalnum() or c in ".-")[:12]  # 簡單消毒
    sym = f"TWSE:{sid}" if market == "tw" else sid
    return render_template_string(CHART_TPL, sym=sym, page="")


@app.route("/manifest.json")
def manifest():
    return Response(json.dumps(MANIFEST, ensure_ascii=False),
                    mimetype="application/manifest+json")


@app.route("/icon.svg")
def icon():
    return Response(ICON_SVG, mimetype="image/svg+xml")


@app.route("/sw.js")
def sw():
    return Response(SW_JS, mimetype="application/javascript")


@app.route("/healthz")   # 給 keep-alive 服務打的輕量端點
def healthz():
    return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
