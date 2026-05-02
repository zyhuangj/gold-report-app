#!/usr/bin/env python3
"""
V9 Gold Dashboard Generator

目前用途：
- 保留 public/index.html 的 V9 儀表板格式
- 防止 GitHub Actions 執行時把網站覆蓋回舊版
- 讓 workflow 每天 6 次可以正常跑完

注意：
- 這一版不會重新抓最新市場資料
- 它只會檢查 public/index.html 是否仍是 V9 格式
- 之後要做「真正即時更新」，再把資料抓取與圖表重畫功能加回來
"""

from pathlib import Path
from datetime import datetime, timezone


PUBLIC_DIR = Path("public")
INDEX_FILE = PUBLIC_DIR / "index.html"
PDF_FILE = PUBLIC_DIR / "gold_report_compact.pdf"
LATEST_DATA_FILE = PUBLIC_DIR / "latest_data.json"


REQUIRED_KEYWORDS = [
    "黃金宏觀儀表板 V9",
    "Gold Macro Score",
    "Dow/Gold",
    "S&P500",
    "Nasdaq/Gold",
    "ETF / CFTC",
    "通膨類型",
    "Market Snapshot",
]


def ensure_public_dir() -> None:
    """確保 public 資料夾存在。"""
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)


def read_index_html() -> str:
    """讀取 public/index.html。"""
    if not INDEX_FILE.exists():
        raise FileNotFoundError(
            "找不到 public/index.html。請先把 V9 版網站內容放到 public/index.html。"
        )

    return INDEX_FILE.read_text(encoding="utf-8")


def validate_v9_format(html: str) -> None:
    """確認 public/index.html 仍是 V9 格式。"""
    missing = [word for word in REQUIRED_KEYWORDS if word not in html]

    if missing:
        raise ValueError(
            "public/index.html 看起來不是 V9 格式，缺少關鍵字："
            + ", ".join(missing)
        )


def write_latest_data_stub() -> None:
    """
    寫入一個簡單的 latest_data.json。
    這是給網站或之後程式使用的狀態檔。
    """
    now = datetime.now(timezone.utc).isoformat()

    content = f"""{{
  "status": "ok",
  "format": "V9",
  "updated_at_utc": "{now}",
  "note": "This generator currently preserves and validates the V9 dashboard format. Live data refresh will be added later."
}}
"""

    LATEST_DATA_FILE.write_text(content, encoding="utf-8")


def verify_optional_files() -> None:
    """
    檢查可選檔案是否存在。
    不存在不會報錯，只會印出提醒。
    """
    if PDF_FILE.exists():
        print(f"PDF found: {PDF_FILE} ({PDF_FILE.stat().st_size:,} bytes)")
    else:
        print(f"PDF not found: {PDF_FILE}. This is optional.")


def main() -> None:
    """主程式。"""
    ensure_public_dir()

    html = read_index_html()
    validate_v9_format(html)
    write_latest_data_stub()
    verify_optional_files()

    print("V9 dashboard format verified.")
    print(f"HTML file: {INDEX_FILE}")
    print(f"HTML size: {INDEX_FILE.stat().st_size:,} bytes")
    print(f"Latest data file: {LATEST_DATA_FILE}")
    print(f"Checked at UTC: {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()
