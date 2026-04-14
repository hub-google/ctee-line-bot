import os
import sys
import time
import requests
import re
import json
import io
import asyncio
import subprocess
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont, ImageFile

# Ensure PIL handles truncated images
ImageFile.LOAD_TRUNCATED_IMAGES = True

# --- Configuration ---
USERNAME = "liang44105"
PASSWORD = "basic123$"
LINE_ACCESS_TOKEN = "C+KCvV5aWScvpd13sg05qhng8tBmQNeyqplxe1+d1v7mJA+Fscys3wUS2JFlzz0QP4FM4I4h58xY9IfbcRc4jwL+7kWx2l/UHeQ2RXtDD5KZRiJFLW8L77Y4d0dpwzNALf7gQgpMYEv/R7L27QCcAQdB04t89/1O/w1cDnyilFU="
LINE_USER_ID = "U260c34dbdb253172fc1aca678b4b2ba7"

KEYWORDS = ["凱基", "保險", "壽險", "金控",
    "國泰", "富邦", "南山", "新光", "中信",
    "台新", "元大", "開發金", "玉山", "兆豐", "永豐",
    "台灣人壽", "三商美邦", "全球人壽", "遠雄人壽",
    "宏泰人壽", "保誠", "安聯", "法巴", "友邦", "產險", "中國人壽"]

BASE_URL = "https://readers.ctee.com.tw/cm"
TARGET_PAPER = "工商時報"
DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
if "桌面" in os.listdir(os.path.expanduser("~")):
    DESKTOP = os.path.join(os.path.expanduser("~"), "桌面")

# --- Utilities ---

def add_banner(img_data, title_kw):
    try:
        img = Image.open(io.BytesIO(img_data)).convert("RGB")
        banner_h = 80
        new_img = Image.new("RGB", (img.width, img.height + banner_h), "white")
        new_img.paste(img, (0, banner_h))
        draw = ImageDraw.Draw(new_img)
        font_paths = ["msjh.ttc", "simhei.ttf", "arial.ttf", "C:\\Windows\\Fonts\\msjh.ttc"]
        font = None
        for path in font_paths:
            try:
                font = ImageFont.truetype(path, 40)
                break
            except: continue
        if not font: font = ImageFont.load_default()
        draw.text((30, 15), f"關鍵字: {title_kw}", fill="black", font=font)
        buf = io.BytesIO()
        new_img.save(buf, format="JPEG", quality=95)
        return buf.getvalue()
    except: return img_data

def upload_cdn(data):
    try:
        r = requests.post("https://uguu.se/upload.php", files={"files[]": ("img.jpg", data, "image/jpeg")}, timeout=15)
        if r.status_code == 200: return r.json()["files"][0]["url"]
    except: pass
    return None

def send_flex_push(img_urls):
    if not img_urls: return
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    title_date = datetime.now().strftime("%Y/%m/%d")
    contents = [{"type": "text", "text": f"📸 {title_date} ({len(img_urls)}則)", "weight": "bold", "size": "lg"}]
    for i in range(0, len(img_urls), 2):
        row = {"type": "box", "layout": "horizontal", "spacing": "sm", "margin": "md", 
               "contents": [{"type": "image", "url": img_urls[i], "size": "full", "aspectRatio": "1:1", "action": {"type": "uri", "uri": img_urls[i]}}]}
        if i+1 < len(img_urls):
            row["contents"].append({"type": "image", "url": img_urls[i+1], "size": "full", "aspectRatio": "1:1", "action": {"type": "uri", "uri": img_urls[i+1]}})
        else: row["contents"].append({"type": "filler"})
        contents.append(row)
    payload = {"to": LINE_USER_ID, "messages": [{"type": "flex", "altText": "工商時報摘要", 
               "contents": {"type": "bubble", "size": "mega", "body": {"type": "box", "layout": "vertical", "contents": contents}}}]}
    r = requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload)
    print(f"[LINE通知] 狀態碼: {r.status_code}")

# --- Core Worker (Optimized Async Turbo) ---

