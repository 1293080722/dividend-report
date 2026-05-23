#!/usr/bin/env python3
"""
红利组合综合估值日报生成器
用于 GitHub Actions 每个工作日9:30自动运行
数据源：akshare（优先）+ 中财网/新浪财经（备选）
"""

import os
import sys
import json
import time
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

# ============================================================
# 配置
# ============================================================

# 15只标的
STOCKS = [
    {"code": "600036", "name": "招商银行", "type": "bank"},
    {"code": "601398", "name": "工商银行", "type": "bank"},
    {"code": "601939", "name": "建设银行", "type": "bank"},
    {"code": "601658", "name": "邮储银行", "type": "bank"},
    {"code": "601988", "name": "中国银行", "type": "bank"},
    {"code": "601318", "name": "中国平安", "type": "insurance"},
    {"code": "600941", "name": "中国移动", "type": "telecom"},
    {"code": "600887", "name": "伊利股份", "type": "consumer"},
    {"code": "600690", "name": "海尔智家", "type": "consumer"},
    {"code": "601888", "name": "中国中免", "type": "consumer"},
    {"code": "600900", "name": "长江电力", "type": "power"},
    {"code": "002096", "name": "易普力", "type": "industry"},
    {"code": "002027", "name": "分众传媒", "type": "media"},
]

ETFS = [
    {"code": "561580", "name": "央企红利ETF", "type": "etf"},
    {"code": "513530", "name": "港股通红利ETF", "type": "etf"},
]

# 行业PE/PB中位数（静态参考值，每日从akshare获取行业数据时更新）
INDUSTRY_MEDIAN = {
    "bank": {"pe": 6.03, "pb": 0.58, "name": "银行"},
    "insurance": {"pe": 10.50, "pb": 1.20, "name": "保险"},
    "telecom": {"pe": 15.00, "pb": 1.50, "name": "电信运营"},
    "consumer": {"pe": 22.00, "pb": 3.50, "name": "消费"},
    "power": {"pe": 20.00, "pb": 2.80, "name": "电力"},
    "industry": {"pe": 18.00, "pb": 1.80, "name": "化工"},
    "media": {"pe": 25.00, "pb": 2.50, "name": "传媒"},
    "etf": {"pe": None, "pb": None, "name": "ETF"},
}

# 邮件配置（从环境变量读取，敏感信息不放代码里）
EMAIL_FROM = os.environ.get("DIV_EMAIL_FROM", "1293080722@qq.com")
EMAIL_TO = os.environ.get("DIV_EMAIL_TO", "1293080722@qq.com")
SMTP_PASS = os.environ.get("DIV_SMTP_PASS", "")
SMTP_SERVER = "smtp.qq.com"
SMTP_PORT = 465

# 建仓/加仓比例
BUILD_RATIO = 0.90   # 建仓价 = 当前价 × 90%
ADD_RATIO = 0.80     # 加仓位 = 当前价 × 80%

# ============================================================
# 数据获取
# ============================================================

def get_stock_price_ak(code):
    """通过akshare获取个股实时行情"""
    try:
        import akshare as ak
        # 判断市场
        market = "sh" if code.startswith("6") else "sz"
        symbol = f"{market}{code}"

        # 获取实时行情
        df = ak.stock_zh_a_spot_em()
        row = df[df["代码"] == code]
        if row.empty:
            return None

        row = row.iloc[0]
        return {
            "price": float(row["最新价"]),
            "pe": float(row["市盈率-动态"]) if row["市盈率-动态"] != "-" else None,
            "pb": float(row["市净率"]) if row["市净率"] != "-" else None,
            "change_pct": float(row["涨跌幅"]) if row["涨跌幅"] != "-" else 0,
            "volume": float(row["成交量"]) if row["成交量"] != "-" else 0,
            "amount": float(row["成交额"]) if row["成交额"] != "-" else 0,
        }
    except Exception as e:
        print(f"[akshare] {code} 获取失败: {e}")
        return None


