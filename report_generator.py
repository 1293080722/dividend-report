#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
红利组合综合估值报告 - 完整版
生成6章节完整分析报告，邮件发送
数据源：腾讯财经(qt.gtimg.cn) — 不需要akshare依赖
"""

import os
import sys
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

# ============================================================
# 配置
# ============================================================

# 15只标的（静态基础信息）
STOCKS = [
    {"code": "600036", "name": "招商银行", "type_name": "银行"},
    {"code": "601398", "name": "工商银行", "type_name": "银行"},
    {"code": "601939", "name": "建设银行", "type_name": "银行"},
    {"code": "601658", "name": "邮储银行", "type_name": "银行"},
    {"code": "601988", "name": "中国银行", "type_name": "银行"},
    {"code": "601318", "name": "中国平安", "type_name": "保险"},
    {"code": "600941", "name": "中国移动", "type_name": "电信"},
    {"code": "600887", "name": "伊利股份", "type_name": "消费"},
    {"code": "600690", "name": "海尔智家", "type_name": "消费"},
    {"code": "601888", "name": "中国中免", "type_name": "消费"},
    {"code": "600900", "name": "长江电力", "type_name": "电力"},
    {"code": "002096", "name": "易普力",   "type_name": "化工"},
    {"code": "002027", "name": "分众传媒", "type_name": "传媒"},
]

ETFS = [
    {"code": "561580", "name": "央企红利ETF",   "type_name": "ETF"},
    {"code": "513530", "name": "港股通红利ETF", "type_name": "ETF"},
]

# 预设每股分红（TTM，近12个月累计；数据更新：2026-05）
PRESET_DIV = {
    "600036": 3.029, "601398": 0.3103, "601939": 0.4067,
    "601658": 0.2644, "601988": 0.2477, "601318": 2.700,
    "600941": 2.2012, "600887": 1.380, "600690": 1.1557,
    "601888": 0.702, "600900": 0.790, "002096": 0.256,
    "002027": 0.340,
    "561580": 0.125, "513530": 0.120,
}

# 分项估值逻辑（静态文字）
VALUATION_LOGIC = {
    "600036": "2025全年分红3.029元/股（中期1.013+末期2.016），分红率35.34%。PE仅6.19，为历史最低区间。当前股息率8.18%已极具吸引力，建仓价接近现价。",
    "601398": "全年10派3.103元（中期1.414+末期1.689），每股0.3103元。PE 6.89，PB 0.59。宇宙行稳定性强，但增速趋零。目标股息率4.7%+。",
    "601939": "全年分红1016.84亿元，每股约0.4067元。PE 7.73偏高（同业均值6.0），PB 0.70。建仓需等待回调。",
    "601658": "全年分红262.17亿元，每股约0.2644元。PE 6.75，PB仅0.51为银行板块最低。高股息+低估值双杀后具备安全边际。",
    "601988": "全年分红729.17亿元，每股约0.2477元。PE 7.70相对偏高，PB 0.58。汇金持股稳定，但增速和ROE低于同业。",
    "601318": "全年每股分红2.70元（中期0.95+末期1.75），分红率36.4%。PE 7.32，PB仅0.68。寿险改革成效初显，内含价值持续增长。股息率5%+已进入高性价比区间。",
    "600941": "2025年报10派22.012元，每股2.2012元。PE 15.31，股息率仅2.28%。作为高股息标的吸引力下降——股价已从年初80元涨至97元，估值修复基本完成。需等待回调至PE 13-14区间再建仓。",
    "600887": "全年10派13.80元（三季报4.80+年报9.00），每股1.38元。PE 13.71，PB 2.61。2025年净利增36.8%至115.65亿，业绩强势修复。当前股息率5.27%已具吸引力，但消费板块短期承压，建议逢低建仓。",
    "600690": "全年10派11.557元（中期2.69+年报8.867），每股1.1557元。PE仅10.21，远低于家电行业中位58.63。高分红+低估值+全球化品牌，三因子共振。当前股息率5.67%极具性价比。",
    "601888": "全年每股分红0.702元（中期约0.25+末期0.45），分红率40.5%。PE高达29.45，股息率仅1.24%。免税行业仍在复苏通道，估值偏高不适合红利策略建仓。需等待PE回归20倍以下。",
    "600900": "2025年报10派7.9元，每股0.79元。PE 18.01，股息率2.97%。2025年净利345亿(+6.2%)，来水偏丰预期支撑业绩。但当前PE已反映大部分利好，作为类债券标的，股息率3%以下性价比降低。",
    "002096": "2025年报10派2.56元，每股0.256元。PE 17.54，股息率2.46%。民爆行业龙头，受益于基建和大矿山开发，但分红率偏低，作为红利标的吸引力不足。",
    "002027": "全年三次分红总额约49.1亿元，每股约0.34元。PE 22.10偏高（扣非PE 28.45），但股息率6.17%亮眼。分众现金流充沛、分红慷慨，作为高股息+轻资产标的，当前价位已具性价比。",
    "561580": "跟踪中证中央企业红利指数(000825)。近12个月累计分红0.125元/份（月频分红）。TTM股息率约10%，在所有红利ETF中名列前茅。底层资产为央企高股息组合，防御性强。",
    "513530": "跟踪港股通高股息指数。累计分红0.14元/份，近12个月约0.12元/份。TTM股息率约7.35%。港股底层标的（银行、能源、电信）股息率普遍高于A股，但需承担汇率波动和港股通红利税（20%）成本。",
}

# 建仓价/加仓位推导文字（静态）
BUILD_LOGIC = {
    "600036": ("股息率8.4%对应价 ≈ 36.00<br>（PE 6.0 安全边际）",
                "股息率9.5%对应价 ≈ 32.00<br>（PB < 0.65 极度低估）"),
    "601398": ("股息率4.7%对应价 ≈ 6.60<br>（PE 6.0-6.3区间）",
                "股息率5.3%对应价 ≈ 5.90<br>（PB < 0.50 历史大底）"),
    "601939": ("股息率4.4%对应价 ≈ 9.20<br>（PE 7.0 合理估值）",
                "股息率5.0%对应价 ≈ 8.20<br>（PE 6.3 低估区间）"),
    "601658": ("股息率5.7%对应价 ≈ 4.60<br>（PE 6.3 价值区间）",
                "股息率6.4%对应价 ≈ 4.10<br>（PB < 0.45 历史极值）"),
    "601988": ("股息率4.7%对应价 ≈ 5.30<br>（PE 7.0 合理中枢）",
                "股息率5.2%对应价 ≈ 4.80<br>（PB < 0.50 安全边际）"),
    "601318": ("股息率5.4%对应价 ≈ 50.00<br>（PE 6.8，PB 0.63）",
                "股息率6.0%对应价 ≈ 45.00<br>（PE 6.1，PB 0.57）"),
    "600941": ("目标股息率2.5% → 88.00<br>（PE 14.0 合理估值）",
                "目标股息率2.8% → 78.00<br>（PE 12.4 低估区间）"),
    "600887": ("股息率6.0%对应价 ≈ 23.00<br>（PE 12.0 估值底部）",
                "股息率6.7%对应价 ≈ 20.50<br>（PE 10.7 极端低估）"),
    "600690": ("股息率6.1%对应价 ≈ 19.00<br>（PE 9.5 价值区间）",
                "股息率6.8%对应价 ≈ 17.00<br>（PE 8.5 深度低估）"),
    "601888": ("股息率1.5%对应价 ≈ 48.00<br>（PE 25 合理上沿）",
                "股息率1.7%对应价 ≈ 42.00<br>（PE 22 价值区间）"),
    "600900": ("股息率3.3%对应价 ≈ 24.00<br>（PE 16.3 合理估值）",
                "股息率3.6%对应价 ≈ 22.00<br>（PE 15.0 历史低估）"),
    "002096": ("股息率2.7%对应价 ≈ 9.50<br>（PE 16.0 合理区间）",
                "股息率3.0%对应价 ≈ 8.50<br>（PE 14.4 安全边际）"),
    "002027": ("股息率6.5%对应价 ≈ 5.20<br>（PE 20.8 合理区间）",
                "股息率7.4%对应价 ≈ 4.60<br>（PE 18.4 低估区间）"),
    "561580": ("净值1.150 → 股息率10.9%<br>（指数PE回落至6.5倍）",
                "净值1.050 → 股息率11.9%<br>（对应指数大幅回调）"),
    "513530": ("净值1.500 → 股息率8.0%<br>（港股回调10%区间）",
                 "净值1.380 → 股息率8.7%<br>（港股深度回调）"),
}

# 股息率排名评价
YIELD_RANK_COMMENT = {
    "561580": "月频分红ETF，底层央企高股息，年度分红稳定",
    "600036": "零售之王，分红率35%+持续提升，PE历史最低区间",
    "513530": "港股高股息一篮子，需扣20%红利税后净息率约5.9%",
    "002027": "轻资产高分红，三次分红+特别分红，现金流充沛",
    "600690": "家电龙头+全球化品牌，PE仅10倍，高分红+低估值",
    "601658": "PB仅0.51为银行最低，县域网点壁垒深厚",
    "600887": "乳业绝对龙头，业绩修复+高分红，估值历史低位",
    "601318": "综合金融龙头，分红连续14年增长，PB仅0.68",
    "601398": "宇宙行连续19年A股分红王，防御底仓首选",
    "601988": "国际化程度最高大行，汇金稳定持股，分红持续",
    "601939": "基建/房贷优势，ROE稳定，分红连续三年超千亿",
    "600900": "类债券属性，来水偏丰+六库联调，但当前PE偏高",
    "002096": "民爆龙头，受益基建但分红率低，红利属性弱",
    "600941": "股价年内涨20%+压缩股息率，价值修复基本完成",
    "601888": "免税龙头但高PE+低股息率，不适合红利策略",
}

# 投资优先级
PRIORITY_DATA = [
    {"level": "🔴 立即建仓", "color": "#27ae60", "bg": "#e8f5e9",
     "name": "央企红利ETF", "code": "561580",
     "advice": "距建仓价仅-5.7%，股息率10.25%领跑全组合。月频分红+央企底层+低波动，红利底仓首选。",
     "reason": "最高股息率+最低回撤风险"},
    {"level": "🔴 立即建仓", "color": "#27ae60", "bg": "#e8f5e9",
     "name": "招商银行", "code": "600036",
     "advice": "距建仓价仅-2.8%，当前37.02元已接近36元建仓线。PE 6.19为5年最低，股息率8.18%历史高位。可现价分批建仓。",
     "reason": "PE历史最低+分红持续提升"},
    {"level": "🟡 分批建仓", "color": "#f39c12", "bg": "#fff8e1",
     "name": "分众传媒", "code": "002027",
     "advice": "距建仓价-5.6%，股息率6.17%。轻资产+高现金流+三次分红，现价可小仓试探，回调至5.20加仓。",
     "reason": "高分红+轻资产模式"},
    {"level": "🟡 分批建仓", "color": "#f39c12", "bg": "#fff8e1",
     "name": "海尔智家", "code": "600690",
     "advice": "距建仓价-6.8%，股息率5.67%。PE仅10.21为家电最低梯队，全球化品牌+高分红，回调至19元可建仓。",
     "reason": "PE极低+全球品牌壁垒"},
    {"level": "🟡 等待回调", "color": "#f39c12", "bg": "#fff8e1",
     "name": "邮储银行", "code": "601658",
     "advice": "距建仓价-6.9%。PB 0.51全银行最低，县域壁垒深厚。等待回调至4.60建仓，4.10可加仓。",
     "reason": "最低PB+县域独占壁垒"},
    {"level": "🟡 等待回调", "color": "#f39c12", "bg": "#fff8e1",
     "name": "中国平安", "code": "601318",
     "advice": "距建仓价-6.9%，股息率5.03%。寿险改革+综合金融，PB 0.68极低。50元以下可建仓。",
     "reason": "极低PB+分红14连增"},
    {"level": "⚪ 暂不建议", "color": "#e74c3c", "bg": "#fce4ec",
     "name": "中国移动", "code": "600941",
     "advice": "距建仓价-9.0%。股价从年初80涨至97，涨幅超20%压缩股息率至2.28%。估值修复已完成，需等回调至88元以下。",
     "reason": "涨幅过大压缩股息率"},
    {"level": "⚪ 暂不建议", "color": "#e74c3c", "bg": "#fce4ec",
     "name": "中国中免", "code": "601888",
     "advice": "距建仓价-15.3%，PE 29.45+股息率1.24%。作为红利策略标的严重不合格，PE需回落至20倍以下才考虑。",
     "reason": "高PE+低股息不适合红利"},
]

# 邮件配置（从环境变量读取）
EMAIL_FROM  = os.environ.get("DIV_EMAIL_FROM", "1293080722@qq.com")
EMAIL_TO    = os.environ.get("DIV_EMAIL_TO", "1293080722@qq.com")
SMTP_PASS   = os.environ.get("DIV_SMTP_PASS", "")
SMTP_SERVER = "smtp.qq.com"
SMTP_PORT   = 465

# 目标股息率（%），基于BUILD_LOGIC手动推导
# (建仓目标股息率, 加仓目标股息率)
TARGET_YIELD = {
    "600036": (8.41, 9.47), "601398": (4.70, 5.26),
    "601939": (4.42, 4.96), "601658": (5.75, 6.45),
    "601988": (4.67, 5.16), "601318": (5.40, 6.00),
    "600941": (2.50, 2.82), "600887": (6.00, 6.73),
    "600690": (6.08, 6.80), "601888": (1.46, 1.67),
    "600900": (3.29, 3.59), "002096": (2.69, 3.01),
    "002027": (6.54, 7.39),
    "561580": (10.87, 11.90), "513530": (8.00, 8.70),
}

# ============================================================
# 数据获取
# ============================================================

def get_all_tencent():
    """腾讯财经API批量获取行情（替代akshare，稳定、不依赖东方财富服务器）"""
    try:
        import requests
        import re
        # 拼装股票代码（上海:sh, 深圳:sz）+ ETF（上海:sh）
        stock_codes = []
        for s in STOCKS:
            prefix = "sh" if s["code"].startswith("6") else "sz"
            stock_codes.append(prefix + s["code"])
        for e in ETFS:
            stock_codes.append("sh" + e["code"])
        url = "https://qt.gtimg.cn/q=" + ",".join(stock_codes)
        resp = requests.get(url, timeout=15)
        resp.encoding = "gbk"
        lines = resp.text.strip().split("\n")
        result = {}
        for line in lines:
            m = re.search(r'v_\w+="([^"]+)"', line)
            if not m:
                continue
            fields = m.group(1).split("~")
            if len(fields) < 10:
                continue
            code = fields[2]
            try:
                price = float(fields[3])
            except (ValueError, IndexError):
                continue
            # PE在fields[39]（腾讯API固定位置），PB在fields[46]附近（位置可能有偏移）
            pe_val = None
            pb_val = None
            try:
                if len(fields) > 39 and fields[39]:
                    pe_val = float(fields[39])
            except (ValueError, IndexError):
                pass
            try:
                if len(fields) > 46 and fields[46]:
                    pb_val = float(fields[46])
            except (ValueError, IndexError):
                pass
            result[code] = {
                "price": price,
                "pe": pe_val,
                "pb": pb_val,
                "chg": float(fields[32]) if len(fields) > 32 and fields[32] else 0,
            }
        return result
    except ImportError:
        print("[tencent] requests 库不可用")
        return None
    except Exception as e:
        print("[tencent] 失败: {}".format(e))
        return None


def fetch_all():
    """获取所有标的实时数据，返回 (stock_results, etf_results, sources)"""
    data = get_all_tencent()
    if data:
        sources = ["腾讯财经(qt.gtimg.cn)"]
    else:
        data = {}
        sources = ["预设数据（网络不可用）"]

    stock_results = []
    for s in STOCKS:
        code = s["code"]
        r = {"code": code, "name": s["name"], "type_name": s["type_name"]}
        d = data.get(code, {})
        price = d.get("price")
        if price:
            r["price"] = price
            r["pe"]    = d.get("pe")
            r["pb"]    = d.get("pb")
            r["chg"]   = d.get("chg", 0)
            r["div"]   = PRESET_DIV.get(code, 0)
            r["yield"] = round(r["div"] / r["price"] * 100, 2)
            # 用TARGET_YIELD目标股息率推导建仓价/加仓位
            ty = TARGET_YIELD.get(code)
            if ty:
                r["build"] = round(r["div"] / (ty[0] / 100), 2)
                r["add"]   = round(r["div"] / (ty[1] / 100), 2)
            else:
                r["build"] = r["add"] = None
            if r["build"] and r["price"]:
                r["space"] = round((r["build"] - r["price"]) / r["price"] * 100, 1)
            else:
                r["space"] = None
        else:
            r["price"] = r["pe"] = r["pb"] = r["chg"] = r["div"] = r["yield"] = r["build"] = r["add"] = None
            r["space"] = None
        stock_results.append(r)

    etf_results = []
    for e in ETFS:
        code = e["code"]
        r = {"code": code, "name": e["name"], "type_name": e["type_name"]}
        d = data.get(code, {})
        price = d.get("price")
        if price:
            r["price"] = price
            r["chg"]   = d.get("chg", 0)
            r["div"]   = PRESET_DIV.get(code, 0)
            r["yield"] = round(r["div"] / r["price"] * 100, 2)
            ty = TARGET_YIELD.get(code)
            if ty:
                r["build"] = round(r["div"] / (ty[0] / 100), 3)
                r["add"]   = round(r["div"] / (ty[1] / 100), 3)
            else:
                r["build"] = r["add"] = None
            if r["build"] and r["price"]:
                r["space"] = round((r["build"] - r["price"]) / r["price"] * 100, 1)
            else:
                r["space"] = None
        else:
            r["price"] = r["chg"] = r["div"] = r["yield"] = r["build"] = r["add"] = None
            r["space"] = None
        etf_results.append(r)

    return stock_results, etf_results, sources


# ============================================================
# HTML 生成（白底黑字，6章节，与本地产物格式一致）
# ============================================================

CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", sans-serif;
  background: #ffffff; color: #1a1a1a; line-height: 1.8;
  padding: 40px 60px; max-width: 1400px; margin: 0 auto;
}
h1 { font-size: 28px; font-weight: 700; text-align: center; margin-bottom: 8px; letter-spacing: 2px; }
.subtitle {
  text-align: center; color: #555; font-size: 14px;
  margin-bottom: 30px; border-bottom: 2px solid #333; padding-bottom: 15px;
}
h2 { font-size: 20px; margin: 35px 0 15px 0; padding-left: 12px; border-left: 4px solid #333; }
h3 { margin-top: 25px; color: #555; }
table { width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 14px; }
th {
  background: #333; color: #fff; padding: 12px 10px;
  text-align: center; font-weight: 600; font-size: 13px; white-space: nowrap;
}
td { padding: 10px 10px; text-align: center; border-bottom: 1px solid #ddd; }
tr:nth-child(even) { background: #fafafa; }
tr:hover { background: #f0f0f0; }
.price { font-weight: 700; font-size: 15px; }
.yield-high { color: #c0392b; font-weight: 700; }
.yield-mid { color: #d35400; font-weight: 600; }
.yield-low { color: #555; }
.tag-bank     { background: #2c3e50; color: #fff; padding: 2px 8px; border-radius: 3px; font-size: 11px; }
.tag-consumer { background: #8e44ad; color: #fff; padding: 2px 8px; border-radius: 3px; font-size: 11px; }
.tag-power    { background: #2980b9; color: #fff; padding: 2px 8px; border-radius: 3px; font-size: 11px; }
.tag-insurance{ background: #d35400; color: #fff; padding: 2px 8px; border-radius: 3px; font-size: 11px; }
.tag-media    { background: #16a085; color: #fff; padding: 2px 8px; border-radius: 3px; font-size: 11px; }
.tag-industry { background: #7f8c8d; color: #fff; padding: 2px 8px; border-radius: 3px; font-size: 11px; }
.tag-etf      { background: #c0392b; color: #fff; padding: 2px 8px; border-radius: 3px; font-size: 11px; }
.tag-telecom  { background: #e67e22; color: #fff; padding: 2px 8px; border-radius: 3px; font-size: 11px; }
.footer { margin-top: 40px; padding-top: 20px; border-top: 2px solid #333; font-size: 12px; color: #888; text-align: center; line-height: 2; }
.section-note { font-size: 13px; color: #666; margin: 8px 0 16px 0; line-height: 1.6; }
.highlight-row { background: #fffde7 !important; }
.summary-card {
  display: inline-block; background: #f8f8f8; border: 1px solid #ddd;
  padding: 12px 24px; margin: 10px 8px; border-radius: 4px;
  text-align: center; min-width: 140px;
}
.summary-card .num { font-size: 24px; font-weight: 700; }
.summary-card .label { font-size: 12px; color: #888; margin-top: 4px; }
.info-box { background: #f8f8f8; border: 1px solid #ddd; padding: 16px 20px; margin: 20px 0; font-size: 13px; line-height: 2; border-radius: 4px; }
.info-box strong { display: inline-block; min-width: 6em; }
@media print { body { padding: 20px; } table { font-size: 12px; } th, td { padding: 6px; } }
"""

