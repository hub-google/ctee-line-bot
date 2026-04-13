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
                page.wait_for_load_state("networkidle", timeout=60000)
                time.sleep(5) # 登入後多等一下讓頁面載入完畢
                print("登入成功！")
            except Exception as e:
                print(f"登入過程異常: {e}")

        # 2. 開始掃描
        print(f"開始並行掃描今日 ({today_str}) 的 {TARGET_PAPER}...")
        processed_pages = set()
        total_found = 0
        
        while True:
            # 等待熱點 map 載入
            try:
                page.wait_for_selector("area", timeout=15000)
            except:
                pass
            
            page.wait_for_load_state("domcontentloaded")
            current_url = page.url
            if current_url in processed_pages: break
            processed_pages.add(current_url)

            # 檢查報紙標題
            paper_info = ""
            try:
                # 雲端環境可能需要更精確的選擇器
                info_elements = page.query_selector_all("p.t_align_l")
                paper_info = " | ".join([el.inner_text() for el in info_elements])
                
                if TARGET_PAPER not in paper_info:
                    print(f"目前為 {paper_info}，非目標報紙，終止。")
                    # 為了除錯，如果第一頁就不是工商時報，我們紀錄一下
                    if len(processed_pages) == 1:
                        print(f"警告：第一頁非目標報紙，請檢查登入後是否被跳轉至正確頁面。")
                    break
                print(f"正在檢查: {paper_info}")
            except Exception as e:
                print(f"讀取頁面資訊失敗: {e}")

            # 文章平行檢索
            areas = page.query_selector_all("area")
            map_links = [] 
            for area in areas:
                href = area.get_attribute("href")
                if not href: continue
                mid = (area.evaluate_handle("el => el.closest('map')").as_element().get_attribute("id") or "").replace("map_", "")
                full_url = requests.compat.urljoin(current_url, href)
                map_links.append((mid, full_url))

            found_pages = {} 
            if map_links:
                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    future_to_map = {
                        executor.submit(check_article_for_keywords, session, url, KEYWORDS): mid 
                        for mid, url in map_links
                    }
                    for future in as_completed(future_to_map):
                        mid = future_to_map[future]
                        result = future.result()
                        if result:
                            kw, url = result
                            if mid not in found_pages: found_pages[mid] = set()
                            found_pages[mid].add(kw)

            # 3. 下載並傳送至 LINE
            for mid, matches in found_pages.items():
                try:
                    img_elem = page.query_selector(f'img[usemap="#map_{mid}"]')
                    if img_elem:
                        img_url = img_elem.get_attribute("src")
                        keyword_str = ",".join(sorted(list(matches)))
                        filename = f"{mid}_{keyword_str}.jpg"
                        local_path = os.path.join(target_folder, filename)
                        
                        # 下載
                        resp = session.get(img_url)
                        with open(local_path, "wb") as f: f.write(resp.content)
                        
                        if local_path and LINE_ACCESS_TOKEN and LINE_USER_ID:
                            public_url = upload_to_catbox(local_path)
                            if public_url:
                                msg = f"📄 頁面: {paper_info}\n🔍 發現關鍵字: {keyword_str}"
                                send_to_line_messaging_api(LINE_ACCESS_TOKEN, LINE_USER_ID, msg, public_url)
                                total_found += 1
                except:
                    pass

            # 4. 翻頁
            next_btn = page.query_selector("img.menu-next")
            if next_btn and next_btn.is_visible():
                next_btn.click()
                time.sleep(2) # 雲端翻頁慢一點，確保圖片穩定
            else:
                break

        # --- 偵錯功能：如果抓到 0 張，傳送當前畫面截圖到 LINE ---
        if total_found == 0 and LINE_ACCESS_TOKEN and LINE_USER_ID:
            debug_shot = os.path.join(target_folder, "debug_failed.png")
            page.screenshot(path=debug_shot)
            debug_url = upload_to_catbox(debug_shot)
            msg = f"⚠️ 除錯通知：今日掃描完成但抓取量為 0。\n目前頁面：{page.url}\n頁面資訊：{paper_info}"
            send_to_line_messaging_api(LINE_ACCESS_TOKEN, LINE_USER_ID, msg, debug_url)

        final_msg = f"✅ 今日掃描完成，共抓取 {total_found} 張。"
        if LINE_ACCESS_TOKEN and LINE_USER_ID:
            send_to_line_messaging_api(LINE_ACCESS_TOKEN, LINE_USER_ID, final_msg)
            
        print(f"任務完成！耗時: {round(time.time() - start_time, 2)}s")
        browser.close()

if __name__ == "__main__":
    t = threading.Thread(target=main_logic)
    t.start()
    t.join()
