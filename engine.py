# engine.py
# 砍价侠基础版 - 决策引擎
# 输入商品数据，输出「买 / 等 / 换 + 证据链」决策
# 三大子模块：比价、历史价格位置判断、评论去水（可解释规则）

from statistics import mean
from collections import Counter


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
    if current_price >= low * 1.10:
        position = "高位"
        position_label = "近30天价格高位（距最低点超10%）"
    elif current_price <= low * 1.05:
        position = "低位"
        position_label = "近30天价格低位（接近最低点）"
    else:
        position = "均值"
        position_label = "近30天价格中段"

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
    template_dates = sorted({r["date"] for r in template_hits})
    concentrated = len(template_hits) >= 3 and len(template_dates) <= 3

    suspicious = template_hits if concentrated else []
    suspicious_count = len(suspicious)
    suspicious_ratio = round(suspicious_count / total, 2) if total else 0

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
            f"检测到 {suspicious_count} 条模板好评（含「物流+质量」话术），集中在 {template_dates[0]} ~ {template_dates[-1]} 共 {len(template_dates)} 天内发布"
        )
    if defects:
        patterns.append(f"真实差评命中质量缺陷关键词：{ '、'.join(defects) }")

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
        headline = f"{name}：便宜也别买——{int(review_analysis['suspicious_ratio']*100)}% 评论疑似刷单，真实差评指向{ '、'.join(review_analysis['defects'][:2]) }"
        evidence.append(f"评论去水：{review_analysis['suspicious_count']} 条好评疑似模板刷单（{int(review_analysis['suspicious_ratio']*100)}%），发布时间高度集中")
        evidence.append(f"真实差评 {len(review_analysis['real_negatives'])} 条，质量缺陷信号：{ '、'.join(review_analysis['defects']) }")
        evidence.append("结论：商品本身存在质量问题，便宜不等于值得买，建议换同类其他商品")

    # 优先级二：当前价处于高位 → 等
    elif price_history["position"] == "高位":
        action = "等"
        next_promo = "年货节 / 618"
        headline = f"{name}：当前 ¥{price_history['current']} 处于近30天高位（距最低 ¥{price_history['min']} 还贵 {price_history['distance_to_low_pct']}%），建议等 {next_promo}"
        evidence.append(f"历史价格：近30天最低 ¥{price_history['min']}、最高 ¥{price_history['max']}、均价 ¥{price_history['avg']}")
        evidence.append(f"当前价 ¥{price_history['current']} 高于均价 8% 以上，处于高位区间")
        evidence.append(f"建议：非急用可等 {next_promo} 回到 ¥{price_history['min']} 附近再入手")

    # 优先级三：当前价处于低位且评论正常 → 买
    elif price_history["position"] == "低位" and review_analysis["suspicious_ratio"] < 0.25:
        action = "买"
        headline = f"{name}：当前 ¥{price_history['current']} 接近历史最低 ¥{price_history['min']}，{cheapest['platform']} 券后 ¥{cheapest.get('coupon_price', cheapest['price'])} 可入手"
        evidence.append(f"历史价格：近30天最低 ¥{price_history['min']}，当前价距最低仅 {price_history['distance_to_low_pct']}%")
        evidence.append(f"比价：{cheapest['platform']} 最便宜，券后 ¥{cheapest.get('coupon_price', cheapest['price'])}，比最贵平台省 ¥{gap}")
        evidence.append(f"评论：去水后未发现严重刷单与质量缺陷信号，可放心购买")

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
