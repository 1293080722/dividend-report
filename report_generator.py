#!/usr/bin/env python3
"""
红利组合综合估值日报生成器
用于 GitHub Actions 每个工作日9:30自动运行
数据源：akshare（优先）+ 新浪财经（备选）
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

# 预置股息数据（TTM，近12个月每股累计分红，静态兜底）
PRESET_DIVIDENDS = {
    "600036": 3.026,
    "601398": 0.310,
    "601939": 0.407,
    "601658": 0.264,
    "601988": 0.248,
    "601318": 2.700,
    "600941": 2.205,
    "600887": 1.380,
    "600690": 1.155,
    "601888": 0.700,
    "600900": 0.790,
    "002096": 0.256,
    "002027": 0.340,
}

PRESET_ETF_DIVIDENDS = {
    "561580": 0.125,
    "513530": 0.120,
}

# 邮件配置
EMAIL_FROM = os.environ.get("DIV_EMAIL_FROM", "1293080722@qq.com")
EMAIL_TO = os.environ.get("DIV_EMAIL_TO", "1293080722@qq.com")
SMTP_PASS = os.environ.get("DIV_SMTP_PASS", "")
SMTP_SERVER = "smtp.qq.com"
SMTP_PORT = 465

BUILD_RATIO = 0.90
ADD_RATIO = 0.80

# ============================================================
# 数据获取
# ============================================================

def get_stock_price_ak(code):
    """通过akshare获取个股实时行情"""
    try:
        import akshare as ak
        market = "sh" if code.startswith("6") else "sz"
        df = ak.stock_zh_a_spot_em()
        row = df[df["代码"] == code]
        if row.empty:
            return None
        row = row.iloc[0]
        return {
            "price": float(row["最新价"]),
            "pe": float(row["市盈率-动态"]) if str(row["市盈率-动态"]) not in ["-", ""] else None,
            "pb": float(row["市净率"]) if str(row["市净率"]) not in ["-", ""] else None,
            "change_pct": float(row["涨跌幅"]) if str(row["涨跌幅"]) not in ["-", ""] else 0,
        }
    except Exception as e:
        print(f"[akshare] {code} 获取失败: {e}")
        return None


def get_etf_price_ak(code):
    """通过akshare获取ETF行情"""
    try:
        import akshare as ak
        df = ak.fund_etf_spot_em()
        row = df[df["代码"] == code]
        if row.empty:
            return None
        row = row.iloc[0]
        return {
            "price": float(row["最新价"]),
            "change_pct": float(row["涨跌幅"]) if str(row["涨跌幅"]) not in ["-", ""] else 0,
        }
    except Exception as e:
        print(f"[akshare] ETF {code} 获取失败: {e}")
        return None


def get_stock_price_sina(code):
    """新浪财经实时行情（备选源）"""
    try:
        import requests
        market = "sh" if code.startswith("6") else "sz"
        url = f"https://hq.sinajs.cn/list={market}{code}"
        headers = {"Referer": "https://finance.sina.com.cn"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "gb2312"
        data = resp.text.split('"')[1].split(",")
        if len(data) < 30:
            return None
        prev_close = float(data[2])
        price = float(data[3])
        return {
            "price": price,
            "pe": None,
            "pb": None,
            "change_pct": round((price / prev_close - 1) * 100, 2) if prev_close > 0 else 0,
        }
    except Exception as e:
        print(f"[sina] {code} 获取失败: {e}")
        return None


# ============================================================
# 计算逻辑
# ============================================================

def calc_dividend_yield(price, ttm_div):
    if not price or not ttm_div or price <= 0:
        return None
    return round(ttm_div / price * 100, 2)


def calc_build_price(price):
    return round(price * BUILD_RATIO, 2)


def calc_add_price(price):
    return round(price * ADD_RATIO, 2)


def classify_yield(y):
    if y is None:
        return "yield-low", "N/A"
    if y >= 6:
        return "yield-high", f"{y:.2f}%"
    elif y >= 3:
        return "yield-mid", f"{y:.2f}%"
    else:
        return "yield-low", f"{y:.2f}%"


def get_type_tag(t):
    tags = {
        "bank": ("tag-bank", "银行"),
        "insurance": ("tag-insurance", "保险"),
        "telecom": ("tag-telecom", "电信"),
        "consumer": ("tag-consumer", "消费"),
        "power": ("tag-power", "电力"),
        "industry": ("tag-industry", "化工"),
        "media": ("tag-media", "传媒"),
        "etf": ("tag-etf", "ETF"),
    }
    return tags.get(t, ("tag-industry", t))


# ============================================================
# HTML报告生成（黑底白字）
# ============================================================

CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body {
  font-family:"Microsoft YaHei","PingFang SC","Hiragino Sans GB",sans-serif;
  background:#000; color:#e0e0e0; line-height:1.8;
  padding:40px 60px; max-width:1400px; margin:0 auto;
}
h1 { font-size:28px; font-weight:700; text-align:center; margin-bottom:8px; letter-spacing:2px; color:#fff; }
.subtitle { text-align:center; color:#999; font-size:14px; margin-bottom:30px; border-bottom:2px solid #444; padding-bottom:15px; }
h2 { font-size:20px; margin:35px 0 15px 0; padding-left:12px; border-left:4px solid #e74c3c; color:#fff; }
.info-box { background:#1a1a1a; border:1px solid #333; padding:16px 20px; margin:20px 0; font-size:13px; line-height:2; border-radius:4px; }
.info-box strong { display:inline-block; min-width:6em; color:#aaa; }
table { width:100%; border-collapse:collapse; margin:20px 0; font-size:14px; }
th { background:#1a1a1a; color:#fff; padding:12px 10px; text-align:center; font-weight:600; font-size:13px; white-space:nowrap; border-bottom:2px solid #444; }
td { padding:10px 10px; text-align:center; border-bottom:1px solid #2a2a2a; color:#ccc; }
tr:nth-child(even) { background:#0d0d0d; }
tr:hover { background:#1a1a1a; }
.price { font-weight:700; font-size:15px; color:#fff; }
.yield-high { color:#ff4444; font-weight:700; }
.yield-mid { color:#ff9800; font-weight:600; }
.yield-low { color:#888; }
.tag-bank { background:#2c3e50; padding:2px 8px; border-radius:3px; font-size:11px; }
.tag-consumer { background:#8e44ad; padding:2px 8px; border-radius:3px; font-size:11px; }
.tag-power { background:#2980b9; padding:2px 8px; border-radius:3px; font-size:11px; }
.tag-insurance { background:#d35400; padding:2px 8px; border-radius:3px; font-size:11px; }
.tag-media { background:#16a085; padding:2px 8px; border-radius:3px; font-size:11px; }
.tag-industry { background:#7f8c8d; padding:2px 8px; border-radius:3px; font-size:11px; }
.tag-etf { background:#c0392b; padding:2px 8px; border-radius:3px; font-size:11px; }
.tag-telecom { background:#e67e22; padding:2px 8px; border-radius:3px; font-size:11px; }
.footer { margin-top:40px; padding-top:20px; border-top:2px solid #444; font-size:12px; color:#666; text-align:center; line-height:2; }
.section-note { font-size:13px; color:#888; margin:8px 0 16px 0; line-height:1.6; }
.summary-card { display:inline-block; background:#1a1a1a; border:1px solid #333; padding:12px 24px; margin:10px 8px; border-radius:4px; text-align:center; min-width:140px; }
.summary-card .num { font-size:24px; font-weight:700; color:#ff4444; }
.summary-card .label { font-size:12px; color:#888; margin-top:4px; }
"""