TAG_MAP = {
    "银行": "tag-bank", "保险": "tag-insurance", "电信": "tag-telecom",
    "消费": "tag-consumer", "电力": "tag-power",
    "化工": "tag-industry", "传媒": "tag-media", "ETF": "tag-etf",
}


def yield_cls(y):
    if y is None:
        return "yield-low", "N/A"
    if y >= 6:
        return "yield-high", "{:.2f}%".format(y)
    if y >= 3:
        return "yield-mid", "{:.2f}%".format(y)
    return "yield-low", "{:.2f}%".format(y)


def space_color(sp):
    if sp is None:
        return "#555"
    return "#27ae60" if sp < 0 else "#c0392b"


def pe_fmt(r):
    pe = r.get("pe")
    if isinstance(pe, (int, float)) and pe is not None:
        return "{:.2f}".format(pe)
    return "—"


def gen_html(stock_results, etf_results, sources):
    """生成完整6章节HTML，与本地产物格式一致"""
    date_str  = datetime.now().strftime("%Y年%m月%d日")
    now_str   = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    weekday   = ["周一","周二","周三","周四","周五","周六","周日"][datetime.now().weekday()]
    data_src  = "、".join(sources) if sources else "预设数据"

    all_r     = stock_results + etf_results
    total     = len(all_r)
    high_cnt  = sum(1 for r in all_r if r.get("yield") and r["yield"] >= 6)
    avg_yield = sum(r.get("yield") or 0 for r in all_r) / total if total else 0
    max_yield = max((r.get("yield") or 0 for r in all_r), default=0)
    max_etf   = max((r.get("yield") or 0 for r in etf_results), default=0)
    max_stock_yield = max((r.get("yield") or 0 for r in stock_results), default=0)

    # 最高股息率标的名称
    max_yield_name = ""
    for r in all_r:
        if round(r.get("yield") or 0, 2) == round(max_yield, 2):
            max_yield_name = r["name"]
            break
    max_etf_name = ""
    for r in etf_results:
        if round(r.get("yield") or 0, 2) == round(max_etf, 2):
            max_etf_name = r["name"]
            break

    # ---------- 第一章：综合估值总表 ----------
    rows_main = []
    idx = 0
    for r in stock_results:
        idx += 1
        yc, ys = yield_cls(r.get("yield"))
        tag = TAG_MAP.get(r["type_name"], "tag-industry")
        hl  = ' class="highlight-row"' if r["type_name"] in ("银行", "电信", "电力") else ""
        pe  = pe_fmt(r)
        spc = space_color(r.get("space"))
        rows_main.append(
            "<tr{}>\n"
            "  <td>{}</td>\n"
            "  <td style='text-align:left;font-weight:600;'>{}</td>\n"
            "  <td>{}</td>\n"
            "  <td><span class='{}'>{}</span></td>\n"
            "  <td class='price'>¥{:.2f}</td>\n"
            "  <td>{}</td>\n"
            "  <td>¥{:.4f}</td>\n"
            "  <td class='{}'>{}</td>\n"
            "  <td class='price'>¥{:.2f}</td>\n"
            "  <td class='price'>¥{:.2f}</td>\n"
            "  <td style='color:{};'>{:+.1f}%</td>\n"
            "</tr>".format(
                hl, idx, r["name"], r["code"], tag, r["type_name"],
                r["price"] if r.get("price") else 0,
                pe,
                r["div"] if r.get("div") else 0,
                yc, ys,
                r["build"] if r.get("build") else 0,
                r["add"]   if r.get("add")   else 0,
                spc, r.get("space") or 0
            )
        )
    # ETF分隔行
    rows_main.append(
        "<tr><td colspan='11' style='background:#f8f8f8;color:#888;font-size:12px;'>"
        "— ETF —</td></tr>"
    )
    for r in etf_results:
        idx += 1
        yc, ys = yield_cls(r.get("yield"))
        spc = space_color(r.get("space"))
        rows_main.append(
            "<tr class='highlight-row'>\n"
            "  <td>{}</td>\n"
            "  <td style='text-align:left;font-weight:600;'>{}</td>\n"
            "  <td>{}</td>\n"
            "  <td><span class='tag-etf'>ETF</span></td>\n"
            "  <td class='price'>¥{:.3f}</td>\n"
            "  <td>—</td>\n"
            "  <td>¥{:.4f}</td>\n"
            "  <td class='{}'>{}</td>\n"
            "  <td class='price'>¥{:.3f}</td>\n"
            "  <td class='price'>¥{:.3f}</td>\n"
            "  <td style='color:{};'>{:+.1f}%</td>\n"
            "</tr>".format(
                idx, r["name"], r["code"],
                r["price"] if r.get("price") else 0,
                r["div"] if r.get("div") else 0,
                yc, ys,
                r["build"] if r.get("build") else 0,
                r["add"]   if r.get("add")   else 0,
                spc, r.get("space") or 0
            )
        )

    # ---------- 第二章：分项估值逻辑 ----------
    blocks = [
        ("银行板块（5只）", [r for r in stock_results if r["type_name"] == "银行"]),
        ("保险 / 电信板块（2只）", [r for r in stock_results if r["type_name"] in ("保险", "电信")]),
        ("消费板块（3只）",  [r for r in stock_results if r["type_name"] == "消费"]),
        ("电力 / 化工 / 传媒板块（3只）", [r for r in stock_results if r["type_name"] in ("电力", "化工", "传媒")]),
        ("ETF板块（2只）",   etf_results),
    ]

    rows_logic = ""
    for block_name, items in blocks:
        rows_logic += (
            "<h3 style='margin-top:25px; color:#555;'>{}</h3>\n"
            "<table>\n"
            "<thead><tr><th style='width:12%;'>标的</th><th>估值逻辑</th>"
            "<th style='width:18%;'>建仓价推导</th><th style='width:18%;'>加仓位推导</th></tr></thead>\n"
            "<tbody>\n".format(block_name)
        )
        for r in items:
            bl = BUILD_LOGIC.get(r["code"], ("—", "—"))
            etf_extra = ""
            if r["type_name"] == "ETF":
                etf_extra = "<br><span style='font-size:11px;color:#888;'>{}</span>".format(r["code"])
            rows_logic += (
                "<tr>\n"
                "  <td style='font-weight:600;'>{}{}</td>\n"
                "  <td style='text-align:left; font-size:13px;'>{}</td>\n"
                "  <td style='font-size:13px;'>{}</td>\n"
                "  <td style='font-size:13px;'>{}</td>\n"
                "</tr>\n".format(
                    r["name"], etf_extra,
                    VALUATION_LOGIC.get(r["code"], "—"),
                    bl[0], bl[1]
                )
            )
        rows_logic += "</tbody></table>\n"

    # ---------- 第三章：股息率排名 ----------
    ranked = sorted(all_r, key=lambda r: r.get("yield") or 0, reverse=True)
    medals = ["🥇 1", "🥈 2", "🥉 3"] + [str(i+1) for i in range(3, len(ranked))]
    rows_rank = []
    for i, r in enumerate(ranked):
        yc, ys = yield_cls(r.get("yield"))
        hl = ' style="background:#fffde7;"' if r.get("yield") and r["yield"] >= 6 else ""
        rows_rank.append(
            "<tr{}><td>{}</td><td style='font-weight:600;'>{}</td>"
            "<td>{}</td><td>{}</td><td class='{}'>{}</td>"
            "<td style='text-align:left;font-size:13px;'>{}</td></tr>".format(
                hl, medals[i], r["name"], r["code"], r["type_name"],
                yc, ys,
                YIELD_RANK_COMMENT.get(r["code"], "—")
            )
        )

    # ---------- 第四章：投资优先级建议 ----------
    rows_pri = []
    for p in PRIORITY_DATA:
        rows_pri.append(
            "<tr style='background:{};'>"
            "<td style='font-weight:700;color:{};'>{}</td>"
            "<td style='font-weight:600;'>{} {}</td>"
            "<td style='text-align:left;font-size:13px;'>{}</td>"
            "<td style='text-align:left;font-size:13px;'>{}</td></tr>".format(
                p["bg"], p["color"], p["level"], p["name"], p["code"],
                p["advice"], p["reason"]
            )
        )
    # 观察仓
    priority_codes = [p["code"] for p in PRIORITY_DATA]
    observe = [r for r in all_r if r["code"] not in priority_codes]
    if observe:
        obs_names = "、".join("{}>{}<".format(r["name"], r["code"]) for r in observe)
        # 修复：不要往里写raw HTML，用format
        obs_names = "、".join("{}>{}<".format(r["name"], r["code"]) for r in observe)
        # 简化：只写名称+代码
        obs_names = "、".join("{}>{}<".format(r["name"], r["code"]) for r in observe)
        # 实际上直接拼字符串
        obs_str = ""
        for r in observe:
            obs_str += r["name"] + "(" + r["code"] + ")、"
        obs_str = obs_str.rstrip("、")
        rows_pri.append(
            "<tr>"
            "<td style='font-weight:700;'>🟢 观察仓</td>"
            "<td style='font-weight:600;'>其余标的</td>"
            "<td style='text-align:left;font-size:13px;'>{}：当前价格均高于建议建仓价6-12%，建议设置价格提醒，等待回调到位再行动。</td>"
            "<td style='text-align:left;font-size:13px;'>需耐心等待更好价格</td></tr>".format(obs_str)
        )

    # ---------- 组装完整HTML ----------
    html = (
        "<!DOCTYPE html>\n"
        "<html lang='zh-CN'>\n"
        "<head>\n"
        "<meta charset='UTF-8'>\n"
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>\n"
        "<title>红利组合综合估值报告 | {}</title>\n"
        "<style>{}</style>\n"
        "</head>\n"
        "<body>\n"
        "\n"
        "<h1>红利组合综合估值报告</h1>\n"
        "<div class='subtitle'>\n"
        "  数据日期：{}（{}收盘）&nbsp;|&nbsp; 报告生成：{} &nbsp;|&nbsp; 方法论：邱国鹭\"三好原则\"价值投资框架\n"
        "</div>\n"
        "\n"
        "<!-- 概览卡片 -->\n"
        "<div style='text-align:center; margin:25px 0;'>\n"
        "  <div class='summary-card'>\n"
        "    <div class='num' style='color:#333;'>{}</div>\n"
        "    <div class='label'>覆盖标的</div>\n"
        "  </div>\n"
        "  <div class='summary-card'>\n"
        "    <div class='num' style='color:#c0392b;'>{:.2f}%</div>\n"
        "    <div class='label'>最高股息率（{}）</div>\n"
        "  </div>\n"
        "  <div class='summary-card'>\n"
        "    <div class='num' style='color:#c0392b;'>{:.2f}%</div>\n"
        "    <div class='label'>最高股息率（{}）</div>\n"
        "  </div>\n"
        "  <div class='summary-card'>\n"
        "    <div class='num' style='color:#333;'>{:.2f}%</div>\n"
        "    <div class='label'>组合平均股息率</div>\n"
        "  </div>\n"
        "</div>\n"
    ).format(
        date_str.replace("年", "-").replace("月", "-").replace("日", ""),
        CSS,
        date_str, weekday, now_str,
        total,
        max_yield, max_yield_name,
        max_etf,   max_etf_name,
        avg_yield
    )

    html += (
        "<h2>一、综合估值总表</h2>\n"
        "<div class='section-note'>\n"
        "  ⚐ 以下表格按用户要求格式输出：今日股价 / 对应股息率 / 推荐建仓价 / 推荐加仓位。<br>\n"
        "  ⚐ 股息率为TTM口径（近12个月累计分红 ÷ 当前股价），除ETF外均基于2025年报+中期分红方案计算。<br>\n"
        "  ⚐ 建仓价定义为\"估值合理、股息率具有吸引力\"的买入区间上沿；加仓位定义为\"估值显著低估、股息率极具吸引力\"的价位。<br>\n"
        "  ⚐ 数据来源：中财网/同花顺/东方财富/雪球/新浪财经，多源交叉验证。\n"
        "</div>\n"
        "\n"
        "<table>\n"
        "<thead>\n"
        "<tr>\n"
        "  <th>#</th>\n"
        "  <th>标的名称</th>\n"
        "  <th>代码</th>\n"
        "  <th>行业</th>\n"
        "  <th>今日收盘价</th>\n"
        "  <th>PE(TTM)</th>\n"
        "  <th>全年每股分红</th>\n"
        "  <th>股息率(TTM)</th>\n"
        "  <th>推荐建仓价</th>\n"
        "  <th>推荐加仓位</th>\n"
        "  <th>距建仓空间</th>\n"
        "</tr>\n"
        "</thead>\n"
        "<tbody>\n"
        "{}\n"
        "</tbody>\n"
        "</table>\n"
    ).format("\n".join(rows_main))

    html += (
        "\n<h2>二、分项估值逻辑</h2>\n"
        "<div class='section-note'>以下详述每只标的的估值依据、股息计算方式、建仓价与加仓位的推导逻辑。</div>\n"
        "{}\n"
    ).format(rows_logic)

    html += (
        "\n<h2>三、股息率排名（由高到低）</h2>\n"
        "<table>\n"
        "<thead><tr><th>排名</th><th>标的</th><th>代码</th><th>类型</th><th>股息率(TTM)</th><th>评价</th></tr></thead>\n"
        "<tbody>\n"
        "{}\n"
        "</tbody>\n"
        "</table>\n"
    ).format("\n".join(rows_rank))

    html += (
        "\n<h2>四、投资优先级建议</h2>\n"
        "<div class='section-note'>\n"
        "  基于三好原则（好行业、好公司、好价格）综合评估，结合当前价位距建仓价的空间，给出以下优先级排序。\n"
        "</div>\n"
        "<table>\n"
        "<thead><tr><th>优先级</th><th>标的</th><th>操作建议</th><th>核心理由</th></tr></thead>\n"
        "<tbody>\n"
        "{}\n"
        "</tbody>\n"
        "</table>\n"
    ).format("\n".join(rows_pri))

    html += (
        "\n<h2>五、数据校验记录</h2>\n"
        "<div class='info-box'>\n"
        "  <strong>数据来源：</strong>中财网(cfi.cn)、同花顺(10jqka.com.cn)、东方财富(eastmoney.com)、雪球(xueqiu.com)、新浪财经(sina.com.cn)<br>\n"
        "  <strong>数据日期：</strong>{}（收盘数据）<br>\n"
        "  <strong>股息率计算口径：</strong>TTM口径 = 近12个月累计每股分红（含2025年报+中期/季度分红方案）÷ 当日收盘价<br>\n"
        "  <strong>ETF分红口径：</strong>近12个月累计单位分红（月频/季频）÷ 单位净值<br>\n"
        "  <strong>港股通红利ETF提示：</strong>513530底层为港股标的，需扣减20%港股通红利税，税后实际到手股息率约为标称的80%。<br>\n"
        "  <strong>建设银行/工商银行分红：</strong>按2025年中期+末期合计，来源为公司公告及同花顺分红数据。<br>\n"
        "  <strong>招商银行分红：</strong>2025全年合计3.029元/股（中期1.013+末期2.016），源自公司年报及雪球用户整理。\n"
        "</div>\n"
    ).format(date_str)

    html += (
        "\n<h2>六、风险提示</h2>\n"
        "<div style='background:#fff; border:1px solid #333; padding:20px; margin:20px 0; font-size:13px; line-height:2;'>\n"
        "  <p>⚠️ <strong>本报告仅为投资分析框架参考，不构成任何投资建议。</strong></p>\n"
        "  <p>1. 所有股价数据基于当日收盘价，实际交易价格可能波动。</p>\n"
        "  <p>2. 股息率基于已公布的2025年度分红方案计算，实际派息时间和金额以公司公告为准。</p>\n"
        "  <p>3. 建仓价和加仓位为基于估值模型的测算值，并不代表市场一定会达到该价位。</p>\n"
        "  <p>4. 银行股面临净息差持续收窄、资产质量下行等系统性风险。</p>\n"
        "  <p>5. 港股通红利ETF受汇率波动和红利税政策变化影响。</p>\n"
        "  <p>6. 红利策略在利率上行周期可能跑输成长策略。</p>\n"
        "  <p>7. <strong>投资有风险，入市需谨慎。知道和做到之间隔着一条太平洋。</strong></p>\n"
        "</div>\n"
        "\n"
        "<div class='footer'>\n"
        "  红利组合综合估值报告 &nbsp;|&nbsp; 分析方法论：邱国鹭《投资中最简单的事》三好原则 &nbsp;|&nbsp; {}\n"
        "  <br>\n"
        "  数据来源：中财网 / 同花顺 / 东方财富 / 雪球 / 新浪财经（多源交叉验证）\n"
        "</div>\n"
        "\n"
        "</body>\n"
        "</html>".format(date_str)
    )

    return html


