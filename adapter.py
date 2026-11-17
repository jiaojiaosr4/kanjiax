# adapter.py
# 数据源适配器
# - TbkAdapter：淘宝联盟官方 API（真实数据，需配置 AppKey/AppSecret/adzone_id）
# - SampleAdapter：内置示例数据（离线演示，无需配置）
#
# 联盟 API 返回真实商品价格、券后价、佣金率、销量，合规且稳定。
# 评论与历史价格联盟不提供，分别由评论数据源（TODO）与自建 SQLite（TODO）补齐。

import hashlib
import time
import urllib.request
import urllib.parse
import json
import os


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

    GATEWAY = "https://eco.taobao.com/router/rest"

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
    def from_config(cls, config_path="config.json"):
        """从 config.json 加载配置。"""
        if not os.path.exists(config_path):
            return cls()
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        tbk = cfg.get("tbk", {})
        return cls(
            app_key=tbk.get("app_key"),
            app_secret=tbk.get("app_secret"),
            adzone_id=tbk.get("adzone_id"),
        )

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

        接口：taobao.tbk.dg.material.optional（物料搜索）
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
        data = self._call("taobao.tbk.dg.material.optional", biz)

        # 解析返回（淘宝返回结构层级较深，做兼容处理）
        resp_key = "tbk_dg_optimus_material_response"
        resp = data.get(resp_key, {})
        if "error_response" in data:
            raise RuntimeError(f"联盟 API 返回错误：{data.get('error_response', {}).get('sub_msg', data)}")

        result = resp.get("result_list_map", resp.get("result_list", {}))
        items = result.get("map_data", [])
        if isinstance(items, dict):
            items = [items]

        products = []
        for it in items[:page_size]:
            title = (it.get("title") or "").replace("<em>", "").replace("</em>", "")
            products.append({
                "id": str(it.get("item_id", "")),
                "name": title.strip(),
                "platform": "淘宝",
                "price": float(it.get("reserve_price", 0) or 0),
                "coupon_price": float(it.get("zk_final_price", 0) or 0),
                "commission_rate": float(it.get("commission_rate", 0) or 0) / 100,
                "volume": int(it.get("volume", 0) or 0),
                "url": it.get("click_url", ""),
                "pict_url": it.get("pict_url", ""),
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
    tbk = TbkAdapter.from_config()
    if tbk.configured():
        return tbk
    tbk = TbkAdapter.from_env()
    if tbk.configured():
        return tbk
    return SampleAdapter()
