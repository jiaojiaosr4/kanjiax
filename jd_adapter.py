# jd_adapter.py
# 砍价侠基础版 - 京东联盟 API 适配器
#
# 接口：京东联盟开放平台（union.jd.com/openplatform）
# 网关：https://router.jd.com/api
# 签名：secret + 按参数名排序的 k+v 拼接 + secret，MD5 大写
# 凭证：导购媒体（社交媒体推广）创建后自动生成的 appkey/secretkey
#
# ===== 权限边界（实测 2026-11-18，如实标注，不硬造）=====
# 个人「导购媒体」类型 appkey 只开通了基础权限包的一部分：
#   [可用] jd.union.open.goods.jingfen.query  京粉精选（按频道拉真实商品）-> 本适配器主通道
#   [403]  jd.union.open.goods.promotiongoodsinfo.query  按SKU查详情（需网站/APP 或更高等级）
#   [403]  jd.union.open.goods.query  关键词搜索（需 V2 等级：月3万单/3万UV，个人拿不到）
#   [2001701] jd.union.open.promotion.common.get  网站/APP 转链（导购媒体 siteId 不支持）
# 官方规则：网站/APP 类转链接口必须用对应媒体类型的 appkey；导购媒体用不了。
# 因此京东这环做到「精选真实商品 -> 比价 -> 买/等/换决策」，与淘宝 --tbk 对称。
# 关键词搜索、按链接查详情、转链拿佣金属路线图，需要网站/APP 资质或更高等级。

import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime

GATEWAY = "https://router.jd.com/api"


