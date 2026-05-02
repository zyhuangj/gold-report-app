from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
PUBLIC.mkdir(exist_ok=True)

PDF_PATH = PUBLIC / "gold_report_compact.pdf"
HTML_PATH = PUBLIC / "index.html"
JSON_PATH = PUBLIC / "latest_data.json"

FRED_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"


def setup_chinese_font() -> None:
    preferred = [
        "Noto Sans CJK TC",
        "Noto Sans CJK JP",
        "Noto Sans CJK SC",
        "Noto Serif CJK TC",
        "Noto Serif CJK JP",
        "Arial Unicode MS",
        "Microsoft JhengHei",
        "SimHei",
        "DejaVu Sans",
    ]

    available = {f.name for f in font_manager.fontManager.ttflist}
    chosen = None

    for font in preferred:
        if font in available:
            chosen = font
            break

    if chosen is None:
        chosen = "DejaVu Sans"

    plt.rcParams["font.family"] = chosen
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["pdf.fonttype"] = 42
    plt.rcParams["ps.fonttype"] = 42


setup_chinese_font()


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


YF_TICKERS = {
    "XAU/USD 現貨金": ["XAUUSD=X", "GC=F"],
    "COMEX 黃金期貨": ["GC=F"],
    "白銀": ["SI=F"],
    "鉑金": ["PL=F"],
    "銅": ["HG=F"],
    "DXY / 美元指數": ["DX-Y.NYB"],
    "VIX": ["^VIX"],
    "S&P 500": ["^GSPC"],
    "Dow Jones": ["^DJI"],
    "Nasdaq": ["^IXIC"],
}

YF_META = {
    "XAU/USD 現貨金": ("黃金與貴金屬", "USD/oz", "neutral / bullish", "現貨金上升利多黃金；若資料源失敗，會用 COMEX 黃金期貨作備援。"),
    "COMEX 黃金期貨": ("黃金與貴金屬", "USD/oz", "bullish", "期貨上升代表槓桿資金回補黃金風險敞口。"),
    "白銀": ("黃金與貴金屬", "USD/oz", "bullish", "白銀強於黃金，代表貴金屬高 beta 端回暖。"),
    "鉑金": ("黃金與貴金屬", "USD/oz", "neutral", "鉑金偏工業屬性，主要反映商品循環與風險偏好。"),
    "銅": ("黃金與貴金屬", "USD/lb", "neutral", "銅弱代表成長降溫；若信用壓力同步擴大才明顯利多黃金。"),
    "DXY / 美元指數": ("美元與匯率", "index", "bullish", "美元下跌降低非美元買家購金成本，減輕美元翻譯壓力。"),
    "VIX": ("信用 / 波動 / 股市", "index", "bearish", "VIX 低代表避險需求不足，不利黃金避險溢價。"),
    "S&P 500": ("信用 / 波動 / 股市", "index", "neutral / bearish", "股市強代表風險偏好仍在，避險黃金需求下降。"),
    "Dow Jones": ("信用 / 波動 / 股市", "index", "neutral / bearish", "Dow 上漲代表資金偏風險資產，不利避險溢價。"),
    "Nasdaq": ("信用 / 波動 / 股市", "index", "bearish", "科技股強代表資金未大規模轉向避險。"),
}

