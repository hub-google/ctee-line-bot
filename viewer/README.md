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

- 正式追蹤清單已從原本 33 個 GitHub 關鍵字遷移到 Supabase `public.ctee_keywords`。新資料完全以 Supabase 為準；根目錄舊 `keywords.txt` 在完成驗收後刪除，舊版備份仍保留於 `legacy/2026-11-18/`。
- 網站：`https://hub-google.github.io/ctee-line-bot/keywords.html`。一般訪客不用任何帳號即可在網頁提出新增、刪除關鍵字建議；單次支援 1～20 個字詞，輸入姓名與選填原因。表單留在本站，不跳 GitHub。
- 管理者在同一網站輸入原管理金鑰 `9`，以待審核／已核准／已駁回分頁管理。每個字詞獨立核准或駁回；一批建議中核准其中一項，其他項不受影響。管理金鑰僅送到 Supabase Edge Function 做伺服器端驗證，不要求 GitHub Token。
- **即時更新**：網站呼叫 Supabase Edge Function `ctee-keywords`，其使用 `public.ctee_review_keyword_item(uuid,text)` 在同一資料庫交易中核准某項申請並新增或刪除 `ctee_keywords`。成功後直接回傳最新清單，網頁立即呈現「已核准・已生效」。未經確認不報成功；沒有 GitHub Actions 同步或任何 20 秒輪詢。
- **剪報程式**：`ctee_downloader_cloud.py` 的 `load_keywords()` 直接請求 `https://unapiwajmgqqtdkixaab.supabase.co/functions/v1/ctee-keywords`。API 空值、錯誤或無法連線時停止本次擷取，不使用過期的 GitHub 清單當備援。
- **資料表**：`public.ctee_keywords`（追蹤字詞）、`public.ctee_keyword_requests`（每項申請及審核結果）、`public.ctee_keyword_access_events`（防濫用記錄）。三張表皆啟用 RLS，匿名角色無直接資料表權限；公開讀取、匿名提交和管理操作都由專用 Edge Function 驗證與執行。其他 Supabase 專案表與 API 不修改。
- **原始碼**：`supabase/functions/ctee-keywords/index.ts`；資料庫 migration `ctee_keyword_supabase_source_and_review` 已套用至 `unapiwajmgqqtdkixaab`。
- **驗收**：GitHub Actions 已確認公開 API 能讀取清單、CORS 正常、網站 JavaScript 語法有效，並完成一次實際端到端測試（匿名一次送出三項、分項核准／駁回、確認立即生效，再核准移除驗收字詞）。測試字詞和申請紀錄已清理，不影響既有 33 個正式關鍵字。
- **歷史**：先前已完成的 5 項 GitHub 審核決策紀錄保留於 `viewer/keyword_gateway/processed.json` 供追溯；它不參與新的 Supabase 流程。

## LINE

- 正式每日推播使用 LINE Flex，包含閱讀、下載、分享、調整關鍵字。
- LIFF 圖文分享：正式推播的「分享新聞給好友」不再使用 `line.me/R/msg/text`（純文字分享）。改為開啟 LIFF 剪報頁面的分享專區，由使用者點「選擇 LINE 好友／群組」後，透過 `liff.shareTargetPicker()` 發送相同設計的 LINE Flex 卡片（包含日期、篇數、閱讀及轉分享按鈕）。
- 在 LINE Developers 的 **LINE Login Channel → LIFF** 新增或選擇 LIFF App，Endpoint URL 必須指向 `https://hub-google.github.io/ctee-line-bot/`，並在同一 Channel 啟用 **shareTargetPicker**。要設定 GitHub Actions repository secret `LIFF_ID`（實際已註冊的 LIFF App ID，不是 Messaging API Channel ID）。
- 每日 workflow 將公開、非機密的 `LIFF_ID` 寫入部署網站的 `liff-config.js`，供瀏覽器呼叫 LIFF SDK；LINE Channel Access Token 仍只存在 GitHub Secrets，不可放入網頁。
- 未設定 `LIFF_ID` 時，原本閱讀器仍正常使用，但分享專區明確顯示設定缺失，不會假裝已成功發送圖文，也不再退回純文字分享。是否有設定可由 workflow log 的 `LIFF enabled` / `LIFF_ID missing` 檢查。驗證實際分享仍需在 LINE 客戶端手動選擇好友。
- LIFF 分享的網址固定所選日期 `?date=YYYY-MM-DD`，歷史新聞也能分享；無需新增 Worker、付費服務或背景伺服器。
- LINE_VALIDATE_ONLY=1 可呼叫官方 validate/push API 驗證卡片而不實際傳送；正式每日任務為實際 Push。
- 手動執行 workflow_dispatch 會照常推播，可能重複傳送當天的訊息，請只在必要時使用。
- 2026-11-18 修復推播：已使用單次 push 觸發重建當日剪報及 LINE Flex 重送，隨後移除該臨時觸發器。正式排程恢復只有每日 cron 與手動 `workflow_dispatch`，一般修改程式不會自動重送新聞。

## 備份

- 原版完整備份：legacy/2026-11-18/，包含爬蟲、字型、關鍵字、套件與原始排程。
- 原有 Secrets 仍由 GitHub Actions 管理，沒有存放在備份裡。

## 內容權限

GitHub Pages 與公開 Git 倉庫的新聞圖片不具私密存取控制。請先確保這些新聞剪報的保存、散布、公開託管符合內容來源授權條款。
