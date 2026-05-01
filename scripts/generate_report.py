from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests
import yfinance as yf
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
PUBLIC.mkdir(exist_ok=True)

PDF_PATH = PUBLIC / "gold_report_compact.pdf"
HTML_PATH = PUBLIC / "index.html"
JSON_PATH = PUBLIC / "latest_data.json"

FRED_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"

# 每個報告固定檢查的市場指標
YF_TICKERS = {
    "XAU/USD 現貨金": "XAUUSD=X",
    "COMEX 黃金期貨": "GC=F",
    "白銀": "SI=F",
    "鉑金": "PL=F",
    "銅": "HG=F",
    "DXY / 美元指數": "DX-Y.NYB",
    "VIX": "^VIX",
    "S&P 500": "^GSPC",
    "Dow Jones": "^DJI",
    "Nasdaq": "^IXIC",
}

FRED_SERIES = {
    "美債 2Y": "DGS2",
    "美債 10Y": "DGS10",
    "美債 30Y": "DGS30",
    "5Y TIPS real yield": "DFII5",
    "10Y TIPS real yield": "DFII10",
    "5Y Breakeven": "T5YIE",
    "10Y Breakeven": "T10YIE",
    "SOFR": "SOFR",
    "ON RRP": "RRPONTSYD",
    "銀行準備金": "WRESBAL",
    "TGA": "WTREGEN",
    "HY OAS": "BAMLH0A0HYM2",
    "IG OAS": "BAMLC0A0CM",
    "M2": "M2SL",
    "Import Price Index": "IR",
    "Average Hourly Earnings": "CES0500000003",
    "Broad Dollar Index": "DTWEXBGS",
    "3M T-bill": "DTB3",
}

@dataclass
class Indicator:
    category: str
    name: str
    unit: str
    latest: str
    previous: str
    change: str
    obs_date: str
    impact: str
    why: str
    source: str
    values: list[float]
    labels: list[str]


def fred_series(series: str, months: int = 12) -> pd.DataFrame:
    url = FRED_BASE.format(series=series)
    df = pd.read_csv(url)
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna()
    cutoff = pd.Timestamp.utcnow().tz_localize(None) - pd.DateOffset(months=months)
    return df[df["date"] >= cutoff].copy()


def yf_series(ticker: str, period: str = "1y") -> pd.DataFrame:
    data = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=False)
    if data.empty:
        raise RuntimeError(f"No data for {ticker}")
    if isinstance(data.columns, pd.MultiIndex):
        close = data["Close"].iloc[:, 0]
    else:
        close = data["Close"]
    df = close.dropna().reset_index()
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    return df


def pct_change(latest: float, prev: float) -> tuple[float, float]:
    diff = latest - prev
    pct = diff / prev * 100 if prev else float("nan")
    return diff, pct


def fmt_num(x: float, unit: str = "") -> str:
    if x is None or not np.isfinite(x):
        return "n/a"
    if abs(x) >= 1000:
        s = f"{x:,.2f}"
    elif abs(x) >= 10:
        s = f"{x:.2f}"
    else:
        s = f"{x:.3f}"
    return s.rstrip("0").rstrip(".") + (unit if unit and unit.startswith("%") else "")


def make_indicator_from_df(category, name, unit, df, impact, why, source, percent_unit=False) -> Indicator:
    df = df.dropna().tail(260)
    latest = float(df["value"].iloc[-1])
    prev = float(df["value"].iloc[-2]) if len(df) >= 2 else latest
    diff, pct = pct_change(latest, prev)
    obs_date = str(pd.to_datetime(df["date"].iloc[-1]).date())
    labels = [str(pd.to_datetime(d).date()) for d in df["date"].tail(12)]
    values = [float(v) for v in df["value"].tail(12)]
    suffix = "%" if percent_unit else ""
    return Indicator(
        category, name, unit,
        fmt_num(latest, suffix),
        fmt_num(prev, suffix),
        f"{diff:+.3f} / {pct:+.2f}%",
        obs_date,
        impact, why, source, values, labels
    )


