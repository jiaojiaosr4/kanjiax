# data.py
# 砍价侠基础版 - 内置示例商品数据
# 数据为演示用模拟数据，正式版通过 adapter 接入真实数据源

from datetime import date


def _d(m, day):
    return f"2026-{m:02d}-{day:02d}"


# 商品一：降噪耳机 —— 当前处于历史高位，决策「等」
HEADPHONE = {
    "id": "headphone",
    "name": "主动降噪蓝牙耳机",
    "category": "数码",
    "prices": [
        {"platform": "淘宝", "price": 1299, "coupon_price": 1299},
        {"platform": "京东", "price": 1349, "coupon_price": 1299},
        {"platform": "拼多多", "price": 1249, "coupon_price": 1249},
    ],
    # 30 天历史价（双 11 期间曾到过 1099 低点，当前回升到高位）
    "history": [
        {"date": _d(10, 18), "price": 1289},
        {"date": _d(10, 21), "price": 1299},
        {"date": _d(10, 24), "price": 1289},
        {"date": _d(10, 27), "price": 1279},
        {"date": _d(10, 30), "price": 1259},
        {"date": _d(11, 2), "price": 1199},
        {"date": _d(11, 5), "price": 1149},
        {"date": _d(11, 8), "price": 1099},   # 双 11 低点
        {"date": _d(11, 9), "price": 1129},
        {"date": _d(11, 10), "price": 1169},
        {"date": _d(11, 11), "price": 1199},
        {"date": _d(11, 12), "price": 1249},
        {"date": _d(11, 13), "price": 1279},
        {"date": _d(11, 14), "price": 1299},
        {"date": _d(11, 15), "price": 1299},
        {"date": _d(11, 16), "price": 1299},
    ],
    "reviews": [
        {"rating": 5, "text": "降噪效果超出预期，地铁里很安静", "date": _d(11, 9)},
        {"rating": 5, "text": "佩戴舒适，续航两天一充", "date": _d(11, 10)},
        {"rating": 4, "text": "音质不错，降噪一般", "date": _d(11, 11)},
        {"rating": 5, "text": "连接稳定，延迟低", "date": _d(11, 12)},
        {"rating": 2, "text": "续航虚标严重，宣传 40 小时实际 20 小时", "date": _d(11, 13)},
        {"rating": 5, "text": "做工精致，性价比高", "date": _d(11, 14)},
        {"rating": 4, "text": "整体满意，耳罩略夹耳朵", "date": _d(11, 15)},
        {"rating": 1, "text": "降噪开有底噪，客服不处理", "date": _d(11, 16)},
        {"rating": 5, "text": "比预期好很多", "date": _d(11, 10)},
        {"rating": 3, "text": "中规中矩，对得起价格", "date": _d(11, 12)},
    ],
}


# 商品二：电动牙刷 —— 接近历史最低，决策「买」
TOOTHBRUSH = {
    "id": "toothbrush",
    "name": "声波电动牙刷",
    "category": "个护",
    "prices": [
        {"platform": "淘宝", "price": 399, "coupon_price": 379},
        {"platform": "京东", "price": 409, "coupon_price": 399},
        {"platform": "拼多多", "price": 319, "coupon_price": 319},
    ],
    "history": [
        {"date": _d(10, 18), "price": 389},
        {"date": _d(10, 21), "price": 399},
        {"date": _d(10, 24), "price": 399},
        {"date": _d(10, 27), "price": 379},
        {"date": _d(10, 30), "price": 369},
        {"date": _d(11, 2), "price": 349},
        {"date": _d(11, 5), "price": 329},
        {"date": _d(11, 8), "price": 309},   # 双 11 低点
        {"date": _d(11, 9), "price": 319},
        {"date": _d(11, 10), "price": 329},
        {"date": _d(11, 11), "price": 339},
        {"date": _d(11, 12), "price": 329},
        {"date": _d(11, 13), "price": 319},
        {"date": _d(11, 14), "price": 319},
        {"date": _d(11, 15), "price": 319},
        {"date": _d(11, 16), "price": 319},
    ],
    "reviews": [
        {"rating": 5, "text": "清洁力强，用了一周牙齿明显变白", "date": _d(11, 9)},
        {"rating": 5, "text": "震动柔和，不刺激牙龈", "date": _d(11, 10)},
        {"rating": 4, "text": "续航久，充电一次用两周", "date": _d(11, 11)},
        {"rating": 5, "text": "配件齐全，送了四个刷头", "date": _d(11, 12)},
        {"rating": 4, "text": "手感好，防水没问题", "date": _d(11, 13)},
        {"rating": 3, "text": "档位太多用不过来，其他还行", "date": _d(11, 14)},
        {"rating": 5, "text": "比飞利浦同价位值", "date": _d(11, 15)},
        {"rating": 2, "text": "刷头偏硬，牙龈出血", "date": _d(11, 16)},
        {"rating": 5, "text": "颜值高，放在洗手台好看", "date": _d(11, 10)},
        {"rating": 4, "text": "整体推荐，入门首选", "date": _d(11, 12)},
    ],
}


