"""Send exactly one test LINE message, but only after the viewer is publicly readable."""
import json
import os
import time
from urllib.parse import urljoin

import requests

site = os.environ["SITE_URL"].rstrip("/") + "/"
token = os.environ["LINE_ACCESS_TOKEN"]
user_id = os.environ["LINE_USER_ID"]
session = requests.Session()
error = "not yet checked"
count = 0

# GitHub Pages may need a short propagation delay after deploy-pages succeeds.
for attempt in range(12):
    try:
        html = session.get(site, timeout=15)
        html.raise_for_status()
        if "每日剪報" not in html.text or "photoswipe" not in html.text:
            raise RuntimeError("站點內容與新閱讀器不符")
        resp = session.get(urljoin(site, "data.json"), timeout=15, headers={"Cache-Control": "no-cache"})
        resp.raise_for_status()
        data = resp.json()
        count = len(data["images"])
        if count < 1:
            raise RuntimeError("無有效剪報內容")
        first = urljoin(site, data["images"][0]["src"])
        image = session.get(first, timeout=20, headers={"Range": "bytes=0-8191"})
        image.raise_for_status()
        if not image.headers.get("Content-Type", "").startswith("image/"):
            raise RuntimeError("第一張圖片無法讀取")
        print(f"[viewer] Public site checked: {site}; {count} images", flush=True)
        break
    except Exception as exc:
        error = str(exc)
        print(f"[viewer] Readiness attempt {attempt + 1} failed: {error}", flush=True)
        if attempt < 11:
            time.sleep(5)
else:
    raise SystemExit("停止推播：新網站尚未可正常閱讀。最後錯誤：" + error)

text = (
    "【工商時報剪報｜新版閱讀器測試】\n"
    f"今日已打包 {count} 張新聞剪報。\n"
    "可在同一頁連續閱讀、雙指縮放、單張下載或打包 ZIP 下載。\n\n"
    f"點此試用：{site}\n\n"
    "這只是新版測試，原本每日 Rentry 推播不變。"
)
payload = {"to": user_id, "messages": [{"type": "text", "text": text}]}
response = session.post(
    "https://api.line.me/v2/bot/message/push",
    json=payload,
    headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    timeout=20
)
response.raise_for_status()
print(f"[LINE] New viewer test push accepted, HTTP {response.status_code}", flush=True)