FRED_SERIES = {
    "美債 2Y": ("DGS2", "名目利率與曲線", "%", "bearish", "短端利率上升代表降息預期後延，壓制無息黃金。", True),
    "美債 10Y": ("DGS10", "名目利率與曲線", "%", "bearish", "10Y 是黃金估值核心折現率，走高會壓制黃金。", True),
    "美債 30Y": ("DGS30", "名目利率與曲線", "%", "bearish", "30Y 上升反映期限溢價或長期通膨壓力。", True),
    "5Y TIPS real yield": ("DFII5", "實質利率與通膨", "%", "bearish", "實質利率上升提高持有黃金機會成本。", True),
    "10Y TIPS real yield": ("DFII10", "實質利率與通膨", "%", "bearish", "10Y 實質利率高位會壓制黃金。", True),
    "5Y Breakeven": ("T5YIE", "實質利率與通膨", "%", "bullish", "通膨補償高位支撐抗通膨買金需求。", True),
    "10Y Breakeven": ("T10YIE", "實質利率與通膨", "%", "bullish", "長期通膨預期高位支撐黃金避險需求。", True),
    "SOFR": ("SOFR", "Fed 與短端流動性", "%", "neutral", "SOFR 急升才代表融資壓力；平穩則中性。", True),
    "ON RRP": ("RRPONTSYD", "Fed 與短端流動性", "$bn", "neutral / stress-watch", "ON RRP 低代表短端流動性緩衝偏薄。", False),
    "銀行準備金": ("WRESBAL", "Fed 與短端流動性", "$bn", "bullish / stress-watch", "準備金下降代表銀行體系流動性變緊。", False),
    "TGA": ("WTREGEN", "Fed 與短端流動性", "$bn", "bearish liquidity", "TGA 上升通常等於財政部抽走市場現金。", False),
    "HY OAS": ("BAMLH0A0HYM2", "信用 / 波動 / 股市", "%", "bearish", "高收益利差未擴大，避險買金需求弱。", True),
    "IG OAS": ("BAMLC0A0CM", "信用 / 波動 / 股市", "%", "bearish", "投資級利差穩定代表系統性信用壓力不足。", True),
    "3M T-bill": ("DTB3", "Fed 與短端流動性", "%", "bearish", "短債收益率高，現金替代吸引力分流黃金。", True),
    "M2": ("M2SL", "通膨與貨幣", "$bn", "bullish", "M2 擴張代表貨幣供給增加，中長期支撐黃金抗通膨需求。", False),
    "Import Price Index": ("IR", "通膨與貨幣", "index", "bullish", "進口物價上升代表輸入型通膨壓力。", False),
    "Average Hourly Earnings": ("CES0500000003", "通膨與貨幣", "USD/hour", "bullish", "薪資上升若持續追物價，會使通膨變黏。", False),
    "Broad Dollar Index": ("DTWEXBGS", "美元與匯率", "index", "bearish", "廣義美元走強會壓制黃金；走弱則利多黃金。", False),
}


def fmt_num(x: float, suffix: str = "") -> str:
    if x is None or not np.isfinite(x):
        return "n/a"
    if abs(x) >= 1000:
        s = f"{x:,.2f}"
    elif abs(x) >= 10:
        s = f"{x:.2f}"
    else:
        s = f"{x:.3f}"
    s = s.rstrip("0").rstrip(".")
    return s + suffix


def pct_change(latest: float, prev: float) -> tuple[float, float]:
    diff = latest - prev
    pct = diff / prev * 100 if prev else float("nan")
    return diff, pct


def yf_series(tickers: list[str], period: str = "1y") -> tuple[pd.DataFrame, str]:
    last_error = None

    for ticker in tickers:
        try:
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
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            df = df.dropna()

            if df.empty:
                raise RuntimeError(f"Empty close for {ticker}")

            return df, ticker

        except Exception as e:
            last_error = e

    raise RuntimeError(str(last_error))


def fred_series(series: str, months: int = 12) -> pd.DataFrame:
    url = FRED_BASE.format(series=series)
    df = pd.read_csv(url)
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna()
    cutoff = pd.Timestamp.utcnow().tz_localize(None) - pd.DateOffset(months=months)
    return df[df["date"] >= cutoff].copy()


def make_indicator(
    category: str,
    name: str,
    unit: str,
    df: pd.DataFrame,
    impact: str,
    why: str,
    source: str,
    percent_unit: bool = False,
) -> Indicator:
    df = df.dropna().tail(260)

    latest = float(df["value"].iloc[-1])
    prev = float(df["value"].iloc[-2]) if len(df) >= 2 else latest
    diff, pct = pct_change(latest, prev)

    obs_date = str(pd.to_datetime(df["date"].iloc[-1]).date())

    chart_df = df.tail(12)
    labels = [str(pd.to_datetime(d).date()) for d in chart_df["date"]]
    values = [float(v) for v in chart_df["value"]]

    suffix = "%" if percent_unit else ""

    return Indicator(
        category=category,
        name=name,
        unit=unit,
        latest=fmt_num(latest, suffix),
        previous=fmt_num(prev, suffix),
        change=f"{diff:+.3f} / {pct:+.2f}%",
        obs_date=obs_date,
        impact=impact,
        why=why,
        source=source,
        values=values,
        labels=labels,
    )


