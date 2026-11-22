"""保存淘宝联盟单品接口返回的本地价格记录。"""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

from engine import read_price


CHINA_TIME = timezone(timedelta(hours=8))


def _ensure_schema(connection):
    columns = {row[1] for row in connection.execute("PRAGMA table_info(price_observations)")}
    legacy = bool(columns) and "price_context" not in columns
    if legacy:
        connection.execute("ALTER TABLE price_observations RENAME TO legacy_price_observations")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS price_observations (
            platform TEXT NOT NULL,
            item_id TEXT NOT NULL,
            price_context TEXT NOT NULL,
            day TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            listed_price REAL,
            checkout_price REAL NOT NULL,
            promotions TEXT NOT NULL,
            PRIMARY KEY (platform, item_id, price_context, day)
        )
    """)
    if legacy:
        connection.execute("""
            INSERT INTO price_observations
            SELECT platform, item_id, '', day, observed_at,
                   listed_price, checkout_price, promotions
            FROM legacy_price_observations
        """)
        connection.execute("DROP TABLE legacy_price_observations")


def record_price(product, *, specification="", eligibility="",
                 database="price_history.sqlite3", observed_at=None):
    """保存今日到手价，返回近 30 日相同规格和优惠条件下的记录。"""
    item_id = product.get("id")
    checkout = read_price(product.get("coupon_price"))
    if not item_id or checkout is None:
        return []

    now = observed_at or datetime.now(CHINA_TIME)
    now = now.astimezone(CHINA_TIME)
    day = now.date()
    start = day - timedelta(days=29)
    specification, eligibility = specification.strip(), eligibility.strip()
    if bool(specification) != bool(eligibility):
        raise ValueError("记录可比历史价时需同时核对规格和优惠条件")
    promotions = sorted({
        text.strip() for text in product.get("promotions") or []
        if isinstance(text, str) and text.strip()
    })
    promotion_data = json.dumps(promotions, ensure_ascii=False)
    price_context = (
        json.dumps([specification, eligibility, product.get("price_source") or "", promotions],
                   ensure_ascii=False)
        if specification else ""
    )
    key = (product["platform"], str(item_id), price_context)

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        _ensure_schema(connection)
        connection.execute("""
            INSERT INTO price_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (platform, item_id, price_context, day) DO UPDATE SET
                observed_at = excluded.observed_at,
                listed_price = excluded.listed_price,
                checkout_price = excluded.checkout_price,
                promotions = excluded.promotions
            WHERE excluded.observed_at >= price_observations.observed_at
        """, (*key, day.isoformat(), now.isoformat(), read_price(product.get("price")),
              checkout, promotion_data))
        rows = connection.execute("""
            SELECT day, checkout_price FROM price_observations
            WHERE platform = ? AND item_id = ? AND price_context = ? AND day BETWEEN ? AND ?
            ORDER BY day
        """, (*key, start.isoformat(), day.isoformat())).fetchall()
    return [{"date": day, "price": price} for day, price in rows]
