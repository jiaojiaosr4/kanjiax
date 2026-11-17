import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

sku = "100012043978"
url = f"https://item.jd.com/{sku}.html"
print(f"stealth 模式爬取 SKU={sku}")

with sync_playwright() as p:
    browser = None
    for kw in [{"headless": True, "channel": "msedge"}, {"headless": True, "channel": "chrome"}, {"headless": True}]:
        try:
            browser = p.chromium.launch(**kw)
            print("BROWSER:", kw)
            break
        except Exception as e:
            print("LAUNCH FAIL:", repr(e)[:80])
    if not browser:
        raise SystemExit("无浏览器")
    ctx = browser.new_context(user_agent=UA, locale="zh-CN", viewport={"width": 1366, "height": 768})
    page = ctx.new_page()
    stealth_sync(page)
    try:
        page.goto(url, wait_until="networkidle", timeout=30000)
        print("FINAL_URL:", page.url)
        print("TITLE:", page.title())
        # 等价格
        try:
            page.wait_for_selector(".p-price, .summary-price, #jd-price, .sku-name", timeout=8000)
        except Exception:
            print("价格元素未出现")
        for sel in [".sku-name", ".p-price .now-price", ".p-price", "#jd-price", ".summary-price", ".comment-count"]:
            el = page.query_selector(sel)
            if el:
                print(f"  {sel}: '{el.inner_text()[:50]}'")
            else:
                print(f"  {sel}: none")
        # 额外：打印 body 前 300 字符判断是不是首页
        body = page.query_selector("body")
        if body:
            print("BODY_HEAD:", body.inner_text()[:200].replace("\n", " "))
    except Exception as e:
        print("ERR:", repr(e)[:150])
    finally:
        browser.close()
