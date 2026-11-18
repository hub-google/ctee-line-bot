# 舊版工商時報每日 LINE 剪報機器人（原版備份）

這個資料夾保存新版高畫質閱讀器正式替換之前，原本每日 Rentry 剪報版本的完整程式、設定與排程。

- 備份建立：2026-11-18（台灣時間）
- 備份來源：main/default 分支 master，Git commit `9d6d3520a346096f5221d8e1842452eb99d2919b`。
- `ctee_downloader_cloud.py` 為原始抓取、ImgBB/Catbox 圖床、Rentry 頁面、LINE Flex 發送程式。
- `assets/font.ttc` 為原有字型二進位檔，與原始 Git blob 完全相同。
- `.github/workflows/daily_ctee.yml` 與 `.github/workflows/keepalive.yml` 保留原始 YAML。位於備份資料夾內，不會自動觸發 GitHub Actions。
- `keywords.txt`、`requirements.txt`、`.gitignore`、`.vscode/settings.json` 一併保留。

如需回復舊版，先確認新排程不會同時發送，再將這份備份中的正式工作流程恢復到儲存庫 `.github/workflows/` 目錄。

注意：新聞來源帳號、LINE token 等為 GitHub Secrets，不包含在程式備份中。