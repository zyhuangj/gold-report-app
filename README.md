# 黃金宏觀指標自動報告系統

這是「方案 3」：每天自動抓資料 → 自動產生緊湊 PDF → 自動更新 Netlify 網站 → 可選擇自動寄 Gmail 附件。

## 固定時間

GitHub Actions 設定為 America/Phoenix：

- 每天 07:30
- 每天 19:30

## 檔案結構

```text
.github/workflows/update-gold-report.yml
scripts/generate_report.py
scripts/send_email.py
requirements.txt
public/index.html
public/gold_report_compact.pdf
```

## 第一次設定步驟

### 1. 建 GitHub repo

建立一個新的 GitHub repo，例如：

```text
gold-report-app
```

把本壓縮包全部檔案上傳到 repo 根目錄。

### 2. 在 Netlify 連接 GitHub repo

在 Netlify 目前的專案裡：

1. Project configuration
2. Build & deploy
3. Continuous deployment
4. Link repository
5. 選你的 GitHub repo
6. Publish directory 設定：
   ```text
   public
   ```
7. Build command 留空或填：
   ```text
   echo "static site"
   ```

之後 GitHub repo 有更新，Netlify 會自動部署。

### 3. 設定 GitHub Actions 權限

到 GitHub repo：

1. Settings
2. Actions
3. General
4. Workflow permissions
5. 選：
   ```text
   Read and write permissions
   ```

這樣 workflow 才能把最新 PDF commit 回 repo。

### 4. Gmail 附件寄送，可選

如果你要 GitHub Actions 自動寄 Gmail PDF 附件，請到 GitHub repo：

Settings → Secrets and variables → Actions → New repository secret

新增：

```text
EMAIL_USER = 你的 Gmail
EMAIL_TO = 收件人 Gmail
EMAIL_APP_PASSWORD = Gmail App Password
```

注意：Gmail App Password 需要 Google 帳號開啟 2-Step Verification。

如果不設這三個 secrets，系統仍會產生 PDF 並更新 Netlify，但不寄信。

## 每天自動流程

```text
GitHub Actions 07:30 / 19:30 Phoenix
→ scripts/generate_report.py 抓最新資料
→ 產生 public/gold_report_compact.pdf
→ 產生 public/index.html
→ commit 回 GitHub
→ Netlify 自動更新
→ optional: Gmail 寄 PDF 附件
```

## 手動測試

到 GitHub repo → Actions → Update Gold Report → Run workflow

## 注意

- Yahoo Finance / yfinance 有時會短暫失敗，腳本會保留欄位並標記 unavailable。
- FRED 非日頻資料會標示最新觀察日。
- 如果某項資料源未更新，報告會使用最新可得 observation date。
