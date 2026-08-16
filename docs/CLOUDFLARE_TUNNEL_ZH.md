# Windows 測試機的 Cloudflare Tunnel 部署

這份文檔記錄目前測試機的實際部署方式。公開網址固定為：

<https://jackdomain.dpdns.org>

本方案不使用 Docker、不設定開機自動啟動，也沒有啟用 Cloudflare Access。任何人都能打開登入頁，但仍需系統帳號和密碼才能進入。

## 運作方式

```text
瀏覽器 → Cloudflare → Named Tunnel → 127.0.0.1:8081
                                      ├─ Vue 前端
                                      └─ /api/* → FastAPI 127.0.0.1:8000
```

域名和 Named Tunnel 是固定的，但網頁依賴這台電腦上的三個進程：FastAPI、Vite Preview 和 `cloudflared`。電腦關機、睡眠、斷網或任一進程停止時，網站會暫時離線；重新啟動三個進程後仍使用同一網址。

## 每次手動啟動

在三個 PowerShell 視窗中分別執行以下命令。所有命令均假定專案位於：

```text
D:\Desktop\Code\Substitute Teacher Management System
```

### 1. 啟動後端

```powershell
cd "D:\Desktop\Code\Substitute Teacher Management System\backend"

$projectRoot = (Resolve-Path ..).Path
$env:SECRET_KEY = [Environment]::GetEnvironmentVariable('GESTOR_SECRET_KEY', 'User')
$env:ENVIRONMENT = 'production'
$env:COOKIE_SECURE = 'true'
$env:DATA_DIR = Join-Path $projectRoot 'data'
$env:AUTH_DB_PATH = Join-Path $projectRoot 'data\auth.db'
$env:APP_INSTITUCIO = 'exemple'
$env:ADMIN_INSTITUCIO = 'exemple'

if (-not $env:SECRET_KEY) { throw 'Windows 使用者環境中缺少 GESTOR_SECRET_KEY' }

python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

看到 Uvicorn 已在 `http://127.0.0.1:8000` 運行後，保持視窗開啟。

### 2. 構建並啟動前端

```powershell
cd "D:\Desktop\Code\Substitute Teacher Management System\frontend"
npm run build
npm run preview
```

前端會監聽 `http://127.0.0.1:8081`。保持視窗開啟。

### 3. 啟動固定 Tunnel

```powershell
cd "D:\Desktop\Code\Substitute Teacher Management System"

& "$env:USERPROFILE\.cloudflared\cloudflared.exe" tunnel `
  --config ".cloudflare-tunnel\substitute-teacher-system.yml" `
  --protocol http2 `
  run substitute-teacher-system
```

看到 `Registered tunnel connection` 後即可訪問 <https://jackdomain.dpdns.org>。不要再次執行 `tunnel create` 或 `tunnel route dns`；Named Tunnel 和 DNS 已經建立。

若這台電腦再次出現 `no such host`，而本機代理仍使用 `127.0.0.1:7897`，可在啟動 Tunnel 前執行：

```powershell
$env:HTTP_PROXY = 'http://127.0.0.1:7897'
$env:HTTPS_PROXY = 'http://127.0.0.1:7897'
```

## 驗證

```powershell
# 後端
Invoke-WebRequest http://127.0.0.1:8000/api/health -UseBasicParsing

# 前端及本地 API 代理
Invoke-WebRequest http://127.0.0.1:8081/ -Headers @{ Host = 'jackdomain.dpdns.org' } -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:8081/api/health -Headers @{ Host = 'jackdomain.dpdns.org' } -UseBasicParsing

# 公網
Invoke-WebRequest https://jackdomain.dpdns.org/api/health -UseBasicParsing
```

健康端點的預期內容是：

```json
{"status":"ok"}
```

## 修改程式後發布

### 只修改前端

在前端視窗按 `Ctrl+C`，然後重新執行：

```powershell
npm run build
npm run preview
```

### 只修改後端

在後端視窗按 `Ctrl+C`，然後重新執行：

```powershell
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

### 修改前後端

分別重啟前端和後端。Tunnel 不需要重啟，域名也不需要重新設定。

`data/` 中的 SQLite 資料、匯入檔案和匯出檔案不會因重新構建前端或重啟 Tunnel 而消失。更新前仍建議備份整個 `data/` 目錄。

## 停止公開網站

在 Tunnel、前端和後端的三個 PowerShell 視窗中分別按 `Ctrl+C`。只停止 Tunnel 也能立即中斷公網訪問，而本地前後端仍可繼續運行。

## 憑證與安全

- Cloudflare 登入憑證與 Tunnel 金鑰位於 `%USERPROFILE%\.cloudflared\`，不得上傳 Git 或傳給他人。
- 本地 Tunnel 配置位於 `.cloudflare-tunnel/`；該目錄已加入 `.gitignore`。
- `GESTOR_SECRET_KEY` 只保存在 Windows 使用者環境中，不要把實際值寫入文檔、截圖或程式碼。
- 目前沒有 Cloudflare Access，登入頁對公網開放。必須使用強密碼，且不要使用範例帳密。
- 系統資料位於 `data/`。這個目錄包含教師及課表資料，備份也應視為敏感資料。

## 常見故障

| 現象 | 檢查 |
|---|---|
| 公網顯示 Cloudflare 502 | 確認前端仍監聽 `127.0.0.1:8081` |
| 首頁能開但功能報錯 | 確認後端仍監聽 `127.0.0.1:8000`，再測試 `/api/health` |
| 啟動提示埠已被使用 | 執行 `Get-NetTCPConnection -State Listen | Where-Object LocalPort -in 8000,8081` |
| Tunnel 無法連接 Cloudflare | 檢查網路、DNS及本機代理，再查看 Tunnel 視窗的錯誤訊息 |
| 重啟電腦後網站離線 | 這是預期行為；重新完成「每次手動啟動」三步 |
