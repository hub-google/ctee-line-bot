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

## 網站關鍵字建議與逐項審核（2026-11-18）

- 唯一的新聞追蹤關鍵字檔案是 GitHub `master/keywords.txt`。爬蟲從此檔取得關鍵字，失敗時退回 GitHub Actions checkout 裡同一份檔案，不使用 Supabase。
- 網站：`https://hub-google.github.io/ctee-line-bot/keywords.html`，訪客可直接送出新增及刪除項目，**不用登入 GitHub、不跳頁**。搜尋輸入框使用 `type=search`、停用自動填字並等使用者主動點擊才可編輯，避免 Chrome 自動塞入 Email。
- 網頁為純靜態 GitHub Pages；匿名網站無法安全地持有 GitHub Token。因此使用獨立的免費 Cloudflare Worker `ctee-keywords-inbox` 加獨立 KV `CTEE_KEYWORDS_INBOX_ONLY` 作**暫時收件／審核緩衝**，不是 Supabase，也不在 Worker 裡保存 GitHub Token。API URL：`https://ctee-keywords-inbox.ber-at.workers.dev`。Worker 程式：`viewer/keyword_gateway/worker.js`。
- 提案 POST `/submit`：`{request_id:UUID,name,reason,items:[{operation:"add"|"remove",keyword}]}`，一次 1～20 個字詞；後端逐字詞存不同紀錄，失敗時網站明確顯示錯誤，不會假裝送出成功。相同 request_id 重送不會產生重複項目。匿名提交有限速。
- **網站審核**：管理者輸入原指定管理金鑰 `9`，使用 `GET /reviews` 在網站查看申請，`POST /review` 對單一 item 做 `approved` 或 `rejected`，每個字詞可獨立處理，例如 A 申請「新增 test1、test2，刪除 test3」會有三個核准／駁回按鈕。這個流程不要求管理者 GitHub Token，也不會跳 GitHub。金鑰放在 Worker Secret `CTEE_ADMIN_PIN`，不放在靜態網站原始碼。
- **寫入 GitHub**：`.github/workflows/apply_keyword_reviews.yml` 每 5 分鐘讀取 Worker 的唯讀 `GET /export`，用 GitHub Actions 內建 `GITHUB_TOKEN` 將已核准的逐項變更套用到 `master/keywords.txt`，並將每個已決定的 item 寫入 `viewer/keyword_gateway/processed.json`。這份 GitHub 檔案用於防重複套用。實際同步受 GitHub Actions 排程延遲影響，並非按下核准瞬間更新；網站顯示「同步中」及「已生效」。
- **完整性**：只在 GitHub 一次 commit 修改 `keywords.txt` 與決策處理記錄；拒絕覆蓋空值、格式異常或服務錯誤資料。每次定時排程無新項目時不 commit。可手動在 GitHub Actions 執行 `Apply CTEE website keyword reviews to GitHub`，與每日新聞推播是兩個獨立流程。
- **測試**：`viewer/keyword_gateway/test_worker.mjs` 用記憶體 KV 測試匿名送出、重複請求、分項核准／駁回、管理金鑰、CORS 和唯讀匯出；發布 GitHub Pages 前執行測試。
- **安全**：為遵循原定預設，管理金鑰目前是 `9`；這只有一個字元，對公開網路**並不安全**，儘管後端有錯誤次數限制。建議儘早換成長密碼。密碼只存在 Cloudflare Worker Secret，管理者登入後只保存在當前瀏覽器記憶體，不會寫入 GitHub。此功能每次動作需要少量免費 Worker/KV 請求，實際使用仍受帳戶免費額度限制。
- **清理**：原本臨時建立的 Supabase 4 張 `ctee_keyword_*` 資料表及 RPC 已刪，舊 Supabase 同步流程已移除。其他專案資源未變更。舊 `ctee-keywords` Edge Function 曾於 2026-11-18 建立，與此新版流程無關；後續處理需避免影響其他專案。
- 2026-11-18 核准的 `test2` 已保留在 `master/keywords.txt`。

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