def build_row(code, name, type_, price, pe, pb, div_yield, build_price, add_price, change_pct):
    tag_cls, tag_name = get_type_tag(type_)
    yield_cls, yield_str = classify_yield(div_yield)
    pe_str = f"{pe:.2f}" if pe else "N/A"
    pb_str = f"{pb:.2f}" if pb else "N/A"
    change_str = f"{change_pct:+.2f}%" if change_pct is not None else "N/A"
    change_cls = "yield-high" if change_pct and change_pct > 0 else ("yield-mid" if change_pct and change_pct < 0 else "")
    return (
        f"    <tr>\n"
        f"      <td>{code}</td>\n"
        f"      <td>{name}</td>\n"
        f'      <td><span class="{tag_cls}">{tag_name}</span></td>\n'
        f'      <td class="price">¥{price:.2f}</td>\n'
        f'      <td class="{change_cls}">{change_str}</td>\n'
        f'      <td class="{yield_cls}">{yield_str}</td>\n'
        f"      <td>{pe_str}</td>\n"
        f"      <td>{pb_str}</td>\n"
        f"      <td>¥{build_price:.2f}</td>\n"
        f"      <td>¥{add_price:.2f}</td>\n"
        f"    </tr>"
    )


def generate_html(date_str, stock_results, etf_results):
    total_count = len(stock_results) + len(etf_results)
    high_yield_count = sum(1 for r in stock_results + etf_results if r.get("div_yield") and r["div_yield"] >= 6)
    yields = [r.get("div_yield", 0) or 0 for r in stock_results + etf_results]
    avg_yield = sum(yields) / total_count if total_count > 0 else 0

    rows = []
    rows.append('  <thead><tr>')
    rows.append('    <th>代码</th><th>名称</th><th>行业</th><th>收盘价</th><th>涨跌幅</th>')
    rows.append('    <th>股息率(TTM)</th><th>PE</th><th>PB</th><th>建仓价</th><th>加仓位</th>')
    rows.append('  </tr></thead>')
    rows.append('  <tbody>')

    for r in stock_results:
        rows.append(build_row(
            r["code"], r["name"], r["type"],
            r["price"], r.get("pe"), r.get("pb"),
            r.get("div_yield"), r["build_price"], r["add_price"],
            r.get("change_pct")
        ))

    rows.append('    <tr><td colspan="10" style="background:#111;color:#888;font-size:12px;text-align:center;">——— ETF ———</td></tr>')
    for r in etf_results:
        rows.append(build_row(
            r["code"], r["name"], r["type"],
            r["price"], None, None,
            r.get("div_yield"), r["build_price"], r["add_price"],
            r.get("change_pct")
        ))

    rows.append('  </tbody>')

    # 操作建议
    buy_now = []
    wait_list = []
    for r in stock_results + etf_results:
        dy = r.get("div_yield")
        if dy and dy >= 6:
            buy_now.append(f"<strong>{r['name']}({r['code']})</strong> 股息率 {dy:.2f}%，建仓价 ¥{r['build_price']:.2f}")
        elif dy and dy < 3:
            wait_list.append(f"<strong>{r['name']}({r['code']})</strong> 股息率仅 {dy:.2f}%，暂不建议")

    advice_html = ""
    if buy_now:
        advice_html += '  <strong style="color:#ff4444;">🔴 立即建仓推荐：</strong><br>\n'
        for item in buy_now:
            advice_html += f"  {item}<br>\n"
        advice_html += "<br>\n"
    if wait_list:
        advice_html += '  <strong style="color:#ff9800;">🟡 暂时观望：</strong><br>\n'
        for item in wait_list:
            advice_html += f"  {item}<br>\n"
        advice_html += "<br>\n"

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')

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
  数据日期：{date_str}（收盘数据）<br>
  自动生成时间：{now_str} 北京时间
