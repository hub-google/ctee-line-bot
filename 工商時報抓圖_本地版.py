import os
import sys
import time
import requests
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw, ImageFont, ImageFile
import io

# 讓 PIL 處理流式內容
ImageFile.LOAD_TRUNCATED_IMAGES = True

# --- 設定區 ---
USERNAME = "liang44105"
PASSWORD = "basic123$"
LINE_ACCESS_TOKEN = "C+KCvV5aWScvpd13sg05qhng8tBmQNeyqplxe1+d1v7mJA+Fscys3wUS2JFlzz0QP4FM4I4h58xY9IfbcRc4jwL+7kWx2l/UHeQ2RXtDD5KZRiJFLW8L77Y4d0dpwzNALf7gQgpMYEv/R7L27QCcAQdB04t89/1O/w1cDnyilFU="
LINE_USER_ID = "U260c34dbdb253172fc1aca678b4b2ba7"

KEYWORDS = ["凱基", "保險", "壽險", "金控", 
    "國泰", "富邦", "南山", "新光", "中信", 
    "台新", "元大", "開發金", "玉山", "兆豐", "永豐", 
    "台灣人壽", "三商美邦", "全球人壽", "遠雄人壽", 
    "宏泰人壽", "保誠", "安聯", "法巴", "友邦","保險","壽險","產險","中國人壽"]
BASE_URL = "https://readers.ctee.com.tw/cm"
TARGET_PAPER = "工商時報"

executor = ThreadPoolExecutor(max_workers=30)

def get_desktop_path():
    return r"C:\Users\cyt18\桌面"

def add_banner_to_raw_image(img_data, keywords_str):
    """將下載的原始二進位圖片加上關鍵字 Banner"""
    try:
        img = Image.open(io.BytesIO(img_data)).convert("RGB")
        banner_h = 80
        new_img = Image.new("RGB", (img.width, img.height + banner_h), "white")
        new_img.paste(img, (0, banner_h))
        draw = ImageDraw.Draw(new_img)
        try: font = ImageFont.truetype("msjh.ttc", 40)
        except: font = ImageFont.load_default()
        draw.text((30, 15), f"關鍵字: {keywords_str}", fill="black", font=font)
        
        out_buf = io.BytesIO()
        new_img.save(out_buf, format="JPEG", quality=95)
        return out_buf.getvalue()
    except Exception as e:
        print(f"    [!] Banner 添加失敗: {e}")
        return img_data

def upload_to_cdn(image_data):
    try:
        r = requests.post("https://uguu.se/upload.php", files={"files[]": ("image.jpg", image_data, "image/jpeg")}, timeout=15)
        if r.status_code == 200: return r.json()["files"][0]["url"]
    except: pass
    return None

def send_flex_push(img_urls):
    if not img_urls: return
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    body_contents = [{"type": "text", "text": datetime.now().strftime("%Y/%m/%d"), "weight": "bold", "size": "lg"}]
    for i in range(0, len(img_urls), 2):
        row = {"type": "box", "layout": "horizontal", "spacing": "sm", "margin": "md", "contents": [{"type": "image", "url": img_urls[i], "size": "full", "aspectRatio": "1:1", "action": {"type": "uri", "uri": img_urls[i]}}]}
        if i + 1 < len(img_urls):
            row["contents"].append({"type": "image", "url": img_urls[i+1], "size": "full", "aspectRatio": "1:1", "action": {"type": "uri", "uri": img_urls[i+1]}})
        else: row["contents"].append({"type": "filler"})
        body_contents.append(row)
    payload = {"to": LINE_USER_ID, "messages": [{"type": "flex", "altText": "📸 工商快訊", "contents": {"type": "bubble", "size": "mega", "body": {"type": "box", "layout": "vertical", "contents": body_contents}}}]}
    requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload)