def safe_indicator(category, name, unit, func, impact, why, source) -> Indicator:
    try:
        return func()
    except Exception as e:
        return Indicator(category, name, unit, "unavailable", "n/a", f"source failed: {type(e).__name__}", "n/a",
                         "neutral", why + "（本次資料源未回傳，需人工檢查。）", source, [0, 0, 0], ["n/a", "n/a", "n/a"])


def build_indicators() -> list[Indicator]:
    indicators: list[Indicator] = []

    yf_meta = {
        "XAU/USD 現貨金": ("黃金與貴金屬", "USD/oz", "neutral / bullish", "金價上升利多；但仍需看美元與實質利率是否同步配合。"),
        "COMEX 黃金期貨": ("黃金與貴金屬", "USD/oz", "bullish", "期貨上升代表槓桿資金回補黃金風險敞口。"),
        "白銀": ("黃金與貴金屬", "USD/oz", "bullish", "白銀強於黃金代表貴金屬高 beta 端回暖。"),
        "鉑金": ("黃金與貴金屬", "USD/oz", "neutral", "鉑金偏工業屬性，主要反映商品循環與風險偏好。"),
        "銅": ("黃金與貴金屬", "USD/lb", "neutral", "銅弱代表成長降溫；需搭配信用壓力才明顯利多黃金。"),
        "DXY / 美元指數": ("美元與匯率", "index", "bullish", "美元下跌降低非美元買家買金成本，減輕美元翻譯壓力。"),
        "VIX": ("信用 / 波動 / 股市", "index", "bearish", "VIX 低代表避險需求不足，不利黃金避險溢價。"),
        "S&P 500": ("信用 / 波動 / 股市", "index", "neutral / bearish", "股市強代表風險偏好仍在，避險黃金需求下降。"),
        "Dow Jones": ("信用 / 波動 / 股市", "index", "neutral / bearish", "Dow 上漲代表資金偏風險資產，不利避險溢價。"),
        "Nasdaq": ("信用 / 波動 / 股市", "index", "bearish", "科技股強代表資金未大規模轉向避險。"),
    }

    for name, ticker in YF_TICKERS.items():
        cat, unit, impact, why = yf_meta[name]
        indicators.append(safe_indicator(
            cat, name, unit,
            lambda name=name, ticker=ticker, cat=cat, unit=unit, impact=impact, why=why:
                make_indicator_from_df(cat, name, unit, yf_series(ticker), impact, why, f"Yahoo Finance / yfinance {ticker}"),
            impact, why, f"Yahoo Finance / yfinance {ticker}"
        ))

    fred_meta = {
        "美債 2Y": ("名目利率與曲線", "%", "bearish", "短端利率上升代表降息預期後延，壓制無息黃金。", True),
        "美債 10Y": ("名目利率與曲線", "%", "bearish", "10Y 是黃金估值核心折現率，走高會壓制黃金。", True),
        "美債 30Y": ("名目利率與曲線", "%", "bearish", "30Y 上升反映期限溢價或長期通膨壓力。", True),
        "5Y TIPS real yield": ("實質利率與通膨", "%", "bearish", "實質利率上升提高持有黃金機會成本。", True),
        "10Y TIPS real yield": ("實質利率與通膨", "%", "bearish", "10Y 實質利率接近高位會壓制黃金。", True),
        "5Y Breakeven": ("實質利率與通膨", "%", "bullish", "通膨補償高位支撐抗通膨買金需求。", True),
        "10Y Breakeven": ("實質利率與通膨", "%", "bullish", "長期通膨預期高位支撐黃金避險需求。", True),
        "SOFR": ("Fed與短端流動性", "%", "neutral", "SOFR 急升才代表融資壓力；平穩則中性。", True),
        "ON RRP": ("Fed與短端流動性", "$bn", "neutral / stress-watch", "ON RRP 低表示短端流動性緩衝偏薄。", False),
        "銀行準備金": ("Fed與短端流動性", "$bn", "bullish / stress-watch", "準備金下降代表銀行體系流動性變緊。", False),
        "TGA": ("Fed與短端流動性", "$bn", "bearish liquidity", "TGA 上升通常等於財政部抽走市場現金。", False),
        "HY OAS": ("信用 / 波動 / 股市", "%", "bearish", "高收益利差未擴大，避險買金需求弱。", True),
        "IG OAS": ("信用 / 波動 / 股市", "%", "bearish", "投資級利差穩定代表系統性信用壓力不足。", True),
        "3M T-bill": ("Fed與短端流動性", "%", "bearish", "短債收益率高，現金替代吸引力分流黃金。", True),
    }

    for name, series in FRED_SERIES.items():
        if name not in fred_meta:
            continue
        cat, unit, impact, why, pct = fred_meta[name]
        indicators.append(safe_indicator(
            cat, name, unit,
            lambda name=name, series=series, cat=cat, unit=unit, impact=impact, why=why, pct=pct:
                make_indicator_from_df(cat, name, unit, fred_series(series), impact, why, f"FRED {series}", pct),
            impact, why, f"FRED {series}"
        ))

    # Calculated ratios and curves
    by_name = {i.name: i for i in indicators}

    def get_latest_float(name):
        s = by_name.get(name).latest.replace(",", "").replace("%", "")
        return float(s) if s not in ("unavailable", "n/a") else None

    try:
        y10 = get_latest_float("美債 10Y")
        y2 = get_latest_float("美債 2Y")
        y3m = get_latest_float("3M T-bill")
        for cname, val, prev in [
            ("10Y-2Y", y10-y2, 0),
            ("10Y-3M", y10-y3m, 0),
        ]:
            indicators.append(Indicator("名目利率與曲線", cname, "pp", fmt_num(val), "n/a", "calculated", datetime.now().date().isoformat(),
                                        "neutral", "曲線變化需分辨由短端下行或長端上行造成；危機型短端下行較利多黃金。",
                                        "calculated from FRED", [val, val, val], ["prev", "mid", "latest"]))
    except Exception:
        pass

    try:
        gold = get_latest_float("XAU/USD 現貨金") or get_latest_float("COMEX 黃金期貨")
        spx = get_latest_float("S&P 500")
        dow = get_latest_float("Dow Jones")
        nas = get_latest_float("Nasdaq")
        for cname, val in [
            ("Dow/Gold", dow/gold),
            ("S&P500/Gold", spx/gold),
            ("Nasdaq/Gold", nas/gold),
        ]:
            indicators.append(Indicator("輪動 / 資金流", cname, "ratio", fmt_num(val), "n/a", "calculated", datetime.now().date().isoformat(),
                                        "hold gold" if cname == "Dow/Gold" else "neutral",
                                        "股票相對黃金未極端便宜前，不支持大量轉股。",
                                        "calculated from market data", [val, val, val], ["prev", "mid", "latest"]))
    except Exception:
        pass

    # Static placeholders for series that often require special access
    indicators.append(Indicator("輪動 / 資金流", "GLD ETF holdings", "tonnes", "check issuer/WGC", "n/a", "not automated", "n/a",
                                "neutral", "ETF 流入利多黃金；流出削弱實物支持型需求。", "WGC / issuer", [0,0,0], ["n/a","n/a","n/a"]))
    indicators.append(Indicator("輪動 / 資金流", "IAU ETF flows", "flow", "check issuer/WGC", "n/a", "not automated", "n/a",
                                "neutral", "ETF 流入利多黃金；流出削弱實物支持型需求。", "iShares / WGC", [0,0,0], ["n/a","n/a","n/a"]))
    indicators.append(Indicator("輪動 / 資金流", "CFTC gold positioning", "contracts", "weekly CoT", "n/a", "weekly", "weekly",
                                "neutral", "淨多支撐趨勢，但過度擁擠會提高去槓桿風險。", "CFTC CoT", [0,0,0], ["n/a","n/a","n/a"]))

    return indicators