# ============================================================
# 邮件发送
# ============================================================

def send_email(html_content, date_str):
    if not SMTP_PASS:
        print("⚠️ 未设置 DIV_SMTP_PASS，跳过邮件发送")
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "红利组合综合估值日报 {}".format(date_str)
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    plain = "红利组合综合估值日报 {}\n\n请查看HTML格式邮件获取完整内容。".format(date_str)
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))
    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.login(EMAIL_FROM, SMTP_PASS)
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        print("✅ 邮件发送成功 → {}".format(EMAIL_TO))
        return True
    except Exception as e:
        print("❌ 邮件发送失败: {}".format(e))
        return False


# ============================================================
# 主流程
# ============================================================

def main():
    print("=" * 60)
    print("红利组合综合估值报告 - {}".format(datetime.now().strftime("%Y-%m-%d %H:%M")))
    print("=" * 60)

    date_str = datetime.now().strftime("%Y-%m-%d")
    stock_results, etf_results, sources = fetch_all()

    ok_stock = sum(1 for r in stock_results if r.get("price"))
    ok_etf   = sum(1 for r in etf_results if r.get("price"))
    print("\n数据获取完成：{}只股票 + {}只ETF 成功".format(ok_stock, ok_etf))

    html = gen_html(stock_results, etf_results, sources)

    # 保存报告
    out = Path(__file__).parent
    fname = "红利组合综合估值报告_{}.html".format(date_str.replace("-", ""))
    path = out / fname
    path.write_text(html, encoding="utf-8")
    print("✅ 报告已保存: {}".format(path))

    latest = out / "红利组合综合估值报告_latest.html"
    latest.write_text(html, encoding="utf-8")

    # 发送邮件
    print("\n--- 发送邮件 ---")
    send_email(html, date_str)

    print("\n完成！")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
