"""Verify the published dated gallery before pushing the official daily LINE Flex card.

A registered LIFF_ID is optional. A Flex message is the chat card; a LIFF URL
is a separately registered web-app entrypoint. Never invent a LIFF ID.
"""
import hashlib
import json
import os
import re
import time
from urllib.parse import quote, urljoin

import requests

site = os.environ["SITE_URL"].rstrip("/") + "/"
token = os.environ["LINE_ACCESS_TOKEN"]
user_id = os.environ["LINE_USER_ID"]
expected = os.environ.get("EXPECTED_REF", "")
session = requests.Session()
last_error = "not ready"
data = None

for attempt in range(48):
    try:
        res = session.get(site, timeout=15)
        res.raise_for_status()
        if "每日剪報" not in res.text or "photoswipe" not in res.text:
            raise RuntimeError("Published site does not look like the new viewer")
        feed = session.get(urljoin(site, "data.json"), timeout=15, headers={"Cache-Control": "no-cache"})
        feed.raise_for_status()
        data = feed.json()
        if expected and data.get("build_ref") != expected:
            raise RuntimeError("GitHub Pages still serving an older build")
        images = data.get("images", [])
        if not images:
            raise RuntimeError("No clipping images")
        history_resp = session.get(urljoin(site, "history.json"), timeout=15)
        history_resp.raise_for_status()
        history = history_resp.json().get("dates", [])
        if data.get("date") not in [d["date"] for d in history]:
            raise RuntimeError("Today's issue missing from persistent history")
        img = session.get(urljoin(site, images[0]["src"]), timeout=20)
        img.raise_for_status()
        if not img.headers.get("Content-Type", "").lower().startswith("image/"):
            raise RuntimeError("Original clipping not served as an image")
        if hashlib.sha256(img.content).hexdigest() != images[0]["sha256"]:
            raise RuntimeError("Original clipping checksum changed")
        zip_resp = session.get(urljoin(site, data["zip"]), headers={"Range": "bytes=0-63"}, timeout=15)
        zip_resp.raise_for_status()
        if not zip_resp.content.startswith(b"PK"):
            raise RuntimeError("Archive download does not contain a ZIP")
        print(f"[viewer] Verified live date {data['date']}; {len(images)} exact original images, archive ZIP, {len(history)} history days", flush=True)
        break
    except Exception as exc:
        last_error = str(exc)
        print(f"[viewer] Readiness {attempt + 1}/48: {last_error}", flush=True)
        if attempt < 47:
            time.sleep(5)
else:
    raise SystemExit("No LINE push: viewer not ready. " + last_error)

date = data["date"]
date_label = data.get("date_label", date)
count = len(images)
normal_url = site + "?date=" + quote(date, safe="")
# The LIFF ID is public. Read the one actually served by the site so the
# outgoing card and the browser share the same LIFF app, without a GitHub secret.
config_response = session.get(urljoin(site, "liff-config.js"), timeout=15)
config_response.raise_for_status()
config_text = config_response.text
def published_liff_id(name):
    # Both identifiers are PUBLIC; the LINE access token remains in GitHub Secrets.
    match = re.search(r'^window\.' + re.escape(name) + r'\s*=\s*("[^"]+")\s*;' + r'\s*$', config_text, re.M)
    if not match:
        raise RuntimeError("Missing LIFF public config: " + name)
    value = json.loads(match.group(1))
    if not re.fullmatch(r"2012346974-[A-Za-z0-9]+", value):
        raise RuntimeError("Invalid published LIFF ID: " + name)
    return value

liff_id = published_liff_id("CTEE_LIFF_ID")
share_liff_id = published_liff_id("CTEE_SHARE_LIFF_ID")
if share_liff_id == liff_id:
    raise RuntimeError("Share LIFF must not reuse full reader")
reader_url = "https://liff.line.me/" + liff_id + "?date=" + quote(date, safe="")
# The first tap runs the small, dedicated LIFF app, not the full reader.
share_link = ("https://liff.line.me/" + share_liff_id +
              "?date=" + quote(date, safe="") + "&count=" + str(count))
print("[LINE] Verified distinct reader and fast-share LIFF entrypoints", flush=True)
keyword_url = "https://hub-google.github.io/ctee-line-bot/keywords.html"

