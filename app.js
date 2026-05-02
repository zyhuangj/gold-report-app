const REFRESH_MS = 10000;
const ORIGINAL_DASHBOARD_URL = "./source-dashboard.html";
const PAXG_INVESTING_URL = "https://hk.investing.com/crypto/pax-gold/paxg-usd";
const PAXG_COINGECKO_URL =
  "https://api.coingecko.com/api/v3/simple/price?ids=pax-gold&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true&include_market_cap=true&include_last_updated_at=true";

const frame = document.querySelector("#dashboardFrame");
const statusText = document.querySelector("#statusText");
const lastChecked = document.querySelector("#lastChecked");
const refreshBtn = document.querySelector("#refreshBtn");
const autoRefresh = document.querySelector("#autoRefresh");
const paxgPrice = document.querySelector("#paxgPrice");
const paxgChange = document.querySelector("#paxgChange");
const paxgMeta = document.querySelector("#paxgMeta");
const paxgVolume = document.querySelector("#paxgVolume");
const paxgMarketCap = document.querySelector("#paxgMarketCap");
const paxgStatus = document.querySelector("#paxgStatus");

let timer = null;
let refreshing = false;
let lastPaxg = null;

function formatTime(iso) {
  if (!iso) return "尚未檢查";
  return new Date(iso).toLocaleString("zh-TW", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
}

function setStatus(message, kind = "") {
  statusText.textContent = message;
  statusText.className = kind;
}

function reloadOriginalPage() {
  const separator = ORIGINAL_DASHBOARD_URL.includes("?") ? "&" : "?";
  frame.src = `${ORIGINAL_DASHBOARD_URL}${separator}t=${Date.now()}`;
}

function compactUsd(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "--";
  return new Intl.NumberFormat("zh-TW", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 2
  }).format(value);
}

function priceUsd(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "--";
  return new Intl.NumberFormat("zh-TW", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2
  }).format(value);
}

function pct(value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "--";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function renderPaxg(payload) {
  if (payload.price) lastPaxg = payload;
  const quote = payload.price ? payload : lastPaxg;

  if (!quote) {
    paxgMeta.textContent = payload.message ? `PAXG/USD 更新失敗：${payload.message}` : "PAXG/USD 暫無資料";
    paxgStatus.textContent = "無資料";
    paxgStatus.className = "bad";
    return;
  }

  const change = quote.changePct24h;
  paxgPrice.textContent = priceUsd(quote.price);
  paxgChange.textContent = pct(change);
  paxgChange.className = `paxg-change ${change > 0 ? "up" : change < 0 ? "down" : ""}`;
  paxgVolume.textContent = compactUsd(quote.volume24h);
  paxgMarketCap.textContent = compactUsd(quote.marketCap);
  paxgMeta.textContent = `資料源 ${quote.source}，對照 Investing.com PAXG/USD；報價時間 ${formatTime(quote.quoteUpdatedAt)}`;
  paxgStatus.textContent = payload.stale ? "使用上一筆成功資料" : `更新 ${formatTime(payload.checkedAt)}`;
  paxgStatus.className = payload.stale ? "stale" : "";
}

async function refreshPaxg() {
  try {
    const response = await fetch(PAXG_COINGECKO_URL, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`);
    }
    const data = await response.json();
    const quote = data["pax-gold"];
    if (!quote || typeof quote.usd !== "number") {
      throw new Error("PAXG quote payload missing price");
    }
    renderPaxg({
      ok: true,
      symbol: "PAXG/USD",
      name: "PAX Gold 美元",
      exchange: "PAXG market aggregate",
      price: quote.usd,
      changePct24h: quote.usd_24h_change ?? null,
      volume24h: quote.usd_24h_vol ?? null,
      marketCap: quote.usd_market_cap ?? null,
      quoteUpdatedAt: quote.last_updated_at ? new Date(quote.last_updated_at * 1000).toISOString() : null,
      checkedAt: new Date().toISOString(),
      source: "CoinGecko",
      sourceUrl: "https://www.coingecko.com/en/coins/pax-gold",
      investingUrl: PAXG_INVESTING_URL,
      stale: false
    });
  } catch (error) {
    renderPaxg({
      ...(lastPaxg || {}),
      ok: false,
      stale: Boolean(lastPaxg),
      checkedAt: new Date().toISOString(),
      message: error.message
    });
  }
}

function loadStatus() {
  const checkedAt = new Date().toISOString();
  lastChecked.textContent = `檢查：${formatTime(checkedAt)}`;
  setStatus(`正在顯示原始部署頁面，檢查時間 ${formatTime(checkedAt)}`, "ok");
}

function refreshOriginalPage(source = "manual") {
  if (refreshing) return;
  refreshing = true;
  refreshBtn.disabled = true;
  refreshBtn.textContent = "更新中";
  setStatus(source === "auto" ? "自動檢查原始部署頁面中" : "手動檢查原始部署頁面中", "warn");

  try {
    reloadOriginalPage();
    loadStatus();
    setStatus("原始部署頁面正常，舊圖表與目前頁面保持不變。", "ok");
  } catch (error) {
    setStatus(`更新失敗：${error.message}。舊圖表與目前頁面保持不變。`, "bad");
  } finally {
    refreshing = false;
    refreshBtn.disabled = false;
    refreshBtn.textContent = "手動更新";
  }
}

function schedule() {
  if (timer) clearInterval(timer);
  if (autoRefresh.checked) {
    timer = setInterval(() => {
      refreshOriginalPage("auto");
      refreshPaxg();
    }, REFRESH_MS);
  }
}

refreshBtn.addEventListener("click", () => {
  refreshOriginalPage("manual");
  refreshPaxg();
});
autoRefresh.addEventListener("change", schedule);

reloadOriginalPage();
loadStatus();
refreshPaxg();
schedule();
