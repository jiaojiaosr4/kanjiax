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
import sys

from data import SAMPLE_PRODUCTS
from engine import analyze_product, analyze_search_results


# 配色（与产品品牌一致）
C_PRIMARY = "#0F6E56"
C_LIGHT = "#E1F5EE"
C_CORAL = "#D85A30"
C_RED = "#A32D2D"
C_TEXT = "#26261F"
C_MUTED = "#5F5E5A"
C_BORDER = "#E6E5DF"

ACTION_COLOR = {"买": C_PRIMARY, "等": C_CORAL, "换": C_RED}


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
    lo, hi = min(prices), max(prices)
    span = hi - lo if hi != lo else 1
    n = len(history)

    def x(i):
        return pad_l + (plot_w * i / (n - 1))

    def y(p):
        return pad_t + plot_h - (plot_h * (p - lo) / span)

    points = " ".join(f"{x(i):.1f},{y(p['price']):.1f}" for i, p in enumerate(history))
    min_idx = prices.index(lo)
    max_idx = prices.index(hi)
    cur = price_history["current"]
    cur_y = y(cur)

    svg = f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img">'
    svg += f'<text x="{pad_l}" y="12" font-size="11" fill="{C_MUTED}">价格 ¥</text>'
    svg += f'<line x1="{pad_l}" y1="{y(lo):.1f}" x2="{w-pad_r}" y2="{y(lo):.1f}" stroke="{C_PRIMARY}" stroke-width="0.5" stroke-dasharray="3,3" opacity="0.5"/>'
    svg += f'<text x="{w-pad_r}" y="{y(lo)-4:.1f}" font-size="10" fill="{C_PRIMARY}" text-anchor="end">最低 ¥{lo}</text>'
    svg += f'<line x1="{pad_l}" y1="{y(hi):.1f}" x2="{w-pad_r}" y2="{y(hi):.1f}" stroke="{C_MUTED}" stroke-width="0.5" stroke-dasharray="3,3" opacity="0.4"/>'
    svg += f'<text x="{w-pad_r}" y="{y(hi)+12:.1f}" font-size="10" fill="{C_MUTED}" text-anchor="end">最高 ¥{hi}</text>'
    svg += f'<polyline points="{points}" fill="none" stroke="{C_PRIMARY}" stroke-width="1.5"/>'
    svg += f'<circle cx="{x(min_idx):.1f}" cy="{y(lo):.1f}" r="3.5" fill="{C_PRIMARY}"/>'
    svg += f'<circle cx="{x(max_idx):.1f}" cy="{y(hi):.1f}" r="3" fill="{C_MUTED}"/>'
    svg += f'<circle cx="{x(n-1):.1f}" cy="{cur_y:.1f}" r="5" fill="{C_CORAL}"/>'
    svg += f'<circle cx="{x(n-1):.1f}" cy="{cur_y:.1f}" r="9" fill="none" stroke="{C_CORAL}" stroke-width="1" opacity="0.4"/>'
    svg += f'<text x="{x(n-1):.1f}" y="{cur_y-10:.1f}" font-size="10" fill="{C_CORAL}" text-anchor="end">当前 ¥{cur}</text>'
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
        real_neg_html = f'<div style="margin-top:8px"><div style="font-size:12px;color:{C_MUTED};margin-bottom:4px">真实差评（最多显示4条）</div>{neg_items}</div>'

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
        <div style="font-size:12.5px;color:{C_MUTED};margin-bottom:6px">共 {ra["total"]} 条评论 · 疑似刷单 {ra["suspicious_count"]} 条（{int(ra["suspicious_ratio"]*100)}%）</div>
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
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER}">{p["volume"]}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER}">{p["commission_rate"]}%</td>'
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
        「{html.escape(keyword)}」搜索结果 · 共 {result["total"]} 个真实商品 · 按划算度排序
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
        划算分 = 券后折扣力度(40%) + 销量验证(40%) + 佣金率(20%) · 数据来自淘宝联盟官方 API（真实价格与佣金）
      </div>
    </div>
    '''


def render_html(body, title, source="淘宝联盟官方 API"):
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
  .footer {{ text-align:center; font-size:11.5px; color:{C_MUTED}; margin-top:24px; line-height:1.7; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>砍价侠 · 购物决策报告</h1>
    <div class="slogan">现有工具给数据，砍价侠给决策</div>
  </div>
  {body}
  <div class="footer">
    砍价侠基础版 · 真实数据来自{source}（配置后）/ 内置示例数据（默认）<br/>
    评论去水采用可解释规则 · 历史价格库与评论数据源为路线图项
  </div>
</div>
</body>
</html>'''


