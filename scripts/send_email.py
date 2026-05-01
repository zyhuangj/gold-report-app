from __future__ import annotations

import os
import ssl
import smtplib
from email.message import EmailMessage
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "public" / "gold_report_compact.pdf"

EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD")
EMAIL_TO = os.environ.get("EMAIL_TO")

def main():
    if not (EMAIL_USER and EMAIL_APP_PASSWORD and EMAIL_TO):
        print("Email secrets not set. Skipping Gmail send.")
        return
    if not PDF.exists():
        raise FileNotFoundError(PDF)

    msg = EmailMessage()
    msg["Subject"] = "黃金宏觀指標 PDF 報告｜自動更新"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO
    msg.set_content(
        "已附上最新緊湊版黃金宏觀指標 PDF 報告。\n\n"
        f"產出時間：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
        "結論請見 PDF 最後一頁。"
    )

    msg.add_attachment(PDF.read_bytes(), maintype="application", subtype="pdf", filename="gold_report_compact.pdf")

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as smtp:
        smtp.login(EMAIL_USER, EMAIL_APP_PASSWORD)
        smtp.send_message(msg)

    print("Email sent with PDF attachment.")

if __name__ == "__main__":
    main()
