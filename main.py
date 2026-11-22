# main.py
# 砍价侠基础版 - 入口
#
# 四种运行模式：
#   python main.py                        -> 示例数据模式（离线，演示决策引擎）
#   python main.py --item "商品ID或链接"   -> 淘宝商品详情模式（真实数据，已可用）
#   python main.py --tbk "耳机"           -> 淘宝联盟搜索模式（27939 权限已通过）
#   python main.py --jd [频道号]            -> 京东京粉精选真实商品决策（基础权限包，默认频道1）

import argparse
import html
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import parse_qs, urlsplit

from data import SAMPLE_PRODUCTS
from engine import analyze_price_history, analyze_product, analyze_search_results, discount_percentage
from price_history import record_price


# 配色（与产品品牌一致）
C_PRIMARY = "#0F6E56"
C_LIGHT = "#E1F5EE"
C_CORAL = "#D85A30"
C_RED = "#A32D2D"
C_TEXT = "#26261F"
C_MUTED = "#5F5E5A"
C_BORDER = "#E6E5DF"

ACTION_COLOR = {"买": C_PRIMARY, "等": C_CORAL, "换": C_RED}


TBK_SOURCE = "淘宝联盟官方 API"
JD_SOURCE = "京东联盟官方 API（京粉精选）"


def format_metric(value, prefix="", suffix=""):
    return "未知" if value is None else f"{prefix}{value:g}{suffix}"


def safe_url(url):
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    try:
        parsed = urlsplit(url)
    except ValueError:
        return ""
    return html.escape(url) if parsed.scheme in {"http", "https"} and parsed.hostname else ""


def plot_history_svg(price_history):
    """绘制 30 天历史价格折线 SVG。"""
    history = price_history["history"]
    if not history:
        return ""
    w, h = 560, 110
    pad_l, pad_r, pad_t, pad_b = 40, 20, 15, 25
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b

    prices = [p["price"] for p in history]
    dates = [date.fromisoformat(p["date"]) for p in history]
    lo, hi = min(prices), max(prices)
    cur = price_history["current"]
    axis_lo, axis_hi = min(lo, cur), max(hi, cur)
    span = axis_hi - axis_lo or 1
    days = max(1, (dates[-1] - dates[0]).days)

    def x(i):
        return pad_l + plot_w * (dates[i] - dates[0]).days / days

    def y(p):
        return pad_t + plot_h - (plot_h * (p - axis_lo) / span)

    points = " ".join(f"{x(i):.1f},{y(p['price']):.1f}" for i, p in enumerate(history))
    min_idx = prices.index(lo)
    max_idx = prices.index(hi)
    cur_y = y(cur)
    current_x = x(len(history) - 1)

    svg = f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img">'
    svg += f'<text x="{pad_l}" y="12" font-size="11" fill="{C_MUTED}">价格 ¥</text>'
    svg += f'<line x1="{pad_l}" y1="{y(lo):.1f}" x2="{w-pad_r}" y2="{y(lo):.1f}" stroke="{C_PRIMARY}" stroke-width="0.5" stroke-dasharray="3,3" opacity="0.5"/>'
    svg += f'<text x="{w-pad_r}" y="{y(lo)-4:.1f}" font-size="10" fill="{C_PRIMARY}" text-anchor="end">最低 ¥{lo}</text>'
    svg += f'<line x1="{pad_l}" y1="{y(hi):.1f}" x2="{w-pad_r}" y2="{y(hi):.1f}" stroke="{C_MUTED}" stroke-width="0.5" stroke-dasharray="3,3" opacity="0.4"/>'
    svg += f'<text x="{w-pad_r}" y="{y(hi)+12:.1f}" font-size="10" fill="{C_MUTED}" text-anchor="end">最高 ¥{hi}</text>'
    svg += f'<polyline points="{points}" fill="none" stroke="{C_PRIMARY}" stroke-width="1.5"/>'
    svg += f'<circle cx="{x(min_idx):.1f}" cy="{y(lo):.1f}" r="3.5" fill="{C_PRIMARY}"/>'
    svg += f'<circle cx="{x(max_idx):.1f}" cy="{y(hi):.1f}" r="3" fill="{C_MUTED}"/>'
    svg += f'<circle cx="{current_x:.1f}" cy="{cur_y:.1f}" r="5" fill="{C_CORAL}"/>'
    svg += f'<circle cx="{current_x:.1f}" cy="{cur_y:.1f}" r="9" fill="none" stroke="{C_CORAL}" stroke-width="1" opacity="0.4"/>'
    svg += f'<text x="{current_x:.1f}" y="{cur_y-10:.1f}" font-size="10" fill="{C_CORAL}" text-anchor="end">当前 ¥{cur}</text>'
    svg += f'<text x="{pad_l}" y="{h-6}" font-size="10" fill="{C_MUTED}">{history[0]["date"]}</text>'
    svg += f'<text x="{w-pad_r}" y="{h-6}" font-size="10" fill="{C_MUTED}" text-anchor="end">{history[-1]["date"]}</text>'
    svg += "</svg>"
    return svg