def run_sample_mode():
    """示例数据模式：演示决策引擎完整能力。"""
    results = [analyze_product(p) for p in SAMPLE_PRODUCTS]
    body = "".join(render_product_card(r) for r in results)
    actions = " · ".join(f'{r["product"]["name"]}：{r["decision"]["action"]}' for r in results)
    body = f'<div style="text-align:center;font-size:13px;color:{C_MUTED};margin-bottom:20px">{actions}</div>' + body
    html_doc = render_html(body, "砍价侠 · 决策报告（示例）")
    with open("report.html", "w", encoding="utf-8") as f:
        f.write(html_doc)
    print("=" * 50)
    print("示例数据模式 · 报告已生成 -> report.html")
    print("=" * 50)
    for r in results:
        d = r["decision"]
        print(f"\n【{d['action']}】{r['product']['name']}")
        print(f"  {d['headline']}")


def run_tbk_mode(keyword):
    """联盟 API 模式：搜索真实淘宝商品并分析推荐。"""
    from adapter import get_default_adapter
    adapter = get_default_adapter()

    # 判断是否联盟适配器
    if not hasattr(adapter, "search"):
        print("未配置淘宝联盟凭证，无法运行真实搜索模式。")
        print("请配置 config.json（参考 config.example.json）或设置环境变量：")
        print("  TBK_APP_KEY / TBK_APP_SECRET / TBK_ADZONE_ID")
        print("\n回退到示例数据模式：")
        run_sample_mode()
        return

    print(f"调用淘宝联盟 API 搜索「{keyword}」...")
    try:
        products = adapter.search(keyword, page_size=20)
    except Exception as e:
        print(f"联盟 API 调用失败：{e}")
        return

    if not products:
        print("未搜索到商品。")
        return

    print(f"获取到 {len(products)} 个真实商品，开始分析...")
    result = analyze_search_results(keyword, products)
    body = render_search_report(result)
    html_doc = render_html(body, f"砍价侠 · 「{keyword}」搜索报告")
    with open("report.html", "w", encoding="utf-8") as f:
        f.write(html_doc)

    print("=" * 50)
    print(f"联盟模式 · 报告已生成 -> report.html")
    print("=" * 50)
    if result["recommendation"]:
        print(f"\n推荐：{result['recommendation']['headline']}")
    print(f"\n划算分前 3：")
    for i, p in enumerate(result["ranked"][:3], 1):
        print(f"  {i}. {p['name'][:30]} | 券后¥{p['coupon_price']} | 划算分 {p['worth_score']}")