def unavailable_indicator(
    category: str,
    name: str,
    unit: str,
    impact: str,
    why: str,
    source: str,
    error: Exception,
) -> Indicator:
    return Indicator(
        category=category,
        name=name,
        unit=unit,
        latest="unavailable",
        previous="n/a",
        change=f"source failed: {type(error).__name__}",
        obs_date="n/a",
        impact="neutral",
        why=why + "（本次資料源未回傳，需人工檢查。）",
        source=source,
        values=[0.0, 0.0, 0.0],
        labels=["n/a", "n/a", "n/a"],
    )


def build_indicators() -> list[Indicator]:
    indicators: list[Indicator] = []

    for name, tickers in YF_TICKERS.items():
        category, unit, impact, why = YF_META[name]
        try:
            df, used_ticker = yf_series(tickers)
            indicators.append(
                make_indicator(
                    category,
                    name,
                    unit,
                    df,
                    impact,
                    why,
                    f"Yahoo Finance / yfinance {used_ticker}",
                    False,
                )
            )
        except Exception as e:
            indicators.append(
                unavailable_indicator(
                    category,
                    name,
                    unit,
                    impact,
                    why,
                    f"Yahoo Finance / yfinance {tickers}",
                    e,
                )
            )

    for name, (series, category, unit, impact, why, pct_unit) in FRED_SERIES.items():
        try:
            df = fred_series(series)
            indicators.append(
                make_indicator(
                    category,
                    name,
                    unit,
                    df,
                    impact,
                    why,
                    f"FRED {series}",
                    pct_unit,
                )
            )
        except Exception as e:
            indicators.append(
                unavailable_indicator(
                    category,
                    name,
                    unit,
                    impact,
                    why,
                    f"FRED {series}",
                    e,
                )
            )

    add_calculated_indicators(indicators)
    add_placeholder_indicators(indicators)

    return indicators


def latest_float(indicators: list[Indicator], name: str) -> float | None:
    for i in indicators:
        if i.name == name and i.latest not in ("unavailable", "n/a"):
            try:
                return float(i.latest.replace(",", "").replace("%", ""))
            except ValueError:
                return None
    return None


def add_calculated_indicators(indicators: list[Indicator]) -> None:
    y10 = latest_float(indicators, "美債 10Y")
    y2 = latest_float(indicators, "美債 2Y")
    y3m = latest_float(indicators, "3M T-bill")

    today = datetime.now(timezone.utc).date().isoformat()

    if y10 is not None and y2 is not None:
        val = y10 - y2
        indicators.append(
            Indicator(
                "名目利率與曲線",
                "10Y-2Y",
                "pp",
                fmt_num(val),
                "n/a",
                "calculated",
                today,
                "neutral",
                "曲線變化需分辨由短端下行或長端上行造成；危機型短端下行較利多黃金。",
                "calculated from FRED",
                [val, val, val],
                ["prev", "mid", "latest"],
            )
        )

    if y10 is not None and y3m is not None:
        val = y10 - y3m
        indicators.append(
            Indicator(
                "名目利率與曲線",
                "10Y-3M",
                "pp",
                fmt_num(val),
                "n/a",
                "calculated",
                today,
                "neutral",
                "10Y-3M 由短端快速下行推動時較像衰退寬鬆訊號；由長端上行推動則偏期限溢價壓力。",
                "calculated from FRED",
                [val, val, val],
                ["prev", "mid", "latest"],
            )
        )

    gold = latest_float(indicators, "XAU/USD 現貨金") or latest_float(indicators, "COMEX 黃金期貨")
    spx = latest_float(indicators, "S&P 500")
    dow = latest_float(indicators, "Dow Jones")
    nasdaq = latest_float(indicators, "Nasdaq")

    ratio_items = [
        ("Dow/Gold", dow, "hold gold"),
        ("S&P500/Gold", spx, "neutral"),
        ("Nasdaq/Gold", nasdaq, "neutral"),
    ]

    if gold:
        for ratio_name, index_value, impact in ratio_items:
            if index_value:
                val = index_value / gold
                indicators.append(
                    Indicator(
                        "輪動 / 資金流",
                        ratio_name,
                        "ratio",
                        fmt_num(val),
                        "n/a",
                        "calculated",
                        today,
                        impact,
                        "股票相對黃金未極端便宜前，不支持大量轉股。",
                        "calculated from market data",
                        [val, val, val],
                        ["prev", "mid", "latest"],
                    )
                )