</div>

<div style="text-align:center;">
  <div class="summary-card"><div class="num">{total_count}</div><div class="label">覆盖标的</div></div>
  <div class="summary-card"><div class="num">{high_yield_count}</div><div class="label">股息率≥6%</div></div>
  <div class="summary-card"><div class="num">{avg_yield:.2f}%</div><div class="label">平均股息率</div></div>
</div>

<h2>一、核心数据表</h2>
<p class="section-note">
  股息率 = 近12个月累计每股分红 ÷ 收盘价（TTM口径）<br>
  建仓价 = 收盘价 × 90% | 加仓位 = 收盘价 × 80%<br>
  PE/PB数据来自东方财富接口，ETF仅展示价格和股息率。
</p>
<table>
{chr(10).join(rows)}
</table>

<h2>二、操作建议</h2>
<div class="info-box">
{advice_html}
  <strong>📌 风险提示：</strong><br>
  1. 以上数据仅供参考，不构成投资建议。<br>
  2. 股息率基于历史分红数据，未来分红不保证。<br>
  3. ETF价格受二级市场交易影响，可能存在折溢价。<br>
  4. 港股通红利ETF需扣20%红利税，实际到手约为名义股息率的80%。
</div>

<div class="footer">
  红利组合综合估值日报 | 自动生成于 {now_str}<br>
  本报告由 GitHub Actions 自动化生成，每周一、周三 9:30 发送