# 商品三：保温杯 —— 评论去水发现严重刷单 + 质量差评，决策「换」
THERMOS = {
    "id": "thermos",
    "name": "不锈钢保温杯",
    "category": "日用",
    "prices": [
        {"platform": "淘宝", "price": 89, "coupon_price": 69},
        {"platform": "京东", "price": 99, "coupon_price": 79},
        {"platform": "拼多多", "price": 69, "coupon_price": 69},
    ],
    "history": [
        {"date": _d(10, 18), "price": 89},
        {"date": _d(10, 21), "price": 89},
        {"date": _d(10, 24), "price": 85},
        {"date": _d(10, 27), "price": 79},
        {"date": _d(10, 30), "price": 79},
        {"date": _d(11, 2), "price": 75},
        {"date": _d(11, 5), "price": 69},
        {"date": _d(11, 8), "price": 65},   # 双 11 低点
        {"date": _d(11, 9), "price": 69},
        {"date": _d(11, 10), "price": 69},
        {"date": _d(11, 11), "price": 69},
        {"date": _d(11, 12), "price": 69},
        {"date": _d(11, 13), "price": 69},
        {"date": _d(11, 14), "price": 69},
        {"date": _d(11, 15), "price": 69},
        {"date": _d(11, 16), "price": 69},
    ],
    "reviews": [
        # 疑似刷单好评：模板话术 + 集中在 11-05~07 三天
        {"rating": 5, "text": "质量很好，物流很快，满意", "date": _d(11, 5)},
        {"rating": 5, "text": "宝贝收到了，质量不错，物流很快", "date": _d(11, 5)},
        {"rating": 5, "text": "质量很好，物流很快，好评", "date": _d(11, 6)},
        {"rating": 5, "text": "收到宝贝了，质量不错，物流很快", "date": _d(11, 6)},
        {"rating": 5, "text": "质量很好，物流很快，推荐", "date": _d(11, 7)},
        {"rating": 5, "text": "宝贝质量不错，物流很快，满意", "date": _d(11, 7)},
        # 真实好评
        {"rating": 5, "text": "颜色好看，容量合适，办公室用刚好", "date": _d(11, 8)},
        {"rating": 4, "text": "外观可以，保温一般般", "date": _d(11, 9)},
        {"rating": 5, "text": "轻便，带出门方便", "date": _d(11, 10)},
        {"rating": 4, "text": "性价比可以，就是有点小", "date": _d(11, 11)},
        # 真实差评（指向质量缺陷）
        {"rating": 1, "text": "保温效果太差，早上倒的热水中午就温了，根本不保温", "date": _d(11, 9)},
        {"rating": 2, "text": "有异味，泡茶都有塑料味，不敢用", "date": _d(11, 10)},
        {"rating": 1, "text": "用了三天就漏水了，质量不行", "date": _d(11, 11)},
        {"rating": 2, "text": "材质看着廉价，盖子拧不紧", "date": _d(11, 13)},
        {"rating": 1, "text": "虚假宣传，根本不是304不锈钢", "date": _d(11, 14)},
        # 中性
        {"rating": 3, "text": "一般般，对得起这个价格", "date": _d(11, 8)},
        {"rating": 3, "text": "样子还行，功能一般", "date": _d(11, 12)},
        {"rating": 4, "text": "还行吧，凑合用", "date": _d(11, 15)},
        {"rating": 5, "text": "没想象中好但也不差", "date": _d(11, 16)},
        {"rating": 3, "text": "价格便宜，质量也就那样", "date": _d(11, 12)},
    ],
}


SAMPLE_PRODUCTS = [HEADPHONE, TOOTHBRUSH, THERMOS]