def inflation_dashboard() -> list[list[str]]:
    return [
        ["需求拉動型通膨", "GDP、零售銷售、消費支出、失業率、薪資", "經濟強、消費強、失業低，代表需求撐住物價", "需求強會讓 Fed 不急降息，短線壓黃金"],
        ["成本推動型通膨", "Brent、WTI、天然氣、ISM Prices、PPI", "油價、原物料、運輸與工資成本上升", "中期偏多，但短線可能因高利率預期壓黃金"],
        ["貨幣型通膨", "M2、Fed 資產負債表、銀行準備金、信貸", "貨幣供給擴張代表紙幣購買力壓力", "中長期偏多，需看信用是否同步擴張"],
        ["輸入型通膨", "美元、進口物價、油價、運價", "美元走弱或進口價格上升會帶入外部成本", "若美元續弱，對黃金明顯偏多"],
        ["結構型通膨", "去全球化、關稅、能源轉型、供應鏈、財政赤字", "不是短期升息即可解決", "中長期利多黃金"],
        ["停滯性通膨", "PCE/CPI + GDP 放慢 + 失業率上升", "經濟變差但通膨不降", "若經濟轉弱但通膨維持高，黃金會更強"],
        ["資產通膨", "股市估值、房價、信用利差、槓桿", "資產漲太快代表泡沫或流動性過剩", "泡沫破裂初期可能賣金，後期偏多"],
        ["薪資—物價螺旋", "平均時薪、ECI、失業率、勞動參與率", "薪資持續漲、企業轉嫁成本，通膨變黏", "若薪資持續追物價，黃金中期偏多"],
        ["預期型通膨", "Breakeven、5Y5Y、消費者預期", "市場相信未來會漲價，就會提前買", "偏多黃金，尤其市場不信央行時"],
        ["惡性通膨", "匯率崩跌、財政赤字貨幣化、M2 暴增", "貨幣信用崩潰，不是一般 CPI 高一點", "若發生會極度利多，目前非主線"],
    ]


