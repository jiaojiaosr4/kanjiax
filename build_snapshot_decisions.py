"""从现有商品快照生成独立课堂页内的决策数据。"""

import argparse
import json
from pathlib import Path

from engine import taobao_price_decision


DATA_PREFIX = "const DATA = "
DECISIONS_PREFIX = "const SNAPSHOT_DECISIONS = "
PAGE = Path(__file__).with_name("index.html")


def render_snapshot(page):
    lines = page.splitlines(keepends=True)
    data_line = next(line for line in lines if line.startswith(DATA_PREFIX))
    data = json.loads(data_line[len(DATA_PREFIX):].rstrip()[:-1])
    decisions = {
        keyword: {product["id"]: taobao_price_decision(product) for product in products}
        for keyword, products in data["keywords"].items()
    }
    payload = json.dumps(decisions, ensure_ascii=False, separators=(",", ":")).replace("<", r"\u003c")
    line_index = next(i for i, line in enumerate(lines) if line.startswith(DECISIONS_PREFIX))
    lines[line_index] = f"{DECISIONS_PREFIX}{payload};\n"
    return "".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="检查课堂页决策是否与 Python 规则一致")
    args = parser.parse_args()
    original = PAGE.read_text(encoding="utf-8")
    generated = render_snapshot(original)
    if args.check:
        parser.exit(0 if original == generated else 1, None if original == generated else "请重新生成课堂页决策\n")
    elif original != generated:
        PAGE.write_text(generated, encoding="utf-8")


if __name__ == "__main__":
    main()