def add_placeholder_indicators(indicators: list[Indicator]) -> None:
    placeholders = [
        ("GLD ETF holdings", "tonnes", "ETF 流入利多黃金；流出削弱實物支持型需求。", "WGC / issuer"),
        ("IAU ETF flows", "flow", "ETF 流入利多黃金；流出削弱實物支持型需求。", "iShares / WGC"),
        ("CFTC gold positioning", "contracts", "淨多支撐趨勢，但過度擁擠會提高去槓桿風險。", "CFTC CoT"),
    ]

    for name, unit, why, source in placeholders:
        indicators.append(
            Indicator(
                "輪動 / 資金流",
                name,
                unit,
                "check manually / weekly",
                "n/a",
                "not automated",
                "n/a",
                "neutral",
                why,
                source,
                [0.0, 0.0, 0.0],
                ["n/a", "n/a", "n/a"],
            )
        )


def inflation_dashboard() -> list[list[str]]:
    return [
        ["需求拉動型通膨", "GDP、零售銷售、消費支出、失業率、薪資", "經濟強、消費強、失業低，代表需求撐住物價", "不一定利多：需求強會讓 Fed 不急降息，短線壓黃金"],
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


def draw_pdf(indicators: list[Indicator]) -> None:
    with PdfPages(PDF_PATH) as pdf:
        draw_snapshot_page(pdf, indicators)
        draw_inflation_page(pdf)
        draw_chart_pages(pdf, indicators)
        draw_conclusion_page(pdf)


def draw_snapshot_page(pdf: PdfPages, indicators: list[Indicator]) -> None:
    fig = plt.figure(figsize=(11.69, 8.27))
    ax = fig.add_subplot(111)
    ax.axis("off")

    fig.suptitle("黃金宏觀指標儀表板｜Market Snapshot", fontsize=18, fontweight="bold")

    rows = [
        [i.name, i.latest, i.change, i.obs_date, i.impact, i.source]
        for i in indicators[:30]
    ]

    table = ax.table(
        cellText=rows,
        colLabels=["指標", "最新", "變動", "日期", "Gold impact", "來源"],
        loc="center",
        cellLoc="left",
        colLoc="left",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(6.2)
    table.scale(1, 1.18)

    ax.text(
        0,
        1.02,
        f"產出時間：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        transform=ax.transAxes,
        fontsize=8,
    )

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def draw_inflation_page(pdf: PdfPages) -> None:
    fig = plt.figure(figsize=(11.69, 8.27))
    ax = fig.add_subplot(111)
    ax.axis("off")

    fig.suptitle("通膨類型追蹤表｜Inflation Regime Dashboard", fontsize=17, fontweight="bold")

    table = ax.table(
        cellText=inflation_dashboard(),
        colLabels=["通膨類型", "主要指標", "如何看", "對黃金"],
        loc="center",
        cellLoc="left",
        colLoc="left",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(6.3)
    table.scale(1, 1.55)

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def draw_chart_pages(pdf: PdfPages, indicators: list[Indicator]) -> None:
    categories = []
    for i in indicators:
        if i.category not in categories:
            categories.append(i.category)

    for category in categories:
        group = [i for i in indicators if i.category == category]

        for start in range(0, len(group), 6):
            page_items = group[start:start + 6]
            fig, axes = plt.subplots(2, 3, figsize=(11.69, 8.27))
            fig.suptitle(category, fontsize=15, fontweight="bold")

            axes = axes.flatten()

            for ax, ind in zip(axes, page_items):
                values = ind.values if ind.values else [0.0, 0.0, 0.0]

                ax.plot(range(len(values)), values, linewidth=1.4)
                ax.set_title(ind.name, fontsize=8, fontweight="bold")
                ax.grid(True, alpha=0.3)

                if len(ind.labels) >= 2:
                    ax.set_xticks([0, len(ind.labels) - 1])
                    ax.set_xticklabels([ind.labels[0], ind.labels[-1]], fontsize=5.5)
                else:
                    ax.set_xticks([])

                ax.tick_params(axis="y", labelsize=5.5)

                text = (
                    f"最新：{ind.latest}｜{ind.obs_date}\n"
                    f"Gold impact：{ind.impact}\n"
                    f"Why：{ind.why[:58]}"
                )

                ax.text(
                    0,
                    -0.34,
                    text,
                    transform=ax.transAxes,
                    fontsize=5.3,
                    va="top",
                    wrap=True,
                )

            for ax in axes[len(page_items):]:
                ax.axis("off")

            fig.tight_layout(rect=[0, 0.04, 1, 0.95])
            pdf.savefig(fig)
            plt.close(fig)


def draw_conclusion_page(pdf: PdfPages) -> None:
    fig = plt.figure(figsize=(11.69, 8.27))
    ax = fig.add_subplot(111)
    ax.axis("off")

    fig.suptitle("總結｜Conclusion", fontsize=18, fontweight="bold")

    conclusion = (
        "結論：持有、等待。若實質利率下行、美元續弱、ETF/CFTC 資金轉強或信用/流動性壓力擴大，"
        "才升級為加碼；若實質利率與美元續上行，則維持等待或小幅控風險。"
    )

    bullets = [
        "Bullish：美元偏弱、breakeven 高位、成本/結構/預期型通膨、流動性緩衝變薄。",
        "Bearish：名目/實質利率偏高、Fed 降息預期後延、信用/VIX 未出現危機型避險。",
        "Stress：SOFR、ON RRP、銀行準備金、TGA 必須持續追蹤。",
        "Rotation：Dow/Gold、S&P500/Gold、Nasdaq/Gold 未到極端便宜區前，不大量轉股。",
    ]

    ax.text(0.05, 0.82, conclusion, fontsize=13, fontweight="bold", wrap=True)
    ax.text(0.05, 0.64, "\n".join("• " + b for b in bullets), fontsize=11, va="top", wrap=True)

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def build_html(indicators: list[Indicator]) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    cards = ""
    for i in indicators[:12]:
        cards += f"""
        <div class="card">
          <b>{i.name}</b>
          <div>Latest: {i.latest}</div>
          <div>Change: {i.change}</div>
          <div>Date: {i.obs_date}</div>
          <div>Gold impact: {i.impact}</div>
        </div>
        """

    html = f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>黃金每日報告 App</title>
<style>
body {{
  margin: 0;
  background: #0f172a;
  color: #e5e7eb;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans TC", Arial, sans-serif;
}}
.app {{
  max-width: 980px;
  margin: auto;
  padding: 18px 14px 80px;
}}
.hero, .card {{
  background: #111827;
  border: 1px solid #334155;
  border-radius: 20px;
  padding: 16px;
  margin: 10px 0;
}}
h1 {{
  font-size: 25px;
}}
.grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 10px;
}}
.btn {{
  display: block;
  text-align: center;
  text-decoration: none;
  border-radius: 16px;
  padding: 14px;
  margin: 10px 0;
  font-weight: 800;
  background: #fbbf24;
  color: #111827;
}}
.small {{
  font-size: 12px;
  color: #94a3b8;
}}
</style>
</head>
<body>
<div class="app">
  <section class="hero">
    <h1>黃金每日報告 App</h1>
    <p>最後更新：{now}</p>
    <p class="small">Arizona 7:30 AM / 7:30 PM 自動更新</p>
  </section>

  <a class="btn" href="gold_report_compact.pdf">打開最新 PDF 報告</a>

  <h2>最新重點</h2>
  <div class="grid">
    {cards}
  </div>

  <section class="hero">
    <b>結論：</b>持有、等待。完整內容請開啟 PDF。
  </section>
</div>
</body>
</html>
"""

    HTML_PATH.write_text(html, encoding="utf-8")


def main() -> None:
    indicators = build_indicators()
    draw_pdf(indicators)
    build_html(indicators)

    JSON_PATH.write_text(
        json.dumps([i.__dict__ for i in indicators], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Wrote {PDF_PATH}")
    print(f"Wrote {HTML_PATH}")
    print(f"Wrote {JSON_PATH}")


if __name__ == "__main__":
    main()