def draw_pdf(indicators: list[Indicator]):
    plt.rcParams["font.family"] = "DejaVu Sans"
    with PdfPages(PDF_PATH) as pdf:
        fig = plt.figure(figsize=(11.69, 8.27))
        fig.suptitle("Gold Macro Dashboard | Compact PDF", fontsize=18, fontweight="bold")
        ax = fig.add_subplot(111)
        ax.axis("off")
        rows = [[i.name, i.latest, i.change, i.obs_date, i.impact] for i in indicators[:28]]
        tbl = ax.table(cellText=rows, colLabels=["Indicator","Latest","Change","Date","Gold impact"],
                       loc="center", cellLoc="left", colLoc="left")
        tbl.auto_set_font_size(False); tbl.set_fontsize(6.5); tbl.scale(1, 1.15)
        ax.text(0, 1.02, f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", transform=ax.transAxes, fontsize=8)
        pdf.savefig(fig, bbox_inches="tight"); plt.close(fig)

        fig = plt.figure(figsize=(11.69, 8.27))
        ax = fig.add_subplot(111); ax.axis("off")
        tbl = ax.table(cellText=inflation_dashboard(), colLabels=["Inflation type","Indicators","How to read","Gold impact"],
                       loc="center", cellLoc="left", colLoc="left")
        tbl.auto_set_font_size(False); tbl.set_fontsize(6.2); tbl.scale(1, 1.4)
        ax.set_title("Inflation Regime Dashboard", fontsize=16, fontweight="bold")
        pdf.savefig(fig, bbox_inches="tight"); plt.close(fig)

        cats = []
        for i in indicators:
            if i.category not in cats:
                cats.append(i.category)
        for cat in cats:
            group = [i for i in indicators if i.category == cat]
            for start in range(0, len(group), 6):
                fig, axes = plt.subplots(2, 3, figsize=(11.69, 8.27))
                fig.suptitle(cat, fontsize=15, fontweight="bold")
                axes = axes.flatten()
                for ax, ind in zip(axes, group[start:start+6]):
                    vals = ind.values if ind.values else [0,0,0]
                    ax.plot(range(len(vals)), vals, linewidth=1.5)
                    ax.set_title(ind.name, fontsize=8, fontweight="bold")
                    ax.set_xticks([0, len(vals)-1])
                    ax.set_xticklabels([ind.labels[0], ind.labels[-1]], fontsize=6)
                    ax.tick_params(axis="y", labelsize=6)
                    ax.grid(True, alpha=.3)
                    ax.text(0, -0.30, f"Latest: {ind.latest} | {ind.obs_date}\nGold impact: {ind.impact}\nWhy: {ind.why[:70]}",
                            transform=ax.transAxes, fontsize=5.6, va="top")
                for ax in axes[len(group[start:start+6]):]:
                    ax.axis("off")
                fig.tight_layout(rect=[0,0.03,1,0.95])
                pdf.savefig(fig)
                plt.close(fig)

        fig = plt.figure(figsize=(11.69, 8.27))
        ax = fig.add_subplot(111); ax.axis("off")
        conclusion = (
            "Conclusion: 持有、等待。若實質利率下行、美元續弱、ETF/CFTC 資金轉強或信用/流動性壓力擴大，才升級為加碼；"
            "若實質利率與美元續上行，則維持等待或小幅控風險。"
        )
        bullets = [
            "Bullish: 美元偏弱、breakeven 高位、成本/結構/預期型通膨、流動性緩衝變薄。",
            "Bearish: 名目/實質利率偏高、Fed 降息預期後延、信用/VIX 未出現危機型避險。",
            "Stress: SOFR、ON RRP、銀行準備金、TGA 必須持續追蹤。",
            "Rotation: Dow/Gold、S&P500/Gold、Nasdaq/Gold 未到極端便宜區前，不大量轉股。",
        ]
        ax.text(.05,.90, conclusion, fontsize=13, weight="bold", wrap=True)
        ax.text(.05,.72, "\n".join("• "+b for b in bullets), fontsize=11, va="top", wrap=True)
        pdf.savefig(fig, bbox_inches="tight"); plt.close(fig)


def build_html(indicators: list[Indicator]):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    cards = "".join(f"""
      <div class="card">
        <b>{i.name}</b>
        <div>Latest: {i.latest}</div>
        <div>Change: {i.change}</div>
        <div>Date: {i.obs_date}</div>
        <div>Gold impact: {i.impact}</div>
      </div>
    """ for i in indicators[:12])
    HTML_PATH.write_text(f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>黃金每日報告 App</title>
<style>
body{{margin:0;background:#0f172a;color:#e5e7eb;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans TC",Arial,sans-serif}}
.app{{max-width:980px;margin:auto;padding:18px 14px 80px}}
.hero,.card{{background:#111827;border:1px solid #334155;border-radius:20px;padding:16px;margin:10px 0}}
h1{{font-size:25px}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}}
.btn{{display:block;text-align:center;text-decoration:none;border-radius:16px;padding:14px;margin:10px 0;font-weight:800;background:#fbbf24;color:#111827}}
.small{{font-size:12px;color:#94a3b8}}
</style></head><body><div class="app">
<section class="hero"><h1>黃金每日報告 App</h1><p>最後更新：{now}</p><p class="small">Arizona 7:30 AM / 7:30 PM 自動更新</p></section>
<a class="btn" href="gold_report_compact.pdf">打開最新 PDF 報告</a>
<h2>最新重點</h2><div class="grid">{cards}</div>
<section class="hero"><b>結論：</b>持有、等待。完整內容請開啟 PDF。</section>
</div></body></html>""", encoding="utf-8")


def main():
    indicators = build_indicators()
    draw_pdf(indicators)
    build_html(indicators)
    JSON_PATH.write_text(json.dumps([i.__dict__ for i in indicators], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {PDF_PATH}")
    print(f"Wrote {HTML_PATH}")


if __name__ == "__main__":
    main()
