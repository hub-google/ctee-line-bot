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

## 關鍵字管理：GitHub 單一資料來源

- **唯一正式關鍵字來源**：`master/keywords.txt`。每日爬蟲先讀 `https://raw.githubusercontent.com/hub-google/ctee-line-bot/master/keywords.txt`；連線失敗時讀取當次 GitHub checkout 中的 `keywords.txt`。不再呼叫 Supabase。
- **公開網站**：`https://hub-google.github.io/ctee-line-bot/keywords.html`。直接讀 GitHub 原始文字檔，提供新增、刪除詞彙及送出申請介面。
- **訪客送出**：目前用 GitHub Issues 儲存申請，會跳至 GitHub 預填表單。GitHub 要求登入才能發 Issue；純 GitHub Pages 靜態網頁無法安全實現完全匿名的共用寫入收件匣。若未來要匿名申請，必須增加可承擔驗證和限流的外部後端，不能把 GitHub Token 或固定密碼放在公開 JavaScript。
- **網站審核**：點「管理者專區」，輸入界面管理金鑰和擁有本儲存庫 `Contents: Read/Write`、`Issues: Read/Write` 的 GitHub fine-grained token（僅保留在當前分頁記憶體）。管理者點「核准並更新 keywords.txt」時，前端會讀最新 GitHub 檔案 SHA、檢查衝突並用 GitHub Contents API 更新 `master/keywords.txt`，成功後關閉 Issue；「駁回」不修改關鍵字。
- **權限安全**：管理金鑰只是進入管理頁的簡單 UI 門檻，*真正的 GitHub 寫入授權由 GitHub Token 權限決定*。不要把 Token 寫入網站、公開儲存庫、網頁原始碼或使用者可取得的 Secrets。
- 亦提供 GitHub Actions `.github/workflows/review_keyword_issues.yml` 作替代審核通道：GitHub 有寫入權限的協作者可於申請 Issue 留言 `/approve` 或 `/reject`，由 GitHub Actions 驗證協作者權限後更新 `keywords.txt`。網頁管理區則是直接寫入的主要入口。
- 舊版 Supabase 關鍵字 API、審核資料表與同步排程已停用／刪除；其他專案的共用 Supabase 資源不受影響。
- 2026-11-18 曾核准的 `test2` 已經寫入 `master/keywords.txt`，不會因停用舊審核系統而遺失。

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