def run_item_mode(num_iid):
    """商品详情模式：按淘宝商品 ID 拉真实数据（关键词搜索权限审核期间可用）。"""
    from adapter import TbkAdapter

    adapter = TbkAdapter.from_config()
    if not adapter.configured():
        print("未配置淘宝联盟凭证。请先填写 config.json。")
        return

    # 支持传入完整淘宝商品链接，自动提取 ID
    raw = str(num_iid)
    if "uland.taobao.com" in raw:
        import re
        m = re.search(r"[?&]id=([^&]+)", raw)
        if m:
            num_iid = m.group(1)
        else:
            print(f"无法从 uland 链接中提取商品 ID：{raw}")
            return
    elif "item.taobao.com" in raw or "detail.tmall" in raw:
        import re
        m = re.search(r"[?&]id=(\d+)", raw)
        if m:
            num_iid = m.group(1)
        else:
            print(f"无法从链接中提取商品 ID：{raw}")
            return

    print(f"调用淘宝联盟商品详情 API（num_iid={num_iid}）...")
    try:
        products = adapter.item_info(num_iid)
    except Exception as e:
        print(f"API 调用失败：{e}")
        return

    if not products:
        print("未查到商品。可能该商品未参加淘宝客推广（联盟 API 只返回有佣金的商品）。")
        print("换个热门商品试试，或从淘宝客商品页复制 ID。")
        return

    p = products[0]
    discount = 0
    if p["price"] > 0:
        discount = round((1 - p["coupon_price"] / p["price"]) * 100)

    # 基础决策：根据折扣力度给买/等/换
    if discount >= 30:
        action, reason = "买", f"折扣力度 {discount}%，属于大促级别，建议入手"
    elif discount >= 15:
        action, reason = "买", f"折扣 {discount}%，价格合理，可以入手"
    elif discount > 0:
        action, reason = "等", f"折扣仅 {discount}%，非低位，建议等大促或找替代品"
    else:
        action, reason = "等", "无折扣信息，建议等待或比价"

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
            <tr><td style="padding:8px 12px;border-bottom:1px solid {C_BORDER};color:{C_MUTED}">原价</td><td style="padding:8px 12px;border-bottom:1px solid {C_BORDER}"><span style="text-decoration:line-through;color:{C_MUTED}">¥{p["price"]}</span></td></tr>
            <tr><td style="padding:8px 12px;border-bottom:1px solid {C_BORDER};color:{C_MUTED}">到手价</td><td style="padding:8px 12px;border-bottom:1px solid {C_BORDER};color:{C_PRIMARY};font-weight:600;font-size:16px">¥{p["coupon_price"]}</td></tr>
            <tr><td style="padding:8px 12px;border-bottom:1px solid {C_BORDER};color:{C_MUTED}">折扣</td><td style="padding:8px 12px;border-bottom:1px solid {C_BORDER};color:{C_CORAL}">{discount}%</td></tr>
            <tr><td style="padding:8px 12px;color:{C_MUTED}">销量</td><td style="padding:8px 12px">{p["volume"]}</td></tr>
          </table>
        </div>
        <div>
          {f'<img src="{p["pict_url"]}" style="width:100%;border-radius:8px;border:1px solid {C_BORDER}" />' if p.get("pict_url") else '<div style="background:#F6F7F5;border-radius:8px;height:120px;display:flex;align-items:center;justify-content:center;color:#999;font-size:12px">无主图</div>'}
          <div style="margin-top:8px;text-align:center">
            <a href="{p.get("url","")}" style="font-size:12px;color:{C_PRIMARY}" target="_blank">查看淘宝商品页 →</a>
          </div>
        </div>
      </div>
    </div>
    '''

    html_doc = render_html(card, f"砍价侠 · 商品详情（真实数据）")
    with open("report.html", "w", encoding="utf-8") as f:
        f.write(html_doc)

    print("=" * 50)
    print("商品详情模式 · 报告已生成 -> report.html")
    print("=" * 50)
    print(f"\n商品：{p['name'][:40]}")
    print(f"原价 ¥{p['price']} → 到手价 ¥{p['coupon_price']}（折扣 {discount}%）")
    print(f"决策：【{action}】{reason}")


def run_jd_mode(elite):
    """京东模式：京粉精选真实商品 -> 划算分排序 -> 买/等/换 + 证据链。

    权限边界（如实标注，不含虚构数据）：个人「导购媒体」仅基础权限包，
    实测只有京粉精选可用；关键词搜索 / 按 SKU 查详情 / 转链拿佣金
    需网站/APP 资质或更高等级（月 3 万单），当前账号拿不到。
    """
    from jd_adapter import JdAdapter
    from engine import analyze_search_results

    adapter = JdAdapter.from_config()
    if not adapter.configured():
        print("未配置京东联盟凭证。请先填写 config.json 的 jd 段（JD_APP_KEY / JD_APP_SECRET）。")
        return

    elite_id = 1
    if elite and str(elite).strip().isdigit():
        elite_id = int(str(elite).strip())

    print(f"调用京东联盟京粉精选 API（频道 eliteId={elite_id}）...")
    try:
        products = adapter.jingfen_select(elite_id=elite_id, page_size=20)
    except Exception as e:
        print(f"API 调用失败：{e}")
        return

    if not products:
        print("该频道暂无商品，换一个频道号试试（如 --jd 2）。")
        return

    print(f"获取到 {len(products)} 个真实京东商品，开始分析...")
    label = f"京东京粉精选 · 频道 {elite_id}"
    result = analyze_search_results(label, products)
    ranked = result["ranked"]
    orig = {str(p["id"]): p for p in products}

    # ===== 决策（可解释规则，全部基于真实字段）=====
    top = ranked[0]
    tp = orig.get(str(top["id"]), {})
    discount = top["discount_pct"]
    good = tp.get("good_rate", 0)
    orders = top["volume"]
    cheaper = [r for r in ranked[1:] if r["coupon_price"] < top["coupon_price"]]

    if discount >= 40 and good >= 95:
        action, color = "买", ACTION_COLOR["买"]
        reason = (f"券后 ¥{top['coupon_price']}，比标价省 {discount}%；好评率 {good:g}%、"
                  f"近 30 天 {orders} 单验证充分，属于破价好券，可入手")
    elif discount >= 15:
        action, color = "等", ACTION_COLOR["等"]
        reason = (f"券后省 {discount}%，力度中等（非破价位）；"
                  f"建议等大促或与淘宝同款比价后再定")
    else:
        action, color = "换", ACTION_COLOR["换"]
        alt = f"，本批有 {len(cheaper)} 款到手价更低" if cheaper else ""
        reason = (f"券后仅省 {discount}%，优惠偏弱{alt}；建议换同批里折扣更狠的真实款")

    # ===== 证据链（真实字段，不编历史价 / 评论内容）=====
    evidence = []
    if tp.get("coupon_discount", 0) > 0:
        q = tp.get("coupon_quota", 0)
        if q > 0:
            evidence.append(f"优惠券：满 {q:g} 减 {tp['coupon_discount']:g} 元（联盟接口真实券）")
        else:
            evidence.append(f"优惠券：减 {tp['coupon_discount']:g} 元（联盟接口真实券）")
    evidence.append(f"价格：标价 ¥{top['price']} → 券后到手 ¥{top['coupon_price']}（省 {discount}%）")
    word_of_mouth = f"{tp.get('comments', 0)} 条评论，好评率 {good:g}%"
    if tp.get("shop_score"):
        word_of_mouth += f"，店铺评分 {tp['shop_score']}"
    evidence.append("口碑：" + word_of_mouth)
    evidence.append(f"市场验证：近 30 天订单 {orders} 单；佣金率 {top['commission_rate']}%（平台认可度）")
    tags = tp.get("tags", [])
    if tags:
        evidence.append("商品标签：" + "、".join(tags[:4]) + "（接口原生标签）")
    if cheaper:
        c = cheaper[0]
        evidence.append(f"同类横向比价：本批还有到手价更低的「{c['name'][:20]}」¥{c['coupon_price']}，可作换的候选")
    evidence.append("划算分 = 券后折扣(40%) + 订单量(40%) + 佣金率(20%)，按真实字段计算")

    # ===== 渲染 =====
    rows = ""
    for i, r in enumerate(ranked[:15], 1):
        o = orig.get(str(r["id"]), {})
        is_top = i == 1
        bg = C_LIGHT if is_top else "#fff"
        gr = o.get("good_rate", 0)
        rows += (
            f'<tr style="background:{bg}">'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER};font-weight:{600 if is_top else 400}">{i}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER};max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{html.escape(r["name"])}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER}">¥{r["price"]}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER};color:{C_PRIMARY};font-weight:600">¥{r["coupon_price"]}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER};color:{C_CORAL}">{r["discount_pct"]}%</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER}">{r["commission_rate"]}%</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER}">{r["volume"]}</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER}">{gr:g}%</td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid {C_BORDER};font-weight:600;color:{C_PRIMARY}">{r["worth_score"]}</td>'
            f'</tr>'
        )

    ev_html = "".join(f'<li style="margin-bottom:6px;color:{C_TEXT};line-height:1.6">{html.escape(e)}</li>' for e in evidence)
    top_pict = tp.get("pict_url", "")
    pict_html = (f'<img src="{top_pict}" style="width:120px;height:120px;object-fit:contain;border-radius:8px;border:1px solid {C_BORDER}" />'
                 if top_pict else "")

    card = f'''
    <div style="background:{C_PRIMARY};color:#fff;padding:18px 22px;border-radius:12px;margin-bottom:20px">
      <div style="font-size:13px;opacity:0.85;margin-bottom:6px">最划算 · 划算分 {top['worth_score']} · 频道「{html.escape(tp.get('elite_name', label))}」</div>
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
        {html.escape(label)} · 共 {result['total']} 个真实商品 · 按划算度排序
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
        权限边界：个人导购媒体基础权限包仅京粉精选可用；关键词搜索、按 SKU 查详情、转链需网站/APP 资质或更高等级。<br/>
        历史价位、评论去水数据源待接入（本页不含任何虚构数字）。
      </div>
    </div>
    '''

    html_doc = render_html(card, "砍价侠 · 京东京粉精选决策报告（真实数据）", source="京东联盟官方 API（京粉精选）")
    with open("report.html", "w", encoding="utf-8") as f:
        f.write(html_doc)

    print("=" * 50)
    print("京东模式 · 报告已生成 -> report.html")
    print("=" * 50)
    print(f"\n商品：{top['name'][:40]}")
    print(f"标价 ¥{top['price']} → 券后 ¥{top['coupon_price']}（省 {discount}%）")
    print(f"决策：【{action}】{reason}")


def main():
    parser = argparse.ArgumentParser(description="砍价侠 - AI 购物决策引擎")
    parser.add_argument("--tbk", metavar="关键词", help="使用淘宝联盟 API 搜索真实商品（27939 权限已通过）")
    parser.add_argument("--item", metavar="商品ID或链接", help="按淘宝商品 ID/链接拉真实详情（已可用）")
    parser.add_argument("--jd", nargs="?", const="1", metavar="频道号", help="京东京粉精选真实商品决策（默认频道1，可指定 --jd 2，需配置 jd 凭证）")
    args = parser.parse_args()

    if args.tbk:
        run_tbk_mode(args.tbk)
    elif args.item:
        run_item_mode(args.item)
    elif args.jd:
        run_jd_mode(args.jd)
    else:
        run_sample_mode()


if __name__ == "__main__":
    main()
