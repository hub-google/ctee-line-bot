# 工商時報每日高畫質剪報｜正式版

## 運作流程

唯一的每日排程：.github/workflows/daily_ctee.yml → 每日台灣時間 06:00 的 GitHub Actions（可能延遲）→ 爬蟲擷取原圖 → 追加至 viewer-archive 日期資料夾 → 更新 GitHub Pages → 驗證發布的原圖及 ZIP → 推送一張 LINE Flex 剪報卡片。

原本 Rentry/ImgBB/Catbox 版本已存放在 legacy/2026-11-18/（原始 Git blob SHA 完全保留）。舊版排程已由新版取代，無第二套每日訊息。正式版仍匯入舊版爬蟲作為來源掃描引擎，但攔截圖片保存與訊息發送，只使用新版流程。

## 畫質與歷史

- 來源下載的圖片原始 bytes 直接保存，不重編碼；連續閱讀、縮圖總覽與全螢幕縮放使用同一份原圖，不另存縮圖。
- 原圖檔名：`YYYYMMDD_01_關鍵字1、關鍵字2.jpg`（例如 `20261118_01_匯率、央行.jpg`）。每張圖的所有命中關鍵字以「、」分隔，重複內容依 SHA-256 只保存一份。
- 每日保留一份 ZIP 供整批下載，ZIP 內檔名與原圖資料夾相同，不額外在網站根目錄保存重複 ZIP。
- ZIP 檔名固定為 `工商時報_YYYYMMDD.zip`（如 `工商時報_20261118.zip`），實際 GitHub Pages 原檔名及下載連結都使用同名；不使用 `latest.zip`。
- 所有日期儲存在 viewer-archive 分支的 viewer/public/archive/YYYY-MM-DD/，提供各日資料、原圖及 ZIP，過去日期不因新日期出現而刪除。
- 日期選單及可分享的網址：https://hub-google.github.io/ctee-line-bot/?date=YYYY-MM-DD
- 網站保存容量接近 900 MiB 時會中止新增部署以保留舊資料，沒有自動刪除政策；長期累積超過 GitHub Pages 容量上限必須更換保存方式。

## 閱讀器批次下載及指定日期重跑（2026-11-19）

- 下載全部剪報只保留閱讀器操作區的一個按鈕，不再於頁首重複；選取任一歷史日期時使用該日期歸檔的 `archive/YYYY-MM-DD/工商時報_YYYYMMDD.zip`。
- LINE LIFF 內點擊下載會呼叫 `liff.openWindow({external:true})` 將 ZIP 交給手機預設瀏覽器；一般 LINE 內建 WebView 使用 LINE 支援的 `openExternalBrowser=1`；一般瀏覽器保留原生 ZIP 下載。是否真的儲存成功仍由手機瀏覽器／作業系統決定，無法在頁面強制繞過系統下載限制。
- 爬蟲、原圖建置和 GitHub Actions 都支援 `CTEE_TARGET_DATE=YYYY-MM-DD`，workflow 手動觸發時可選填 `target_date`。沒指定仍照台灣當日執行。歷史重跑會以既有歸檔的文章網址補足歷史版面連結，但原圖仍逐篇重新擷取，不複製舊圖冒充重跑。
- 2026-11-18 已成功重跑並發布 31 張依 SHA-256 去重的原圖及當日 ZIP；驗證後 LINE Push API 回傳 HTTP 200，GitHub Actions run `44343340866`。舊日期資料仍留在同一日期資料夾，不建立第二份。
- 正式排程維持每日 06:00（台灣時間）；一次性的 11/18 自動觸發入口在驗證完成後移除。

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

## LINE Flex 分享（2026-11-18 快速版）

- 兩個獨立工商時報 LIFF：閱讀器 `2012346974-oasuaJGG`（Endpoint `https://hub-google.github.io/ctee-line-bot/`），**快速分享** `2012346974-960BgCEy`（Endpoint `https://hub-google.github.io/ctee-line-bot/share.html`）。兩個都在 LINE Login Channel `2012346974`，Scope `openid` / `profile` / `chat_message.write`。另兩個既有排隊怪獸 LIFF 保持不變。
- LINE Flex 卡片的「分享新聞給好友」**直接開啟獨立快速分享 LIFF**：`https://liff.line.me/2012346974-960BgCEy?date=YYYY-MM-DD&count=N`。此 LIFF 僅載入小型 HTML、公開設定及 LINE SDK；**不抓剪報 data.json、不載入新聞圖片、PhotoSwipe 或整個閱讀器**。依 URL 日期/篇數組出完整 Flex 卡片，待 `liff.init()` 完成，立即呼叫 `liff.shareTargetPicker([Flex])`，不需要再點網頁上的第二次分享按鈕。
- 分享好友收到的仍是 **Flex 圖文卡片**；其「開啟每日剪報」前往閱讀器 LIFF `https://liff.line.me/2012346974-oasuaJGG?date=YYYY-MM-DD`，到閱讀時才載入全部原圖/歷史/ZIP。
- 已開啟的完整閱讀器保留本頁「分享至 LINE」按鈕，直接呼叫 `shareTargetPicker`；閱讀器內產生的 Flex 卡片也改為快速分享入口。舊卡片的 `?share=1` 仍相容，不會中斷之前已經送出的連結。
- 因 LINE 平台限制，Flex 原生選人畫面只能在 LIFF SDK 初始化、完成必要授權後由 `shareTargetPicker` 開啟；即使使用極簡快速分享頁，也無法保證絕對零載入或略過 LINE 自身的 WebView。避免純文字替代破壞使用者要求：分享失敗會顯示錯誤與重試，**不會退回傳網址文字**。
- 兩個工商時報 LIFF 均由 `hub-google/LINE` 的 `.github/scripts/create-ctee-liff.py` 與 `.github/workflows/create-ctee-liff.yml` 使用原有 GitHub Secrets 自動建立/讀回驗證，建立後流程已恢復手動觸發。快分享、閱讀器與兩個舊 LIFF 狀態均已被建立流程檢查。
- 網站資料由 `viewer/public/liff-config.js` 提供公開 reader/share LIFF ID；每日 workflow 必須保留兩個 ID 並同步部署 `share.html`。權杖仍只存放在 GitHub Secrets；沒有額外 Worker、Supabase 功能或高頻排程。
- 2026-11-18 驗證：GitHub Actions 發布成功、LINE Flex validate API HTTP 200、重送 Push API HTTP 200（Run `44268579200`），14 張原圖完整存在。**手機端原生選人畫面與好友收件端尚需實機驗證**。
- 若需重發請手動執行 `resend_ctee_line.yml`（不重爬、不重存新聞），正式日排程台灣時間 06:00。

## 備份

- 原版完整備份：legacy/2026-11-18/，包含爬蟲、字型、關鍵字、套件與原始排程。
- 原有 Secrets 仍由 GitHub Actions 管理，沒有存放在備份裡。

## 內容權限

GitHub Pages 與公開 Git 倉庫的新聞圖片不具私密存取控制。請先確保這些新聞剪報的保存、散布、公開託管符合內容來源授權條款。