async def turbo_capture(aid, hit_info, context, folder, semaphore, result_list):
    async with semaphore:
        page = await context.new_page()
        try:
            # article check
            await page.goto(hit_info['url'], wait_until="domcontentloaded", timeout=10000)
            
            # Click directly
            await page.evaluate(f'document.getElementById("{aid}").click()')
            
            img_src = None
            # Polling for high-quality image SRC
            for _ in range(20):
                img_src = await page.evaluate('() => { const i = document.querySelector(".fancybox-image"); return i ? i.src : null; }')
                if img_src and "data:image" not in img_src: break
                await asyncio.sleep(0.3)
                
            if img_src:
                # Adding Referer to ensure server doesn't block direct image fetch
                resp = requests.get(img_src, timeout=12, headers={"Referer": hit_info['url']})
                if resp.status_code == 200:
                    final_data = add_banner(resp.content, hit_info['kw'])
                    local_path = os.path.join(folder, f"{aid}_{hit_info['kw'].replace(',','_')}.jpg")
                    with open(local_path, "wb") as f: f.write(final_data)
                    cdn_url = upload_cdn(final_data)
                    if cdn_url: result_list.append(cdn_url)
                    print(f"  √ 下載成功: {aid}")
            else:
                # If image not found, fail fast. Do NOT try to log in again here.
                pass
        except: pass
        finally:
            await page.close()

async def run_worker():
    from playwright.async_api import async_playwright
    print("\n--- 啟動 Turbo 工作行程 (優化版) ---")
    start_time = time.time()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Use a context that we log in ONCE
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await context.new_page()
        
        # 1. NEW LOGIN LOGIC: Use Member domain
        print("[1/3] 正在登入工商會員系統...")
        login_url = "https://member.ctee.com.tw/Account/Login?ReturnUrl=https://readers.ctee.com.tw"
        await page.goto(login_url)
        if await page.query_selector("input#UserName"):
            await page.fill("input#UserName", USERNAME)
            await page.fill("input#Password", PASSWORD)
            await page.click("input[type='submit']")
            # Wait until redirected back to the readers domain
            await page.wait_for_url("https://readers.ctee.com.tw/**", timeout=20000)
            print("登入成功。")
        
        # 2. Parallel Scanning
        print("[2/3] 正在併行掃描全報 30+ 版面...")
        await page.goto(BASE_URL)
        links = set(re.findall(r'/cm/\d+/[a-z0-9]+', await page.content()))
        section_urls = [f"https://readers.ctee.com.tw{l}" for l in links if any(k in l for k in ["aa", "ab", "ac", "asa"])]
        
        unique_hits = {}
        cookies = {c['name']: c['value'] for c in await context.cookies()}
        session = requests.Session()
        session.cookies.update(cookies)
        
        def scan_job(url):
            try:
                r = session.get(url, timeout=10)
                items = re.findall(r'id=["\'](\d+)["\'].*?data-fulltitle=["\']([^"\']*)["\']', r.text, re.DOTALL | re.IGNORECASE)
                for aid, fulltitle in items:
                    matching = [k for k in KEYWORDS if k in fulltitle]
                    if matching:
                        unique_hits[aid] = {"kw": ",".join(sorted(matching)), "url": url}
            except: pass

        with ThreadPoolExecutor(max_workers=30) as scanner:
            list(scanner.map(scan_job, section_urls))

        # 3. Parallel Capture
        if not unique_hits:
            print("今日無符合關鍵字內容。")
            await browser.close()
            return

        print(f"[3/3] 發現 {len(unique_hits)} 則文章。啟動 15 分頁極速抓取...")
        folder = os.path.join(DESKTOP, f"{TARGET_PAPER}_{datetime.now().strftime('%Y%m%d')}")
        if not os.path.exists(folder): os.makedirs(folder)
        
        captured_urls = []
        semaphore = asyncio.Semaphore(15) # Increase slightly for speed
        tasks = [turbo_capture(aid, hit, context, folder, semaphore, captured_urls) for aid, hit in unique_hits.items()]
        await asyncio.gather(*tasks)
        
        await browser.close()
        
        print(f"\n全數處理完成！發送 LINE 通知中...")
        send_flex_push(captured_urls)
        print(f"總耗時: {round(time.time() - start_time, 2)}s")

# --- Launcher ---

def main():
    if "--worker-mode" in sys.argv:
        asyncio.run(run_worker())
    else:
        print("\n--- 工商時報 (Turbo-Fix 高速版) ---")
        python_exe = sys.executable
        if "spyder" in python_exe.lower() or "pythonw" in python_exe.lower():
            possible = os.path.join(os.path.dirname(python_exe), "python.exe")
            if os.path.exists(possible): python_exe = possible

        process = subprocess.Popen(
            [python_exe, sys.argv[0], "--worker-mode"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace"
        )
        
        for line in process.stdout:
            try:
                sys.stdout.write(f"    {line}")
                sys.stdout.flush()
            except: pass
        process.wait()

if __name__ == "__main__":
    main()