# main.py
# 砍价侠基础版 - 入口
# 跑决策引擎，生成 HTML 决策卡报告
# 用法：python main.py   ->  生成 report.html

import html
from data import SAMPLE_PRODUCTS
from engine import analyze_product


# 配色（与产品品牌一致）
C_PRIMARY = "#0F6E56"
C_LIGHT = "#E1F5EE"
C_CORAL = "#D85A30"
C_RED = "#A32D2D"
C_TEXT = "#26261F"
C_MUTED = "#5F5E5A"
C_BORDER = "#E6E5DF"

# 决策动作配色
ACTION_COLOR = {"买": C_PRIMARY, "等": C_CORAL, "换": C_RED}


def plot_history_svg(price_history):
    """绘制 30 天历史价格折线 SVG，标注最低 / 最高 / 当前点。"""
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
    # 最低 / 最高参考线
    svg += f'<line x1="{pad_l}" y1="{y(lo):.1f}" x2="{w-pad_r}" y2="{y(lo):.1f}" stroke="{C_PRIMARY}" stroke-width="0.5" stroke-dasharray="3,3" opacity="0.5"/>'
    svg += f'<text x="{w-pad_r}" y="{y(lo)-4:.1f}" font-size="10" fill="{C_PRIMARY}" text-anchor="end">最低 ¥{lo}</text>'
    svg += f'<line x1="{pad_l}" y1="{y(hi):.1f}" x2="{w-pad_r}" y2="{y(hi):.1f}" stroke="{C_MUTED}" stroke-width="0.5" stroke-dasharray="3,3" opacity="0.4"/>'
    svg += f'<text x="{w-pad_r}" y="{y(hi)+12:.1f}" font-size="10" fill="{C_MUTED}" text-anchor="end">最高 ¥{hi}</text>'
    # 折线
    svg += f'<polyline points="{points}" fill="none" stroke="{C_PRIMARY}" stroke-width="1.5"/>'
    # 最低点
    svg += f'<circle cx="{x(min_idx):.1f}" cy="{y(lo):.1f}" r="3.5" fill="{C_PRIMARY}"/>'
    # 最高点
    svg += f'<circle cx="{x(max_idx):.1f}" cy="{y(hi):.1f}" r="3" fill="{C_MUTED}"/>'
    # 当前价点（脉冲）
    svg += f'<circle cx="{x(n-1):.1f}" cy="{cur_y:.1f}" r="5" fill="{C_CORAL}"/>'
    svg += f'<circle cx="{x(n-1):.1f}" cy="{cur_y:.1f}" r="9" fill="none" stroke="{C_CORAL}" stroke-width="1" opacity="0.4"/>'
    svg += f'<text x="{x(n-1):.1f}" y="{cur_y-10:.1f}" font-size="10" fill="{C_CORAL}" text-anchor="end">当前 ¥{cur}</text>'
    # x 轴日期首尾
    svg += f'<text x="{pad_l}" y="{h-6}" font-size="10" fill="{C_MUTED}">{history[0]["date"]}</text>'
    svg += f'<text x="{w-pad_r}" y="{h-6}" font-size="10" fill="{C_MUTED}" text-anchor="end">{history[-1]["date"]}</text>'
    svg += "</svg>"
    return svg


def render_product_card(result):
    """渲染单个商品的决策卡。"""
    p = result["product"]
    decision = result["decision"]
    comparison = result["comparison"]
    ph = result["price_history"]
    ra = result["review_analysis"]

    action = decision["action"]
    color = ACTION_COLOR[action]

    # 比价表行
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

    # 证据链
    evidence_html = "".join(
        f'<li style="margin-bottom:6px;color:{C_TEXT};line-height:1.6">{html.escape(e)}</li>'
        for e in decision["evidence"]
    )

    # 评论去水
    patterns_html = "".join(
        f'<div style="font-size:12.5px;color:{C_MUTED};line-height:1.6;padding:4px 0">· {html.escape(pat)}</div>'
        for pat in ra["patterns"]
    ) or '<div style="font-size:12.5px;color:{C_MUTED}">未检测到异常刷单信号</div>'.format(C_MUTED=C_MUTED)

    real_neg_html = ""
    if ra["real_negatives"]:
        neg_items = "".join(
            f'<div style="font-size:12px;color:{C_RED};padding:3px 0">{r["rating"]}星 · {html.escape(r["text"])}</div>'
            for r in ra["real_negatives"][:4]
        )
        real_neg_html = f'<div style="margin-top:8px"><div style="font-size:12px;color:{C_MUTED};margin-bottom:4px">真实差评（最多显示4条）</div>{neg_items}</div>'

    card = f'''
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
    return card


def render_html(results):
    cards = "".join(render_product_card(r) for r in results)
    actions_summary = " · ".join(
        f'{r["product"]["name"]}：{r["decision"]["action"]}' for r in results
    )
    html_doc = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>砍价侠 · 决策报告</title>
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
    <div class="slogan">现有工具给数据，砍价侠给决策 · {actions_summary}</div>
  </div>
  {cards}
  <div class="footer">
    本报告由砍价侠基础版生成 · 数据为演示用模拟数据，正式版通过数据源适配器接入联盟官方 API<br/>
    评论去水采用可解释规则（模板话术 + 发布时间集中度），不追求高准确率，追求每条判断可验证
  </div>
</div>
</body>
</html>'''
    return html_doc


def main():
    results = [analyze_product(p) for p in SAMPLE_PRODUCTS]
    html_doc = render_html(results)
    out_path = "report.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_doc)

    # 控制台摘要
    print("=" * 50)
    print("砍价侠 · 决策报告已生成 ->", out_path)
    print("=" * 50)
    for r in results:
        d = r["decision"]
        print(f"\n【{d['action']}】{r['product']['name']}")
        print(f"  {d['headline']}")
        print(f"  证据 {len(d['evidence'])} 条 | 评论去水 {r['review_analysis']['suspicious_count']} 条疑似")
    print("\n双击 report.html 查看完整决策卡。")


if __name__ == "__main__":
    main()
