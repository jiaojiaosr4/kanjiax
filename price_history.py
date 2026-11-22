"""保存淘宝联盟单品接口返回的本地价格记录。"""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

from engine import read_price


CHINA_TIME = timezone(timedelta(hours=8))


def record_price(product, *, database="price_history.sqlite3", observed_at=None):
    """同一商品每天保留最近一次到手价，返回近 30 个自然日的记录。"""
    item_id = product.get("id")
    checkout = read_price(product.get("coupon_price"))
    if not item_id or checkout is None:
        return []

    now = observed_at or datetime.now(CHINA_TIME)
    now = now.astimezone(CHINA_TIME)
    day = now.date()
    start = day - timedelta(days=29)
    key = (product["platform"], str(item_id))

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS price_observations (
                platform TEXT NOT NULL,
                item_id TEXT NOT NULL,
                day TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                listed_price REAL,
                checkout_price REAL NOT NULL,
                promotions TEXT NOT NULL,
                PRIMARY KEY (platform, item_id, day)
            )
        """)
        connection.execute("""
            INSERT INTO price_observations VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (platform, item_id, day) DO UPDATE SET
                observed_at = excluded.observed_at,
                listed_price = excluded.listed_price,
                checkout_price = excluded.checkout_price,
                promotions = excluded.promotions
            WHERE excluded.observed_at >= price_observations.observed_at
        """, (*key, day.isoformat(), now.isoformat(), read_price(product.get("price")),
              checkout, json.dumps(product.get("promotions") or [], ensure_ascii=False)))
        rows = connection.execute("""
            SELECT day, checkout_price FROM price_observations
            WHERE platform = ? AND item_id = ? AND day BETWEEN ? AND ?
            ORDER BY day
        """, (*key, start.isoformat(), day.isoformat())).fetchall()
    return [{"date": day, "price": price} for day, price in rows]
