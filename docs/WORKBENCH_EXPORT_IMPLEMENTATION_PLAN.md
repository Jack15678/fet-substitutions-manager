# 工作臺、顯示及每日匯出：並行實作計劃

狀態：已完成及驗收

最後更新：2026-08-30

本計劃把 2026-08-30 已確認需求拆成三個可並行工作包。實作期間每個 agent 只修改列明的所有權檔案；三個工作包完成後由整合者統一驗收及更新文件。

## 1. 已固定的產品決定

- 系統候選全部不合適時，使用者從該課堂進入現有人工安排頁，直接選擇合資格老師並完成安排；不新增審批流程或第二套頁面。
- 缺席原因必選：病假、事假、公假、培訓、其他；選擇其他後的補充輸入可以留空，placeholder 為「可留空」。
- 課表核對畫面最多三位老師，按顯示次序固定使用藍、綠、橙三色；不保存老師個人顏色。
- 變更課堂顯示「原」與「現／新安排」，不再以「調整」概括整個變更。
- 網頁字號提供標準、大、超大；字體類型提供系統預設、黑體類、宋體類、楷體類；偏好只保存在目前瀏覽器。
- 匯出入口放在工作臺上方；統計頁不再承載匯出表單。
- PDF 為單一檔案，A4 直向每頁上下兩表；奇數最後一表只佔上半頁。
- Excel 附註使用 `月-日-老師全名-上班別科目`，多項以全形逗號分隔。

## 2. 共享契約（所有 agent 開工前不得自行改名）

### 2.1 缺席原因 API

缺席新增及批量新增的每個 item 增加：

```json
{
  "reason_type": "sick | personal | official | training | other",
  "reason_detail": "可選字串或 null"
}
```

- `reason_type` 必填，只接受上述五個固定代碼。
- `reason_detail` 最長 200 字；去除前後空白後的空字串保存為 `null`。
- 非 `other` 類別忽略 `reason_detail`，避免同一原因同時出現預設及自由文字。
- `other` 的 `reason_detail` 可以是 `null`，顯示時仍輸出「其他」。
- `AbsenceCase` 使用獨立的 `reason_type`、`reason_detail` 欄位；不可借用 `ScheduleAdjustment.reason`。
- 缺席記錄回應、記錄詳情及每日匯出資料都返回這兩個欄位；舊資料沒有原因時保持可讀，顯示「未填寫」，不猜測原因。

### 2.2 人工安排資格

- `GET /api/manual-arrangements` 返回所有仍為 open 且尚未完成的缺席課堂，包括分析狀態為 `recommended` 或 `unresolved` 的 task。
- task 保留現有 `status`，前端可標示它原本是否已有系統候選，但人工頁使用同一套老師資格、排序及確認摘要。
- `POST /api/manual-arrangements/cover` 接受上述兩種狀態；提交時仍以最新 revision、有效課表、缺席、長期假期、教師忙碌格及共同教師狀態重新驗證。
- 完成人工安排後，沿用現有有效課表、統計、記錄、審計及缺席狀態更新流程。

### 2.3 課表核對顯示

- 顏色按 `verificationTimetables` 顯示次序分配：第 1 位藍、第 2 位綠、第 3 位橙；同一次對話框不變，關閉後無需保存。
- 顏色只作輔助識別，老師全名及「原／現」文字必須保留，不能只靠顏色傳達內容。
- 未變更課堂維持現有中性樣式。
- 變更格至少顯示：`原：班別 科目` 與 `現：班別 科目`；其中一側沒有課時顯示「空堂」。
- 二堂互調、三堂循環及緊急代課使用相同的逐格 before／after 表達，不再顯示獨立的「調整」標籤。

### 2.4 顯示偏好

