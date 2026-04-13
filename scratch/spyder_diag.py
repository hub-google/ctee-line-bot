import threading
import time
from playwright.sync_api import sync_playwright

def playwright_worker():
    """在獨立線程中執行，不受 Spyder asyncio 迴圈影響"""
    print("[Diag] 正在啟動獨立線程執行 Playwright...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False) # 開啟瀏覽器供您親眼確認
            page = browser.new_page()
            print("[Diag] 正在造訪工商時報首頁...")
            page.goto("https://readers.ctee.com.tw/cm", timeout=30000)
            print(f"[Diag] 成功成功！目前頁面標題: {page.title()}")
            time.sleep(3) # 停 3 秒供您檢視
            browser.close()
            print("[Diag] 測試驗證成功：獨立線程模式可在 Spyder 中正常運行！")
    except Exception as e:
        print(f"[Diag] 測試失敗: {e}")

def run_test_in_spyder():
    print("=== Spyder 環境衝突診斷程式 ===")
    # 建立一個新線程，這樣它就沒有連接著主線程的 asyncio 迴圈
    thread = threading.Thread(target=playwright_worker)
    thread.start()
    thread.join()
    print("=== 診斷程式結束 ===")

if __name__ == "__main__":
    run_test_in_spyder()
