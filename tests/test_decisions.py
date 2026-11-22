import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import main
from adapter import TbkAdapter
from data import HEADPHONE
from engine import analyze_price_history, analyze_product, analyze_search_results, detect_fake_reviews
from jd_adapter import JdAdapter
from price_history import CHINA_TIME, record_price


@contextmanager
def chdir(folder):
    previous = Path.cwd()
    os.chdir(folder)
    try:
        yield
    finally:
        os.chdir(previous)


def tbk_item(item_id, price=None):
    return {
        "item_id": item_id,
        "item_basic_info": {"title": item_id},
        "price_promotion_info": {"reserve_price": "100", "final_promotion_price": price},
    }


def jd_item(item_id, name, category, price, checkout, orders):
    return {
        "skuId": item_id,
        "skuName": name,
        "categoryInfo": {"cid3": category},
        "priceInfo": {"price": price, "lowestCouponPrice": checkout},
        "inOrderCount30Days": orders,
        "goodCommentsShare": 98,
    }


class DecisionTests(unittest.TestCase):
    def test_incomplete_prices_do_not_rank(self):
        response = {"tbk_dg_material_optional_upgrade_response": {
            "result_list": {"map_data": [tbk_item("未知价格"), tbk_item("已知价格", "50")]}
        }}
        adapter = TbkAdapter("test", "test", "1")
        with patch.object(adapter, "_call", return_value=response):
            products = adapter.search("测试商品")
        self.assertIsNone(products[0]["coupon_price"])
        result = analyze_search_results("测试商品", products)
        self.assertEqual(result["unranked"], 1)
        self.assertEqual(result["top_pick"]["id"], "已知价格")
        self.assertIsNone(analyze_search_results("测试商品", products[:1])["recommendation"])

    def test_taobao_search_and_item_accept_the_same_environment(self):
        response = {"tbk_item_info_upgrade_get_response": {
            "results": {"tbk_item_detail": [tbk_item("123")]}
        }}
        env = {"TBK_APP_KEY": "test", "TBK_APP_SECRET": "test", "TBK_ADZONE_ID": "1"}
        with tempfile.TemporaryDirectory() as folder, chdir(folder), \
                patch.dict(os.environ, env, clear=True), \
                patch.object(TbkAdapter, "_call", return_value=response), \
                redirect_stdout(io.StringIO()):
            self.assertTrue(TbkAdapter.load().configured())
            exit_code = main.main(["--item", "https://item.taobao.com/item.htm?id=123"])
            report = Path("report.html").read_text(encoding="utf-8")
        self.assertEqual(exit_code, 0)
        self.assertIn("资料不足", report)
        self.assertIn("数据来源 · 淘宝联盟官方 API", report)
        self.assertNotIn("100% 折扣", report)

    def test_failed_query_replaces_previous_report(self):
        with tempfile.TemporaryDirectory() as folder, chdir(folder), \
                patch.object(TbkAdapter, "load", return_value=TbkAdapter()), \
                redirect_stderr(io.StringIO()):
            path = Path("report.html")
            path.write_text("上一份报告", encoding="utf-8")
            exit_code = main.main(["--tbk", "耳机"])
            report = path.read_text(encoding="utf-8")
        self.assertEqual(exit_code, 1)
        self.assertIn("淘宝搜索「耳机」（运行失败）", report)
        self.assertIn("本次未生成商品结果", report)
        self.assertNotIn("上一份报告", report)

    def test_jd_alternatives_match_category_and_use_real_order_count(self):
        adapter = JdAdapter("test", "test")
        mixed = [
            jd_item(1, "耳机", 100, 100, 90, 1500),
            jd_item(2, "纸巾", 200, 20, 10, 0),
            jd_item(3, "同品类耳机", 100, 100, 80, 0),
        ]
        with tempfile.TemporaryDirectory() as folder, chdir(folder), \
                patch.object(JdAdapter, "from_config", return_value=adapter), \
                patch.object(adapter, "_call") as call, redirect_stdout(io.StringIO()) as output:
            call.return_value = {"code": 200, "data": mixed}
            self.assertEqual(main.main(["--jd"]), 0)
            report = Path("report.html").read_text(encoding="utf-8")
            self.assertIn("同品类较低价候选：同品类耳机", report)
            self.assertNotIn("同品类较低价候选：纸巾", report)
            call.return_value = {"code": 200, "data": [jd_item(4, "耳机", 100, 100, 50, 0)]}
            self.assertEqual(main.main(["--jd"]), 0)
            self.assertIn("【等】", output.getvalue())
            report = Path("report.html").read_text(encoding="utf-8")
            self.assertIn("近 30 天订单：0", report)
            self.assertNotIn("验证充分", report)

    def test_review_window_is_three_consecutive_calendar_days(self):
        def reviews(days):
            return [{"rating": 5, "text": "物流快，质量好", "date": day} for day in days]

        dispersed = reviews(["2026-08-01", "2026-09-01", "2026-10-01"])
        clustered = reviews(["2026-08-31", "2026-09-01", "2026-09-02"])
        self.assertFalse(detect_fake_reviews(dispersed)["concentrated"])
        self.assertEqual(detect_fake_reviews(clustered + dispersed)["suspicious_count"], 4)

    def test_price_evidence_matches_history_threshold(self):
        result = analyze_product(HEADPHONE)
        self.assertEqual(result["decision"]["action"], "等")
        evidence = " ".join(result["decision"]["evidence"])
        self.assertIn("比已记录最低价高 13.6%", evidence)
        self.assertNotIn("高于均价 8%", evidence)
        history = [{"date": "2026-11-20", "price": 100}]
        self.assertEqual(analyze_price_history(history, 110)["position"], "高位")

    def test_sqlite_history_keeps_latest_sample_per_day_and_item(self):
        day = datetime(2026, 11, 22, 12, tzinfo=CHINA_TIME)
        product = {"id": "one", "platform": "淘宝", "price": 100, "coupon_price": 70}
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder, "price.sqlite3")
            self.assertEqual(record_price({**product, "coupon_price": None}, database=db), [])
            self.assertFalse(db.exists())
            record_price(product, database=db, observed_at=day - timedelta(days=30))
            record_price(product, database=db, observed_at=day - timedelta(days=29))
            first = record_price(product, database=db, observed_at=day)
            self.assertEqual(len(first), 2)
            repeat = record_price({**product, "coupon_price": 90},
                                  database=db, observed_at=day + timedelta(hours=1))
            older = record_price(product, database=db, observed_at=day)
            self.assertEqual(older, repeat)
            self.assertEqual(repeat[-1], {"date": "2026-11-22", "price": 90})
            other = record_price({**product, "id": "two"}, database=db, observed_at=day)
            self.assertEqual(len(other), 1)
            self.assertIn("<svg", main.plot_history_svg(analyze_price_history(other, 70)))

    @unittest.skipUnless(shutil.which("node"), "需要 Node.js 校验课堂页评分")
    def test_classroom_and_python_use_identical_snapshot_ranking(self):
        path = Path(__file__).resolve().parents[1] / "index.html"
        script = r"""
const fs = require("node:fs");
const vm = require("node:vm");
const page = fs.readFileSync(process.argv[1], "utf8");
const dataLine = page.split("\n").find(line => line.startsWith("const DATA = "));
const data = JSON.parse(dataLine.slice("const DATA = ".length, -1));
const logic = page.slice(page.indexOf("function readNumber("), page.indexOf("// 页面内提示"));
const rank = vm.runInNewContext(logic + '\nsorted', {DATA: data});
const rankings = Object.fromEntries(Object.keys(data.keywords).map(keyword =>
  [keyword, rank(keyword).map(({p, m}) => [p.id, m.score])]));
process.stdout.write(JSON.stringify({rankings, keywords: Object.fromEntries(
  Object.entries(data.keywords).map(([key, items]) => [key,
    items.map(({id, name, price, coupon_price, volume, commission_rate}) =>
      ({id, name, price, coupon_price, volume, commission_rate}))]))}));
"""
        output = subprocess.run(["node", "-e", script, str(path)], check=True, capture_output=True, text=True)
        result = json.loads(output.stdout)
        for keyword, items in result["keywords"].items():
            ranks = analyze_search_results(keyword, items)["ranked"]
            self.assertEqual([[p["id"], p["worth_score"]] for p in ranks], result["rankings"][keyword])