- 字號值固定為 `standard`、`large`、`extra-large`，分別對應根字號 100%、112.5%、125%。
- 字體值固定為 `system`、`sans`、`serif`、`kai`，介面名稱為「系統預設」、「黑體」、「宋體」、「楷體」。
- 使用瀏覽器 `localStorage` 保存，不新增 API 或資料庫欄位；讀取到未知值時回落到 `standard` 及 `system`。
- 設定套用至登入頁及登入後介面，但不影響 PDF／Excel。

### 2.5 每日匯出

- `build_daily_pdf(entries, period_times)` 一次接收當日全部老師，返回一個 PDF bytes；匯出 API 永遠回傳 `application/pdf`，不再回傳 ZIP。
- PDF 使用 A4 直向、上下兩個固定半頁區域及約 5 mm 外邊距；每份表只在自己的半頁內排版。奇數最後一份放上半頁，下半頁留空。
- PDF 表格優先使用現有可嵌入中文字體；標題、資料及表格字號應在半頁限制內盡量放大，不能裁切或跨越另一份表。
- Excel 維持一個 workbook、每名缺席老師一個 worksheet。
- 互調／循環附註按對應課堂輸出 `MM-DD-老師全名-上班別科目`；多項按調動順序去重後以 `，` 連接。老師名稱一律取 `Professor.nom` 完整值。
- 缺席原因在 Excel／PDF 表頭輸出固定繁中名稱；`other` 有補充時顯示 `其他：補充內容`，沒有補充時顯示 `其他`。

### 2.6 匯出位置及權限

- 工作臺上方顯示一個「匯出」操作，展開後選日期及 Excel／PDF；只有 `exports.download` 可見。
- 統計頁刪除匯出區，只在 `statistics.view` 成立時出現在導覽及可用頁面清單。
- `exports.download` 新增父權限 `workbench.view`；後端權限驗證及前端用戶權限編輯器使用相同關係。
- 不新增第三個匯出頁面，也不新增 Excel／PDF 兩個獨立權限。

## 3. 可同時進行的三個工作包

### Agent A：後端資料、人工安排及匯出文件

所有權：

- `backend/models.py`
- `backend/database.py`
- `backend/permissions.py`
- `backend/routes/rescheduling.py`
- `backend/daily_exports.py`
- 本需求新增或修改的 `backend/tests/` 檔案

交付：

1. 為 `absence_cases` 加入向後相容的 `reason_type`、`reason_detail` 欄位及啟動時 SQLite 遷移；舊資料保持可讀。
2. 依共享契約驗證、建立、更新、序列化及審計缺席原因，並把原因帶入每日匯出資料。
3. 讓人工安排清單及確認接口同時接受 `recommended`、`unresolved`，保留全部最新衝突驗證及狀態更新。
4. 把 PDF 生成改為單一檔案、每頁兩表；刪除多人 ZIP 分支。Excel 版式不重做，只修改附註及原因輸出。
5. 把 `exports.download` 加入 `workbench.view` 前置權限。
6. 留下最小可運行測試：原因驗證／舊庫遷移、已有系統候選仍可人工安排、PDF 頁數為 `ceil(老師數 / 2)` 且回應不是 ZIP、Excel 附註使用完整老師名稱。

不得修改：

- `frontend/`
- 三份需求／計劃文件

### Agent B：工作臺缺席表單、人工入口及課表核對

所有權：

- `frontend/src/views/ReschedulingView.vue`
- `frontend/src/views/RecordsView.vue`

交付：

1. 缺席編輯器加入必選原因類別；只有「其他」顯示可留空補充框。每筆最多三位老師的缺席都保存自己的原因。
2. 有系統候選的 task 也顯示「系統建議均不合適，人工安排」操作，開啟現有人工頁並預選該 task；未解決 task 繼續使用同一入口。
3. 人工佇列文案及狀態呈現不再暗示清單只包含系統無解課堂。
4. 課表核對按共享契約套用固定三色，並由現有效課表與候選 legs 計算每個格子的 before／after；移除「調整」標籤。
5. 記錄詳情及管理員編輯缺席同步顯示／修改原因；舊資料沒有原因時顯示「未填寫」。
6. 保留鍵盤焦點、老師文字標識、手機橫向捲動及現有確認流程；不修改候選演算法或 API 名稱。