def render_product_card(result):
    """示例模式：渲染单个商品的决策卡。"""
    p = result["product"]
    decision = result["decision"]
    comparison = result["comparison"]
    ph = result["price_history"]
    ra = result["review_analysis"]

    action = decision["action"]
    color = ACTION_COLOR[action]

    price_rows = ""
    for pr in comparison["sorted"]:
        cp = pr.get("coupon_price", pr["price"])
        is_cheap = pr is comparison["cheapest"]
        tag = '<span style="color:#0F6E56;font-weight:600">最便宜</span>' if is_cheap else ""
        price_rows += (
            f'<tr>'
            f'<td style="padding:8px 12px;border-bottom:1px solid {C_BORDER}">{html.escape(pr["platform"])}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid {C_BORDER}">¥{pr["price"]}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid {C_BORDER};color:{C_PRIMARY};font-weight:600">¥{cp}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid {C_BORDER}">{tag}</td>'
            f'</tr>'
        )

    evidence_html = "".join(
        f'<li style="margin-bottom:6px;color:{C_TEXT};line-height:1.6">{html.escape(e)}</li>'
        for e in decision["evidence"]
    )

    patterns_html = "".join(
        f'<div style="font-size:12.5px;color:{C_MUTED};line-height:1.6;padding:4px 0">· {html.escape(pat)}</div>'
        for pat in ra["patterns"]
    ) or f'<div style="font-size:12.5px;color:{C_MUTED}">未检测到异常刷单信号</div>'

    real_neg_html = ""
    if ra["real_negatives"]:
        neg_items = "".join(
            f'<div style="font-size:12px;color:{C_RED};padding:3px 0">{r["rating"]}星 · {html.escape(r["text"])}</div>'
            for r in ra["real_negatives"][:4]
        )
        real_neg_html = f'<div style="margin-top:8px"><div style="font-size:12px;color:{C_MUTED};margin-bottom:4px">低星评论（最多显示4条）</div>{neg_items}</div>'

    return f'''
    <div style="background:#fff;border:1px solid {C_BORDER};border-radius:14px;padding:24px;margin-bottom:20px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
        <div>
          <div style="font-size:18px;font-weight:600;color:{C_TEXT}">{html.escape(p["name"])}</div>
          <div style="font-size:12px;color:{C_MUTED};margin-top:2px">{html.escape(p["category"])} · 当前到手价 ¥{result["current_price"]}</div>
        </div>
        <div style="background:{color};color:#fff;padding:10px 22px;border-radius:10px;font-size:22px;font-weight:600">{action}</div>
      </div>
      <div style="background:{C_LIGHT};border-left:4px solid {color};padding:12px 16px;border-radius:8px;margin-bottom:16px;font-size:14px;color:{C_TEXT};line-height:1.6">
        {html.escape(decision["headline"])}
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
        <div>
          <div style="font-size:13px;font-weight:600;color:{C_PRIMARY};margin-bottom:8px">全网比价</div>
          <table style="width:100%;border-collapse:collapse;font-size:12.5px;color:{C_TEXT}">
            <thead><tr style="background:#F6F7F5">
              <th style="padding:8px 12px;text-align:left;border-bottom:1px solid {C_BORDER}">平台</th>
              <th style="padding:8px 12px;text-align:left;border-bottom:1px solid {C_BORDER}">标价</th>
              <th style="padding:8px 12px;text-align:left;border-bottom:1px solid {C_BORDER}">券后</th>
              <th style="padding:8px 12px;border-bottom:1px solid {C_BORDER}"></th>
            </tr></thead>
            <tbody>{price_rows}</tbody>
          </table>
        </div>
        <div>
          <div style="font-size:13px;font-weight:600;color:{C_PRIMARY};margin-bottom:8px">30 天价格走势</div>
          {plot_history_svg(ph)}
          <div style="font-size:11.5px;color:{C_MUTED};margin-top:6px">{ph["position_label"]} · 最低 ¥{ph["min"]} · 均价 ¥{ph["avg"]}</div>
        </div>
      </div>
      <div style="margin-top:18px">
        <div style="font-size:13px;font-weight:600;color:{C_PRIMARY};margin-bottom:8px">评论去水（可解释规则）</div>
        <div style="font-size:12.5px;color:{C_MUTED};margin-bottom:6px">共 {ra["total"]} 条评论 · 命中疑似模板规则 {ra["suspicious_count"]} 条（{ra["suspicious_ratio"]:.0%}）</div>
        {patterns_html}
        {real_neg_html}
      </div>
      <div style="margin-top:18px;background:#F6F7F5;border-radius:8px;padding:14px 16px">
        <div style="font-size:13px;font-weight:600;color:{C_PRIMARY};margin-bottom:8px">证据链</div>
        <ul style="margin:0;padding-left:18px">{evidence_html}</ul>
      </div>
    </div>
    '''


