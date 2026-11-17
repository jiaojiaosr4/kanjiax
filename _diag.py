import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 换一个更可能有效的 SKU + 诊断
for sku in ["100012043978", "100008348542", "100022820158"]:
    url = f"https://item.jd.com/{sku}.html"
    print(f"\n===== SKU {sku} =====")
    with sync_playwright() as p:
        browser = None
        for kw in [{"headless": True}, {"headless": True, "channel": "msedge"}, {"headless": True, "channel": "chrome"}]:
            try:
                browser = p.chromium.launch(**kw)
                print("BROWSER:", kw)
                break
            except Exception as e:
                print("LAUNCH FAIL:", repr(e)[:80])
        if not browser:
            print("无可用浏览器")
            continue
        ctx = browser.new_context(user_agent=UA, locale="zh-CN")
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            print("FINAL_URL:", page.url)
            print("TITLE:", page.title())
            html = page.content()
            print("HTML_LEN:", len(html))
            # 关键元素
            for sel in [".sku-name", ".p-price .now-price", ".p-price", "#jd-price", ".summary-price", ".comment-count"]:
                el = page.query_selector(sel)
                if el:
                    print(f"  {sel}: '{el.inner_text()[:40]}'")
                else:
                    print(f"  {sel}: none")
        except Exception as e:
            print("ERR:", repr(e)[:120])
        finally:
            browser.close()
