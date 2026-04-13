import os
import sys
import time
import requests
import re
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont, ImageFile
import io

# 讓 PIL 處理損壞或截斷的圖片
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

def get_desktop_path():
    return r"C:\Users\cyt18\桌面"

def add_banner_to_raw_image(img_data, keywords_str):
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
    except: return img_data

def upload_to_cdn(image_data):
    try:
        r = requests.post("https://uguu.se/upload.php", files={"files[]": ("image.jpg", image_data, "image/jpeg")}, timeout=15)
        if r.status_code == 200: return r.json()["files"][0]["url"]
    except: pass
    return None

def send_flex_push(img_urls):
    if not img_urls: return
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    today_date = datetime.now().strftime("%Y/%m/%d")
    final_title = f"{today_date} ({len(img_urls)}則新聞)"
    
    body_contents = [{"type": "text", "text": final_title, "weight": "bold", "size": "lg"}]
    for i in range(0, len(img_urls), 2):
        row = {"type": "box", "layout": "horizontal", "spacing": "sm", "margin": "md", "contents": [{"type": "image", "url": img_urls[i], "size": "full", "aspectRatio": "1:1", "action": {"type": "uri", "uri": img_urls[i]}}]}
        if i + 1 < len(img_urls):
            row["contents"].append({"type": "image", "url": img_urls[i+1], "size": "full", "aspectRatio": "1:1", "action": {"type": "uri", "uri": img_urls[i+1]}})
        else: row["contents"].append({"type": "filler"})
        body_contents.append(row)
    payload = {"to": LINE_USER_ID, "messages": [{"type": "flex", "altText": final_title, "contents": {"type": "bubble", "size": "mega", "body": {"type": "box", "layout": "vertical", "contents": body_contents}}}]}
    requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload)

def get_logged_session():
    """純 Requests 模擬登入獲取核心 Session"""
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    
    # 1. 取得登入頁 CSRF Token (如果有)
    res = session.get("https://readers.ctee.com.tw/Reader/Login")
    token_match = re.search(r'name="__RequestVerificationToken".*?value="(.*?)"', res.text)
    
    # 2. 模擬 POST 登入
    payload = {
        "UserName": USERNAME,
        "Password": PASSWORD,
        "RememberMe": "true"
    }
    if token_match:
        payload["__RequestVerificationToken"] = token_match.group(1)
        
    session.post("https://readers.ctee.com.tw/Reader/Login", data=payload)
    return session

def download_task(session, hit, target_folder, shared_results):
    """單個圖片下載線程：純 Requests 正則抓取"""
    try:
        aid = hit['aid']
        # 訪問文章頁面直接提取圖源
        res = session.get(hit['url'], timeout=15)
        # CTEE 的圖源規律：隱藏在 fancybox-image 或特定 API 中
        # 經分析，GetImage API 是最穩定的直接路徑
        paper_date = datetime.now().strftime("%Y%m%d")
        image_api_url = f"https://readers.ctee.com.tw/Reader/GetImage?id={aid}&paper={TARGET_PAPER}&date={paper_date}&type=1"
        
        img_res = session.get(image_api_url, timeout=20)
        if img_res.status_code == 200 and len(img_res.content) > 10000:
            final_data = add_banner_to_raw_image(img_res.content, hit['kw'])
            local_path = os.path.join(target_folder, f"{aid}_{hit['kw']}.jpg")
            with open(local_path, "wb") as f: f.write(final_data)
            
            u_url = upload_to_cdn(final_data)
            if u_url: shared_results.append(u_url)
    except: pass

def main_worker():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 啟動純線程引擎 (去 Playwright 化)...")
    session = get_logged_session()
    
    # 1. 掃描今日版面
    res = session.get(BASE_URL)
    links = sorted(list(set(re.findall(r'/cm/\d+/[a-z0-9]+', res.text))))
    all_section_urls = [f"https://readers.ctee.com.tw{l}" for l in links if any(k in l for k in ["aa", "ab", "ac", "asa"])]
    
    def scan_url(url):
        try:
            r = session.get(url, timeout=10)
            matches = re.findall(r'id=[\"\'](\d+)[\"\'].*?data-fulltitle=[\"\'](.*?)[\"\']', r.text, re.DOTALL | re.IGNORECASE)
            return [{"aid": aid, "kw": ",".join(sorted([kw for kw in KEYWORDS if kw in ft])), "url": f"https://readers.ctee.com.tw/cm/{datetime.now().strftime('%Y%m%d')}/{url.split('/')[-1]}/{aid}/"} for aid, ft in matches if any(k in ft for k in KEYWORDS)]
        except: return []

    with ThreadPoolExecutor(max_workers=30) as scan_pool:
        scan_results = list(scan_pool.map(scan_url, all_section_urls))
    
    unique_hits = {h['aid']: h for r in scan_results for h in r}
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 發現 {len(unique_hits)} 則新聞，啟動 50 線程併發下載...")

    # 2. 併發下載與處理
    today_str = datetime.now().strftime("%Y%m%d")
    target_folder = os.path.join(get_desktop_path(), f"{TARGET_PAPER}_{today_str}")
    if not os.path.exists(target_folder): os.makedirs(target_folder)
    
    shared_results = []
    with ThreadPoolExecutor(max_workers=50) as download_pool:
        for hit in unique_hits.values():
            download_pool.submit(download_task, session, hit, target_folder, shared_results)

    # 3. LINE 推播
    if shared_results:
        send_flex_push(shared_results)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 全速任務完成！")

if __name__ == "__main__":
    main_worker()