本 agent 使用下列 i18n key，但不修改語言檔：

```text
rescheduling.absenceReason
rescheduling.absenceReasons.sick
rescheduling.absenceReasons.personal
rescheduling.absenceReasons.official
rescheduling.absenceReasons.training
rescheduling.absenceReasons.other
rescheduling.otherReasonPlaceholder
rescheduling.useManualInstead
rescheduling.originalArrangement
rescheduling.newArrangement
rescheduling.freePeriod
```

不得修改：

- `backend/`
- `frontend/src/App.vue`
- `frontend/src/views/StatisticsView.vue`
- `frontend/src/locales/`
- 三份需求／計劃文件

### Agent C：應用外殼、顯示設定、匯出入口及全部文案

所有權：

- `frontend/src/App.vue`
- `frontend/src/views/StatisticsView.vue`
- `frontend/src/components/config/UserPermissionsPanel.vue`
- 新增 `frontend/src/components/DisplayPreferences.vue`
- 新增 `frontend/src/components/DailyExportActions.vue`
- `frontend/src/locales/zh-HK.json`
- `frontend/src/locales/en.json`

交付：

1. 在工作臺上方加入單一匯出操作及日期、Excel、PDF 選擇，重用現有 blob 下載方式；統計頁移除匯出 panel 及下載程式。
2. 統計導覽及頁面只按 `statistics.view` 顯示；工作臺匯出只按 `exports.download` 顯示。
3. 在用戶權限編輯器加入 `exports.download → workbench.view` 父子關係。
4. 加入字號及字體類型選擇，依共享契約保存並套用；桌面及手機均可操作。
5. 統一補齊本 agent 與 Agent B 使用的繁中／英文文案；不重新載入已停用的西班牙語或加泰羅尼亞語。
6. 確認大／超大字號下桌面導覽、手機頂部、對話框及表單沒有文字裁切；前端正式建置通過。

不得修改：

- `backend/`
- `frontend/src/views/ReschedulingView.vue`
- 三份需求／計劃文件

## 4. 整合及驗收記錄

- [x] 三個工作包按後端、工作臺、應用外殼的檔案邊界完成，整合時沒有以整檔覆蓋解決衝突。
- [x] Agent B 使用的 i18n key 已由 Agent C 補齊繁中及英文，正式建置沒有 raw key。
- [x] 完整後端測試結果為 79 passed、8 skipped；前端 `npm run build`、Python `compileall` 及 `git diff --check` 通過。
- [x] PDF 自動測試覆蓋 1、2、3 位老師頁數；三位老師樣本實際渲染為兩頁 A4，首頁上下兩表、末頁單表只佔上半頁，中文字體清楚且沒有裁切。
- [x] Excel 實際開啟核對三個 worksheet、缺席原因、老師全名、`MM-DD-老師全名-上班別科目` 及全形逗號分隔。
- [x] 權限測試覆蓋匯出 API 守衛及 `exports.download → workbench.view` 保存規則；管理員瀏覽器驗收確認匯出只在工作臺上方，統計頁不再顯示匯出。
- [x] 桌面及 390px 手機寬度驗收原因表單、三段字號、三種字體及重新整理保存；已有候選轉人工安排和二／三堂課表核對由後端測試及前端邏輯檢查覆蓋。
- [x] `DEVELOPMENT_PROGRESS.md`、需求記錄、管理員／一般用戶說明書及本計劃狀態已更新。

## 5. 明確不在本批實作

- 管理員自訂缺席原因種類。
- 把顯示偏好同步到其他裝置或用戶帳號。
- 為每位老師保存永久顏色或允許使用者自行配色。
- 新建另一套人工調課頁、審批佇列或通知流程。
- 為 PDF 每位老師產生獨立檔案、ZIP 或多種版式選擇。
- 把 Excel、PDF 下載拆成兩個權限。
