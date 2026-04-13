import os
import sys
import time
import requests
import re
import subprocess
import io
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw, ImageFont, ImageFile

# 讓 PIL 處理流式內容
ImageFile.LOAD_TRUNCATED_IMAGES = True

# --- 秘密資料區 (僅由 GitHub Actions 從 Secrets 注入) ---
USERNAME = os.getenv("CTEE_USER")
PASSWORD = os.getenv("CTEE_PASS")
LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")

KEYWORDS = ["凱基", "保險", "壽險", "金控", 
    "國泰", "富邦", "南山", "新光", "中信", 
    "台新", "元大", "開發金", "玉山", "兆豐", "永豐", 
    "台灣人壽", "三商美邦", "全球人壽", "遠雄人壽", 
    "宏泰人壽", "保誠", "安聯", "法巴", "友邦","保險","壽險","產險","中國人壽"]
BASE_URL = "https://readers.ctee.com.tw/cm"
TARGET_PAPER = "工商時報"
GITHUB_ASSETS_URL = f"https://raw.githubusercontent.com/hub-google/ctee-line-bot/assets"

# 掃描用 (requests)
scan_executor = ThreadPoolExecutor(max_workers=30)
# 下載用 (Playwright)
capture_executor = ThreadPoolExecutor(max_workers=5)

def get_temp_path():
    path = os.path.join(os.getcwd(), "temp_images")
    if not os.path.exists(path): os.makedirs(path)
    return path

def add_banner_to_raw_image(img_data, keywords_str):
    try:
        img = Image.open(io.BytesIO(img_data)).convert("RGB")
        banner_h = 80
        new_img = Image.new("RGB", (img.width, img.height + banner_h), "white")
        new_img.paste(img, (0, banner_h))
        draw = ImageDraw.Draw(new_img)
        font = ImageFont.load_default()
        draw.text((30, 20), f"關鍵字: {keywords_str}", fill="black", font=font)
        out_buf = io.BytesIO()
        new_img.save(out_buf, format="JPEG", quality=95)
        return out_buf.getvalue()
    except: return img_data

def upload_to_github_assets(folder):
    print("[Cloud] 正在執行資產同步至 GitHub Assets 分支...")
    try:
        subprocess.run(["git", "config", "user.name", "GitHub Actions"], capture_output=True)
        subprocess.run(["git", "config", "user.email", "actions@github.com"], capture_output=True)
        subprocess.run(["git", "add", f"{folder}/"], capture_output=True)
        subprocess.run(["git", "commit", "-m", "update cloud_assets"], capture_output=True)
        subprocess.run(["git", "push", "origin", "master:assets", "--force"], capture_output=True)
        return True
    except: return False

def send_flex_push(img_filenames):
    if not LINE_ACCESS_TOKEN or not img_filenames: return
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    body_contents = [{"type": "text", "text": datetime.now().strftime("%Y/%m/%d (Cloud Turbo)"), "weight": "bold", "size": "lg"}]
    img_urls = [f"{GITHUB_ASSETS_URL}/temp_images/{f}?t={int(time.time())}" for f in img_filenames]
    for i in range(0, len(img_urls), 2):
        row = {"type": "box", "layout": "horizontal", "spacing": "sm", "margin": "md", "contents": [{"type": "image", "url": img_urls[i], "size": "full", "aspectRatio": "1:1", "action": {"type": "uri", "uri": img_urls[i]}}]}
        if i + 1 < len(img_urls):
            row["contents"].append({"type": "image", "url": img_urls[i+1], "size": "full", "aspectRatio": "1:1", "action": {"type": "uri", "uri": img_urls[i+1]}})
        else: row["contents"].append({"type": "filler"})
        body_contents.append(row)
    payload = {"to": LINE_USER_ID, "messages": [{"type": "flex", "altText": "📸 工商雲端快訊", "contents": {"type": "bubble", "size": "mega", "body": {"type": "box", "layout": "vertical", "contents": body_contents}}}]}
    requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload)