class JdAdapter:
    """京东联盟 API 适配器（京粉精选真实商品）。"""

    def __init__(self, app_key, app_secret, union_id="", site_id="", position_id=""):
        self.app_key = app_key
        self.app_secret = app_secret
        self.union_id = union_id
        self.site_id = site_id
        self.position_id = position_id

    @classmethod
    def from_config(cls):
        cfg = {}
        env = os.environ
        if env.get("JD_APP_KEY"):
            cfg = {
                "app_key": env.get("JD_APP_KEY", ""),
                "app_secret": env.get("JD_APP_SECRET", ""),
                "union_id": env.get("JD_UNION_ID", ""),
                "site_id": env.get("JD_SITE_ID", ""),
                "position_id": env.get("JD_POSITION_ID", ""),
            }
        else:
            here = os.path.dirname(os.path.abspath(__file__))
            for root, _dirs, files in os.walk(here):
                if "config.json" in files:
                    with open(os.path.join(root, "config.json"), encoding="utf-8-sig") as f:
                        cfg = json.load(f).get("jd", {})
                    break
        return cls(
            cfg.get("app_key", ""),
            cfg.get("app_secret", ""),
            cfg.get("union_id", ""),
            cfg.get("site_id", ""),
            cfg.get("position_id", ""),
        )

    def configured(self):
        return bool(self.app_key and self.app_secret)

    # ---- 底层：签名 + 请求 ----
    def _sign(self, params):
        """京东签名：secret + 按参数名 ASCII 升序的 k+v 拼接 + secret，MD5 大写。"""
        items = sorted(params.items(), key=lambda x: x[0])
        raw = self.app_secret + "".join(f"{k}{v}" for k, v in items) + self.app_secret
        return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()

    def _call(self, method, biz):
        params = {
            "app_key": self.app_key,
            "method": method,
            "format": "json",
            "v": "1.0",
            "sign_method": "md5",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "param_json": json.dumps(biz, ensure_ascii=False, separators=(",", ":")),
        }
        params["sign"] = self._sign(params)
        url = GATEWAY + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "kanjiax/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if "error_response" in data:
            er = data["error_response"]
            raise RuntimeError(
                f"京东联盟 API 错误：code={er.get('code')} zh_desc={er.get('zh_desc','')} msg={er.get('en_desc','')}"
            )
        resp_key = method.replace(".", "_") + "_response"
        payload = data.get(resp_key)
        if payload is None:
            raise RuntimeError(f"京东联盟 API 返回结构异常：{list(data.keys())}")
        # 京东联盟把业务结果塞在 result 字符串里，这里统一解析
        r = payload.get("result")
        if isinstance(r, str):
            r = json.loads(r)
        return r if isinstance(r, dict) else {}

    # ---- 业务：京粉精选（个人导购媒体可用通道）----
    def jingfen_select(self, elite_id=1, page_size=20, page_index=1):
        """按京粉精选频道拉真实京东商品。

        接口：jd.union.open.goods.jingfen.query（基础权限包内，实测可用）
        eliteId 常见频道：1=好券、2=京粉精选等；业务参数必须包在 goodsReq 里。
        返回：规整后的商品列表（字段口径对齐 adapter.py / engine.analyze_search_results）。
        """
        if not self.configured():
            raise RuntimeError("京东联盟未配置，请设置 JD_APP_KEY / JD_APP_SECRET")

        r = self._call(
            "jd.union.open.goods.jingfen.query",
            {"goodsReq": {"eliteId": int(elite_id), "pageIndex": int(page_index), "pageSize": int(page_size)}},
        )
        if r.get("code") != 200:
            raise RuntimeError(f"京粉精选返回错误：code={r.get('code')} msg={r.get('message','')}")

        items = r.get("data") or []
        return [self._normalize(it) for it in items]

    def _normalize(self, it):
        """把京粉精选字段规整成砍价侠统一商品结构（+ 证据链用的真实扩展字段）。"""
        price_info = it.get("priceInfo") or {}
        price = _f(price_info.get("price"))
        # 券后到手价：优先 lowestCouponPrice，其次 purchasePrice，都没有则等于标价
        coupon_price = _f(price_info.get("lowestCouponPrice")) or _f(
            (it.get("purchasePriceInfo") or {}).get("purchasePrice")
        ) or price

        # 优惠券明细（真实券面额 + 门槛）
        promotions = []
        coupon_quota = 0.0
        coupon_discount = 0.0
        for c in (it.get("couponInfo") or {}).get("couponList") or []:
            d, q = _f(c.get("discount")), _f(c.get("quota"))
            if d > 0:
                promotions.append(f"满{q:g}减{d:g}元" if q > 0 else f"减{d:g}元")
                if d > coupon_discount:
                    coupon_discount, coupon_quota = d, q

        # 主图
        img_info = it.get("imageInfo") or {}
        img_list = img_info.get("imageList") or []
        pict = img_list[0].get("url", "") if img_list else img_info.get("whiteImage", "")

        # 推广落地页
        mat = it.get("materialUrl") or ""
        url = mat if mat.startswith("http") else ("https://" + mat if mat else "")

        comm = _f((it.get("commissionInfo") or {}).get("commissionShare"))  # 百分比，如 45.0
        shop = it.get("shopInfo") or {}
        return {
            "id": str(it.get("itemId") or it.get("spuid") or ""),
            "name": (it.get("skuName") or "").strip(),
            "platform": "京东",
            "price": price,
            "coupon_price": coupon_price,
            "commission_rate": comm,
            "volume": int(it.get("inOrderCount30Days") or 0),  # 近30天订单量（市场验证度）
            "url": url,
            "pict_url": (pict or "").replace("http://", "https://"),
            "promotions": promotions,
            # ==== 证据链用的真实扩展字段（全部来自接口，无编造）====
            "coupon_discount": coupon_discount,
            "coupon_quota": coupon_quota,
            "comments": int(it.get("comments") or 0),
            "good_rate": _f(it.get("goodCommentsShare")),
            "brand": it.get("brandName") or "",
            "shop": shop.get("shopName") or "",
            "shop_score": shop.get("userEvaluateScore") or "",
            "tags": [t.get("name") for t in (it.get("skuTagList") or []) if t.get("name")],
            "elite_name": (it.get("resourceInfo") or {}).get("eliteName") or "",
        }


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def extract_jd_sku(text):
    """从京东链接/纯数字里提取 SKU ID（保留工具，当前主模式用京粉精选不需要它）。"""
    raw = str(text).strip()
    if raw.isdigit():
        return raw
    m = re.search(r"item\.(?:m\.)?jd\.com/(?:product/)?(\d+)", raw)
    if m:
        return m.group(1)
    m = re.search(r"sku(?:Id|id)?[=:](\d+)", raw)
    if m:
        return m.group(1)
    m = re.search(r"(\d{6,})", raw)
    return m.group(1) if m else None
