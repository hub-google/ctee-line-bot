# 工商時報每日高畫質剪報｜正式版

## 運作流程

唯一的每日排程：.github/workflows/daily_ctee.yml → 每日台灣時間 06:00 的 GitHub Actions（可能延遲）→ 爬蟲擷取原圖 → 追加至 viewer-archive 日期資料夾 → 更新 GitHub Pages → 驗證發布的原圖及 ZIP → 推送一張 LINE Flex 剪報卡片。

原本 Rentry/ImgBB/Catbox 版本已存放在 legacy/2026-11-18/（原始 Git blob SHA 完全保留）。舊版排程已由新版取代，無第二套每日訊息。正式版仍匯入舊版爬蟲作為來源掃描引擎，但攔截圖片保存與訊息發送，只使用新版流程。

## 畫質與歷史

- 來源下載的圖片原始 bytes 直接保存，不重編碼；連續閱讀、縮圖總覽與全螢幕縮放使用同一份原圖，不另存縮圖。
- 原圖檔名：`YYYYMMDD_01_關鍵字1、關鍵字2.jpg`（例如 `20261118_01_匯率、央行.jpg`）。每張圖的所有命中關鍵字以「、」分隔，重複內容依 SHA-256 只保存一份。
- 每日保留一份 ZIP 供整批下載，ZIP 內檔名與原圖資料夾相同，不額外在網站根目錄保存重複 ZIP。
- 所有日期儲存在 viewer-archive 分支的 viewer/public/archive/YYYY-MM-DD/，提供各日資料、原圖及 ZIP，過去日期不因新日期出現而刪除。
- 日期選單及可分享的網址：https://hub-google.github.io/ctee-line-bot/?date=YYYY-MM-DD
- 網站保存容量接近 900 MiB 時會中止新增部署以保留舊資料，沒有自動刪除政策；長期累積超過 GitHub Pages 容量上限必須更換保存方式。

## 關鍵字：Supabase 單一正式來源（2026-11-18）

- 正式追蹤清單已從原本 33 個 GitHub 關鍵字遷移到 Supabase `public.ctee_keywords`。新資料完全以 Supabase 為準；根目錄舊 `keywords.txt` 已在端到端驗收通過後刪除；歷史備份仍保留於 `legacy/2026-11-18/`，不參與運行。
- 網站：`https://hub-google.github.io/ctee-line-bot/keywords.html`。一般訪客不用任何帳號即可在網頁提出新增、刪除關鍵字建議；單次支援 1～20 個字詞，輸入姓名與選填原因。表單留在本站，不跳 GitHub。
- 管理者在同一網站輸入原管理金鑰 `9`，以待審核／已核准／已駁回分頁管理。每個字詞獨立核准或駁回；一批建議中核准其中一項，其他項不受影響。管理金鑰僅送到 Supabase Edge Function 做伺服器端驗證，不要求 GitHub Token。
- **即時更新**：網站呼叫 Supabase Edge Function `ctee-keywords`，其使用 `public.ctee_review_keyword_item(uuid,text)` 在同一資料庫交易中核准某項申請並新增或刪除 `ctee_keywords`。成功後直接回傳最新清單，網頁立即呈現「已核准・已生效」。未經確認不報成功；沒有 GitHub Actions 同步或任何 20 秒輪詢。 為避免清單被誤刪至零筆，審核交易會串行處理修改並拒絕刪除最後一個關鍵字；此時原申請維持待審核，網站顯示明確錯誤。
- **剪報程式**：`ctee_downloader_cloud.py` 的 `load_keywords()` 直接請求 `https://unapiwajmgqqtdkixaab.supabase.co/functions/v1/ctee-keywords`。API 空值、錯誤或無法連線時停止本次擷取，不使用過期的 GitHub 清單當備援。
- **資料表**：`public.ctee_keywords`（追蹤字詞）、`public.ctee_keyword_requests`（每項申請及審核結果）、`public.ctee_keyword_access_events`（防濫用記錄）。三張表皆啟用 RLS，匿名角色無直接資料表權限；公開讀取、匿名提交和管理操作都由專用 Edge Function 驗證與執行。其他 Supabase 專案表與 API 不修改。
- **原始碼**：`supabase/functions/ctee-keywords/index.ts`；資料庫 migration `ctee_keyword_supabase_source_and_review` 已套用至 `unapiwajmgqqtdkixaab`。
- **驗收**：GitHub Actions 已確認公開 API 能讀取清單、CORS 正常、網站 JavaScript 語法有效，並完成一次實際端到端測試（匿名一次送出三項、分項核准／駁回、確認立即生效，再核准移除驗收字詞）。測試字詞和申請紀錄已清理，不影響既有 33 個正式關鍵字。
- **歷史**：先前已完成的 5 項 GitHub 審核決策紀錄保留於 `viewer/keyword_gateway/processed.json` 供追溯；它不參與新的 Supabase 流程。