def parallel_download_worker(aid, hit, temp_folder, session):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(hit['url'], wait_until="domcontentloaded", timeout=15000)
            page.evaluate(f'document.getElementById("{aid}").click()')
            
            img_src = None
            for _ in range(15):
                img_src = page.evaluate('() => { const img = document.querySelector(".fancybox-image"); return img ? img.src : null; }')
                if img_src and "data:image" not in img_src: break
                time.sleep(0.3)
            
            if not img_src or "限登入會員使用" in page.content():
                login_link = page.query_selector(".fancybox-container a:has-text('會員登入')")
                if login_link:
                    login_link.click()
                    page.fill("input#UserName", USERNAME); page.fill("input#Password", PASSWORD); page.click("input[type='submit']")
                    page.wait_for_load_state("networkidle")
                    page.goto(hit['url'], wait_until="domcontentloaded"); page.evaluate(f'document.getElementById("{aid}").click()')
                    time.sleep(1)
                    img_src = page.evaluate('() => document.querySelector(".fancybox-image") ? document.querySelector(".fancybox-image").src : null')

            if img_src:
                resp = session.get(img_src, timeout=15)
                if resp.status_code == 200:
                    final_data = add_banner_to_raw_image(resp.content, hit['kw'])
                    filename = f"{aid}_{hit['kw']}.jpg"
                    local_path = os.path.join(temp_folder, filename)
                    with open(local_path, "wb") as f: f.write(final_data)
                    browser.close()
                    return filename
            browser.close()
    except: pass
    return None

def main():
    start_time = time.time()
    temp_folder = get_temp_path()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://readers.ctee.com.tw/Reader/Login")
        if page.query_selector("input#UserName"):
            page.fill("input#UserName", USERNAME); page.fill("input#Password", PASSWORD); page.click("input[type='submit']")
            page.wait_for_load_state("networkidle")

        page.goto(BASE_URL)
        links = sorted(list(set(re.findall(r'/cm/\d+/[a-z0-9]+', page.content()))))
        all_section_urls = [f"https://readers.ctee.com.tw{l}" for l in links if any(k in l for k in ["aa", "ab", "ac", "asa"])]
        
        session = requests.Session()
        for ck in context.cookies(): session.cookies.set(ck['name'], ck['value'], domain=ck['domain'])
        session.headers.update({"User-Agent": "Mozilla/5.0"})
        browser.close()

    def scan_url(url):
        try:
            r = session.get(url, timeout=10)
            matches = re.findall(r'id=[\"\'](\d+)[\"\'].*?data-fulltitle=[\"\'](.*?)[\"\']', r.text, re.DOTALL | re.IGNORECASE)
            return [{"aid": aid, "kw": ",".join(sorted([kw for kw in KEYWORDS if kw in ft])), "url": url} for aid, ft in matches if any(k in ft for k in KEYWORDS)]
        except: return []

    print("[Cloud] 正在檢索全報內容...")
    scan_results = list(scan_executor.map(scan_url, all_section_urls))
    unique_hits = {h['aid']: h for r in scan_results for h in r}
    print(f"[Cloud] 發現 {len(unique_hits)} 則文章。啟動 5 核心並行下載...")

    captured_filenames = []
    futures = [capture_executor.submit(parallel_download_worker, aid, hit, temp_folder, session) for aid, hit in unique_hits.items()]
    for f in as_completed(futures):
        res = f.result()
        if res: captured_filenames.append(res)

    if captured_filenames:
        if upload_to_github_assets("temp_images"):
            send_flex_push(captured_filenames)
    
    print(f"[Cloud] 任務結束！總耗時: {round(time.time() - start_time, 2)}s")

if __name__ == "__main__":
    if not USERNAME or not PASSWORD:
        sys.exit(1)
    main()
    scan_executor.shutdown(wait=False)
    capture_executor.shutdown(wait=False)
