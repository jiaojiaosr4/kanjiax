# adapter.py
# 数据源适配器
# - TbkAdapter：淘宝联盟官方 API（真实数据，需配置 AppKey/AppSecret/adzone_id）
# - SampleAdapter：内置示例数据（离线演示，无需配置）
#
# 联盟 API 返回真实商品价格、券后价、佣金率、销量，合规且稳定。
# 联盟接口未提供评论正文与历史价格。历史价可由单品查询逐日记录。

import hashlib
import time
import urllib.request
import urllib.parse
import json
import os
from functools import partial
from pathlib import Path

from engine import read_number, read_price


def mapping(value):
    return value if isinstance(value, dict) else {}


def text_value(value):
    return value.strip() if isinstance(value, str) else ""


def identifier(value):
    return str(value) if type(value) is int else text_value(value)


def records(value):
    if isinstance(value, dict):
        return [value]
    return value if isinstance(value, list) else []


class ProductBatch(list):
    """保留商品列表的调用方式，同时携带本次跳过的记录数。"""

    def __init__(self):
        super().__init__()
        self.skipped = 0


def collect_products(raw, normalize, source, *, limit=None):
    if raw is not None and not isinstance(raw, (list, dict)):
        raise RuntimeError(f"{source}返回的商品列表结构异常")
    products = ProductBatch()
    for item in records(raw)[:limit]:
        product = normalize(item) if isinstance(item, dict) else None
        if product and product["name"]:
            products.append(product)
        else:
            products.skipped += 1
    if products.skipped and not products:
        raise RuntimeError(f"{source}返回了 {products.skipped} 条无效商品记录，本次无法生成结果")
    return products


def read_config(section, config_path=None):
    path = Path(config_path) if config_path is not None else Path("config.json")
    if config_path is None and not path.is_file():
        path = Path(__file__).with_name("config.json")
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8-sig") as config_file:
        config = json.load(config_file)
    values = config.get(section, {}) if isinstance(config, dict) else None
    if not isinstance(values, dict):
        raise ValueError(f"{path.name} 的 {section} 配置必须是 JSON 对象")
    return values


def _normalize_prices(price_info):
    price = read_price(price_info.get("reserve_price"))
    for field in ("final_promotion_price", "zk_final_price"):
        checkout = read_price(price_info.get(field))
        if checkout is not None:
            return price, checkout, field
    return price, None, ""


def _commission_rate(published):
    rate = read_number(mapping(published.get("income_info")).get("commission_rate"))
    return rate / 100 if rate is not None else None


def _promotions(price_info):
    paths = mapping(price_info.get("final_promotion_path_list")).get("final_promotion_path_map_data")
    descriptions = (text_value(mapping(path).get("promotion_desc")) for path in records(paths))
    return [description for description in descriptions if description]


def _taobao_records(response, response_key, container_key, records_key):
    if "error_response" in mapping(response):
        error = mapping(response["error_response"])
        raise RuntimeError(
            f"淘宝联盟返回错误：code={error.get('code')} {error.get('sub_code', '')} {error.get('sub_msg', '')}"
        )
    data = mapping(response).get(response_key)
    if not isinstance(data, dict):
        raise RuntimeError("淘宝联盟响应结构异常")
    container = data.get(container_key)
    if container is not None and not isinstance(container, dict):
        raise RuntimeError("淘宝联盟结果结构异常")
    return mapping(container).get(records_key)


def _taobao_product(item, *, detail=False):
    basic = mapping(item.get("item_basic_info"))
    price_info = mapping(item.get("price_promotion_info"))
    published = mapping(item.get("publish_info"))
    title = text_value(basic.get("title")).replace("<em>", "").replace("</em>", "").strip()
    price, checkout, price_source = _normalize_prices(price_info)
    url = text_value(basic.get("item_url") if detail else published.get("click_url"))
    return {
        "id": identifier(item.get("item_id")),
        "name": title,
        "platform": "淘宝",
        "price": price,
        "coupon_price": checkout,
        "price_source": price_source,
        "commission_rate": _commission_rate(published),
        "volume": read_number(published.get("daily_promotion_sales")),
        "url": "https:" + url if url.startswith("//") else url,
        "pict_url": text_value(basic.get("pict_url")),
        "nick": text_value(basic.get("shop_title")),
        "brand": text_value(basic.get("brand_name")),
        "category": text_value(basic.get("category_name")),
        "promotions": _promotions(price_info),
    }


