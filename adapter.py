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
from pathlib import Path

from engine import read_number, read_price


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
    return (
        read_price(price_info.get("reserve_price")),
        read_price(price_info.get("final_promotion_price"))
        or read_price(price_info.get("zk_final_price")),
    )


def _commission_rate(published):
    rate = read_number((published.get("income_info") or {}).get("commission_rate"))
    return rate / 100 if rate is not None else None


def _promotions(price_info):
    paths = (price_info.get("final_promotion_path_list") or {}).get("final_promotion_path_map_data") or []
    if isinstance(paths, dict):
        paths = [paths]
    return [p["promotion_desc"] for p in paths if p.get("promotion_desc")]


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

        if "error_response" in data:
            er = data["error_response"]
            raise RuntimeError(f"联盟 API 返回错误：code={er.get('code')} {er.get('sub_code','')} {er.get('sub_msg','')}")

        # 升级版返回嵌套结构，字段分布在 item_basic_info / price_promotion_info / publish_info
        resp = data.get("tbk_dg_material_optional_upgrade_response") or {}
        items = (resp.get("result_list") or {}).get("map_data") or []
        if isinstance(items, dict):
            items = [items]

        products = []
        for it in items[:page_size]:
            basic = it.get("item_basic_info") or {}
            price_info = it.get("price_promotion_info") or {}
            pub = it.get("publish_info") or {}
            title = (basic.get("title") or "").replace("<em>", "").replace("</em>", "")
            # 到手价优先取 final_promotion_price（含券），否则取 zk_final_price
            reserve, coupon_price = _normalize_prices(price_info)
            # 佣金率：联盟返回 "300" 表示 3.00%
            commission_rate = _commission_rate(pub)
            # 推广链接可能是 // 开头，补全协议
            click_url = pub.get("click_url", "") or ""
            if click_url.startswith("//"):
                click_url = "https:" + click_url

            products.append({
                "id": str(it.get("item_id") or ""),
                "name": title.strip(),
                "platform": "淘宝",
                "price": reserve,
                "coupon_price": coupon_price,
                "commission_rate": commission_rate,
                "volume": read_number(pub.get("daily_promotion_sales")),
                "url": click_url,
                "pict_url": basic.get("pict_url", ""),
                "nick": basic.get("shop_title", ""),
                "brand": basic.get("brand_name", ""),
                "category": basic.get("category_name", ""),
                "promotions": _promotions(price_info),
            })
        return products

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

        if "error_response" in data:
            er = data["error_response"]
            raise RuntimeError(f"联盟 API 返回错误：code={er.get('code')} {er.get('sub_code','')} {er.get('sub_msg','')}")

        resp = data.get("tbk_item_info_upgrade_get_response") or {}
        details = (resp.get("results") or {}).get("tbk_item_detail") or []
        if isinstance(details, dict):
            details = [details]

        products = []
        for d in details:
            basic = d.get("item_basic_info") or {}
            price_info = d.get("price_promotion_info") or {}
            pub = d.get("publish_info") or {}
            title = (basic.get("title") or "").replace("<em>", "").replace("</em>", "")
            # 到手价优先取 final_promotion_price（含券），否则取 zk_final_price
            reserve, coupon_price = _normalize_prices(price_info)
            # 佣金率：联盟返回 "300" 表示 3.00%
            commission_rate = _commission_rate(pub)

            products.append({
                "id": str(d.get("item_id") or ""),
                "name": title.strip(),
                "platform": "淘宝",
                "price": reserve,
                "coupon_price": coupon_price,
                "commission_rate": commission_rate,
                "volume": read_number(pub.get("daily_promotion_sales")),
                "url": basic.get("item_url", ""),
                "pict_url": basic.get("pict_url", ""),
                "nick": basic.get("shop_title", ""),
                "brand": basic.get("brand_name", ""),
                "category": basic.get("category_name", ""),
                "promotions": _promotions(price_info),
            })
        return products


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
