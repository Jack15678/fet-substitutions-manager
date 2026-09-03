# 學校伺服器連線與部署 Runbook

更新日期：2026 年 9 月 3 日

本文件記錄目前學校 Ubuntu 電腦的實際連線及部署方法。通用首次安裝、HTTPS、備份和災難復原說明另見 [DEPLOYMENT_ZH.md](DEPLOYMENT_ZH.md)。

## 1. 現行環境

| 項目 | 現行值 |
|---|---|
| 作業系統 | Ubuntu 20.04 |
| 主機名稱 | `hpccpslinux01` |
| SSH 用戶 | `hpccps` |
| Tailscale IP | `100.114.218.10` |
| 校內固定 IP | `10.54.128.30` |
| 校內網站 | `http://10.54.128.30:8080` |
| 伺服器專案目錄 | `/home/hpccps/fet-substitutions-manager` |
| 部署分支 | `codex/deployment-guide` |
| GitHub 倉庫 | `https://github.com/Jack15678/fet-substitutions-manager.git` |
| Compose 文件 | `docker-compose.local.yml` |

Tailscale 只供遠端維護；老師的電腦不需要安裝 Tailscale，應在學校有線內網開啟校內網站。Ubuntu 停留在登入畫面不影響服務，但電腦關機、休眠、網線中斷或 Docker 停止時網站會離線。

## 2. 連線到學校伺服器

先確認兩台電腦都在線：

```powershell
tailscale status
tailscale ping -c 1 100.114.218.10
```

再用 SSH 連線：

```powershell
ssh hpccps@100.114.218.10
```

如出現 `Tailscale SSH requires an additional check`，開啟終端顯示的一次性 `https://login.tailscale.com/a/...` 網址，以與這兩台電腦相同的 Tailscale 帳戶批准，再重新執行 SSH。一次性網址每次不同，不要保存到本文件。

離開 SSH：

```bash
exit
```

### 從校外臨時查看網站

網站沒有綁定 Tailscale IP。需要從校外查看時，在本機建立臨時 SSH 隧道：

```powershell
ssh -N -L 18080:127.0.0.1:8080 hpccps@100.114.218.10
```

然後開啟 `http://127.0.0.1:18080`。完成後在該終端按 `Ctrl+C` 關閉隧道；這不會停止學校網站。

## 3. 提交及推送本機更新

在本機專案根目錄先檢查變更：

```powershell
git status --short --branch
git diff --check
git diff --stat
```

不要提交原始課表、匯出結果、資料庫、`.env`、密碼或其他真實學校資料。只明確加入本次相關檔案：

```powershell
git add -- path/to/changed-file path/to/test-file
git diff --cached --check
git diff --cached --stat
```

按改動範圍執行驗證：

```powershell
cd backend
python -m pytest tests -q

cd ../frontend
npm run build

cd ..
```

測試通過後提交並推送：

```powershell
git commit -m "fix: describe the change"
git push fork HEAD:codex/deployment-guide
```

## 4. 部署到學校伺服器

先登入並檢查現況：

```bash
ssh hpccps@100.114.218.10
cd /home/hpccps/fet-substitutions-manager
git rev-parse --short HEAD
git status --short
docker compose -f docker-compose.local.yml ps
```

伺服器目前可能有未追蹤的 `docker-compose.local.yml.before-ip-change`，不要刪除或提交。若出現其他未預期的修改，先停止部署並查明來源。

記下舊、新 commit，為舊版本建立本機回退標記，然後只作快進更新：

```bash
git tag server-before-NEW_COMMIT-YYYYMMDD OLD_COMMIT
git fetch origin codex/deployment-guide
git merge --ff-only origin/codex/deployment-guide
```

按變更範圍重建：

```bash
# 只有後端變更
docker compose -f docker-compose.local.yml up -d --build backend

# 有前端、說明頁或前後端共同變更
docker compose -f docker-compose.local.yml up -d --build
```

不要使用 `docker compose down -v`；`-v` 可能刪除持久化資料。

## 5. 部署後驗證

```bash
cd /home/hpccps/fet-substitutions-manager
git rev-parse --short HEAD
docker compose -f docker-compose.local.yml ps
curl -fsS http://127.0.0.1:8080/api/health
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/
```

預期結果：

- commit 是剛推送的版本；
- `backend` 和 `frontend` 都是 `Up`；
- 健康端點返回 `{"status":"ok"}`；
- 首頁返回 HTTP `200`。

最後在瀏覽器使用另行保存的管理員帳號登入一次。密碼不要寫進本文件或 commit 訊息。

## 6. 查看錯誤

```bash
docker compose -f docker-compose.local.yml logs --tail 100 backend
docker compose -f docker-compose.local.yml logs --tail 100 frontend
```

常見判斷：

| 現象 | 先檢查 |
|---|---|
| SSH 連不上 | `tailscale status`、`tailscale ping`、一次性 SSH 授權 |
| 全校都開不到網站 | 電源／休眠、網線、`10.54.128.30`、Docker 及 Compose 狀態 |
| 首頁可開但操作失敗 | `/api/health` 和 backend logs |
| 只有部分老師開不到 | 老師電腦是否在相同有線網段、VLAN／防火牆規則 |

## 7. 回退剛部署的版本

只有新版本驗證失敗時才回退。使用第 4 節建立的明確標記，不要猜 commit：

```bash
cd /home/hpccps/fet-substitutions-manager
git switch --detach server-before-NEW_COMMIT-YYYYMMDD
docker compose -f docker-compose.local.yml up -d --build
```

確認舊版本恢復後再調查。修正完成並要部署新版時：

```bash
git switch codex/deployment-guide
git fetch origin codex/deployment-guide
git merge --ff-only origin/codex/deployment-guide
docker compose -f docker-compose.local.yml up -d --build
```

## 8. 每次部署記錄

完成後在維護紀錄寫下：日期、新 commit、舊 commit／回退標記、測試結果、部署人及健康檢查結果。當前版本以伺服器上的 `git rev-parse --short HEAD` 為準。
