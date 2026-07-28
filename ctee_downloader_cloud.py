import os
import sys
import time
import requests
import re
import json
import io
import asyncio
import functools
import urllib.parse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont, ImageFile

# Ensure PIL handles truncated images
ImageFile.LOAD_TRUNCATED_IMAGES = True

# --- Configuration (Secrets from Environment) ---
USERNAME = os.getenv("CTEE_USER")
PASSWORD = os.getenv("CTEE_PASS")
LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")

KEYWORDS_URL = "https://raw.githubusercontent.com/hub-google/ctee-line-bot/master/keywords.txt"
KEYWORDS_EDIT_URL = "https://github.com/hub-google/ctee-line-bot/edit/master/keywords.txt"

def load_keywords():
    """從 GitHub 讀取最新關鍵字清單，若失敗則使用本地備用。"""
    try:
        r = requests.get(KEYWORDS_URL, timeout=8)
        if r.status_code == 200:
            kws = [line.strip() for line in r.text.splitlines() if line.strip()]
            if kws:
                print(f"[關鍵字] 已從 GitHub 讀取 {len(kws)} 個關鍵字。")
                return kws
    except Exception as e:
        print(f"[關鍵字] GitHub 讀取失敗 ({e})，準備讀取本地備用檔案...")
    
    # 本地備用：讀取倉庫裡的 keywords.txt
    try:
        local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keywords.txt")
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                kws = [line.strip() for line in f.readlines() if line.strip()]
            if kws:
                print(f"[關鍵字] 已從本地檔案讀取 {len(kws)} 個關鍵字。")
                return kws
    except:
        pass

    print("[警告] 找不到任何關鍵字名單，程式將結束。")
    return []

BASE_URL = "https://readers.ctee.com.tw/cm"
TARGET_PAPER = "工商時報"
FONT_PATH = os.path.join(os.path.dirname(__file__), "assets", "font.ttc")

# ==========================================
# 圖片處理與上傳模組
# ==========================================

def add_banner(img_data, title_kw):
    try:
        img = Image.open(io.BytesIO(img_data)).convert("RGB")
        banner_h = 80
        new_img = Image.new("RGB", (img.width, img.height + banner_h), "white")
        new_img.paste(img, (0, banner_h))
        draw = ImageDraw.Draw(new_img)
        
        # Load local packaged font for universal Chinese support
        try:
            font = ImageFont.truetype(FONT_PATH, 40)
        except:
            font = ImageFont.load_default()
            
        draw.text((30, 15), f"關鍵字: {title_kw}", fill="black", font=font)
        buf = io.BytesIO()
        new_img.save(buf, format="JPEG", quality=95)
        return buf.getvalue()
    except: return img_data

def upload_cdn(data):
    """
    圖片上傳模組：優先使用 ImgBB (官方 API、永久保存)，失敗時退回 Catbox 備用 (長期儲存)。
    """
    # 1. 優先嘗試 ImgBB (超級穩定，且帶金鑰好管理)
    try:
        url = "https://api.imgbb.com/1/upload"
        payload = {"key": os.getenv("IMGBB_API_KEY")}
        files = {"image": ("img.jpg", data, "image/jpeg")}
        r = requests.post(url, data=payload, files=files, timeout=25)
        if r.status_code == 200:
            res = r.json()
            if res.get("success"):
                return res["data"]["url"]
    except Exception as e:
        print(f"ImgBB 上傳失敗 ({e})，切換至備用圖床 Catbox...")

    # 2. 備用方案：Catbox (無廣告、可長期直連)
    try:
        files = {'fileToUpload': ('img.jpg', data, 'image/jpeg')}
        payload = {'reqtype': 'fileupload'}
        r = requests.post("https://catbox.moe/user/api.php", files=files, data=payload, timeout=20)
        if r.status_code == 200 and r.text.startswith("http"):
            return r.text.strip()
    except Exception as e:
        print(f"Catbox 備用上傳也失敗: {e}")
    
    return None




