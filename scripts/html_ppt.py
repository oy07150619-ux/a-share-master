#!/usr/bin/env python3
"""
A股 HTML PPT 报告生成器
========================
从数据源生成可在浏览器中翻页的HTML报告。
支持全部5种报告类型：盘前、竞价、早盘、复盘、个股研报。

用法:
  python html_ppt.py --type replay --output report.html
  python html_ppt.py --type stock --code 600519 --output report.html
  python html_ppt.py --data data.json --output report.html
  python html_ppt.py --text "报告内容" --output report.html

注: Linux/macOS可用 python3, Windows使用 python
"""

import json, sys, os, re, subprocess, textwrap
from datetime import datetime

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "reports")
TEMPLATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates", "report_template.html")
COLLECTOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "collector.py")
STOCK_TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools", "stock_data.py")

os.makedirs(REPORT_DIR, exist_ok=True)


def _run(cmd):
    """运行子命令"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.stdout.strip():
            try:
                return json.loads(r.stdout)
            except:
                return r.stdout.strip()
        return {}
    except:
        return {}


def _load_template():
    """加载HTML模板"""
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        return f.read()


def _build_slide(title, content_lines, icon="📊", extra_class=""):
    """生成一个幻灯片HTML"""
    lines = []
    lines.append(f'<div class="slide {extra_class}">')
    if title:
        lines.append(f'  <div class="slide-title"><span class="icon">{icon}</span>{title}</div>')
    for line in content_lines:
        lines.append(f'  {line}')
    lines.append('</div>')
    return "\n".join(lines)


def _kpi_card(value, label, color_class=""):
    """KPI卡片"""
    return f'<div class="kpi-card"><div class="value {color_class}">{value}</div><div class="label">{label}</div></div>'


def _kpi_grid(cards):
    """KPI网格"""
    items = "\n".join(f"      {c}" for c in cards)
    return f'<div class="kpi-grid">\n{items}\n    </div>'


def _data_table(headers, rows):
    """数据表格"""
    h = "".join(f"<th>{h}</th>" for h in headers)
    r = ""
    for row in rows:
        r += "<tr>" + "".join(f"<td{' class=\"left\"' if i==0 else ''}>{c}</td>" for i, c in enumerate(row)) + "</tr>"
    return f'<table class="data-table"><thead><tr>{h}</tr></thead><tbody>{r}</tbody></table>'


def _flow_row(name, pct, flow=""):
    """资金流向行"""
    pct_cls = "green" if pct >= 0 else "red"
    flow_cls = "green" if flow >= 0 else "red"
    pct_str = f"{pct:+.2f}%"
    flow_str = f"{flow/1e8:+.1f}亿" if flow else ""
    flow_part = f'<span class="flow {flow_cls}">{flow_str}</span>' if flow_str else ""
    return f'<div class="flow-row"><span class="name">{name}</span><span class="pct {pct_cls}">{pct_str}</span>{flow_part}</div>'


def _analysis_box(title, content):
    """分析框"""
    return f'<div class="analysis-box"><div class="title">{title}</div><div class="content">{content}</div></div>'


def _risk_box(content):
    return f'<div class="risk-box"><div class="title">⚠ 风险提示</div><div class="content">{content}</div></div>'


def _bullet_list(items, colors=None):
    """列表"""
    lis = []
    for i, item in enumerate(items):
        cls = f' class="{colors[i]}"' if colors and i < len(colors) else ""
        lis.append(f'<li{cls}>{item}</li>')
    return f'<ul class="bullet-list">{"".join(lis)}</ul>'


def _sentiment_bar(up_pct, down_pct, flat_pct=0):
    """情绪条"""
    return f'''
    <div class="sentiment-labels">
      <span style="color:var(--green)">↑大涨 {up_pct:.0f}%</span>
      <span>{flat_pct:.0f}%</span>
      <span style="color:var(--red)">↓大跌 {down_pct:.0f}%</span>
    </div>
    <div class="sentiment-bar">
      <div class="up" style="width:{up_pct:.1f}%"></div>
      <div class="flat" style="width:{flat_pct:.1f}%"></div>
      <div class="down" style="width:{down_pct:.1f}%"></div>
    </div>'''


def _scenario_card(label, content, cls):
    return f'<div class="scenario-card {cls}"><div class="label">{label}</div><div class="content">{content}</div></div>'


# ============ Report Generators ============

def _generate_cover_slides(report_type, date_str, extra_meta=""):
    """生成封面幻灯片"""
    titles = {
        "premarket": "A股盘前分析",
        "auction": "集合竞价解读",
        "morning": "早盘解读",
        "replay": "A股收盘复盘",
        "stock": "个股深度研报",
    }
    title = titles.get(report_type, "A股综合研报")
    
    slides = []
    # Cover slide
    meta = f"报告日期：{date_str}"
    if extra_meta:
        meta += f"<br>{extra_meta}"
    
    slides.append(_build_slide(None, [
        f'<div class="cover-slide slide" style="display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;height:100%;">',
        f'  <div class="main-title">{title}</div>',
        f'  <div class="decor-line"></div>',
        f'  <div class="sub-title">A股综合研报</div>',
        f'  <div class="decor-line"></div>',
        f'  <div class="meta">{meta}</div>',
        f'  <div class="stamp">📈 仅供参考</div>',
        f'</div>',
    ], icon="", extra_class="cover-slide"))
    
    return slides


def _generate_text_slides(text_content, report_type, date_str):
    """从纯文本内容生成幻灯片
    按语义分割文本为多个段落/模块，每个模块一页。
    """
    slides = _generate_cover_slides(report_type, date_str)
    lines = text_content.strip().split("\n")
    
    current_title = ""
    current_content = []
    
    def flush_section():
        nonlocal current_title, current_content
        if current_content:
            slides.append(_build_slide(current_title, current_content))
            current_content = []
    
    for line in lines:
        stripped = line.strip()
        
        # Section headers as new slides
        if stripped.startswith("## ") or stripped.startswith("# "):
            flush_section()
            current_title = stripped.lstrip("#").strip()
            continue
        
        if stripped.startswith("### "):
            flush_section()
            current_title = stripped.lstrip("#").strip()
            continue
        
        # Table rows
        if stripped.startswith("|") and stripped.endswith("|"):
            current_content.append(f'<p class="slide-text small">{stripped}</p>')
            continue
        
        # Bold items
        if stripped.startswith("**") and stripped.endswith("**"):
            current_content.append(f'<p class="slide-text" style="font-weight:700;color:var(--accent);">{stripped.strip("*")}</p>')
            continue
        
        # Bullets
        if stripped.startswith("- ") or stripped.startswith("* "):
            current_content.append(f'<p class="slide-text" style="padding-left:12px;">• {stripped[2:]}</p>')
            continue
        
        # Separator
        if stripped == "---":
            continue
        
        # Empty line
        if not stripped:
            if current_content:
                current_content.append('<div style="height:8px;"></div>')
            continue
        
        # Regular text
        current_content.append(f'<p class="slide-text">{stripped}</p>')
    
    flush_section()
    
    # Footer slide
    slides.append(_build_slide("免责声明", [
        '<p class="slide-text small muted">',
        '本报告内容仅基于公开数据及AI分析生成，不构成任何投资建议或荐股行为。',
        '投资者据此操作，风险自担。证券市场有风险，投资需谨慎。',
        '</p>',
        f'<p class="slide-text small muted">生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}</p>',
        '<div class="slide-footer">Data: 东方财富·腾讯·新浪·AKShare | A股综合研报</div>',
    ], icon="⚖️"))
    
    return slides


def _generate_replay_slides(data, date_str):
    """生成复盘报告的幻灯片"""
    slides = _generate_cover_slides("replay", date_str)
    
    # Slide 1: 大盘概况
    indexes = data.get("indexes", [])
    kpi_cards = []
    for idx in indexes[:4]:
        name = idx.get("指数", "")
        price = idx.get("最新", 0)
        pct = idx.get("涨跌幅", 0)
        cls = "green" if pct >= 0 else "red"
        pct_str = f"{pct:+.2f}%"
        kpi_cards.append(_kpi_card(pct_str, name, cls))
    
    if kpi_cards:
        slides.append(_build_slide("大盘收盘概况", [
            _kpi_grid(kpi_cards),
            '<p class="slide-text small muted">数据来源：东方财富 | 更新时间：' + datetime.now().strftime("%H:%M") + '</p>',
        ], icon="🏛️"))
    
    # Slide 2: 涨跌家数+情绪
    updown = data.get("updown", {})
    limits = data.get("limits", {})
    up = updown.get("上涨", 0)
    down = updown.get("下跌", 0)
    lu = limits.get("涨停", 0)
    ld = limits.get("跌停", 0)
    
    total_st = up + down
    if total_st > 0:
        up_pct = up / total_st * 100
        down_pct = down / total_st * 100
    else:
        up_pct = down_pct = 0
    
    mood = "强势 🔥"
    if lu > ld * 2:
        mood = "强势 🔥 做多情绪高涨"
    elif lu > ld:
        mood = "偏多 👍 多方占优"
    elif ld > lu * 2:
        mood = "恐慌 😱 亏钱效应明显"
    elif ld > lu:
        mood = "偏空 👎 市场谨慎"
    else:
        mood = "中性 ➖ 多空均衡"
    
    slides.append(_build_slide("市场情绪分析", [
        _kpi_grid([
            _kpi_card(up, "上涨家数", "green"),
            _kpi_card(down, "下跌家数", "red"),
            _kpi_card(lu, "涨停家数", "green"),
            _kpi_card(ld, "跌停家数", "red"),
        ]),
        _sentiment_bar(up_pct, down_pct),
        _analysis_box("情绪判断", mood),
    ], icon="📊"))
    
    # Slide 3: 板块排行+资金
    sector_flow = data.get("sector_flow", {})
    if isinstance(sector_flow, dict):
        gain = sector_flow.get("涨幅榜", [])[:8]
        flow_in = sector_flow.get("资金流入榜", [])[:5]
        flow_out = sector_flow.get("资金流出榜", [])[:5]
        
        if gain:
            rows = []
            for s in gain:
                name = s.get("板块名称", "")
                pct = s.get("涨跌幅", 0)
                flow = s.get("主力净流入", 0)
                lead = s.get("领涨股票", "")
                row = f"<tr><td class='left'>{name}</td><td class=\"{'green' if pct>=0 else 'red'}\">{pct:+.2f}%</td>"
                row += f"<td class=\"{'green' if flow>=0 else 'red'}\">{flow/1e8:+.1f}亿</td>"
                row += f"<td class='left'>{lead}</td></tr>"
                rows.append(row)
            
            slides.append(_build_slide("行业板块排行", [
                _data_table(["板块", "涨跌幅", "主力净流入", "领涨股"], 
                          [[s.get("板块名称",""), 
                            f"{s.get('涨跌幅',0):+.2f}%",
                            f"{s.get('主力净流入',0)/1e8:+.1f}亿",
                            s.get("领涨股票","")] for s in gain]),
            ], icon="📈"))
        
        if flow_in or flow_out:
            rows = []
            max_flow = max(
                max([abs(f.get("主力净流入",0)) for f in flow_in], default=1),
                max([abs(f.get("主力净流入",0)) for f in flow_out], default=1)
            ) or 1
            
            items = []
            items.append('<p class="slide-subtitle">🔴 主力资金流入 TOP5</p>')
            for s in flow_in:
                name = s.get("板块名称", "")
                f = s.get("主力净流入", 0)
                pct = s.get("涨跌幅", 0)
                items.append(_flow_row(name, pct, f))
            
            items.append('<p class="slide-subtitle">🔵 主力资金流出 TOP5</p>')
            for s in flow_out:
                name = s.get("板块名称", "")
                f = s.get("主力净流入", 0)
                pct = s.get("涨跌幅", 0)
                items.append(_flow_row(name, pct, f))
            
            slides.append(_build_slide("板块资金流向", items, icon="💰"))
    
    # Slide 4: 个股排行
    gainers = data.get("gainers", [])[:10]
    losers = data.get("losers", [])[:10]
    
    if gainers:
        slides.append(_build_slide("涨幅TOP10", [
            _data_table(["排行", "名称", "代码", "涨跌幅", "最新价"],
                       [(str(i+1), g.get("名称",""), g.get("代码",""),
                         f"{g.get('涨跌幅',0):+.2f}%",
                         f"{g.get('最新价',0):.2f}")
                        for i, g in enumerate(gainers[:10])]),
        ], icon="🚀"))
    
    if losers:
        slides.append(_build_slide("跌幅TOP10", [
            _data_table(["排行", "名称", "代码", "涨跌幅", "最新价"],
                       [(str(i+1), l.get("名称",""), l.get("代码",""),
                         f"{l.get('涨跌幅',0):+.2f}%",
                         f"{l.get('最新价',0):.2f}")
                        for i, l in enumerate(losers[:10])]),
        ], icon="📉"))
    
    # Slide 5: 深度分析
    sentiment_analysis = []
    if lu > ld * 2:
        sentiment_analysis.append("涨停家数远大于跌停，市场做多情绪强烈。")
    elif ld > lu * 2:
        sentiment_analysis.append("跌停家数远超涨停，市场恐慌情绪蔓延。")
    else:
        sentiment_analysis.append("涨跌停比基本均衡，市场情绪中性。")
    
    slides.append(_build_slide("深度分析", [
        _analysis_box("情绪分析", " ".join(sentiment_analysis)),
        _analysis_box("板块轮动", "今日市场板块轮动情况：关注资金流入前列板块的持续性。"),
    ], icon="🔍"))
    
    return slides


def generate(data, output=None, report_type="replay"):
    """生成HTML报告"""
    date_str = data.get("date", data.get("日期", datetime.now().strftime("%Y-%m-%d")))
    
    # Determine what to generate
    if report_type == "text":
        text = data.get("text", "")
        slides = _generate_text_slides(text, "replay", date_str)
    elif report_type == "replay":
        slides = _generate_replay_slides(data, date_str)
    else:
        slides = _generate_text_slides(data.get("text", str(data)), report_type, date_str)
    
    # Build slides HTML
    slides_html = "\n".join(slides)
    
    # Load template and inject
    template = _load_template()
    title_map = {
        "premarket": "盘前分析",
        "auction": "集合竞价解读",
        "morning": "早盘解读",
        "replay": "收盘复盘",
        "stock": "个股深度研报",
        "text": "综合研报",
    }
    report_title = f"A股{title_map.get(report_type, '综合研报')} {date_str}"
    
    html = template.replace("{报告标题}", report_title)
    html = html.replace("{SLIDES_CONTENT}", slides_html)
    
    # Save
    if not output:
        output = os.path.join(REPORT_DIR, f"{report_type}_{date_str}.html")
    
    with open(output, "w", encoding="utf-8") as f:
        f.write(html)
    
    return output


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="A股 HTML PPT 报告生成器")
    parser.add_argument("--type", choices=["premarket", "auction", "morning", "replay", "stock", "text"],
                       default="replay", help="报告类型")
    parser.add_argument("--output", help="输出文件路径")
    parser.add_argument("--data", help="数据JSON文件路径")
    parser.add_argument("--code", help="股票代码（stock类型时）")
    parser.add_argument("--text", help="直接输入文本内容")
    
    args = parser.parse_args()
    
    data = {}
    
    if args.data:
        with open(args.data, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif args.text:
        data = {"text": args.text}
    else:
        # Auto-collect via subprocess (avoid import path issues)
        collector_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "collector.py")
        try:
            r = subprocess.check_output([sys.executable, collector_script, "all", "--json"], text=True, timeout=60)
            raw = json.loads(r)
            data = raw
            data["gainers"] = []
            data["losers"] = []
            data["date"] = datetime.now().strftime("%Y-%m-%d")
            # Get gains/losses separately
            try:
                r2 = subprocess.check_output([sys.executable, collector_script, "tops", "--json", "--limit", "20"], text=True, timeout=30)
                tops = json.loads(r2)
                data["gainers"] = tops.get("gainers", [])
                data["losers"] = tops.get("losers", [])
            except:
                pass
        except Exception as e:
            print(f"[自动采集失败] {e}", file=sys.stderr)
            data = {"date": datetime.now().strftime("%Y-%m-%d"), "indexes": [], "sector_flow": {}, "gainers": [], "losers": []}
    
    output_path = generate(data, args.output, args.type)
    print(f"✅ HTML PPT报告已生成: {output_path}")
