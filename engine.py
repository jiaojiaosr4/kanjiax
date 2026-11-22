# engine.py
# 砍价侠基础版 - 决策引擎
# 输入商品数据，输出「买 / 等 / 换 + 证据链」决策
# 三大子模块：比价、历史价格位置判断、评论去水（可解释规则）

from datetime import date
from decimal import Decimal
from math import floor, isfinite
from statistics import mean


def read_number(value):
    """保留有效的非负数，缺失或无效值用 None 表示。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) and number >= 0 else None


def read_price(value):
    return read_number(value) or None


def _round_score(value):
    return floor(value * 10 + 0.5) / 10


def discount_percentage(price, checkout_price):
    price = read_price(price)
    checkout_price = read_price(checkout_price)
    if price is None or checkout_price is None:
        return None
    return _round_score(max(0, 100 * (price - checkout_price) / price))


def compare_prices(prices):
    """比价：跨平台价格对比，返回最便宜平台与价差。"""
    # 用券后价作为真实到手价
    sorted_prices = sorted(prices, key=lambda p: p.get("coupon_price", p["price"]))
    cheapest = sorted_prices[0]
    most_expensive = sorted_prices[-1]
    gap = most_expensive.get("coupon_price", most_expensive["price"]) - cheapest.get("coupon_price", cheapest["price"])
    return {
        "sorted": sorted_prices,
        "cheapest": cheapest,
        "most_expensive": most_expensive,
        "gap": gap,
    }


def analyze_price_history(history, current_price):
    """历史价格分析：判断当前价处于高位 / 低位 / 均值区间。"""
    prices = [h["price"] for h in history]
    low = min(prices)
    high = max(prices)
    avg = round(mean(prices), 1)

    # 位置判断：相对近 30 天最低点（大促低点会拉低均价，故以距最低点距离为准）
    current_value = Decimal(str(current_price))
    minimum_value = Decimal(str(low))
    if current_value >= minimum_value * Decimal("1.10"):
        position = "高位"
        position_label = "价格高位（比已记录最低价高至少 10%）"
    elif current_value <= minimum_value * Decimal("1.05"):
        position = "低位"
        position_label = "价格低位（接近已记录最低价）"
    else:
        position = "均值"
        position_label = "价格中段（相对已记录最低价）"

    # 距最低点的距离
    to_low = round(((current_price - low) / low) * 100, 1) if low else 0

    return {
        "min": low,
        "max": high,
        "avg": avg,
        "current": current_price,
        "position": position,
        "position_label": position_label,
        "distance_to_low_pct": to_low,
        "history": history,
    }


# 评论去水：可解释规则引擎
# 不追求高准确率，追求「每条判断能解释、能验证」
# 检测两类刷单信号：
#   1. 模板话术：好评同时包含「物流」+「质量/不错/好/满意」类高频词
#   2. 时间集中：模板好评集中在 ≤3 天内批量发布
TEMPLATE_LOGISTICS = "物流"
TEMPLATE_QUALITY_KEYS = ("质量", "不错", "好", "满意")

# 质量缺陷关键词（用于从真实差评里提取核心问题）
DEFECT_KEYWORDS = ("保温", "异味", "漏水", "材质", "虚假宣传", "续航", "底噪", "刷头")


def _is_template_review(text):
    """判定单条好评是否为模板话术。"""
    if TEMPLATE_LOGISTICS not in text:
        return False
    return any(k in text for k in TEMPLATE_QUALITY_KEYS)


def detect_fake_reviews(reviews):
    """评论去水：识别疑似刷单好评，提取真实差评与质量缺陷信号。"""
    total = len(reviews)
    positives = [r for r in reviews if r["rating"] >= 4]

    # 规则一：模板话术检测
    template_hits = [r for r in positives if _is_template_review(r["text"])]

    # 规则二：时间集中检测（模板好评集中在 ≤3 天）
    dated_hits = sorted(
        ((date.fromisoformat(r["date"]), r) for r in template_hits),
        key=lambda hit: hit[0],
    )
    start = 0
    best_start = best_end = 0
    for end, (day, _) in enumerate(dated_hits, 1):
        while (day - dated_hits[start][0]).days >= 3:
            start += 1
        if end - start > best_end - best_start:
            best_start, best_end = start, end
    concentrated = best_end - best_start >= 3
    suspicious = [r for _, r in dated_hits[best_start:best_end]] if concentrated else []
    suspicious_count = len(suspicious)
    suspicious_ratio = suspicious_count / total if total else 0

    # 真实差评：1-2 星评论（不区分是否刷单，差评本身就是信号）
    real_negatives = [r for r in reviews if r["rating"] <= 2]

    # 质量缺陷提取：从差评里命中关键词
    defects = []
    for r in real_negatives:
        hit = [k for k in DEFECT_KEYWORDS if k in r["text"]]
        for k in hit:
            if k not in defects:
                defects.append(k)

    # 规则说明（可解释性的证据）
    patterns = []
    if concentrated:
        patterns.append(
            f"检测到 {suspicious_count} 条疑似模板好评，发布于 {suspicious[0]['date']} 至 {suspicious[-1]['date']}"
        )
    if defects:
        patterns.append(f"低星评论提及：{'、'.join(defects)}")

    return {
        "total": total,
        "suspicious_count": suspicious_count,
        "suspicious_ratio": suspicious_ratio,
        "concentrated": concentrated,
        "patterns": patterns,
        "real_negatives": real_negatives,
        "defects": defects,
    }


def make_decision(product, comparison, price_history, review_analysis):
    """综合决策：输出「买 / 等 / 换」+ 人话结论 + 证据链。"""
    name = product["name"]
    cheapest = comparison["cheapest"]
    gap = comparison["gap"]

    evidence = []

    # 优先级一：评论去水发现严重质量缺陷 → 换
    if review_analysis["suspicious_ratio"] >= 0.25 and review_analysis["defects"]:
        action = "换"
        headline = f"{name}：{review_analysis['suspicious_ratio']:.0%} 评论命中疑似模板规则，低星评论提及{'、'.join(review_analysis['defects'][:2])}"
        evidence.append(f"评论去水：{review_analysis['suspicious_count']} 条好评命中疑似模板规则，集中发布")
        evidence.append(f"低星评论 {len(review_analysis['real_negatives'])} 条，提及{'、'.join(review_analysis['defects'])}")
        evidence.append("建议：核对低星评论提及的问题，或考虑同类商品")

    # 优先级二：当前价处于高位 → 等
    elif price_history["position"] == "高位":
        action = "等"
        gap_pct = price_history["distance_to_low_pct"]
        headline = f"{name}：当前 ¥{price_history['current']} 比已记录最低价 ¥{price_history['min']} 高 {gap_pct}%，非急用可以再等"
        evidence.append(f"历史价格：最低 ¥{price_history['min']}、最高 ¥{price_history['max']}、均价 ¥{price_history['avg']}")
        evidence.append(f"当前价格比已记录最低价高 {gap_pct}%，达到高位判断阈值 10%")

    # 优先级三：当前价处于低位且评论正常 → 买
    elif price_history["position"] == "低位" and review_analysis["suspicious_ratio"] < 0.25:
        action = "买"
        headline = f"{name}：当前 ¥{price_history['current']} 接近历史最低 ¥{price_history['min']}，{cheapest['platform']} 券后 ¥{cheapest.get('coupon_price', cheapest['price'])} 可入手"
        evidence.append(f"历史价格：近30天最低 ¥{price_history['min']}，当前价距最低仅 {price_history['distance_to_low_pct']}%")
        evidence.append(f"比价：{cheapest['platform']} 最便宜，券后 ¥{cheapest.get('coupon_price', cheapest['price'])}，比最贵平台省 ¥{gap}")
        evidence.append("评论：当前样本未触发换款规则")

    # 默认：买（拼多多便宜且评论可接受）
    else:
        action = "买"
        headline = f"{name}：{cheapest['platform']} 券后 ¥{cheapest.get('coupon_price', cheapest['price'])} 最便宜，比最贵平台省 ¥{gap}，可入手"
        evidence.append(f"比价：{cheapest['platform']} 最便宜，价差 ¥{gap}")
        evidence.append(f"历史价格：当前 ¥{price_history['current']}，最低 ¥{price_history['min']}")
        evidence.append("评论：未触发换货预警")

    return {
        "action": action,
        "headline": headline,
        "evidence": evidence,
    }


def analyze_product(product):
    """完整分析入口：对单个商品跑全部子模块，返回结构化决策结果。"""
    prices = product["prices"]
    history = product["history"]
    # 当前价取最便宜平台的券后价（用户视角的实际到手价）
    current_price = min(p.get("coupon_price", p["price"]) for p in prices)

    comparison = compare_prices(prices)
    price_history = analyze_price_history(history, current_price)
    review_analysis = detect_fake_reviews(product["reviews"])
    decision = make_decision(product, comparison, price_history, review_analysis)

    return {
        "product": product,
        "current_price": current_price,
        "comparison": comparison,
        "price_history": price_history,
        "review_analysis": review_analysis,
        "decision": decision,
    }


# ============================================================
# 搜索结果分析（联盟 API 模式）
# 对关键词搜索返回的多个真实商品做排序与推荐
# ============================================================
def analyze_search_results(keyword, products):
    """对联盟搜索返回的真实商品列表做划算度排序与推荐。

    联盟 API 不提供评论与历史价格，故此模式下决策基于：
      - 券后折扣力度（coupon_price vs price）
      - 销量（淘宝日销或京东近 30 天订单）
    评论去水与历史价高位判断需接入补充数据源（路线图）。
    """
    products = products or []
    ranked = []
    unranked = 0
    for p in products:
        price = read_price(p.get("price"))
        coupon = read_price(p.get("coupon_price"))
        discount_pct = discount_percentage(price, coupon)
        if discount_pct is None:
            unranked += 1
            continue
        volume = read_number(p.get("volume"))
        comm = read_number(p.get("commission_rate"))
        volume_cap = 1500 if p.get("platform") == "京东" else 50
        volume_score = min((volume or 0) / volume_cap, 1) * 100
        worth_score = _round_score(discount_pct * 0.6 + volume_score * 0.4)

        ranked.append({
            "product": p,
            "id": p.get("id"),
            "name": p.get("name", "")[:60],
            "platform": p.get("platform", "淘宝"),
            "price": price,
            "coupon_price": coupon,
            "discount_pct": discount_pct,
            "volume": volume,
            "commission_rate": comm,
            "worth_score": worth_score,
            "url": p.get("url", ""),
        })

    # 按划算分降序
    ranked.sort(key=lambda x: x["worth_score"], reverse=True)
    top = ranked[0] if ranked else None

    # 推荐理由
    recommendation = None
    if top:
        reason_parts = []
        if top["discount_pct"] > 0:
            reason_parts.append(f"券后 ¥{top['coupon_price']}（省 {top['discount_pct']}%）")
        if top["volume"]:
            reason_parts.append(f"销量 {top['volume']:g}")
        if not reason_parts:
            reason_parts.append("暂无有效折扣或销量优势")
        recommendation = {
            "name": top["name"],
            "headline": f"「{keyword}」推荐：{top['name'][:30]}，" + "，".join(reason_parts),
            "worth_score": top["worth_score"],
        }

    return {
        "keyword": keyword,
        "total": len(products),
        "unranked": unranked,
        "ranked": ranked,
        "top_pick": top,
        "recommendation": recommendation,
    }