# ============================================================
# 淘宝联盟 API 适配器（真实数据源）
# ============================================================
class TbkAdapter:
    """淘宝联盟官方 API 适配器。

    配置项（从环境变量或 config.json 读取）：
      TBK_APP_KEY     阿里妈妈开放平台 AppKey
      TBK_APP_SECRET  AppSecret
      TBK_ADZONE_ID   推广位 ID（PID 末段，如 mm_xxx_xxx_123 中的 123）
    """

    GATEWAY = "https://gw.api.taobao.com/router/rest"

    def __init__(self, app_key=None, app_secret=None, adzone_id=None):
        self.app_key = app_key
        self.app_secret = app_secret
        self.adzone_id = str(adzone_id) if adzone_id else None

    @classmethod
    def from_env(cls):
        """从环境变量加载配置。"""
        return cls(
            app_key=os.environ.get("TBK_APP_KEY"),
            app_secret=os.environ.get("TBK_APP_SECRET"),
            adzone_id=os.environ.get("TBK_ADZONE_ID"),
        )

    @classmethod
    def from_config(cls, config_path=None):
        """从 config.json 加载配置。"""
        tbk = read_config("tbk", config_path)
        return cls(
            app_key=tbk.get("app_key"),
            app_secret=tbk.get("app_secret"),
            adzone_id=tbk.get("adzone_id"),
        )

    @classmethod
    def load(cls):
        adapter = cls.from_env()
        return adapter if adapter.configured() else cls.from_config()

    def configured(self):
        """是否已配置完整凭证。"""
        return all([self.app_key, self.app_secret, self.adzone_id])

    def _sign(self, params):
        """淘宝开放平台 MD5 签名：参数排序拼接，前后加 secret，MD5 转大写。"""
        keys = sorted(params.keys())
        raw = self.app_secret + "".join(f"{k}{params[k]}" for k in keys) + self.app_secret
        return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()

    def _call(self, method, biz_params):
        """调用淘宝开放平台 REST 网关。"""
        sys_params = {
            "method": method,
            "app_key": self.app_key,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "format": "json",
            "v": "2.0",
            "sign_method": "md5",
        }
        all_params = {**sys_params, **{k: str(v) for k, v in biz_params.items()}}
        all_params["sign"] = self._sign(all_params)
        url = self.GATEWAY + "?" + urllib.parse.urlencode(all_params)
        req = urllib.request.Request(url, headers={"User-Agent": "KanjiaX/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def search(self, keyword, page_size=20):
        """关键词搜索淘宝商品，返回真实价格、券后价、佣金、销量。

        接口：taobao.tbk.dg.material.optional.upgrade（物料搜索升级版）
        旧版 taobao.tbk.dg.material.optional 已于 2024-01 下线，
        升级版需权限包「淘宝客【推广者】商品物料获取」。
        """
        if not self.configured():
            raise RuntimeError("淘宝联盟未配置，请设置 TBK_APP_KEY / TBK_APP_SECRET / TBK_ADZONE_ID")

        biz = {
            "q": keyword,
            "adzone_id": self.adzone_id,
            "page_size": page_size,
            "platform": "2",  # 无线端
            "page_no": 1,
        }
        data = self._call("taobao.tbk.dg.material.optional.upgrade", biz)

        items = _taobao_records(
            data, "tbk_dg_material_optional_upgrade_response", "result_list", "map_data"
        )
        return collect_products(items, _taobao_product, "淘宝联盟", limit=page_size)

    def item_info(self, item_id):
        """按商品 ID 查询真实商品详情（价格、标题、主图、佣金、促销）。

        接口：taobao.tbk.item.info.upgrade.get（商品详情升级版）
        权限包：淘宝客【公用】物料信息查询（已开通，升级版自动可用）
        支持新版动态字符串 ID（如 uland 链接中的 id 参数）。
        """
        if not self.configured():
            raise RuntimeError("淘宝联盟未配置，请设置 TBK_APP_KEY / TBK_APP_SECRET / TBK_ADZONE_ID")

        if isinstance(item_id, (list, tuple)):
            item_id = ",".join(str(n) for n in item_id)

        biz = {
            "item_id": str(item_id),
            "platform": "2",
        }
        data = self._call("taobao.tbk.item.info.upgrade.get", biz)

        items = _taobao_records(
            data, "tbk_item_info_upgrade_get_response", "results", "tbk_item_detail"
        )
        return collect_products(items, partial(_taobao_product, detail=True), "淘宝联盟")


# ============================================================
# 示例数据适配器（离线演示）
# ============================================================
class SampleAdapter:
    """内置示例数据适配器，无需配置即可演示决策引擎能力。"""

    def __init__(self):
        from data import SAMPLE_PRODUCTS
        self._samples = SAMPLE_PRODUCTS

    def configured(self):
        return True

    def get_samples(self):
        """返回示例商品（含价格、历史、评论，完整决策数据）。"""
        return self._samples


def get_default_adapter():
    """优先用联盟 API（如已配置），否则回退示例数据。"""
    tbk = TbkAdapter.load()
    if tbk.configured():
        return tbk
    return SampleAdapter()
