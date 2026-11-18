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

- 正式追蹤關鍵字以 GitHub `master/keywords.txt` 為準，爬蟲優先讀取該檔，失敗時才使用工作目錄中的同一份備援，不依賴 Supabase。
- 網頁：`https://hub-google.github.io/ctee-line-bot/keywords.html`。匿名訪客在網頁提出新增及刪除建議，管理者也在網站審核；每個字詞獨立核准或駁回。
- 網站使用獨立 Cloudflare Worker `ctee-keywords-inbox` + KV `CTEE_KEYWORDS_INBOX_ONLY` 暫存申請與審核紀錄，原始程式在 `viewer/keyword_gateway/worker.js`，不使用 Supabase。
- **即時核准方式**：`POST /review` 收到一項核准時，先透過 GitHub Contents API 讀取 `master/keywords.txt` 和 SHA，直接增刪該詞並 PUT 到 GitHub。取得成功 commit 後才把 KV 紀錄設成已核准，回傳 `synced:true`。拒絕只修改該項狀態，沒有 Github 寫入。SHA 版本衝突會重試，GitHub 失敗不會顯示核准成功。
- **授權前提**：必須在 Cloudflare Worker `ctee-keywords-inbox` 的 Secrets 設定 `GITHUB_WRITE_TOKEN`，使用僅授權 `hub-google/ctee-line-bot`、`Contents: Read and write` 的 fine-grained GitHub PAT。不可放在網頁原始碼或 GitHub 程式庫。**截至 2026-11-18 尚未配置這項 Secret；新核准會收到清楚錯誤而非假成功。** ChatGPT 的 GitHub 連線不能直接轉交憑證到公開 Worker。
- **無固定輪詢**：已刪掉管理網站每 20 秒查詢的 `setInterval`。`.github/workflows/apply_keyword_reviews.yml` 已移除定時 cron，只保留手動 `workflow_dispatch` 作為舊資料復原途徑。正常核准不需要等 GitHub Actions 排程。
- **畫面回應**：核准成功後直接使用 API 返回的 GitHub 關鍵字清單更新畫面。拒絕不更新清單。失敗保留待審核，不得顯示已生效。
- **驗證**：`viewer/keyword_gateway/test_worker.mjs` 使用模擬 GitHub Contents API 測試逐項核准、拒絕、沒有 Token 不得核准、只在 GitHub 提交成功後回報。GitHub Pages 發布前執行測試。
- 歷史防重複執行紀錄保留在 `viewer/keyword_gateway/processed.json`；之前已核准並寫入的變更包括新增「什麼」、刪除「阿」和 `test2`、保留被駁回的「凱壽」。這些既有變更透過 ChatGPT GitHub 連線實際提交，不代表 Worker 的私密自動授權已設定。

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
