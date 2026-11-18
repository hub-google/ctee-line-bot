# 工商時報獨立閱讀器（測試方案）

這個資料夾是與舊版 Rentry 推播並行的方案。**不改動**原本 `ctee_downloader_cloud.py`、`daily_ctee.yml` 或關鍵字設定。

## 預覽功能

- 連續捲動閱讀全部剪報，或切換縮圖總覽。
- 點圖開啟 PhotoSwipe 全螢幕閱讀：雙指縮放、平移、左右換篇。
- 單張下載原圖、整批下載 ZIP（由 GitHub Actions 預先產生，避免瀏覽器跨站下載限制）。
- 手機／LINE 內建瀏覽器適配。未載入外部 PhotoSwipe 時會退回開啟原圖。
- 靜態網站：不使用 Worker、Supabase 或持續運作伺服器。

## 建置與發布

`.github/workflows/viewer_preview.yml` 在測試部署時掃描當天新聞，將爬蟲結果轉成 `viewer/public/data.json`、`images/*.jpg`、`latest.zip` 並部署到 GitHub Pages。

`viewer/build_preview.py` 動態匯入舊爬蟲並攔截本次推播結果；**不會額外送出舊版訊息**。`viewer/send_preview.py` 驗證實際已部署頁面、JSON 與原圖均可存取後，才發出一則 LINE 測試通知。正式日常推播仍由原本的工作流程獨立運作。

本資料夾不是額外的每日定時推播服務。後續若決定採用新版，再評估是否連接每日流程。

## 注意

GitHub Pages 為公開靜態託管，`noindex` 不等於存取權限。應確認對付費新聞剪報的公開託管、轉載、分享及下載有適當授權；未獲授權時不應公開部署圖片。