message = {
    "type": "flex",
    "altText": f"工商時報｜{date_label} 每日剪報，共 {count} 則，點擊閱讀原圖",
    "contents": {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box", "layout": "vertical", "backgroundColor": "#173C32",
            "paddingTop": "18px", "paddingBottom": "18px", "paddingStart": "20px", "paddingEnd": "20px",
            "contents": [
                {"type": "text", "text": "工商時報", "size": "xl", "weight": "bold", "color": "#FFFFFF"},
                {"type": "text", "text": "每日新聞剪報  |  原圖典藏", "size": "xs", "color": "#C3DFD5", "margin": "xs"}
            ]
        },
        "body": {
            "type": "box", "layout": "vertical", "spacing": "md",
            "contents": [
                {"type": "text", "text": date_label + "  精選報導", "weight": "bold", "size": "md", "color": "#1D3331"},
                {"type": "text", "text": f"依照追蹤關鍵字，今日共整理 {count} 則相關新聞。", "wrap": True, "size": "sm", "color": "#50615D"},
                {"type": "separator", "margin": "md", "color": "#E7EDEB"},
                {"type": "text", "text": "原圖畫質・雙指縮放・歷史查閱・整批下載", "size": "xs", "wrap": True, "color": "#65736D"}
            ]
        },
        "footer": {
            "type": "box", "layout": "vertical", "spacing": "sm",
            "contents": [
                {"type": "button", "style": "primary", "height": "sm", "color": "#176B57",
                 "action": {"type": "uri", "label": "開啟每日剪報", "uri": reader_url}},
                {"type": "button", "style": "primary", "height": "sm", "color": "#286BA6",
                 "action": {"type": "uri", "label": "分享新聞給好友", "uri": share_link}},
                {"type": "button", "style": "primary", "height": "sm", "color": "#7156A4",
                 "action": {"type": "uri", "label": "調整追蹤關鍵字", "uri": keyword_url}}
            ]
        }
    }
}
validate_only = os.environ.get("LINE_VALIDATE_ONLY") == "1"
endpoint = (
    "https://api.line.me/v2/bot/message/validate/push"
    if validate_only else "https://api.line.me/v2/bot/message/push"
)
payload = {"messages": [message]} if validate_only else {"to": user_id, "messages": [message]}
response = session.post(
    endpoint,
    json=payload,
    headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    timeout=20,
)
if response.status_code != 200:
    kind = "validation" if validate_only else "push"
    raise RuntimeError(f"LINE Flex {kind} rejected: HTTP {response.status_code} {response.text[:1000]}")
if validate_only:
    print(f"[LINE] Production Flex validation passed (no message sent): HTTP {response.status_code}", flush=True)
else:
    print(f"[LINE] Daily HQ Flex push accepted: HTTP {response.status_code}", flush=True)
, config_text, re.M)
    if not match:
        raise RuntimeError("Missing LIFF public config: " + name)
    value = json.loads(match.group(1))
    if not re.fullmatch(r"2012346974-[A-Za-z0-9]+", value):
        raise RuntimeError("Invalid published LIFF ID: " + name)
    return value

liff_id = published_liff_id("CTEE_LIFF_ID")
share_liff_id = published_liff_id("CTEE_SHARE_LIFF_ID")
if share_liff_id == liff_id:
    raise RuntimeError("Share LIFF must not reuse full reader")
reader_url = "https://liff.line.me/" + liff_id + "?date=" + quote(date, safe="")
# The first tap runs the small, dedicated LIFF app, not the full reader.
share_link = ("https://liff.line.me/" + share_liff_id +
              "?date=" + quote(date, safe="") + "&count=" + str(count))
print("[LINE] Verified distinct reader and fast-share LIFF entrypoints", flush=True)
keyword_url = "https://hub-google.github.io/ctee-line-bot/keywords.html"

message = {
    "type": "flex",
    "altText": f"工商時報｜{date_label} 每日剪報，共 {count} 則，點擊閱讀原圖",
    "contents": {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box", "layout": "vertical", "backgroundColor": "#173C32",
            "paddingTop": "18px", "paddingBottom": "18px", "paddingStart": "20px", "paddingEnd": "20px",
            "contents": [
                {"type": "text", "text": "工商時報", "size": "xl", "weight": "bold", "color": "#FFFFFF"},
                {"type": "text", "text": "每日新聞剪報  |  原圖典藏", "size": "xs", "color": "#C3DFD5", "margin": "xs"}
            ]
        },
        "body": {
            "type": "box", "layout": "vertical", "spacing": "md",
            "contents": [
                {"type": "text", "text": date_label + "  精選報導", "weight": "bold", "size": "md", "color": "#1D3331"},
                {"type": "text", "text": f"依照追蹤關鍵字，今日共整理 {count} 則相關新聞。", "wrap": True, "size": "sm", "color": "#50615D"},
                {"type": "separator", "margin": "md", "color": "#E7EDEB"},
                {"type": "text", "text": "原圖畫質・雙指縮放・歷史查閱・整批下載", "size": "xs", "wrap": True, "color": "#65736D"}
            ]
        },
        "footer": {
            "type": "box", "layout": "vertical", "spacing": "sm",
            "contents": [
                {"type": "button", "style": "primary", "height": "sm", "color": "#176B57",
                 "action": {"type": "uri", "label": "開啟每日剪報", "uri": reader_url}},
                {"type": "button", "style": "primary", "height": "sm", "color": "#286BA6",
                 "action": {"type": "uri", "label": "分享新聞給好友", "uri": share_link}},
                {"type": "button", "style": "primary", "height": "sm", "color": "#7156A4",
                 "action": {"type": "uri", "label": "調整追蹤關鍵字", "uri": keyword_url}}
            ]
        }
    }
}
validate_only = os.environ.get("LINE_VALIDATE_ONLY") == "1"
endpoint = (
    "https://api.line.me/v2/bot/message/validate/push"
    if validate_only else "https://api.line.me/v2/bot/message/push"
)
payload = {"messages": [message]} if validate_only else {"to": user_id, "messages": [message]}
response = session.post(
    endpoint,
    json=payload,
    headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    timeout=20,
)
if response.status_code != 200:
    kind = "validation" if validate_only else "push"
    raise RuntimeError(f"LINE Flex {kind} rejected: HTTP {response.status_code} {response.text[:1000]}")
if validate_only:
    print(f"[LINE] Production Flex validation passed (no message sent): HTTP {response.status_code}", flush=True)
else:
    print(f"[LINE] Daily HQ Flex push accepted: HTTP {response.status_code}", flush=True)
