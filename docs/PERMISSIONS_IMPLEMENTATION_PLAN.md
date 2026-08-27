# 普通用戶權限：並行實作計劃

狀態：已完成實作及整合驗收

最後更新：2026-08-27

驗證結果：後端 `77 passed, 8 skipped`（另 6 個 subtests）、前端正式建置通過、`git diff --check` 通過，並以預設普通用戶、只讀用戶、只可上傳課表用戶、完整管理員及零權限用戶完成桌面／手機瀏覽器驗收。撤權後舊頁下一次寫入即回傳 `403`，重新載入後入口同步消失。

## 1. 已固定的產品決定

- 介面採用方案一：現有「系統設定 → 用戶」內，左側為可搜尋用戶清單，右側為所選用戶的分組權限詳情。
- 保留 `super_admin`、`admin`、`user` 三種角色，不新增固定 `timetable_uploader` 角色。
- `admin`／`super_admin` 永遠擁有全部權限；普通 `user` 才讀取個別權限。
- 普通用戶預設沿用現況：`workbench.view`、`absence.create`、`adjustment.confirm`、`records.view`。
- 課表「上傳及預覽」與「啟用及管理」分開授權；每日 Excel／PDF 下載亦是獨立權限。
- 用戶管理、系統配置、假期、節次時間及長期缺席管理首版仍為管理員專用。
- 前端隱藏與後端拒絕必須同時完成；後端權限是最終安全邊界。

## 2. 共享契約（所有 agent 開工前不得自行改名）

權限鍵固定為：

```text
workbench.view
absence.create
adjustment.confirm
manual_arrangement.manage
records.view
records.manage
statistics.view
exports.download
timetable.upload
timetable.manage
```

用戶 API 契約：

- 用戶列表、建立、修改及個人資料回應增加 `permissions: string[]`。
- 建立／修改普通用戶可提交 `permissions: string[]`；未知鍵回傳 `400`。
- 舊資料的權限欄位為 `NULL` 時，以普通用戶預設集合讀取，避免升級後失去原有能力；明確保存的空陣列 `[]` 代表沒有任何功能權限，不能再套用預設。
- 權限 JSON 解析失敗或包含非字串值時採取 fail-closed，不把損壞資料誤當成預設全權；同時記錄錯誤供管理員修正。
- `admin`／`super_admin` 的 `permissions` 回應可統一返回全部 10 個鍵，但後端授權不得依賴資料庫內是否完整保存這個集合。
- 權限不放進 JWT 作唯一判斷來源；每次請求沿用現有 `get_current_user` 取得最新用戶資料，確保撤權立即在後端生效。
- 共用授權函數提供「單一權限」及「任一權限」檢查，未登入仍為 `401`，已登入但缺權限為 `403`，管理員自動通過。

頁面與子權限關係：

- `absence.create`、`adjustment.confirm`、`manual_arrangement.manage` 需要 `workbench.view`。
- `records.manage` 需要 `records.view`。
- `statistics.view` 或 `exports.download` 任一成立即可顯示統計／匯出頁，頁內兩個區塊分別檢查權限。
- `timetable.upload` 或 `timetable.manage` 任一成立即可顯示課表匯入頁；頁內按鈕分別檢查兩個權限。

### 2.1 後端接口分組

Agent B 依下表加守衛；同一接口若可由不同頁面共用，使用「任一權限」而不是複製接口或放寬為所有登入用戶：

| 接口組 | 所需權限／角色 | 補充限制 |
|---|---|---|
| 工作臺教師、缺席個案、有效課表及停課日只讀資料 | `workbench.view` | 只讀，不等同可建立或確認安排 |
| `POST /api/absence-cases`、批量建立及分析 | `absence.create` | 對既有個案操作時須核對建立者及未鎖定狀態 |
| 更新或撤回缺席 | `absence.create` 或 `records.manage` | 前者只可處理自己建立且尚未產生已確認安排的個案；後者可管理同校個案 |
| 確認系統建議 | `adjustment.confirm` | 仍執行最新撞課及有效課表驗證 |
| 人工安排清單、人工代課及共同教師繼續上課 | `manual_arrangement.manage` | 同時要求 `workbench.view` |
| 記錄列表及詳情 | `records.view` | 不開放寫入 |
| 修改、撤銷、刪除安排及永久刪除缺席 | `records.manage` | 同時要求 `records.view`；保留同校限制與審計 |
| 統計 | `statistics.view` | 日期範圍及既有統計口徑不變 |
| 每日 Excel／PDF／ZIP | `exports.download` | 不因有統計權限而自動取得下載權限 |
| 課表版本列表及目前課表 | `workbench.view`、`timetable.upload`、`timetable.manage` 任一 | 回傳目前頁面所需的只讀範圍 |
| 上傳、預覽、保存差異決定及丟棄預覽 | `timetable.upload` | 不包含啟用正式版本 |
| 啟用、取消匯入、修改及刪除課表版本 | `timetable.manage` | 保留版本使用中及歷史記錄保護 |
| 用戶、系統配置、節次時間、假期及長期缺席管理 | `admin`／`super_admin` | 首版不對普通用戶開放對應權限鍵 |

## 3. 可同時進行的四個工作包

以下四個工作包在共享契約固定後可以並行。每個 agent 只修改列明的所有權檔案；需要其他檔案時先回報主 agent，不直接跨界修改。

### Agent A：用戶資料、遷移及管理 API

所有權：

