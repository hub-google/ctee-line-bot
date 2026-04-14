import os
import sys
import time
import requests
import re
import json
import io
import asyncio
import subprocess
import urllib.parse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont, ImageFile

# Ensure PIL handles truncated images
ImageFile.LOAD_TRUNCATED_IMAGES = True

# --- Configuration (Secrets from Environment) ---
USERNAME = os.getenv("CTEE_USER", "liang44105")
PASSWORD = os.getenv("CTEE_PASS", "basic123$")
LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN", "C+KCvV5aWScvpd13sg05qhng8tBmQNeyqplxe1+d1v7mJA+Fscys3wUS2JFlzz0QP4FM4I4h58xY9IfbcRc4jwL+7kWx2l/UHeQ2RXtDD5KZRiJFLW8L77Y4d0dpwzNALf7gQgpMYEv/R7L27QCcAQdB04t89/1O/w1cDnyilFU=")
LINE_USER_ID = os.getenv("LINE_USER_ID", "U260c34dbdb253172fc1aca678b4b2ba7")

KEYWORDS = ["凱基", "保險", "壽險", "金控",
    "國泰", "富邦", "南山", "新光", "中信",
    "台新", "元大", "開發金", "玉山", "兆豐", "永豐",
    "台灣人壽", "三商美邦", "全球人壽", "遠雄人壽",
    "宏泰人壽", "保誠", "安聯", "法巴", "友邦", "產險", "中國人壽"]

BASE_URL = "https://readers.ctee.com.tw/cm"
TARGET_PAPER = "工商時報"
GITHUB_ASSETS_URL = "https://raw.githubusercontent.com/hub-google/ctee-line-bot/assets"

# --- Utilities ---

def get_temp_path():
    path = os.path.join(os.getcwd(), "temp_images")
    if not os.path.exists(path): os.makedirs(path)
    return path

def add_banner(img_data, title_kw):
    try:
        img = Image.open(io.BytesIO(img_data)).convert("RGB")
        banner_h = 80
        new_img = Image.new("RGB", (img.width, img.height + banner_h), "white")
        new_img.paste(img, (0, banner_h))
        draw = ImageDraw.Draw(new_img)
        font = ImageFont.load_default()
        draw.text((30, 20), f"Keyword: {title_kw}", fill="black", font=font)
        buf = io.BytesIO()
        new_img.save(buf, format="JPEG", quality=95)
        return buf.getvalue()
    except: return img_data

def upload_to_github_assets(folder):
    """Sync images to the assets branch for hosting."""
    try:
        subprocess.run(["git", "config", "user.name", "GitHub Actions"], capture_output=True)
        subprocess.run(["git", "config", "user.email", "actions@github.com"], capture_output=True)
        subprocess.run(["git", "add", f"{folder}/"], capture_output=True)
        subprocess.run(["git", "commit", "-m", f"update cloud_assets {datetime.now().strftime('%Y%m%d')}"], capture_output=True)
        subprocess.run(["git", "push", "origin", "master:assets", "--force"], capture_output=True)
        return True
    except: return False

def send_flex_push(img_filenames):
    """Send a single LINE Flex Message with all captured images (Parity with Local Version)."""
    if not img_filenames: return
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    today_date = datetime.now().strftime("%Y/%m/%d")
    
    alt_text = f"📸 {today_date} ({len(img_filenames)}則)"
    contents = [{"type": "text", "text": alt_text, "weight": "bold", "size": "lg"}]
    
    # Build image grid (No batching, single message)
    for i in range(0, len(img_filenames), 2):
        url1 = f"{GITHUB_ASSETS_URL}/temp_images/{urllib.parse.quote(img_filenames[i])}?t={int(time.time())}"
        row = {"type": "box", "layout": "horizontal", "spacing": "sm", "margin": "md", 
               "contents": [{"type": "image", "url": url1, "size": "full", "aspectRatio": "1:1", "action": {"type": "uri", "uri": url1}}]}
        
        if i+1 < len(img_filenames):
            url2 = f"{GITHUB_ASSETS_URL}/temp_images/{urllib.parse.quote(img_filenames[i+1])}?t={int(time.time())}"
            row["contents"].append({"type": "image", "url": url2, "size": "full", "aspectRatio": "1:1", "action": {"type": "uri", "uri": url2}})
        else:
            row["contents"].append({"type": "filler"})
        contents.append(row)
        
    payload = {"to": LINE_USER_ID, "messages": [{"type": "flex", "altText": "工商時報快訊", 
               "contents": {"type": "bubble", "size": "mega", "body": {"type": "box", "layout": "vertical", "contents": contents}}}]}
    r = requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload)
    print(f"[LINE通知] 狀態碼: {r.status_code}")