def render_search_report(result):
    """联盟模式：渲染真实商品搜索结果报告。"""
    keyword = result["keyword"]
    ranked = result["ranked"]
    rec = result["recommendation"]

    rows = ""
    for i, p in enumerate(ranked[:15], 1):
        is_top = i == 1
        row_bg = C_LIGHT if is_top else "#fff"
        rows += (
            f'<tr style="background:{row_bg}">'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER};font-weight:{600 if is_top else 400}">{i}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER};max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{html.escape(p["name"])}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER}">¥{p["price"]}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER};color:{C_PRIMARY};font-weight:600">¥{p["coupon_price"]}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER};color:{C_CORAL}">{p["discount_pct"]}%</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER}">{format_metric(p["volume"])}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER}">{format_metric(p["commission_rate"], suffix="%")}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER};font-weight:600;color:{C_PRIMARY}">{p["worth_score"]}</td>'
            f'</tr>'
        )

    rec_html = ""
    if rec:
        rec_html = f'''
        <div style="background:{C_PRIMARY};color:#fff;padding:18px 22px;border-radius:12px;margin-bottom:20px">
          <div style="font-size:13px;opacity:0.8;margin-bottom:6px">最划算推荐 · 划算分 {rec["worth_score"]}</div>
          <div style="font-size:16px;font-weight:600;line-height:1.5">{html.escape(rec["headline"])}</div>
        </div>
        '''

    return f'''
    {rec_html}
    <div style="background:#fff;border:1px solid {C_BORDER};border-radius:14px;padding:20px;margin-bottom:20px">
      <div style="font-size:15px;font-weight:600;color:{C_TEXT};margin-bottom:14px">
        「{html.escape(keyword)}」搜索结果 · 共 {result["total"]} 件 · {result["unranked"]} 件价格不完整，未计入排名
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:12.5px;color:{C_TEXT}">
        <thead><tr style="background:#F6F7F5;color:{C_MUTED}">
          <th style="padding:8px 10px;text-align:left;border-bottom:1px solid {C_BORDER}">排名</th>
          <th style="padding:8px 10px;text-align:left;border-bottom:1px solid {C_BORDER}">商品</th>
          <th style="padding:8px 10px;text-align:left;border-bottom:1px solid {C_BORDER}">标价</th>
          <th style="padding:8px 10px;text-align:left;border-bottom:1px solid {C_BORDER}">券后</th>
          <th style="padding:8px 10px;text-align:left;border-bottom:1px solid {C_BORDER}">折扣</th>
          <th style="padding:8px 10px;text-align:left;border-bottom:1px solid {C_BORDER}">销量</th>
          <th style="padding:8px 10px;text-align:left;border-bottom:1px solid {C_BORDER}">佣金</th>
          <th style="padding:8px 10px;border-bottom:1px solid {C_BORDER}">划算分</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
      <div style="font-size:11.5px;color:{C_MUTED};margin-top:14px;line-height:1.6">
        划算分 = 券后折扣 × 60% + 日销归一化得分 × 40%（50 件封顶）
      </div>
    </div>
    '''