- `backend/models.py`
- `backend/database.py`
- `backend/repositories.py`
- `backend/routes/users.py`
- 新增 `backend/permissions.py`
- 新增 `backend/tests/test_permission_management.py`

交付：

1. 為 `users` 增加可向後相容的權限 JSON 欄位及啟動時遷移；`NULL`、`[]` 及損壞 JSON 按共享契約分別處理。
2. 在 `backend/permissions.py` 保存權限鍵、普通用戶預設集合、全部集合及組合驗證；其他 agent 只引用，不各自複製字串。
3. 擴展用戶列表、建立、修改及 profile API 的 `permissions` 契約。
4. 保留同校限制、超級管理員保護及角色驗證；普通管理員不能藉權限欄位授予用戶管理或系統配置。
5. 在共用 `auth.db` 新增小型 `user_permission_audits` 審計表，保存學校、操作者、目標用戶、變更前後權限及時間；權限更新與審計寫入使用同一資料庫交易，不跨校務資料庫拼湊非原子寫入。
6. 測試舊用戶預設、明確空權限、損壞資料 fail-closed、未知鍵拒絕、同校邊界、審計內容及管理員全權。

### Agent B：後端業務 API 權限強制

所有權：

- `backend/auth_utils.py`
- `backend/routes/rescheduling.py`
- 新增 `backend/tests/test_permission_guards.py`

交付：

1. 實作引用 `backend/permissions.py` 的單一／任一權限依賴，保留 `require_admin` 供未開放的設定功能使用。
2. 依共享契約保護工作臺讀取、新增缺席、確認建議、人工安排、記錄讀取／管理、統計、每日匯出及課表匯入／管理 API。
3. 共用讀取 API 如目前課表，按真正消費者設定任一權限，不因單一頁面規則阻塞另一頁。
4. 使用參數化測試證明：無權限直接呼叫回傳 `403`、授權後成功、管理員保持相容。
5. 特別測試 `absence.create` 不能更新或撤回其他人建立的個案，亦不能繞過已確認安排的鎖定；`records.manage` 才可在同校範圍管理其他人的記錄。
6. 不修改排課演算法、資料輸出內容或用戶 CRUD。

### Agent C：方案一的用戶權限編輯介面

所有權：

- `frontend/src/components/config/UsuarisTab.vue`
- 新增 `frontend/src/components/config/UserPermissionsPanel.vue`
- `frontend/src/components/ConfiguracioDialog.vue`
- `frontend/src/locales/zh-HK.json`
- `frontend/src/locales/en.json`

交付：

1. 把現有用戶表／編輯對話流程整理為桌面主從布局：左側搜尋及選擇用戶，右側以單一 `UserPermissionsPanel` 顯示帳號與三組權限；不再拆分只使用一次的用戶清單元件。
2. 普通用戶顯示 10 個權限開關、說明及高風險提示；管理員顯示「擁有全部權限」且不提供無效開關。
3. 自動維持必要頁面與子權限組合，提交 `permissions` 陣列；保存失敗不清除未保存選擇。
4. 手機版改為用戶清單後進入完整編輯頁，保留鍵盤焦點、標籤及觸控範圍。
5. 本 agent 統一負責本功能全部中英文文案，避免語言檔衝突。

### Agent D：前端導覽、頁面及操作按鈕限制

所有權：

- 新增 `frontend/src/permissions.js`
- `frontend/src/App.vue`
- `frontend/src/views/ReschedulingView.vue`
- `frontend/src/views/RecordsView.vue`
- `frontend/src/views/StatisticsView.vue`
- `frontend/src/views/TimetableImportView.vue`

交付：

1. 從 profile 的角色與 `permissions` 建立單一 `can(permission)` 判斷；管理員自動通過。
2. 按權限控制桌面／手機導覽、初始頁及失去目前頁面權限後的安全跳轉。
3. 在各頁控制新增缺席、確認方案、人工安排、記錄管理、統計、下載、課表上傳及課表管理操作。
4. 只隱藏未授權操作，不在各元件自行定義另一套權限名稱或預設集合。
5. 不修改語言檔；缺少文案鍵交由 Agent C 統一補上。
6. 若普通用戶沒有任何頁面權限，顯示「尚未獲分配功能」，並保留個人資料及登出，不呈現空白工作區。

## 4. 主 agent 的整合工作（四個工作包完成後）

1. 先整合 Agent A 的資料與 API 契約，再整合 Agent B 的後端守衛；確認所有 import 只指向單一權限目錄。
2. 整合 Agent C 的用戶管理介面及語言檔，再整合 Agent D 的前端守衛。
3. 核對所有前端開關都有後端 API 保護，所有後端權限亦有可到達的前端入口。
4. 執行完整後端測試、前端正式建置及 `git diff --check`。
5. 使用至少四個帳號做瀏覽器驗收：現行普通用戶、只讀用戶、只可上傳課表用戶、完整管理員。
6. 驗證撤權後舊頁面即使仍開啟，下一次寫入也會被後端拒絕；重新載入後導覽及按鈕同步消失。
7. 更新管理員／一般教師說明書及需求進度；實作完成前不得把本計劃標記為完成。

## 5. 明確不在首版實作

- 管理員自行新增權限種類或自訂角色名稱。
- 角色繼承、多層群組、班級／年級資料範圍權限。
- 針對每一個下載格式再拆 Excel、PDF、ZIP 三個開關。
- 把權限只存於前端、JWT 或瀏覽器本地資料。
- 讓普通用戶透過功能權限管理其他用戶、系統配置或學校。
