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

## LINE Flex 分享與 LIFF（2026-11-18）

- **專屬 LIFF 已由 LINE 官方 API 建立並讀回驗證**：ID `2012346974-oasuaJGG`，名稱「工商時報每日剪報」，Size `Full`，Endpoint `https://hub-google.github.io/ctee-line-bot/`； scopes：`openid`、`profile`、`chat_message.write`。LIFF URL：`https://liff.line.me/2012346974-oasuaJGG`。
- 沿用排隊怪獸的 LINE Login Channel `2012346974`，但建立**第三個獨立 LIFF App**；原有 `2012346974-bmC3fZuf`、`2012346974-jSefrnfw` 未修改。
- 建立程序在 `hub-google/LINE` 的 `.github/scripts/create-ctee-liff.py` + `.github/workflows/create-ctee-liff.yml`；使用該 Repo 原有 `LINE_LOGIN_CHANNEL_ID` 與 `LINE_LOGIN_CHANNEL_SECRET`。建立時會檢查舊 LIFF、以 Endpoint 去重，建立後再確認 ID、scopes、Endpoint；工作流程不輸出任何憑證，且已復原為僅可手動執行。
- 本 Repo 的 `viewer/public/liff-config.js` 設定公開 LIFF ID，`publish_keywords.yml` 更新網站及讀者介面。這個 ID 不是密鑰；Messaging API Channel Access Token 仍只能存於 GitHub Secrets。
- 每日推播仍為 LINE Flex 卡片（「開啟每日剪報」、「分享新聞給好友」、「調整追蹤關鍵字」）。「分享新聞給好友」改為點擊 `https://liff.line.me/2012346974-oasuaJGG?date=YYYY-MM-DD&share=1`，讓剪報閱讀器在 LIFF 初始化、登入及剪報載入完成後，直接呼叫 `liff.shareTargetPicker([Flex])` 開啟 LINE 好友／群組選擇器。不再送純文字網址，也不再需要先點第二層分享按鈕。
- 網站的「分享至 LINE」也直接呼叫 `shareTargetPicker` 傳送相同 Flex 卡片；收件人可在卡片開啟指定日期的完整 LIFF 剪報，含原圖、縮放、歷史及 ZIP 下載。
- LIFF 不支援或登入失敗時**不能假裝已分享**，網頁明確顯示錯誤供重試，不會悄悄改傳純文字。
- 分享對象選擇器需在 LINE Developers 同一 LINE Login Channel 啟用。GitHub CI 可以驗證 LINE 建立及推播 API，LINE App 內實際選人、授權及收件端顯示仍要手機實測。
- `resend_ctee_line.yml` 僅可手動執行，重送已發布的剪報卡片，不重新擷取或儲存圖片；正式每日排程維持台灣時間 06:00。未新增 Worker 或高頻排程。

## 備份

- 原版完整備份：legacy/2026-11-18/，包含爬蟲、字型、關鍵字、套件與原始排程。
- 原有 Secrets 仍由 GitHub Actions 管理，沒有存放在備份裡。

## 內容權限

GitHub Pages 與公開 Git 倉庫的新聞圖片不具私密存取控制。請先確保這些新聞剪報的保存、散布、公開託管符合內容來源授權條款。
