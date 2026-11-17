import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from adapter import fetch_jd_product

# 测试一个真实京东 SKU
sku = "100012043978"
print(f"爬取京东商品 SKU={sku} ...")
try:
    r = fetch_jd_product(sku)
    print("名称:", r["name"][:60])
    print("价格:", r["price"])
    print("评论数:", r["comment_count"])
    print("好评率:", r["good_rate"])
    print("评论条数:", len(r["reviews"]))
    if r["reviews"]:
        print("示例评论:", r["reviews"][0]["text"][:60])
except Exception as e:
    import traceback
    traceback.print_exc()
    print("ERR:", repr(e))