def robust_download_capture(page, aid, hit, target_folder, shared_results, session):
    """強力下載模式 (改進版)：解決選擇器超時，直接獲取 src"""
    try:
        page.goto(hit['url'], wait_until="domcontentloaded", timeout=15000)
        page.evaluate(f'document.getElementById("{aid}").click()')
        
        # 穩定等待彈窗容器
        page.wait_for_selector(".fancybox-container.fancybox-is-open", timeout=8000)
        
        # 輪詢檢查 src，最多等 5 秒
        img_src = None
        for _ in range(25):
            img_src = page.evaluate('() => { const img = document.querySelector(".fancybox-image"); return img ? img.src : null; }')
            if img_src and "data:image" not in img_src: break # 排除 base64 佔位圖
            time.sleep(0.2)
        
        if not img_src:
            # 偵測是否被登入牆擋住
            is_blocked = page.evaluate('() => document.querySelector(".fancybox-container").innerText.includes("限登入會員使用")')
            if is_blocked:
                print(f"    [!] 偵測到登入遮罩，執行彈窗內授權修補...")
                login_link = page.query_selector(".fancybox-container a:has-text('會員登入')")
                if login_link:
                    login_link.click()
                    page.wait_for_selector("input#UserName", timeout=8000)
                    page.fill("input#UserName", USERNAME); page.fill("input#Password", PASSWORD); page.click("input[type='submit']")
                    page.wait_for_load_state("networkidle")
                    # 修復後再次嘗試
                    page.goto(hit['url'], wait_until="domcontentloaded")
                    page.evaluate(f'document.getElementById("{aid}").click()')
                    page.wait_for_selector(".fancybox-container.fancybox-is-open", timeout=8000)
                    time.sleep(1) # 給予渲染時間
                    img_src = page.evaluate('() => document.querySelector(".fancybox-image") ? document.querySelector(".fancybox-image").src : null')

        if img_src:
            print(f"    正在從網址下載高清原圖: {aid}")
            resp = session.get(img_src, timeout=15)
            if resp.status_code == 200:
                final_data = add_banner_to_raw_image(resp.content, hit['kw'])
                local_path = os.path.join(target_folder, f"{aid}_{hit['kw']}.jpg")
                with open(local_path, "wb") as f: f.write(final_data)
                print(f"    √ 下載成功: {aid}")
                u_url = upload_to_cdn(final_data)
                if u_url: shared_results.append(u_url)
                return True
        return False
    except Exception as e:
        print(f"    [!] 下載 {aid} 噴錯: {e}")
        return False

def main():
    print("--- 腳本啟動 (高清原圖下載定音版) ---")
    start_time = time.time()
    today_str = datetime.now().strftime("%Y%m%d")
    target_folder = os.path.join(get_desktop_path(), f"{TARGET_PAPER}_{today_str}")
    if not os.path.exists(target_folder): os.makedirs(target_folder)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 850}, device_scale_factor=2)
        page = context.new_page()

        # 初始登入
        page.goto("https://readers.ctee.com.tw/Reader/Login")
        if page.query_selector("input#UserName"):
            page.fill("input#UserName", USERNAME); page.fill("input#Password", PASSWORD); page.click("input[type='submit']")
            page.wait_for_load_state("networkidle")

        # 索引搜尋
        page.goto(BASE_URL)
        links = sorted(list(set(re.findall(r'/cm/\d+/[a-z0-9]+', page.content()))))
        all_section_urls = [f"https://readers.ctee.com.tw{l}" for l in links if any(k in l for k in ["aa", "ab", "ac", "asa"])]
        
        session = requests.Session()
        for ck in context.cookies(): session.cookies.set(ck['name'], ck['value'], domain=ck['domain'])
        session.headers.update({"User-Agent": "Mozilla/5.0"})
        
        def scan_url(url):
            try:
                r = session.get(url, timeout=10)
                matches = re.findall(r'id=[\"\'](\d+)[\"\'].*?data-fulltitle=[\"\'](.*?)[\"\']', r.text, re.DOTALL | re.IGNORECASE)
                return [{"aid": aid, "kw": ",".join(sorted([kw for kw in KEYWORDS if kw in ft])), "url": url} for aid, ft in matches if any(k in ft for k in KEYWORDS)]
            except: return []

        print(f"[1/2] 正在檢索 30 版面內容...")
        scan_results = list(executor.map(scan_url, all_section_urls))
        unique_hits = {h['aid']: h for r in scan_results for h in r}
        print(f"發現 {len(unique_hits)} 則文章。開始執行「高清原圖下載」...")

        shared_results = []
        for aid, hit in unique_hits.items():
            robust_download_capture(page, aid, hit, target_folder, shared_results, session)

        if shared_results: send_flex_push(shared_results)
        print(f"全任務結束！總耗時: {round(time.time() - start_time, 2)}s")
        browser.close()
    executor.shutdown(wait=False)

if __name__ == "__main__":
    main()