def get_etf_price_ak(code):
    """通过akshare获取ETF行情"""
    try:
        import akshare as ak
        market = "sh" if code.startswith("5") else "sz"
        df = ak.fund_etf_spot_em()
        row = df[df["代码"] == code]
        if row.empty:
            return None
        row = row.iloc[0]
        return {
            "price": float(row["最新价"]),
            "change_pct": float(row["涨跌幅"]) if row["涨跌幅"] != "-" else 0,
            "volume": float(row["成交量"]) if row["成交量"] != "-" else 0,
        }
    except Exception as e:
        print(f"[akshare] ETF {code} 获取失败: {e}")
        return None


def get_dividend_data(code):
    """获取个股TTM股息（近12个月累计每股分红）"""
    try:
        import akshare as ak

        # 获取分红历史
        df = ak.stock_history_dividend_detail(
            indicator="分红", symbol=code, date=""
        )

        if df is None or df.empty:
            return None

        # 筛选近12个月的现金分红
        cutoff = datetime.now() - timedelta(days=365)
        total_div = 0.0
        div_records = []

        for _, row in df.iterrows():
            try:
                div_date = pd.to_datetime(row.get("除权除息日", ""))
                if div_date >= cutoff:
                    div_per_share = float(row.get("派息", 0) or 0)
                    total_div += div_per_share
                    div_records.append({
                        "date": div_date.strftime("%Y-%m-%d"),
                        "amount": div_per_share
                    })
            except Exception:
                continue

        return {"ttm_dividend": round(total_div, 4), "records": div_records}
    except Exception as e:
        print(f"[akshare] {code} 分红数据获取失败: {e}")
        return None


# ============================================================
# 备份数据源（直接HTTP请求）
# ============================================================

