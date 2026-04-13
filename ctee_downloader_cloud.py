import os
import sys
import time
import requests
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont, ImageFile
import io

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

def add_banner_to_raw_image(img_data, keywords_str):
    try:
        img = Image.open(io.BytesIO(img_data)).convert("RGB")
        banner_h = 80
        new_img = Image.new("RGB", (img.width, img.height + banner_h), "white")
        new_img.paste(img, (0, banner_h))
        draw = ImageDraw.Draw(new_img)
        font = ImageFont.load_default()
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
    if not LINE_ACCESS_TOKEN or not img_urls: return
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
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    res = session.get("https://readers.ctee.com.tw/Reader/Login")
    token_match = re.search(r'name="__RequestVerificationToken".*?value="(.*?)"', res.text)
    payload = {"UserName": USERNAME, "Password": PASSWORD, "RememberMe": "true"}
    if token_match: payload["__RequestVerificationToken"] = token_match.group(1)
    session.post("https://readers.ctee.com.tw/Reader/Login", data=payload)
    return session

def download_task(session, hit, shared_results):
    try:
        aid = hit['aid']
        paper_date = datetime.now().strftime("%Y%m%d")
        image_api_url = f"https://readers.ctee.com.tw/Reader/GetImage?id={aid}&paper={TARGET_PAPER}&date={paper_date}&type=1"
        img_res = session.get(image_api_url, timeout=20)
        if img_res.status_code == 200 and len(img_res.content) > 10000:
            final_data = add_banner_to_raw_image(img_res.content, hit['kw'])
            u_url = upload_to_cdn(final_data)
            if u_url: shared_results.append(u_url)
    except: pass

def main():
    if not USERNAME or not PASSWORD: return
    session = get_logged_session()
    
    # 掃描
    res = session.get(BASE_URL)
    links = sorted(list(set(re.findall(r'/cm/\d+/[a-z0-9]+', res.text))))
    all_section_urls = [f"https://readers.ctee.com.tw{l}" for l in links if any(k in l for k in ["aa", "ab", "ac", "asa"])]
    
    def scan_url(url):
        try:
            r = session.get(url, timeout=10)
            matches = re.findall(r'id=[\"\'](\d+)[\"\'].*?data-fulltitle=[\"\'](.*?)[\"\']', r.text, re.DOTALL | re.IGNORECASE)
            return [{"aid": aid, "kw": ",".join(sorted([kw for kw in KEYWORDS if kw in ft])), "url": url} for aid, ft in matches if any(k in ft for k in KEYWORDS)]
        except: return []

    with ThreadPoolExecutor(max_workers=30) as scan_pool:
        scan_results = list(scan_pool.map(scan_url, all_section_urls))
    unique_hits = {h['aid']: h for r in scan_results for h in r}
    
    # 併發下載
    shared_results = []
    with ThreadPoolExecutor(max_workers=50) as download_pool:
        for hit in unique_hits.values():
            download_pool.submit(download_task, session, hit, shared_results)

    # 推播
    if shared_results:
        send_flex_push(shared_results)

if __name__ == "__main__":
    main()