# --- Core Scraper Engine ---

async def turbo_capture(aid, hit_info, context, folder, semaphore, result_list):
    async with semaphore:
        page = await context.new_page()
        try:
            await page.goto(hit_info['url'], wait_until="domcontentloaded", timeout=12000)
            await page.evaluate(f'document.getElementById("{aid}").click()')
            img_src = None
            for _ in range(20):
                img_src = await page.evaluate('() => document.querySelector(".fancybox-image")?.src')
                if img_src and "data:image" not in img_src: break
                await asyncio.sleep(0.3)
            if img_src:
                resp = requests.get(img_src, timeout=12, headers={"Referer": hit_info['url']})
                if resp.status_code == 200:
                    final_data = add_banner(resp.content, hit_info['kw'])
                    filename = f"{aid}_{hit_info['kw'].replace(',','_')}.jpg"
                    with open(os.path.join(folder, filename), "wb") as f: f.write(final_data)
                    result_list.append(filename)
                    print(f"  √ Captured: {aid}")
        except: pass
        finally: await page.close()

async def run_cloud_turbo():
    from playwright.async_api import async_playwright
    print("\n--- Starting Cloud Turbo Engine (Unity Edition) ---")
    start_total = time.time()
    temp_folder = get_temp_path()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await context.new_page()
        
        # 1. Login
        print("[1/4] Authenticating with Member System...")
        login_url = "https://member.ctee.com.tw/Account/Login?ReturnUrl=https://readers.ctee.com.tw"
        await page.goto(login_url)
        if await page.query_selector("input#UserName"):
            await page.fill("input#UserName", USERNAME)
            await page.fill("input#Password", PASSWORD)
            await page.click("input[type='submit']")
            await page.wait_for_url("https://readers.ctee.com.tw/**", timeout=20000)
        
        # 2. Scanning
        print("[2/4] Scanning Sections...")
        await page.goto(BASE_URL)
        links = set(re.findall(r'/cm/\d+/[a-z0-9]+', await page.content()))
        section_urls = [f"https://readers.ctee.com.tw{l}" for l in links if any(k in l for k in ["aa", "ab", "ac", "asa"])]
        unique_hits = {}
        session = requests.Session()
        for ck in await context.cookies(): session.cookies.set(ck['name'], ck['value'], domain=ck['domain'])
        
        def scan_job(url):
            try:
                r = session.get(url, timeout=10)
                items = re.findall(r'id=["\'](\d+)["\'].*?data-fulltitle=["\']([^"\']*)["\']', r.text, re.DOTALL | re.IGNORECASE)
                for aid, ft in items:
                    matches = [k for k in KEYWORDS if k in ft]
                    if matches: unique_hits[aid] = {"kw": ",".join(sorted(matches)), "url": url}
            except: pass

        with ThreadPoolExecutor(max_workers=30) as scanner:
            list(scanner.map(scan_job, section_urls))

        # 3. Capture
        if not unique_hits:
            print("No matching keywords found today.")
            await browser.close()
            return

        print(f"[3/4] Found {len(unique_hits)} articles. Extracting...")
        captured_filenames = []
        semaphore = asyncio.Semaphore(12)
        tasks = [turbo_capture(aid, hit, context, temp_folder, semaphore, captured_filenames) for aid, hit in unique_hits.items()]
        await asyncio.gather(*tasks)
        await browser.close()
        
        # 4. Storage & Notification
        if captured_filenames:
            # Sync to GitHub
            print(f"[4/4] Syncing {len(captured_filenames)} images to GitHub Assets...")
            upload_to_github_assets("temp_images")
            
            # Send single notification
            print("Sending LINE Flex Notification...")
            send_flex_push(captured_filenames)
            print(f"Cloud Task Finished! Total Time: {round(time.time() - start_total, 2)}s")

if __name__ == "__main__":
    asyncio.run(run_cloud_turbo())
