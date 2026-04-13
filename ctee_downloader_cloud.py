import os
import sys
import time
import requests
import re
import io
import queue
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw, ImageFont, ImageFile

# 讓 PIL 處理流式內容
ImageFile.LOAD_TRUNCATED_IMAGES = True

# --- 秘密資料區 ---
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

scan_executor = ThreadPoolExecutor(max_workers=30)

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

def upload_to_cdn(image_data):
    """跟本地版完全一樣的圖床上傳邏輯"""
    try:
        r = requests.post("https://uguu.se/upload.php", files={"files[]": ("image.jpg", image_data, "image/jpeg")}, timeout=15)
        if r.status_code == 200: return r.json()["files"][0]["url"]
    except: pass
    return None

def send_flex_push(img_urls):
    if not LINE_ACCESS_TOKEN or not img_urls: return
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    
    # 分批發送確保穩定性
    BATCH_SIZE = 10
    total_images = len(img_urls)
    
    for start_idx in range(0, total_images, BATCH_SIZE):
        batch = img_urls[start_idx : start_idx + BATCH_SIZE]
        batch_num = (start_idx // BATCH_SIZE) + 1
        total_batches = (total_images + BATCH_SIZE - 1) // BATCH_SIZE
        
        body_contents = [{"type": "text", "text": f"{datetime.now().strftime('%Y/%m/%d')} (Cloud Turbo v2) - {batch_num}/{total_batches}", "weight": "bold", "size": "md"}]
        
        for i in range(0, len(batch), 2):
            row = {"type": "box", "layout": "horizontal", "spacing": "sm", "margin": "md", "contents": [{"type": "image", "url": batch[i], "size": "full", "aspectRatio": "1:1", "action": {"type": "uri", "uri": batch[i]}}]}
            if i + 1 < len(batch):
                row["contents"].append({"type": "image", "url": batch[i+1], "size": "full", "aspectRatio": "1:1", "action": {"type": "uri", "uri": batch[i+1]}})
            else: 
                row["contents"].append({"type": "filler"})
            body_contents.append(row)
            
        payload = {"to": LINE_USER_ID, "messages": [{"type": "flex", "altText": f"📸 工商快報 ({batch_num}/{total_batches})", "contents": {"type": "bubble", "size": "mega", "body": {"type": "box", "layout": "vertical", "contents": body_contents}}}]}
        requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload)
        time.sleep(1)

def persistent_worker(task_queue, shared_results, session):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            while not task_queue.empty():
                try:
                    aid, hit = task_queue.get_nowait()
                except queue.Empty: break
                
                try:
                    page.goto(hit['url'], wait_until="domcontentloaded", timeout=15000)
                    page.evaluate(f'document.getElementById("{aid}").click()')
                    img_src = None
                    for _ in range(15):
                        img_src = page.evaluate('() => document.querySelector(".fancybox-image") ? document.querySelector(".fancybox-image").src : null')
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
                            u_url = upload_to_cdn(final_data)
                            if u_url: shared_results.append(u_url)
                    page.keyboard.press("Escape")
                except: pass
                finally: task_queue.task_done()
            browser.close()
    except: pass

def main():
    if not USERNAME or not PASSWORD:
        sys.exit(1)
    
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

    scan_results = list(scan_executor.map(scan_url, all_section_urls))
    unique_hits = {h['aid']: h for r in scan_results for h in r}
    print(f"[Cloud] 發現 {len(unique_hits)} 則文章。")

    task_queue = queue.Queue()
    for item in unique_hits.items(): task_queue.put(item)
    shared_results = []
    threads = []
    for _ in range(5):
        t = threading.Thread(target=persistent_worker, args=(task_queue, shared_results, session))
        t.start()
        threads.append(t)
    for t in threads: t.join()

    if shared_results:
        send_flex_push(shared_results)
    print(f"[Cloud] 任務結束。")

if __name__ == "__main__":
    main()
    scan_executor.shutdown(wait=False)
