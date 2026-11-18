# 工商時報獨立剪報閱讀器

此新方案不改動原本 Rentry 與 LINE 正式每日推播。舊版 daily_ctee.yml 及 ctee_downloader_cloud.py 仍可獨立執行。

## 閱讀與畫質

- 手機連續閱讀、縮圖總覽、PhotoSwipe 雙指縮放、左右滑動切換、單張下載、整日 ZIP。
- 新版只在本次獨立程序中攔截爬蟲下載的原始 bytes，寫入原圖；不追加原本的 JPEG 橫幅、不二次有損壓縮、不透過外部圖床再下載。
- 連續閱讀與放大使用來源原圖；低解析縮圖只用於縮圖模式。網站來源本身若畫質不足，無法無損增加不存在的細節。

## 每日保留歷史

- 日期資料位於 viewer-archive 分支的 viewer/public/archive/YYYY-MM-DD 目錄。
- GitHub Actions 每次只更新當日目錄，不刪除其他日期。頁首可選歷史日期，網址可附 ?date=YYYY-MM-DD。
- 新版每日定時流程只更新歷史，不額外發 LINE；手動執行才發送新版卡片，保留舊版每日推播。

## LINE Flex 與 LIFF

- 使用接近舊版正式排版的 LINE Flex 訊息。卡片含開啟剪報、下載 ZIP、分享、調整關鍵字。
- 如果 GitHub Secrets 設有已註冊且 Endpoint 對應本站的 LIFF_ID，卡片開啟 https://liff.line.me/LIFF_ID；否則使用 LINE 內建瀏覽器開啟 GitHub Pages。
- Flex 是聊天訊息樣式，LIFF 是在 LINE Developers 登錄的網頁應用入口，兩者不同。

## 容量與授權

- GitHub Pages 約有 1 GB 網站容量限制。本專案不會自動清掉舊檔；接近 900 MiB 時停止發布並保留先前資料，後續需規劃更長期儲存。
- GitHub Pages 是公開網站，robots.txt 與 noindex 不能防止他人讀取；需確認付費剪報的保存與公開託管符合新聞來源授權。

操作入口：https://hub-google.github.io/ctee-line-bot/