# ==========================================
# 網頁產生與 LINE 發送模組
# ==========================================

def create_rentry_page(date_str, results):
    content = f"# 📰 {date_str} 重點新聞整理\n\n💡 **閱讀提示：本頁面無縮放限制，您可以直接使用「雙指放大」觀看每一張剪報的清晰細節！**\n\n---\n\n"
    for res in results:
        if res.get('cdn_url') and res['cdn_url'] != "N/A":
            content += f"### 📥 [下載原圖]({res['cdn_url']})\n"
            content += f"![]({res['cdn_url']})\n\n---\n"
    try:
        session = requests.Session()
        session.get('https://rentry.co')
        csrf = session.cookies.get('csrftoken', '')
        payload = {'csrfmiddlewaretoken': csrf, 'text': content}
        headers = {'Referer': 'https://rentry.co'}
        r = session.post('https://rentry.co/api/new', data=payload, headers=headers, timeout=15)
        url = r.json().get('url')
        if url: return url
    except Exception as e:
        print(f"Rentry 網頁產生失敗: {e}")
    return None

def create_telegraph_page(date_str, results):
    try:
        r = requests.get("https://api.telegra.ph/createAccount?short_name=NewsBot&author_name=工商時報剪報系統")
        token = r.json().get("result", {}).get("access_token")
        if not token: return None
        content = [{"tag": "hr"}]
        for res in results:
            if res.get('cdn_url') and res['cdn_url'] != "N/A":
                content.append({"tag": "h4", "children": [{"tag": "a", "attrs": {"href": res['cdn_url'], "target": "_blank"}, "children": ["📥 下載原圖"]}]})
                content.append({"tag": "img", "attrs": {"src": res['cdn_url']}})
                content.append({"tag": "hr"})
        if not content: return None
        payload = {"access_token": token, "title": f"News Summary {date_str.replace('/', '')}", "content": json.dumps(content), "return_content": False}
        r = requests.post("https://api.tel  egra.ph/createPage", data=payload)
        url = r.json().get("result", {}).get("url")
        if url: return urllib.parse.quote(url, safe=':/?=&')
    except: pass
    return None

def send_summary_message(results):
    valid_results = [r for r in results if r.get('cdn_url') and r['cdn_url'] != "N/A"]
    if not valid_results: return
    
    # 🌟 修正：使用台灣時間 (UTC+8) 作為標題日期
    from datetime import datetime, timedelta, timezone
    tw_now = datetime.now(timezone.utc) + timedelta(hours=8)
    title_date = tw_now.strftime("%Y/%m/%d")
    print("\n[處理中] 正在將所有圖片打包成閱讀網頁...", flush=True)
    
    # 🌟 優先使用支援雙指縮放的 Rentry 網頁
    page_url = create_rentry_page(title_date, valid_results)
    if page_url:
        print("  -> 成功產生 Rentry 閱讀網頁 (支援縮放)")
    else:
        # 萬一 Rentry 掛了，自動退回使用 Telegraph 備用
        print("  -> Rentry 產生失敗，切換至 Telegraph 備用網頁...")
        page_url = create_telegraph_page(title_date, valid_results)
    
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    
    if page_url:
        # 建立一鍵分享的連結 (使用 LINE 原生 URI 捷徑)
        share_text = f"📰 {title_date} 工商時報重點新聞\n👉 點擊閱讀全文 (可雙指放大)：\n{page_url}"
        share_uri = f"line://msg/text/?{urllib.parse.quote(share_text)}"

        bubble = {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": f"📰 {title_date} 工商時報擷取",
                        "weight": "bold",
                        "size": "lg",
                        "color": "#1DB954"
                    },
                    {
                        "type": "text",
                        "text": f"🎯 已為您打包 {len(valid_results)} 則相關新聞。",
                        "wrap": True,
                        "color": "#666666",
                        "size": "sm"
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#1DB954",
                        "action": {
                            "type": "uri",
                            "label": "開啟閱讀全文",
                            "uri": page_url
                        }
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {
                            "type": "uri",
                            "label": "💌 將新聞分享給好友",
                            "uri": share_uri
                        }
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {
                            "type": "uri",
                            "label": "⚙️ 調整抓取關鍵字",
                            "uri": KEYWORDS_EDIT_URL
                        }
                    }
                ]
            }
        }
        payload = {
            "to": LINE_USER_ID,
            "messages": [{"type": "flex", "altText": share_text, "contents": bubble}]
        }
    else:
        text = f"📰 {title_date} 處理失敗，退回純文字：\n\n"
        for i, res in enumerate(valid_results, 1):
            text += f"[{res['kw']}]\n{res['cdn_url']}\n"
        payload = {
            "to": LINE_USER_ID,
            "messages": [{"type": "text", "text": text[:4999]}]
        }
        
    r = requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload)
    status_msg = "成功" if r.status_code == 200 else f"失敗({r.status_code} - 詳細: {r.text})"
    print(f"[LINE通知] 總結訊息發送{status_msg}", flush=True)

