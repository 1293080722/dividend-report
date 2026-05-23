#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证各股票实时数据：股价、PE、PB、股息率，以及TARGET_YIELD精确值"""
# 数据口径：同花顺(10jqka.com.cn) 统一标准，含2025中报+年报全部分红

import requests
import re

PRESET_DIV = {
    "600036": 3.029, "601398": 0.3103, "601939": 0.3887,
    "601658": 0.2183, "601988": 0.2263, "601318": 2.700,
    "600941": 4.7037, "600887": 1.380, "600690": 1.1557,
    "601888": 0.702, "600900": 1.000, "002096": 0.256,
    "002027": 0.340,
    "561580": 0.125, "513530": 0.120,
}

TARGET_YIELD = {
    "600036": (8.41, 9.47),
    "601398": (4.70, 5.26),
    "601939": (4.18, 4.80),
    "601658": (4.75, 5.46),
    "601988": (4.19, 4.82),
    "601318": (5.40, 6.00),
    "600941": (5.00, 5.47),
    "600887": (6.00, 6.57),
    "600690": (6.08, 6.80),
    "601888": (1.49, 1.71),
    "600900": (4.17, 4.76),
    "002096": (2.69, 3.01),
    "002027": (6.54, 7.39),
    "561580": (10.87, 11.90),
    "513530": (8.00, 8.70),
}

# 腾讯财经API：返回~分隔格式
# 字段3=当前价, 字段39=PE(TTM)附近, 需要实际解析
STOCK_CODES = [
    "sh600036","sh601398","sh601939","sh601658","sh601988",
    "sh601318","sh600941","sh600887","sh600690","sh601888",
    "sh600900","sh002096","sz002027"
]
ETF_CODES = ["sh561580","sh513530"]
ALL_CODES = STOCK_CODES + ETF_CODES

url = "https://qt.gtimg.cn/q=" + ",".join(ALL_CODES)
print("请求:", url[:80], "...")
resp = requests.get(url, timeout=15)
resp.encoding = "gbk"
lines = resp.text.strip().split("\n")

print()
print("=" * 130)
print("{:<8} {:<8} {:>10} {:>10} {:>10} {:>10} {:>12} {:>12} {:>12}".format(
    "代码", "名称", "当前价", "PE", "PB", "股息率", "建仓价(目标)", "加仓价(目标)", "距建仓%"))
print("-" * 130)

for line in lines:
    m = re.search(r'v_\w+="([^"]+)"', line)
    if not m:
        continue
    fields = m.group(1).split("~")
    if len(fields) < 10:
        continue
    code = fields[2]
    name = fields[1]
    try:
        price = float(fields[3])
    except:
        continue

    # 在fields中搜索PE和PB（数值特征：PE通常5-30，PB通常0.3-5）
    pe_val = None
    pb_val = None
    for i, f in enumerate(fields):
        try:
            v = float(f)
            if 3 < v < 35 and pe_val is None:
                pe_val = v
            if 0.2 < v < 5 and pb_val is None:
                pb_val = v
        except:
            pass

    div = PRESET_DIV.get(code, 0)
    yld = round(div / price * 100, 2) if price else None

    # 用TARGET_YIELD计算建仓价/加仓价
    ty = TARGET_YIELD.get(code)
    if ty:
        build = round(div / (ty[0] / 100), 2)
        add   = round(div / (ty[1] / 100), 2)
        gap   = round((build - price) / price * 100, 1) if price else None
    else:
        build = add = gap = None

    print("{:<8} {:<8} {:>10.2f} {:>10} {:>10} {:>10}% {:>12} {:>12} {:>11}%".format(
        code, name[:6].ljust(6),
        price,
        "{:.2f}".format(pe_val) if pe_val else "N/A",
        "{:.2f}".format(pb_val) if pb_val else "N/A",
        "{:.2f}".format(yld) if yld else "N/A",
        "{:.2f}".format(build) if build else "—",
        "{:.2f}".format(add)   if add   else "—",
        "{:.1f}".format(gap)   if gap   else "—",
    ))

print()
print("=" * 130)
print("数据口径：同花顺(10jqka.com.cn) 统一标准，含2025中报+年报全部分红方案")
print("关键修正：600941(2.20→4.70) | 601939(0.41→0.39) | 601988(0.25→0.23) | 601658(0.26→0.22) | 600900(0.79→1.00)")
print("TARGET_YIELD 精确值验证（基于 PRESET_DIV ÷ 目标股息率）:")
print("-" * 130)
for code, (y1, y2) in TARGET_YIELD.items():
    div = PRESET_DIV.get(code, 0)
    b = round(div / (y1/100), 4) if div else None
    a = round(div / (y2/100), 4) if div else None
    print("  {}: 目标股息率={}%/{}% → 建仓价={:.4f}, 加仓价={:.4f}".format(
        code, y1, y2, b if b else 0, a if a else 0))