## LINE 分享（直接開原生收件者選擇）

- 正式每日推播仍使用 LINE Flex 卡片；三個按鈕為「開啟每日剪報」、「分享新聞給好友」、「調整追蹤關鍵字」。
- 不再先開啟第二層分享面板：LINE 卡片的「分享新聞給好友」使用 LINE 官方 URL scheme `https://line.me/R/share?text=...`，點擊後直接進入 LINE 收件者選擇畫面；傳送日期固定的完整剪報網址，不只是單篇原圖。手機安裝 LINE 時由 LINE App 處理，桌面／外部瀏覽器畫面由 LINE 決定。
- 剪報閱讀器的「分享至 LINE」按鈕也只需點一次：在已有專屬 LIFF App、已登入且 shareTargetPicker 可用時，呼叫 `liff.shareTargetPicker()` 分享完整的 LINE Flex 卡片；其他情況走 LINE 原生分享網址，傳送完整剪報閱讀器連結。
- 真正的 LIFF 連結格式：`https://liff.line.me/<LIFF_ID>?date=YYYY-MM-DD`。**目前尚未註冊工商時報專屬 LIFF App，公開設定仍為空值，因此現階段分享的是 GitHub Pages 閱讀器網址，不能稱為已發送 LIFF 連結或 Flex 分享。**
- 既有排隊怪獸兩個 LIFF ID 不可直接搬來使用，因為它們有各自的 Endpoint。專屬 LIFF 必須在 LINE Login Channel `2012346974` 建立，名稱「工商時報每日剪報」、Size `Full`、Endpoint `https://hub-google.github.io/ctee-line-bot/`，並啟用該 Channel 的 shareTargetPicker；LINE Developers 將產生新 ID。
- 將取得的新 LIFF ID 寫入 `viewer/public/liff-config.js` 的 `window.CTEE_LIFF_ID`（公開識別碼，不是 Token）。推送到 master 後，`publish_keywords.yml` 同步發布網站設定、剪報閱讀器和關鍵字頁面；每日 workflow 亦採用這個公開 ID，無須在 GitHub Secrets 新增 LIFF_ID。既有 LINE_ACCESS_TOKEN 仍只放在 Secrets。
- 傳給朋友的是選定日期的整份閱讀器網址，支援原圖縮放、歷史與 ZIP。沒有新增 Worker 或計時輪詢。
- `resend_ctee_line.yml` 僅限手動執行，按需重送已發布的剪報卡片，不重爬或重存圖片；正式日排程仍為每日 06:00。
- 如要真正驗收 LINE 原生畫面與 LIFF Flex 分享，必須在有安裝 LINE 的手機進行實際選人、傳送及收件端開啟測試；GitHub CI 僅能驗證程式和推播 API。

## 備份

- 原版完整備份：legacy/2026-11-18/，包含爬蟲、字型、關鍵字、套件與原始排程。
- 原有 Secrets 仍由 GitHub Actions 管理，沒有存放在備份裡。

## 內容權限

GitHub Pages 與公開 Git 倉庫的新聞圖片不具私密存取控制。請先確保這些新聞剪報的保存、散布、公開託管符合內容來源授權條款。
