# 课堂演示用真实商品链接

> 从大淘客（dataoke.com）选取的热门淘宝客商品，已验证 API 可返回真实数据。
> 用法：python main.py --item "商品ID"

## 演示推荐顺序（低价→高价，覆盖不同品类）

### 1. 大运河洗衣皂（日用品，¥6.88）
```bash
python main.py --item "xWbeg99sktqad9x5yOiQbxsAt9-djGP3KNH0Pkr4wRvHW3"
```
- 原价 ¥10.48 → 到手价 ¥6.88（折扣 34%）
- 促销：满8减2 + 官方立减1.6
- 决策：【买】

### 2. 众知堂筋骨贴（医药保健，¥17）
```bash
python main.py --item "qy836Amu2t4OR4NZXGSg5vtWt0-zD03ZyKIWRwyXAPXtzO"
```
- 佣金率高达 75%
- 月销 9万+
- 决策：【买】

### 3. 薇诺娜宝贝舒润霜（母婴护肤，¥39）
```bash
python main.py --item "KqY5r4b7H3toVjexRvOHmPbfJt7-XqGwrmpu0xyR2oaniw3"
```
- 佣金 35%，月销 30万+
- 品牌：薇诺娜宝贝官方旗舰店
- 决策：【买】

### 4. babycare卫生巾（母婴用品，¥57.8）
```bash
python main.py --item "BQakMWDt6t85byOAbGHpRQcrtr-pBx2XAdIRNZ3WJkgFqn"
```
- 原价 ¥200 → API到手价 ¥74.3（折扣 63%）
- 大淘客叠补贴后 ¥57.8（可讲"不同平台价格差异"）
- 佣金 28%
- 决策：【买】

## 演示流程建议

1. 先跑 `python main.py`（示例模式，展示决策引擎全貌：买/等/换三场景）
2. 再跑 `python main.py --item "xWbeg99sktqad9x5yOiQbxsAt9-djGP3KNH0Pkr4wRvHW3"`（真实数据模式，证明不是假数据）
3. 打开生成的 report.html 展示决策报告
4. 讲解：数据来自淘宝联盟官方 API（taobao.tbk.item.info.upgrade.get），真实价格/佣金/促销

## 备注

- 商品 ID 是淘宝联盟新版动态字符串（非旧版纯数字），从 uland.taobao.com 链接提取
- 大淘客上的商品会随时间下架，如遇"未查到商品"换一个即可
- 到手价以 API 返回的 final_promotion_price 为准（含基础券+满减），大淘客显示的更低价格通常含额外补贴/淘金币叠加