def render_html(body, title, source):
    generated = datetime.now().astimezone().isoformat(timespec="seconds")
    title = html.escape(title)
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, "Microsoft YaHei", "PingFang SC", sans-serif; background:#F6F7F5; margin:0; padding:32px; color:{C_TEXT}; }}
  .container {{ max-width:900px; margin:0 auto; }}
  .header {{ text-align:center; margin-bottom:28px; }}
  .header h1 {{ font-size:26px; color:{C_PRIMARY}; margin:0 0 6px; }}
  .header .slogan {{ font-size:13px; color:{C_MUTED}; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>{title}</h1>
    <div class="slogan">数据来源 · {html.escape(source)}　｜　生成时间 · {generated}</div>
  </div>
  {body}
</div>
</body>
</html>'''


def write_report(body, title, source):
    target = Path("report.html")
    temporary_path = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(render_html(body, title, source))
        temporary_path.replace(target)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def run_sample_mode():
    """示例数据模式：演示决策引擎完整能力。"""
    results = [analyze_product(p) for p in SAMPLE_PRODUCTS]
    body = "".join(render_product_card(r) for r in results)
    actions = " · ".join(f'{r["product"]["name"]}：{r["decision"]["action"]}' for r in results)
    body = f'<div style="text-align:center;font-size:13px;color:{C_MUTED};margin-bottom:20px">{actions}</div>' + body
    write_report(body, "砍价侠 · 决策报告（示例）", "内置模拟数据，供离线演示")
    print("=" * 50)
    print("示例数据模式 · 报告已生成 -> report.html")
    print("=" * 50)
    for r in results:
        d = r["decision"]
        print(f"\n【{d['action']}】{r['product']['name']}")
        print(f"  {d['headline']}")


def run_tbk_mode(keyword):
    """联盟 API 模式：搜索真实淘宝商品并分析推荐。"""
    from adapter import TbkAdapter

    adapter = TbkAdapter.load()
    if not adapter.configured():
        raise RuntimeError("请配置淘宝联盟凭证（config.json 或 TBK_* 环境变量）")
    print(f"调用淘宝联盟 API 搜索「{keyword}」...")
    products = adapter.search(keyword, page_size=20)
    if not products:
        raise RuntimeError("淘宝联盟未返回匹配商品")

    result = analyze_search_results(keyword, products)
    body = render_search_report(result)
    write_report(body, f"砍价侠 · 「{keyword}」搜索报告", TBK_SOURCE)

    print("=" * 50)
    print(f"联盟模式 · 报告已生成 -> report.html")
    print("=" * 50)
    if result["recommendation"]:
        print(f"\n推荐：{result['recommendation']['headline']}")
    if result["ranked"]:
        print("\n划算分前 3：")
    for i, p in enumerate(result["ranked"][:3], 1):
        print(f"  {i}. {p['name'][:30]} | 券后¥{p['coupon_price']} | 划算分 {p['worth_score']}")


def taobao_item_id(text):
    raw = text.strip()
    parsed = urlsplit(raw)
    if not parsed.scheme and not parsed.netloc and raw:
        return raw
    if parsed.scheme in {"http", "https"} and parsed.hostname in {
        "uland.taobao.com", "item.taobao.com", "detail.tmall.com", "detail.tmall.hk",
    }:
        item_id = parse_qs(parsed.query).get("id", [""])[0]
        if item_id:
            return item_id
    raise ValueError("请输入淘宝商品 ID 或带 id 参数的淘宝、天猫商品链接")


def run_item_mode(query, track_price=False):
    """查询淘宝联盟单品数据，可选保存当日到手价。"""
    from adapter import TbkAdapter

    adapter = TbkAdapter.load()
    if not adapter.configured():
        raise RuntimeError("请配置淘宝联盟凭证（config.json 或 TBK_* 环境变量）")

    item_id = taobao_item_id(query)
    print(f"调用淘宝联盟商品详情 API（商品 ID={item_id}）...")
    products = adapter.item_info(item_id)
    if not products:
        raise RuntimeError("淘宝联盟未返回此商品的推广数据")

    p = products[0]
    discount = discount_percentage(p["price"], p["coupon_price"])
    history = record_price(p) if track_price else []
    history_analysis = analyze_price_history(history, p["coupon_price"]) if history else None
    history_card = ""
    if track_price:
        history_card = '<p>缺少可记录的到手价或商品 ID，本次未新增价格记录。</p>'
        if history_analysis:
            history_card = (
                '<h3>最近 30 个自然日内的到手价记录</h3>'
                f'<p>共记录 {len(history)} 天，以当天最近一次查询为准，'
                '价格可能随促销及规格变化。至少记录 3 天后使用历史价信号。</p>'
                f'{plot_history_svg(history_analysis)}'
            )

    if discount is None:
        action, reason = "资料不足", "联盟未提供完整标价和到手价，暂无法计算折扣并推荐。"
    elif len(history) >= 3 and history_analysis["position"] == "高位":
        gap = history_analysis["distance_to_low_pct"]
        minimum = history_analysis["min"]
        action, reason = "等", f"到手价较已记录最低价 ¥{minimum:g} 高 {gap:g}%，可继续观察。"
    elif discount >= 15:
        action, reason = "买", f"当前到手价比接口标价低 {discount:g}%，可考虑入手。"
    elif discount > 0:
        action, reason = "等", f"当前到手价比接口标价低 {discount:g}%，可等更合适的促销。"
    else:
        action, reason = "等", "当前到手价无可确认的折扣，可继续观察。"

    listed_text = format_metric(p["price"], "¥")
    checkout_text = format_metric(p["coupon_price"], "¥")
    discount_text = format_metric(discount, suffix="%")
    picture = safe_url(p.get("pict_url"))
    item_url = safe_url(p.get("url"))
    image = f'<img src="{picture}" style="width:100%;border-radius:8px" alt="商品图" />' if picture else ""
    link = f'<a href="{item_url}" target="_blank" rel="noopener noreferrer">查看淘宝商品页 →</a>' if item_url else ""
    color = ACTION_COLOR.get(action, C_MUTED)

    card = f'''
    <div style="background:#fff;border:1px solid {C_BORDER};border-radius:14px;padding:24px;margin-bottom:20px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
        <div>
          <div style="font-size:18px;font-weight:600;color:{C_TEXT}">{html.escape(p["name"])}</div>
          <div style="font-size:12px;color:{C_MUTED};margin-top:2px">淘宝 · {html.escape(p.get("nick",""))}</div>
        </div>
        <div style="background:{color};color:#fff;padding:10px 22px;border-radius:10px;font-size:22px;font-weight:600">{action}</div>
      </div>
      <div style="background:{C_LIGHT};border-left:4px solid {color};padding:12px 16px;border-radius:8px;margin-bottom:16px;font-size:14px;color:{C_TEXT};line-height:1.6">
        {reason}
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
        <div>
          <div style="font-size:13px;font-weight:600;color:{C_PRIMARY};margin-bottom:8px">真实价格（联盟 API）</div>
          <table style="width:100%;border-collapse:collapse;font-size:13px;color:{C_TEXT}">
            <tr><td style="padding:8px 12px;border-bottom:1px solid {C_BORDER};color:{C_MUTED}">原价</td><td style="padding:8px 12px;border-bottom:1px solid {C_BORDER}"><span style="text-decoration:line-through;color:{C_MUTED}">{listed_text}</span></td></tr>
            <tr><td style="padding:8px 12px;border-bottom:1px solid {C_BORDER};color:{C_MUTED}">到手价</td><td style="padding:8px 12px;border-bottom:1px solid {C_BORDER};color:{C_PRIMARY};font-weight:600;font-size:16px">{checkout_text}</td></tr>
            <tr><td style="padding:8px 12px;border-bottom:1px solid {C_BORDER};color:{C_MUTED}">折扣</td><td style="padding:8px 12px;border-bottom:1px solid {C_BORDER};color:{C_CORAL}">{discount_text}</td></tr>
            <tr><td style="padding:8px 12px;color:{C_MUTED}">销量</td><td style="padding:8px 12px">{format_metric(p["volume"])}</td></tr>
          </table>
        </div>
        <div>
          {image}
          <div style="margin-top:8px;text-align:center">{link}</div>
        </div>
      </div>
    </div>
    {history_card}
    '''

    write_report(card, f"砍价侠 · 淘宝单品 {item_id}", TBK_SOURCE)

    print("=" * 50)
    print("商品详情模式 · 报告已生成 -> report.html")
    print("=" * 50)
    print(f"\n商品：{p['name'][:40]}")
    print(f"标价 {listed_text} → 到手价 {checkout_text}（折扣 {discount_text}）")
    print(f"决策：【{action}】{reason}")


def run_jd_mode(elite):
    """京东模式：京粉精选真实商品 -> 划算分排序 -> 买/等/换 + 证据链。

    权限边界（如实标注，不含虚构数据）：个人「导购媒体」仅基础权限包，
    实测只有京粉精选可用；关键词搜索 / 按 SKU 查详情 / 转链拿佣金
    需网站/APP 资质或更高等级（月 3 万单），当前账号拿不到。
    """
    from jd_adapter import JdAdapter

    adapter = JdAdapter.from_config()
    if not adapter.configured():
        raise RuntimeError("请配置京东联盟凭证（config.json 或 JD_* 环境变量）")

    print(f"调用京东联盟京粉精选 API（频道 eliteId={elite}）...")
    products = adapter.jingfen_select(elite_id=elite, page_size=20)
    if not products:
        raise RuntimeError("该频道暂无商品，可换一个频道号试试")

    label = f"京东京粉精选 · 频道 {elite}"
    title = f"砍价侠 · {label}"
    result = analyze_search_results(label, products)
    ranked = result["ranked"]
    if not ranked:
        write_report(f'<p>本频道返回 {result["total"]} 件商品，均缺少标价或到手价，暂无法推荐。</p>', title, JD_SOURCE)
        print("商品价格不完整，已生成无推荐结果的 report.html")
        return

    top = ranked[0]
    tp = top["product"]
    discount = top["discount_pct"]
    good = tp.get("good_rate")
    orders = top["volume"]
    category_id = tp.get("category_id")
    similar = [
        candidate for candidate in ranked[1:]
        if category_id and candidate["product"].get("category_id") == category_id
        and candidate["id"] and top["id"] and candidate["id"] != top["id"]
        and candidate["coupon_price"] < top["coupon_price"]
    ]
    alternative = min(similar, key=lambda candidate: candidate["coupon_price"], default=None)

    if discount >= 40 and good is not None and good >= 95 and orders:
        action = "买"
        reason = f"券后省 {discount:g}%，好评率 {good:g}%，近 30 天 {orders:g} 单，可考虑入手。"
    elif discount < 15 and alternative:
        action = "换"
        reason = f"当前价较标价低 {discount:g}%，有到手价更低的同品类候选。选购前请核对型号和规格。"
    else:
        action = "等"
        reason = f"当前价较标价低 {discount:g}%，近 30 天订单 {format_metric(orders)}，好评率 {format_metric(good, suffix='%')}，可以继续观察。"
    color = ACTION_COLOR[action]

    evidence = [
        f"价格：标价 ¥{top['price']:g} → 到手价 ¥{top['coupon_price']:g}（较标价低 {discount:g}%）",
        f"口碑：评论数 {format_metric(tp.get('comments'))}，好评率 {format_metric(good, suffix='%')}",
        f"近 30 天订单：{format_metric(orders)}",
    ]
    promotions = tp.get("promotions") or []
    if promotions:
        evidence.append("接口列出的优惠券（可用性与叠加条件以结算页为准）：" + "、".join(promotions))
    if alternative:
        evidence.append(f"同品类较低价候选：{alternative['name'][:32]}，到手价 ¥{alternative['coupon_price']:g}，请核对规格。")

    # ===== 渲染 =====
    rows = ""
    for i, r in enumerate(ranked[:15], 1):
        is_top = i == 1
        bg = C_LIGHT if is_top else "#fff"
        gr = r["product"].get("good_rate")
        rows += (
            f'<tr style="background:{bg}">'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER};font-weight:{600 if is_top else 400}">{i}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER};max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{html.escape(r["name"])}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER}">¥{r["price"]}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER};color:{C_PRIMARY};font-weight:600">¥{r["coupon_price"]}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER};color:{C_CORAL}">{r["discount_pct"]}%</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER}">{format_metric(r["commission_rate"], suffix="%")}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER}">{format_metric(r["volume"])}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER}">{format_metric(gr, suffix="%")}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER};font-weight:600;color:{C_PRIMARY}">{r["worth_score"]}</td>'
            f'</tr>'
        )

    ev_html = "".join(f'<li style="margin-bottom:6px;color:{C_TEXT};line-height:1.6">{html.escape(e)}</li>' for e in evidence)
    top_pict = safe_url(tp.get("pict_url"))
    pict_html = (f'<img src="{top_pict}" style="width:120px;height:120px;object-fit:contain;border-radius:8px;border:1px solid {C_BORDER}" />'
                 if top_pict else "")

    card = f'''
    <div style="background:{C_PRIMARY};color:#fff;padding:18px 22px;border-radius:12px;margin-bottom:20px">
      <div style="font-size:13px;opacity:0.85;margin-bottom:6px">最划算 · 划算分 {top['worth_score']} · 频道「{html.escape(tp.get('elite_name') or label)}」</div>
      <div style="font-size:16px;font-weight:600;line-height:1.6">{html.escape(top['name'][:40])}</div>
    </div>
    <div style="background:#fff;border:1px solid {C_BORDER};border-radius:14px;padding:22px;margin-bottom:20px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
        <div style="font-size:16px;font-weight:600;color:{C_TEXT}">{html.escape(top['name'][:34])}</div>
        <div style="background:{color};color:#fff;padding:9px 22px;border-radius:10px;font-size:22px;font-weight:600">{action}</div>
      </div>
      <div style="background:{C_LIGHT};border-left:4px solid {color};padding:12px 16px;border-radius:8px;margin-bottom:16px;font-size:14px;color:{C_TEXT};line-height:1.7">
        {html.escape(reason)}
      </div>
      <div style="display:flex;gap:18px;align-items:flex-start">
        {pict_html}
        <div style="flex:1">
          <div style="font-size:13px;font-weight:600;color:{C_PRIMARY};margin-bottom:8px">证据链（全部来自京东联盟接口真实字段）</div>
          <ul style="margin:0;padding-left:18px;font-size:12.5px">{ev_html}</ul>
        </div>
      </div>
    </div>
    <div style="background:#fff;border:1px solid {C_BORDER};border-radius:14px;padding:20px;margin-bottom:20px">
      <div style="font-size:15px;font-weight:600;color:{C_TEXT};margin-bottom:14px">
        {html.escape(label)} · 共 {result["total"]} 件 · {result["unranked"]} 件价格不完整，未计入排名
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:12.5px;color:{C_TEXT}">
        <thead><tr style="background:#F6F7F5;color:{C_MUTED}">
          <th style="padding:8px 10px;text-align:left;border-bottom:1px solid {C_BORDER}">#</th>
          <th style="padding:8px 10px;text-align:left;border-bottom:1px solid {C_BORDER}">商品</th>
          <th style="padding:8px 10px;text-align:left;border-bottom:1px solid {C_BORDER}">标价</th>
          <th style="padding:8px 10px;text-align:left;border-bottom:1px solid {C_BORDER}">券后</th>
          <th style="padding:8px 10px;text-align:left;border-bottom:1px solid {C_BORDER}">折扣</th>
          <th style="padding:8px 10px;text-align:left;border-bottom:1px solid {C_BORDER}">佣金</th>
          <th style="padding:8px 10px;text-align:left;border-bottom:1px solid {C_BORDER}">30天单</th>
          <th style="padding:8px 10px;text-align:left;border-bottom:1px solid {C_BORDER}">好评</th>
          <th style="padding:8px 10px;border-bottom:1px solid {C_BORDER}">划算分</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
      <div style="font-size:11.5px;color:{C_MUTED};margin-top:14px;line-height:1.7">
        数据来源：京东联盟官方 API（jd.union.open.goods.jingfen.query 京粉精选）· 真实价格 / 券 / 佣金 / 订单 / 好评<br/>
        划算分 = 券后折扣 × 60% + 近 30 天订单归一化得分 × 40%（1,500 单封顶）。<br/>
        历史价位、评论去水数据源待接入（本页不含任何虚构数字）。
      </div>
    </div>
    '''

    write_report(card, title, JD_SOURCE)

    print("=" * 50)
    print("京东模式 · 报告已生成 -> report.html")
    print("=" * 50)
    print(f"\n商品：{top['name'][:40]}")
    print(f"标价 ¥{top['price']} → 券后 ¥{top['coupon_price']}（省 {discount}%）")
    print(f"决策：【{action}】{reason}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="砍价侠 - 购物决策引擎")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--tbk", metavar="关键词", help="用淘宝联盟 API 搜索商品")
    modes.add_argument("--item", metavar="商品ID或链接", help="用淘宝联盟 API 查询商品详情")
    modes.add_argument("--jd", nargs="?", const=1, type=int, metavar="频道号", help="用京东联盟 API 查询京粉精选，默认频道 1")
    parser.add_argument("--track-price", action="store_true", help="在淘宝单品模式下保存今日到手价")
    args = parser.parse_args(argv)

    if args.track_price and not args.item:
        parser.error("--track-price 仅用于 --item")
    if args.jd is not None and args.jd < 1:
        parser.error("--jd 频道号应为正整数")

    title = "砍价侠 · 离线示例"
    try:
        if args.tbk is not None:
            title = f"砍价侠 · 淘宝搜索「{args.tbk}」"
            run_tbk_mode(args.tbk)
        elif args.item is not None:
            title = f"砍价侠 · 淘宝单品「{args.item}」"
            run_item_mode(args.item, args.track_price)
        elif args.jd is not None:
            title = f"砍价侠 · 京粉精选频道 {args.jd}"
            run_jd_mode(args.jd)
        else:
            run_sample_mode()
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
        print(f"运行失败：{error}", file=sys.stderr)
        try:
            write_report(f"<p>{html.escape(str(error))}</p>", title + "（运行失败）", "本次未生成商品结果")
        except OSError as report_error:
            print(f"未能更新 report.html，请核对报告时间：{report_error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
