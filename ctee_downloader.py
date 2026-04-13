import os
import time
import requests
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from playwright.sync_api import sync_playwright

# --- 秘密資料區 (從環境變數讀取) ---
USERNAME = os.getenv("CTEE_USER", "liang44105")
PASSWORD = os.getenv("CTEE_PASS", "basic123$")
# LINE Messaging API 相關
LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")

KEYWORDS = ["凱基", "保險"]
BASE_URL = "https://readers.ctee.com.tw/cm"
TARGET_PAPER = "工商時報"
MAX_WORKERS = 10 

def get_output_path():
    # 統一存放在當前目錄的 output
    path = os.path.join(os.getcwd(), "output")
    os.makedirs(path, exist_ok=True)
    return path

def upload_to_catbox(image_path):
    """將圖片上傳至 Catbox.moe 取得臨時公開 URL (用於 LINE 預覽)"""
    url = "https://catbox.moe/user/api.php"
    try:
        with open(image_path, "rb") as f:
            data = {"reqtype": "fileupload"}
            files = {"fileToUpload": f}
            resp = requests.post(url, data=data, files=files)
            if resp.status_code == 200:
                img_url = resp.text.strip()
                print(f"  [HOST] 圖片已託管: {img_url}")
                return img_url
    except Exception as e:
        print(f"  [HOST] 託管失敗: {e}")
    return None

def send_to_line_messaging_api(token, user_id, message, image_url=None):
    """透過 LINE Messaging API 發送 Push Message"""
    if not token or not user_id:
        return
    
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    # 建立訊息物件
    messages = [{"type": "text", "text": message}]
    if image_url:
        messages.append({
            "type": "image",
            "originalContentUrl": image_url,
            "previewImageUrl": image_url
        })
    
    payload = {
        "to": user_id,
        "messages": messages
    }
    
    try:
        resp = requests.post(url, headers=headers, json=payload)
        if resp.status_code == 200:
            print(f"  [LINE] 成功推播訊息")
        else:
            print(f"  [LINE] 推播失敗: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"  [LINE] 發生錯誤: {e}")

def check_article_for_keywords(session, url, keywords):
    try:
        resp = session.get(url, timeout=5)
        if resp.status_code == 200:
            content = resp.text
            for kw in keywords:
                if kw in content:
                    return kw, url
    except:
        pass
    return None

def main_logic():
    print(f"--- 腳本啟動 (Messaging API 版) ---")
    start_time = time.time()
    
    session = requests.Session()
    today_str = datetime.now().strftime("%Y%m%d")
    target_folder = get_output_path()
    
    with sync_playwright() as p:
        print("正在啟動瀏覽器...")
        browser = p.chromium.launch(headless=True) 
        context = browser.new_context()
        page = context.new_page()

        # 1. 登入
        print("正在開啟登入頁面...")
        page.goto(BASE_URL)
        if "CM" not in page.url.upper():
            try:
                page.fill("input#UserName", USERNAME)
                page.fill("input#Password", PASSWORD)
                page.click("input[type='submit']")
                page.wait_for_load_state("networkidle")
                print("登入成功！")
            except: pass

        # 2. 掃描
        processed_pages = set()
        total_found = 0
        
        while True:
            page.wait_for_load_state("domcontentloaded")
            current_url = page.url
            if current_url in processed_pages: break
            processed_pages.add(current_url)

            # 檢查報紙標題
            paper_info = "第 " + str(len(processed_pages)) + " 頁"
            try:
                info_el = page.query_selector("p.t_align_l")
                if info_el: paper_info = info_el.inner_text()
                if TARGET_PAPER not in paper_info: break
            except: pass
            
            print(f"正在檢查: {paper_info}")

            # 平行掃描
            areas = page.query_selector_all("area")
            map_links = []
            for area in areas:
                href = area.get_attribute("href")
                if not href: continue
                mid = (area.evaluate_handle("el => el.closest('map')").as_element().get_attribute("id") or "").replace("map_", "")
                map_links.append((mid, requests.compat.urljoin(current_url, href)))

            found_pages = {}
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {executor.submit(check_article_for_keywords, session, url, KEYWORDS): mid for mid, url in map_links}
                for f in as_completed(futures):
                    res = f.result()
                    if res:
                        kw, _ = res
                        mid = futures[f]
                        if mid not in found_pages: found_pages[mid] = set()
                        found_pages[mid].add(kw)

            # 3. 推送
            for mid, matches in found_pages.items():
                try:
                    img_elem = page.query_selector(f'img[usemap="#map_{mid}"]')
                    if img_elem:
                        img_url = img_elem.get_attribute("src")
                        kw_str = ",".join(sorted(list(matches)))
                        filename = f"{mid}_{kw_str}.jpg"
                        
                        # 下載本地
                        local_path = os.path.join(target_folder, filename)
                        resp = session.get(img_url)
                        with open(local_path, "wb") as f: f.write(resp.content)
                        
                        # 託管並推播
                        if LINE_ACCESS_TOKEN and LINE_USER_ID:
                            public_url = upload_to_catbox(local_path)
                            if public_url:
                                msg = f"📄 頁面: {paper_info}\n🔍 發現關鍵字: {kw_str}"
                                send_to_line_messaging_api(LINE_ACCESS_TOKEN, LINE_USER_ID, msg, public_url)
                                total_found += 1
                except: pass

            # 4. 下一頁
            next_btn = page.query_selector("img.menu-next")
            if next_btn and next_btn.is_visible():
                next_btn.click()
                time.sleep(0.5)
            else: break

        if LINE_ACCESS_TOKEN and LINE_USER_ID:
            send_to_line_messaging_api(LINE_ACCESS_TOKEN, LINE_USER_ID, f"✅ 今日掃描完成，共抓取 {total_found} 張。")
            
        print(f"任務完成！耗時: {round(time.time() - start_time, 2)}s")
        browser.close()

if __name__ == "__main__":
    t = threading.Thread(target=main_logic)
    t.start()
    t.join()