def get_stock_price_sina(code):
    """新浪财经实时行情（备选源）"""
    try:
        import requests
        market = "sh" if code.startswith("6") else "sz"
        url = f"https://hq.sinajs.cn/list={market}{code}"
        headers = {"Referer": "https://finance.sina.com.cn"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "gbk"
        data = resp.text.split('"')[1].split(",")
        if len(data) < 30:
            return None
        return {
            "price": float(data[3]),
            "pe": None,
            "pb": None,
            "change_pct": (float(data[3]) / float(data[2]) - 1) * 100 if float(data[2]) > 0 else 0,
        }
    except Exception as e:
        print(f"[sina] {code} 获取失败: {e}")
        return None


# ============================================================
# 预置股息数据（静态备选，当API获取失败时使用）
# ============================================================

PRESET_DIVIDENDS = {
    "600036": 3.026,   # 招商银行 2025年累计
    "601398": 0.310,   # 工商银行
    "601939": 0.407,   # 建设银行
    "601658": 0.264,   # 邮储银行
    "601988": 0.248,   # 中国银行
    "601318": 2.700,   # 中国平安
    "600941": 2.205,   # 中国移动
    "600887": 1.380,   # 伊利股份
    "600690": 1.155,   # 海尔智家
    "601888": 0.700,   # 中国中免
    "600900": 0.790,   # 长江电力
    "002096": 0.256,   # 易普力
    "002027": 0.340,   # 分众传媒
}

PRESET_ETF_DIVIDENDS = {
    "561580": 0.125,   # 央企红利ETF
    "513530": 0.120,   # 港股通红利ETF
}


# ============================================================
# 计算逻辑
# ============================================================

def calc_dividend_yield(price, ttm_div):
    """计算TTM股息率"""
    if not price or not ttm_div or price <= 0:
        return None
    return round(ttm_div / price * 100, 2)


def calc_build_price(price):
    """建仓价 = 当前价 × 90%"""
    return round(price * BUILD_RATIO, 2)


def calc_add_price(price):
    """加仓位 = 当前价 × 80%"""
    return round(price * ADD_RATIO, 2)


def classify_yield(y):
    """股息率分级"""
    if y is None:
        return "yield-low", "N/A"
    if y >= 6:
        return "yield-high", f"{y:.2f}%"
    elif y >= 3:
        return "yield-mid", f"{y:.2f}%"
    else:
        return "yield-low", f"{y:.2f}%"


def get_type_tag(t):
    """行业标签"""
    tags = {
        "bank": ('tag-bank', '银行'),
        "insurance": ('tag-insurance', '保险'),
        "telecom": ('tag-telecom', '电信'),
        "consumer": ('tag-consumer', '消费'),
        "power": ('tag-power', '电力'),
        "industry": ('tag-industry', '化工'),
        "media": ('tag-media', '传媒'),
        "etf": ('tag-etf', 'ETF'),
    }
    return tags.get(t, ('tag-industry', t))


# ============================================================
# HTML报告生成（黑底白字）
# ============================================================

CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", sans-serif;
  background: #000000;
  color: #e0e0e0;
  line-height: 1.8;
  padding: 40px 60px;
  max-width: 1400px;
  margin: 0 auto;
}
h1 {
  font-size: 28px; font-weight: 700; text-align: center;
  margin-bottom: 8px; letter-spacing: 2px; color: #ffffff;
}
.subtitle {
  text-align: center; color: #999; font-size: 14px;
  margin-bottom: 30px; border-bottom: 2px solid #444;
  padding-bottom: 15px;
}
h2 {
  font-size: 20px; margin: 35px 0 15px 0;
  padding-left: 12px; border-left: 4px solid #e74c3c; color: #ffffff;
}
.info-box {
  background: #1a1a1a; border: 1px solid #333;
  padding: 16px 20px; margin: 20px 0; font-size: 13px;
  line-height: 2; border-radius: 4px;
}
.info-box strong { display: inline-block; min-width: 6em; color: #aaa; }
table {
  width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 14px;
}
th {
  background: #1a1a1a; color: #fff; padding: 12px 10px;
  text-align: center; font-weight: 600; font-size: 13px;
  white-space: nowrap; border-bottom: 2px solid #444;
}
td {
  padding: 10px 10px; text-align: center;
  border-bottom: 1px solid #2a2a2a; color: #ccc;
}
tr:nth-child(even) { background: #0d0d0d; }
tr:hover { background: #1a1a1a; }
.price { font-weight: 700; font-size: 15px; color: #fff; }
.yield-high { color: #ff4444; font-weight: 700; }
.yield-mid { color: #ff9800; font-weight: 600; }
.yield-low { color: #888; }
.tag-bank { background: #2c3e50; padding: 2px 8px; border-radius: 3px; font-size: 11px; }
.tag-consumer { background: #8e44ad; padding: 2px 8px; border-radius: 3px; font-size: 11px; }
.tag-power { background: #2980b9; padding: 2px 8px; border-radius: 3px; font-size: 11px; }
.tag-insurance { background: #d35400; padding: 2px 8px; border-radius: 3px; font-size: 11px; }
.tag-media { background: #16a085; padding: 2px 8px; border-radius: 3px; font-size: 11px; }
.tag-industry { background: #7f8c8d; padding: 2px 8px; border-radius: 3px; font-size: 11px; }
.tag-etf { background: #c0392b; padding: 2px 8px; border-radius: 3px; font-size: 11px; }
.tag-telecom { background: #e67e22; padding: 2px 8px; border-radius: 3px; font-size: 11px; }
.footer {
  margin-top: 40px; padding-top: 20px;
  border-top: 2px solid #444; font-size: 12px;
  color: #666; text-align: center; line-height: 2;
}
.section-note { font-size: 13px; color: #888; margin: 8px 0 16px 0; line-height: 1.6; }
.summary-card {
  display: inline-block; background: #1a1a1a; border: 1px solid #333;
  padding: 12px 24px; margin: 10px 8px; border-radius: 4px;
  text-align: center; min-width: 140px;
}
.summary-card .num { font-size: 24px; font-weight: 700; color: #ff4444; }
.summary-card .label { font-size: 12px; color: #888; margin-top: 4px; }
@media print {
  body { padding: 20px; background: #fff; color: #000; }
  th { background: #ddd; color: #000; }
  td { color: #000; border-color: #ccc; }
}
"""


def build_row(code, name, type_, price, pe, pb, div_yield, build_price, add_price, change_pct, is_etf=False):
    """生成表格行HTML"""
    tag_cls, tag_name = get_type_tag(type_)
    yield_cls, yield_str = classify_yield(div_yield)

    pe_str = f"{pe:.2f}" if pe else "N/A"
    pb_str = f"{pb:.2f}" if pb else "N/A"
    change_str = f"{change_pct:+.2f}%" if change_pct is not None else "N/A"
    change_cls = "yield-high" if change_pct and change_pct > 0 else ("yield-mid" if change_pct and change_pct < 0 else "")

    row_html = f"""    <tr>
      <td>{code}</td>
      <td>{name}</td>
      <td><span class="{tag_cls}">{tag_name}</span></td>
      <td class="price">¥{price:.2f}</td>
      <td class="{change_cls}">{change_str}</td>
      <td class="{yield_cls}">{yield_str}</td>
      <td>{pe_str}</td>
      <td>{pb_str}</td>
      <td>¥{build_price:.2f}</td>
      <td>¥{add_price:.2f}</td>
    </tr>"""
    return row_html


def generate_html(date_str, stock_results, etf_results, data_sources):
    """生成完整HTML报告"""

    # 汇总卡片数据
    total_count = len(stock_results) + len(etf_results)
    high_yield_count = sum(1 for r in stock_results + etf_results if r.get("div_yield", 0) and r["div_yield"] >= 6)
    avg_yield = sum(r.get("div_yield", 0) or 0 for r in stock_results + etf_results) / total_count if total_count > 0 else 0

    rows = []
    rows.append('  <thead><tr>')
    rows.append('    <th>代码</th><th>名称</th><th>行业</th><th>收盘价</th><th>涨跌幅</th>')
    rows.append('    <th>股息率(TTM)</th><th>PE</th><th>PB</th><th>建仓价</th><th>加仓位</th>')
    rows.append('  </tr></thead>')
    rows.append('  <tbody>')

    # 股票行
    for r in stock_results:
        rows.append(build_row(
            r["code"], r["name"], r["type"],
            r["price"], r.get("pe"), r.get("pb"),
            r.get("div_yield"), r["build_price"], r["add_price"],
            r.get("change_pct")
        ))

    # ETF行（加分隔）
    rows.append('    <tr><td colspan="10" style="background:#1a1a1a;color:#888;font-size:12px;">— ETF —</td></tr>')
    for r in etf_results:
        rows.append(build_row(
            r["code"], r["name"], r["type"],
            r["price"], None, None,
            r.get("div_yield"), r["build_price"], r["add_price"],
            r.get("change_pct"), is_etf=True
        ))

    rows.append('  </tbody>')

    sources_text = "、".join(data_sources)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>红利组合综合估值日报 | {date_str}</title>
<style>{CSS}</style>
</head>
<body>
<h1>红利组合综合估值日报</h1>
<div class="subtitle">
  数据日期：{date_str}（收盘数据） | 数据源：{sources_text}<br>
  自动生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} 北京时间
</div>

<div style="text-align:center;">
  <div class="summary-card">
    <div class="num">{total_count}</div>
    <div class="label">覆盖标的</div>
  </div>
  <div class="summary-card">
    <div class="num">{high_yield_count}</div>
    <div class="label">股息率≥6%</div>
  </div>
  <div class="summary-card">
    <div class="num">{avg_yield:.2f}%</div>
    <div class="label">平均股息率</div>
  </div>
</div>

<h2>一、核心数据表</h2>
<p class="section-note">
  股息率 = 近12个月累计每股分红 ÷ 收盘价（TTM口径）<br>
  建仓价 = 收盘价 × 90% | 加仓位 = 收盘价 × 80%<br>
  PE/PB数据来自akshare东方财富接口，ETF仅展示价格和股息率。
</p>
<table>
{chr(10).join(rows)}
</table>

<h2>二、操作建议</h2>
<div class="info-box">
"""

    # 生成操作建议
    buy_now = []
    wait_list = []
    for r in stock_results + etf_results:
        dy = r.get("div_yield")
        if dy and dy >= 6:
            buy_now.append(f"<strong>{r['name']}({r['code']})</strong> 股息率 {dy:.2f}%，建仓价 ¥{r['build_price']:.2f}")
        elif dy and dy < 3:
            wait_list.append(f"<strong>{r['name']}({r['code']})</strong> 股息率仅 {dy:.2f}%，暂不建议")

    if buy_now:
        html += "  <strong style='color:#ff4444;'>🔴 立即建仓推荐：</strong><br>\n"
        for item in buy_now:
            html += f"  {item}<br>\n"
        html += "<br>\n"

    if wait_list:
        html += "  <strong style='color:#ff9800;'>🟡 暂时观望：</strong><br>\n"
        for item in wait_list:
            html += f"  {item}<br>\n"
        html += "<br>\n"

    html += f"""  <strong>📌 风险提示：</strong><br>
  1. 以上数据仅供参考，不构成投资建议。<br>
  2. 股息率基于历史分红数据，未来分红不保证。<br>
  3. ETF价格受二级市场交易影响，可能存在折溢价。<br>
  4. 港股通红利ETF需扣20%红利税，实际到手约为名义股息率的80%。
</div>

<div class="footer">
  红利组合综合估值日报 | 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}<br>
  数据源：{sources_text}<br>
  本报告由 GitHub Actions 自动化生成，每个工作日 9:30 发送
</div>
</body>
</html>"""

    return html


# ============================================================
# 发送邮件
# ============================================================

def send_email(html_content, date_str):
    """通过QQ邮箱SMTP发送报告"""
    if not SMTP_PASS:
        print("⚠️ 未设置 DIV_SMTP_PASS 环境变量，跳过邮件发送")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"红利组合综合估值日报 {date_str}"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    plain = f"红利组合综合估值日报 {date_str}\n\n本报告覆盖15只红利标的，包含股息率、PE/PB估值、建仓/加仓建议。\n请查看HTML格式邮件获取完整内容。"
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.login(EMAIL_FROM, SMTP_PASS)
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        print(f"✅ 邮件发送成功 → {EMAIL_TO}")
        return True
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")
        return False


# ============================================================
# 主流程
# ============================================================

def main():
    print("=" * 60)
    print(f"红利组合综合估值日报 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    date_str = datetime.now().strftime("%Y-%m-%d")
    data_sources = []
    stock_results = []
    etf_results = []

    # 尝试导入akshare
    try:
        import akshare as ak
        global pd
        import pandas as pd
        data_sources.append("akshare(东方财富)")
        use_akshare = True
        print("✓ akshare 已加载")
    except ImportError:
        use_akshare = False
        print("⚠️ akshare 未安装，将使用备选数据源")

    # 获取股票数据
    print("\n--- 获取个股数据 ---")
    for s in STOCKS:
        code = s["code"]
        name = s["name"]
        result = {"code": code, "name": name, "type": s["type"]}

        # 获取行情
        price_data = None
        if use_akshare:
            price_data = get_stock_price_ak(code)
        if not price_data:
            price_data = get_stock_price_sina(code)
            if price_data:
                data_sources.append("新浪财经")

        if price_data and price_data.get("price"):
            result["price"] = price_data["price"]
            result["pe"] = price_data.get("pe")
            result["pb"] = price_data.get("pb")
            result["change_pct"] = price_data.get("change_pct", 0)

            # 股息率
            ttm_div = None
            if use_akshare:
                div_data = get_dividend_data(code)
                if div_data:
                    ttm_div = div_data["ttm_dividend"]

            # 备选：预设股息
            if not ttm_div and code in PRESET_DIVIDENDS:
                ttm_div = PRESET_DIVIDENDS[code]
                print(f"  {name}({code}) 股息使用预置数据: {ttm_div}")

            result["ttm_div"] = ttm_div
            result["div_yield"] = calc_dividend_yield(result["price"], ttm_div)
            result["build_price"] = calc_build_price(result["price"])
            result["add_price"] = calc_add_price(result["price"])

            print(f"  ✓ {name}({code}) ¥{result['price']:.2f} | "
                  f"股息率 {result.get('div_yield', 'N/A')}% | "
                  f"PE {result.get('pe', 'N/A')}")
        else:
            print(f"  ✗ {name}({code}) 数据获取失败")
            result["price"] = 0
            result["div_yield"] = None
            result["build_price"] = 0
            result["add_price"] = 0

        stock_results.append(result)
        time.sleep(0.5)  # 防止请求过快

    # 获取ETF数据
    print("\n--- 获取ETF数据 ---")
    for e in ETFS:
        code = e["code"]
        name = e["name"]
        result = {"code": code, "name": name, "type": e["type"]}

        price_data = None
        if use_akshare:
            price_data = get_etf_price_ak(code)

        if price_data and price_data.get("price"):
            result["price"] = price_data["price"]
            result["change_pct"] = price_data.get("change_pct", 0)

            # ETF股息
            ttm_div = PRESET_ETF_DIVIDENDS.get(code, 0)
            result["ttm_div"] = ttm_div
            result["div_yield"] = calc_dividend_yield(result["price"], ttm_div)
            result["build_price"] = calc_build_price(result["price"])
            result["add_price"] = calc_add_price(result["price"])

            print(f"  ✓ {name}({code}) ¥{result['price']:.3f} | 股息率 {result.get('div_yield', 'N/A')}%")
        else:
            print(f"  ✗ {name}({code}) 数据获取失败")
            result["price"] = 0
            result["div_yield"] = None
            result["build_price"] = 0
            result["add_price"] = 0

        etf_results.append(result)
        time.sleep(0.5)

    # 生成HTML
    print("\n--- 生成报告 ---")
    if "新浪财经" not in data_sources:
        data_sources.insert(0, "akshare")
    data_sources = list(dict.fromkeys(data_sources))  # 去重

    html = generate_html(date_str, stock_results, etf_results, data_sources)

    # 保存报告
    output_dir = Path(__file__).parent
    report_path = output_dir / f"红利组合综合估值报告_{date_str.replace('-', '')}.html"
    report_path.write_text(html, encoding="utf-8")
    print(f"  ✓ 报告已保存: {report_path}")

    # 也保存一份 latest.html 作为最新报告
    latest_path = output_dir / "红利组合综合估值报告_latest.html"
    latest_path.write_text(html, encoding="utf-8")
    print(f"  ✓ 最新报告: {latest_path}")

    # 发送邮件
    print("\n--- 发送邮件 ---")
    email_sent = send_email(html, date_str)

    # 输出JSON数据（用于GitHub Actions后续步骤）
    report_json = {
        "date": date_str,
        "email_sent": email_sent,
        "total_stocks": len(stock_results),
        "total_etfs": len(etf_results),
        "data_sources": data_sources,
    }
    json_path = output_dir / "report_summary.json"
    json_path.write_text(json.dumps(report_json, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  ✓ 摘要已保存: {json_path}")

    print("\n" + "=" * 60)
    print(f"完成！邮件发送: {'✅ 成功' if email_sent else '❌ 失败/跳过'}")
    print("=" * 60)

    return email_sent


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