</div>
</body>
</html>"""
    return html


# ============================================================
# 发送邮件
# ============================================================

def send_email(html_content, date_str):
    if not SMTP_PASS:
        print("⚠️ 未设置 DIV_SMTP_PASS 环境变量，跳过邮件发送")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"红利组合综合估值日报 {date_str}"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    plain = (
        f"红利组合综合估值日报 {date_str}\n\n"
        f"本报告覆盖{len(STOCKS)}只股票和{len(ETFS)}只ETF，\n"
        f"包含股息率、PE/PB估值、建仓/加仓建议。\n"
        f"请使用支持HTML的邮件客户端查看完整内容。"
    )
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
    stock_results = []
    etf_results = []

    # 尝试导入akshare
    try:
        import akshare as ak
        use_akshare = True
        print("✓ akshare 已加载")
    except ImportError:
        use_akshare = False
        print("⚠️ akshare 未安装，将使用新浪财经备选源")

    # 获取股票数据
    print("\n--- 获取个股数据 ---")
    for s in STOCKS:
        code = s["code"]
        name = s["name"]
        result = {"code": code, "name": name, "type": s["type"]}

        price_data = None
        if use_akshare:
            price_data = get_stock_price_ak(code)
        if not price_data:
            price_data = get_stock_price_sina(code)
            if price_data:
                print(f"  {name}({code}) 使用新浪财经数据")

        if price_data and price_data.get("price"):
            result["price"] = price_data["price"]
            result["pe"] = price_data.get("pe")
            result["pb"] = price_data.get("pb")
            result["change_pct"] = price_data.get("change_pct", 0)

            # 股息率：优先用预置数据（可靠），未来可接入akshare分红接口
            ttm_div = PRESET_DIVIDENDS.get(code)
            result["ttm_div"] = ttm_div
            result["div_yield"] = calc_dividend_yield(result["price"], ttm_div)
            result["build_price"] = calc_build_price(result["price"])
            result["add_price"] = calc_add_price(result["price"])

            print(f"  ✓ {name}({code}) ¥{result['price']:.2f} | 股息率 {result.get('div_yield', 'N/A')}% | PE {result.get('pe', 'N/A')}")
        else:
            print(f"  ✗ {name}({code}) 数据获取失败")
            result["price"] = 0
            result["div_yield"] = None
            result["build_price"] = 0
            result["add_price"] = 0

        stock_results.append(result)
        time.sleep(0.3)

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
        time.sleep(0.3)

    # 生成HTML
    print("\n--- 生成报告 ---")
    html = generate_html(date_str, stock_results, etf_results)

    # 保存报告
    output_dir = Path(__file__).parent
    report_path = output_dir / f"红利组合综合估值报告_{date_str.replace('-', '')}.html"
    report_path.write_text(html, encoding="utf-8")
    print(f"  ✓ 报告已保存: {report_path}")

    latest_path = output_dir / "红利组合综合估值报告_latest.html"
    latest_path.write_text(html, encoding="utf-8")
    print(f"  ✓ 最新报告: {latest_path}")

    # 发送邮件
    print("\n--- 发送邮件 ---")
    email_sent = send_email(html, date_str)

    # 输出JSON摘要
    report_json = {
        "date": date_str,
        "email_sent": email_sent,
        "total_stocks": len(stock_results),
        "total_etfs": len(etf_results),
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
