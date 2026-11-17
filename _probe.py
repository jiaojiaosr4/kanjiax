import urllib.request, re

sku = "100012043978"
url = f"https://item.jd.com/{sku}.html"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

try:
    req = urllib.request.Request(url, headers=headers)
    html = urllib.request.urlopen(req, timeout=12).read().decode("utf-8", errors="replace")
except Exception as e:
    print("FETCH_ERR:", repr(e))
    raise SystemExit

print("LEN:", len(html))
m = re.search(r"<title>(.*?)</title>", html)
print("TITLE:", m.group(1) if m else "N/A")

# 价格相关字段
price_patterns = [
    r'"p"\s*:\s*"?\s*(\d+\.?\d*)',
    r'"op"\s*:\s*"?\s*(\d+\.?\d*)',
    r'"m"\s*:\s*"?\s*(\d+\.?\d*)',
    r'jdPrice["\']?\s*[:=]\s*["\']?(\d+\.?\d*)',
    r'p-price[^>]*>\s*[￥¥]?\s*(\d+\.?\d*)',
]
for pat in price_patterns:
    hits = re.findall(pat, html)
    if hits:
        print(f"PAT {pat[:30]} ->", hits[:8])

# 评论摘要
rate_patterns = [
    r'"goodRate"\s*:\s*([\d.]+)',
    r'"CommentCount"\s*:\s*"?(\d+)',
    r'"commentCount"\s*:\s*"?(\d+)',
    r'"rate"\s*:\s*"?([\d.]+)',
]
for pat in rate_patterns:
    hits = re.findall(pat, html)
    if hits:
        print(f"RATE {pat[:30]} ->", hits[:5])

# 商品名
nm = re.search(r'"name"\s*:\s*"([^"]+)"', html)
print("NAME:", nm.group(1)[:80] if nm else "N/A")