# ==========================================
# 爬蟲引擎模組 (Cloud Optimized)
# ==========================================

async def turbo_capture_cloud(aid, hit_info, context, folder, semaphore, result_list):
    async with semaphore:
        for attempt in range(5):
            page = await context.new_page()
            try:
                await page.goto(hit_info['url'], wait_until="domcontentloaded", timeout=12000)
                await page.evaluate(f'document.getElementById("{aid}").click()')
                img_src = None
                for _ in range(40):
                    img_src = await page.evaluate('() => document.querySelector(".fancybox-image")?.src')
                    if img_src and "data:image" not in img_src: break
                    await asyncio.sleep(0.3)
                
                if img_src:
                    loop = asyncio.get_event_loop()
                    # 非同步下載
                    get_func = functools.partial(requests.get, img_src, timeout=12, headers={"Referer": hit_info['url']})
                    resp = await loop.run_in_executor(None, get_func)
                    
                    if resp.status_code == 200:
                        final_data = add_banner(resp.content, hit_info['kw'])
                        # 非同步上傳
                        cdn_url = await loop.run_in_executor(None, upload_cdn, final_data)
                        
                        result_list.append({
                            "aid": aid, "status": "成功" if cdn_url else "成功 (但CDN上傳失敗)", 
                            "cdn_url": cdn_url or "N/A", "kw": hit_info['kw'], "article_url": hit_info['url']
                        })
                        print(f"  下載結果{len(result_list)}: {'成功' if cdn_url else 'CDN失敗'} ({aid})")
                        await page.close()
                        return
                    else: raise Exception(f"IMG HTTP {resp.status_code}")
                else: raise Exception("找不到圖片元件")
            except Exception as e:
                await page.close()
                if attempt == 4:
                    result_list.append({"aid": aid, "status": f"失敗 ({str(e)})", "cdn_url": "N/A"})
                else: await asyncio.sleep(1)

