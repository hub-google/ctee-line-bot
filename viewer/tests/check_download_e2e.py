#!/usr/bin/env python3
"""Live published CTEE gallery browser smoke test. Does not send any LINE message."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import quote, urlencode, urljoin
import requests
from playwright.sync_api import sync_playwright

SITE = os.environ.get("CTEE_SITE_URL", "https://hub-google.github.io/ctee-line-bot/").rstrip("/") + "/"
OUT = Path("/tmp/ctee-download-check")
OUT.mkdir(parents=True, exist_ok=True)
session = requests.Session()

def live(path, **kwargs):
    r = session.get(urljoin(SITE,path), timeout=40, **kwargs)
    r.raise_for_status()
    return r

reader = live("?qa=download-20261119").text
landing = live("download.html?qa=download-20261119").text
data = live("data.json?qa=download-20261119").json()
assert "ctee-external-browser-download-v2" in reader, "Live reader has old download code"
assert "ctee-external-download-v1" in landing, "Live download page is missing"
assert 'downloadDialog' not in reader, "Old modal is still present"
assert 'sendPhotoToChat' not in reader, "Old LINE photo selection is still present"
assert data.get("images") and data.get("zip"), "Published manifest incomplete"
day, images = data["date"], data["images"]
assert day == "2026-11-19", f"Unexpected published date {day}"
assert len(images) == 39, f"Expected 39 images; saw {len(images)}"
jpg = images[0]
zip_path = data["zip"]
for path in (jpg["src"], zip_path):
    result = live(path, headers={"Range": "bytes=0-8"})
    if path.endswith(".zip"):
        assert result.content.startswith(b"PK"), "ZIP HTTP response is not ZIP"
    else:
        assert result.content.startswith(b"\xff\xd8\xff"), "JPG HTTP response is not JPG"
    print("LIVE FILE", path, "HTTP", result.status_code, "bytes_received",len(result.content),flush=True)
print("PASS live page, manifest, JPG and ZIP file contents", flush=True)

browser_base = SITE.rstrip("/")
fake_liff = """
window.__openedExternal=[];
window.liff={
  init:()=>Promise.resolve(),
  isInClient:()=>true,
  isLoggedIn:()=>true,
  isApiAvailable:()=>false,
  openWindow:(o)=>{window.__openedExternal.push(o)}
};
"""
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    ctx = browser.new_context(
      viewport={"width":390,"height":844},
      device_scale_factor=2,
      is_mobile=True,
      has_touch=True,
      user_agent="Mozilla/5.0 (Linux; Android 15; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0 Mobile Safari/537.36 Line/15.1.0",
    )
    ctx.route("https://static.line-scdn.net/liff/edge/2/sdk.js",lambda r:r.fulfill(status=200, content_type="application/javascript", body=fake_liff))
    page = ctx.new_page()
    page.goto(SITE+"?date="+day,wait_until="domcontentloaded",timeout=60000)
    page.locator("#zipBtn:not([disabled])").wait_for(timeout=40000)
    page.screenshot(path=str(OUT/"mobile-reader.png"),full_page=True)
    page.locator("#zipBtn").click()
    opened=page.evaluate("window.__openedExternal")
    assert len(opened)==1 and opened[0].get("external") is True, f"ZIP tap failed external browser: {opened}"
    assert "download.html?file=" in opened[0]["url"] and ".zip" in opened[0]["url"], f"Wrong ZIP browser URL: {opened}"
    print("PASS LINE mobile ZIP tap => direct external:true",opened[0]["url"],flush=True)

    page.locator("#gallery .download").first.click()
    opened=page.evaluate("window.__openedExternal")
    assert len(opened)==2 and opened[1].get("external") is True, f"JPG tap failed external browser: {opened}"
    assert "download.html?file=" in opened[1]["url"] and ".jpg" in opened[1]["url"], f"Wrong JPG browser URL: {opened}"
    print("PASS LINE mobile JPG tap => direct external:true",opened[1]["url"],flush=True)
    assert page.locator("#downloadDialog").count()==0, "Old option modal remains"
    ctx.close()

    # Test actual browser-initiated downloads, not merely the presence of links or HTTP 200.
    desktop = browser.new_context(accept_downloads=True,viewport={"width":1280,"height":820})
    for kind,path in [("jpg",jpg["src"]),("zip",zip_path)]:
        tab=desktop.new_page()
        downloads=[]
        tab.on("download",lambda d:downloads.append(d))
        target="/ctee-line-bot/"+path
        url=urljoin(SITE,"download.html")+"?"+urlencode({"file":target})
        try:
            tab.goto(url,wait_until="domcontentloaded",timeout=60000)
        except Exception as exc:
            if "ERR_ABORTED" not in str(exc): raise
        tab.locator("#downloadBtn:not([disabled])").wait_for(timeout=60000)
        tab.wait_for_timeout(3000)
        if not downloads:
            with tab.expect_download(timeout=30000) as info:
                tab.locator("#downloadBtn").click()
            downloads.append(info.value)
        download=downloads[0]
        suggested=download.suggested_filename
        expected=path.split("/")[-1]
        assert suggested==expected, f"{kind} filename mismatch: {suggested!r} vs {expected!r}"
        dst=OUT/("real-download-"+kind+("." + kind))
        download.save_as(str(dst))
        with open(dst,"rb") as f:
            signature=f.read(4)
        assert signature.startswith(b"PK" if kind=="zip" else b"\xff\xd8\xff"), f"{kind} downloaded content invalid"
        print("PASS browser download",kind,"suggested_filename",suggested,"bytes",dst.stat().st_size,flush=True)
        tab.screenshot(path=str(OUT/("browser-"+kind+".png")),full_page=True)
        tab.close()
    desktop.close()
    browser.close()
print("PASS all published page and browser download checks",flush=True)
