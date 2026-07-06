// Cloudflare Worker：準時觸發 GitHub Actions 掃描
// 部署方式見 部署設定教學.md 第 6 步。
//
// 需要在 Worker 的「設定 → 變數與機密」加三個變數：
//   GITHUB_REPO  （純文字）你的帳號/stock-scanner，例如 batty1652/stock-scanner
//   GITHUB_PAT   （機密）  GitHub Fine-grained token（教學第 5 步）
//   TRIGGER_KEY  （機密）  自己隨便取一串密碼，手動測試用
//
// Cron Triggers 要加四條（都是 UTC 時間）：
//   10 4 * * 1-5    → 台北 12:10 台股掃描
//   0 19 * * 1-5    → 美東 15:00（夏令期間由程式碼判斷放行）
//   0 20 * * 1-5    → 美東 15:00（冬令期間由程式碼判斷放行）
//   0 14 * * 1-5    → 台北 22:00 夜間更新
// 兩條美股 cron 搭配下面的夏令判斷，全年自動切換、不用手動改。

export default {
  // 排程觸發（主要用途）
  async scheduled(event, env, ctx) {
    let mode = null;
    switch (event.cron) {
      case "10 4 * * 1-5":
        mode = "tw";
        break;
      case "0 14 * * 1-5":
        mode = "fundamentals";
        break;
      case "0 19 * * 1-5":          // 夏令的美東 15:00
        if (isUsDst()) mode = "us";
        break;
      case "0 20 * * 1-5":          // 冬令的美東 15:00
        if (!isUsDst()) mode = "us";
        break;
    }
    if (mode) ctx.waitUntil(dispatch(mode, env));
  },

  // 手動測試用：瀏覽器開
  // https://你的worker網址/?key=你的TRIGGER_KEY&mode=tw
  async fetch(request, env) {
    const url = new URL(request.url);
    const mode = url.searchParams.get("mode");
    const key = url.searchParams.get("key");
    if (key !== env.TRIGGER_KEY) {
      return new Response("unauthorized", { status: 401 });
    }
    if (!["tw", "us", "fundamentals"].includes(mode)) {
      return new Response("mode 要是 tw / us / fundamentals 其中之一", { status: 400 });
    }
    const r = await dispatch(mode, env);
    return new Response(
      `dispatched "${mode}" → GitHub 回應 ${r.status}（204 = 成功）`);
  },
};

// 美東夏令時間判斷：3月第2個週日 ～ 11月第1個週日
function isUsDst() {
  const now = new Date();
  const y = now.getUTCFullYear();
  return now >= nthSundayUTC(y, 2, 2) && now < nthSundayUTC(y, 10, 1);
}

function nthSundayUTC(year, monthIndex, n) {
  const d = new Date(Date.UTC(year, monthIndex, 1, 7, 0, 0)); // 約當地清晨切換
  let count = 0;
  while (true) {
    if (d.getUTCDay() === 0) {
      count += 1;
      if (count === n) return d;
    }
    d.setUTCDate(d.getUTCDate() + 1);
  }
}

async function dispatch(mode, env) {
  return fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/dispatches`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.GITHUB_PAT}`,
      "Accept": "application/vnd.github+json",
      "User-Agent": "cf-worker-stock-scan",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ event_type: mode }),
  });
}