async def run_worker():
    from playwright.async_api import async_playwright
    print("\n--- 啟動工商時報自動爬蟲 (雲端 Rentry 版) ---")
    start_time = time.time()
    keywords = load_keywords()
    temp_folder = "/tmp"
    if not os.path.exists(temp_folder): os.makedirs(temp_folder)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await context.new_page()
        
        # 🚀 精準化對策：根據台灣時間強制抓取當天日期，防止被官網舊緩存誤導
        from datetime import datetime, timedelta, timezone
        tw_now = datetime.now(timezone.utc) + timedelta(hours=8)
        target_date = tw_now.strftime("%Y%m%d")
        target_url = f"https://readers.ctee.com.tw/cm/{target_date}"
        
        print(f"[1/3] 正在登入並導向今日版面 ({target_date})...")
        login_url = f"https://member.ctee.com.tw/Account/Login?ReturnUrl={urllib.parse.quote(target_url)}"
        await page.goto(login_url)
        if await page.query_selector("input#UserName"):
            await page.fill("input#UserName", USERNAME)
            await page.fill("input#Password", PASSWORD)
            await page.click("input[type='submit']")
            await page.wait_for_url(f"https://readers.ctee.com.tw/cm/{target_date}**", timeout=20000)
            print("登入成功，已到達今日標靶頁面。")
        
        # 確保真的有在目標頁面
        if target_date not in page.url:
            await page.goto(target_url, wait_until='domcontentloaded')
        
        print("[2/3] 正在用 Playwright 掃描全報各版面（確保 JS 渲染）...")
        # 2. 全部用 Playwright 掃描（確保 JavaScript 渲染完成，A1~A5付費版也能正確讀到文章）
        unique_hits = {}
        scan_semaphore = asyncio.Semaphore(8)
        
        async def scan_section(url):
            async with scan_semaphore:
                try:
                    scan_page = await context.new_page()
                    # 💡 鏡像同步：與本地版完全一致，使用 networkidle 確保最高精準度
                    await scan_page.goto(url, wait_until='networkidle', timeout=20000)
                    # 從已渲染的 DOM 直接抓所有文章資料（超精準地毯式搜索）
                    articles = await scan_page.evaluate("""
                        () => {
                            const results = [];
                            document.querySelectorAll('[id]').forEach(el => {
                                if (/^\\d+$/.test(el.id)) {
                                    // 抓取所有可能的文字來源，組成文字池
                                    let pool = [
                                        el.getAttribute('data-fulltitle'),
                                        el.getAttribute('data-title'),
                                        el.getAttribute('alt'),
                                        el.getAttribute('title'),
                                        el.innerText
                                    ].filter(x => x).join(' ');
                                    
                                    if (pool.length > 2) {
                                        results.push({ 
                                            id: el.id, 
                                            pool: pool.replace(/\\s+/g, ' ').trim() 
                                        });
                                    }
                                }
                            });
                            return results;
                        }
                    """)
                    import html
                    for article in articles:
                        aid = article.get('id', '')
                        text_pool = html.unescape(article.get('pool', ''))
                        if not aid or not text_pool:
                            continue
                        matching = [k for k in keywords if k in text_pool]
                        if matching and aid not in unique_hits:
                            unique_hits[aid] = {"kw": ",".join(sorted(matching)), "url": url}
                except:
                    pass
                finally:
                    try: await scan_page.close()
                    except: pass
        
        # 取得版面連結
        await page.goto(BASE_URL)
        links = set(re.findall(r'/cm/\d+/[a-zA-Z0-9]+', await page.content(), re.IGNORECASE))
        # 💡 過濾邏輯：確保我們只點擊當天日期的連結，防止抓到舊新聞
        section_urls = [f"https://readers.ctee.com.tw{l}" for l in links if target_date in l and any(k in l.lower() for k in ["aa", "ab", "ac", "asa"])]
        
        await asyncio.gather(*[scan_section(url) for url in section_urls])

        if not unique_hits:
            print("今日無符合關鍵字內容。")
            await browser.close()
            return

        print(f"[3/3] 發現 {len(unique_hits)} 則文章。啟動 10 分頁極速抓取與非同步上傳...")
        captured_data = []
        semaphore = asyncio.Semaphore(10)
        tasks = [turbo_capture_cloud(aid, hit, context, temp_folder, semaphore, captured_data) for aid, hit in unique_hits.items()]
        await asyncio.gather(*tasks)
        await browser.close()
        
        print("\n--- 雲端執行報告 ---")
        send_summary_message(captured_data)
        print(f"總耗時: {round(time.time() - start_time, 2)}s")

if __name__ == "__main__":
    asyncio.run(run_worker())