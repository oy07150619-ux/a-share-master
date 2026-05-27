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


# ============ 集合竞价报告幻灯片生成 ============

def _tag_limit(status):
    """生成涨停分类的HTML标签"""
    if not status:
        return ''
    tag_map = {
        'limit_up_sealed': ('tag-sealed', '封板'),
        'limit_up_touched': ('tag-touched', '触板'),
        'near_limit_up': ('tag-near', '近板'),
        'limit_down_sealed': ('tag-sealed', '封板'),
        'limit_down_touched': ('tag-touched', '触板'),
        'near_limit_down': ('tag-near', '近板'),
    }
    cls, label = tag_map.get(status, ('', ''))
    if cls:
        return f'<span class="{cls}">{label}</span>'
    return ''


def _news_item(source, content, tag=""):
    """生成结构化新闻条目"""
    tag_html = f'<span class="news-tag">{tag}</span>' if tag else ''
    return f'<div class="news-item"><span class="news-source">{source}</span>{tag_html}<span class="slide-text small">{content}</span></div>'


def _warning_box(title, content):
    """生成警告框"""
    return f'<div class="warning-box"><div class="title">⚠ {title}</div><div class="content">{content}</div></div>'


def _generate_auction_slides(data, date_str):
    """
    生成集合竞价解读报告的幻灯片（9页）
    
    参数:
        data (dict): 包含竞价、涨幅榜、跌幅榜、情绪、风险等数据
        date_str (str): 日期字符串
    """
    slides = _generate_cover_slides("auction", date_str)
    
    # ==== 从 data 中提取数据（带安全缺省值）====
    indexes = data.get("indexes", [])
    
    # 指数竞价涨跌幅
    bid_pct = data.get("竞价涨跌幅", data.get("bid_pct", ''))
    if not bid_pct and indexes:
        sh = next((i for i in indexes if i.get('指数','') in ['上证指数','上证']), {})
        bid_pct = sh.get('涨跌幅', sh.get('最新', ''))
    # 尝试从竞价涨幅推断
    try:
        bid_pct = float(bid_pct) if bid_pct else 0
    except (ValueError, TypeError):
        bid_pct = 0
    
    # 涨跌停/涨跌家数
    limits = data.get("limits", {})
    lu = limits.get("涨停", limits.get("涨停数", 0))
    ld = limits.get("跌停", limits.get("跌停数", 0))
    
    updown = data.get("updown", {})
    up = updown.get("上涨", updown.get("上涨家数", 0))
    down = updown.get("下跌", updown.get("下跌家数", 0))
    
    # 涨幅/跌幅榜
    gainers = data.get("gainers", data.get("涨幅榜", []))[:10]
    losers = data.get("losers", data.get("跌幅榜", []))[:10]
    
    # 分析引擎结果
    analysis = data.get("analysis", {})
    volume_div = analysis.get("volume_divergence", {})
    signal_matrix = analysis.get("signal_matrix", {})
    support_resist = analysis.get("support_resistance", {})
    risks = analysis.get("risks", {})
    news_list = analysis.get("news", data.get("news", []))
    
    # ============ 幻灯片1: 竞价现象总览 ============
    bid_direction = "高开" if bid_pct > 0 else ("低开" if bid_pct < 0 else "平开")
    bid_abs = abs(bid_pct)
    
    # 涨停触板数（从涨幅榜中按涨停分类统计）
    sealed_up = sum(1 for s in gainers if s.get('limit_status','') == 'limit_up_sealed')
    touched_up = sum(1 for s in gainers if s.get('limit_status','') in ('limit_up_sealed', 'limit_up_touched'))
    sealed_down = sum(1 for s in losers if s.get('limit_status','') == 'limit_down_sealed')
    touched_down = sum(1 for s in losers if s.get('limit_status','') in ('limit_down_sealed', 'limit_down_touched'))
    
    kpi_cards = []
    kpi_cards.append(_kpi_card(f"{bid_pct:+.2f}%", f"竞价{bid_direction}", "green" if bid_pct > 0 else "red"))
    kpi_cards.append(_kpi_card(touched_up, "涨停触板", "green"))
    kpi_cards.append(_kpi_card(touched_down, "跌停触板", "red"))
    kpi_cards.append(_kpi_card(f"{sealed_up}/{touched_up}", "封板/触板", "green" if sealed_up > 0 else ""))
    
    slides.append(_build_slide("竞价现象总览", [
        _kpi_grid(kpi_cards),
        '<p class="slide-text small muted">涨停封板/触板说明：封板=竞价价精确等于涨停价；触板=涨幅≥9.9%但未封板</p>',
        _analysis_box("开盘定性", f"上证竞价{bid_direction}{bid_abs:.2f}%，涨停触板{touched_up}家，跌停触板{touched_down}家")
    ], icon="🔔"))
    
    # ============ 幻灯片2: 涨幅榜分析 ============
    if gainers:
        g_rows = []
        for i, g in enumerate(gainers[:10]):
            pct = g.get('涨跌幅', 0)
            pct_str = f"{pct:+.2f}%" if isinstance(pct, (int, float)) else str(pct)
            vol = g.get('成交额', g.get('成交量', ''))
            try:
                vol_str = f"{float(vol)/10000:.1f}万" if float(vol) > 0 else "-"
            except:
                vol_str = "-"
            status = g.get('limit_status', '')
            tag = _tag_limit(status)
            g_rows.append((
                str(i+1),
                g.get('名称', ''),
                g.get('代码', ''),
                pct_str,
                vol_str,
                tag
            ))
        slides.append(_build_slide("竞价涨幅榜TOP10", [
            _data_table(["#", "名称", "代码", "竞价涨幅", "竞价额", "涨停分类"], g_rows),
        ], icon="🚀"))
    
    # ============ 幻灯片3: 跌幅榜分析 ============
    if losers:
        l_rows = []
        for i, l in enumerate(losers[:10]):
            pct = l.get('涨跌幅', 0)
            pct_str = f"{pct:+.2f}%" if isinstance(pct, (int, float)) else str(pct)
            vol = l.get('成交额', l.get('成交量', ''))
            try:
                vol_str = f"{float(vol)/10000:.1f}万" if float(vol) > 0 else "-"
            except:
                vol_str = "-"
            status = l.get('limit_status', '')
            tag = _tag_limit(status)
            l_rows.append((
                str(i+1),
                l.get('名称', ''),
                l.get('代码', ''),
                pct_str,
                vol_str,
                tag
            ))
        slides.append(_build_slide("竞价跌幅榜TOP10", [
            _data_table(["#", "名称", "代码", "竞价跌幅", "竞价额", "跌停分类"], l_rows),
        ], icon="📉"))
    
    # ============ 幻灯片4: 量能分析 ============
    vol_items = []
    vol_items.append('<p class="slide-subtitle">量能分化指数</p>')
    
    ratio = volume_div.get('ratio', 1.0)
    label = volume_div.get('label', 'balanced')
    
    # 显示量能比例
    ratio_str = f"涨幅TOP5总成交额 / 跌幅TOP5总成交额 = {ratio:.2f}:1"
    vol_items.append(f'<p class="slide-text">{ratio_str}</p>')
    
    # 标签可视化
    label_map = {
        'extremely_bullish': ('量能严重偏多 🔥', 'green'),
        'bullish': ('量能偏多 👍', 'green'),
        'balanced': ('量能均衡 ➖', 'yellow'),
        'bearish': ('量能偏空 👎', 'red'),
        'extremely_bearish': ('量能严重偏空 😱', 'red'),
    }
    lbl, lbl_cls = label_map.get(label, ('', ''))
    vol_items.append(f'<p class="slide-text" style="color:var(--{lbl_cls});font-weight:700;">{lbl}</p>')
    
    # 虚涨预警/真实封板判断
    fake_up = sum(1 for s in gainers[:10] 
                  if float(s.get('涨跌幅', 0) or 0) > 8.0 
                  and float(s.get('成交额', 0) or 0) < 1000000)
    real_up = sum(1 for s in gainers[:10]
                  if float(s.get('涨跌幅', 0) or 0) > 8.0
                  and float(s.get('成交额', 0) or 0) >= 5000000)
    
    vol_items.append('<p class="slide-subtitle">封板质量</p>')
    if fake_up > 0:
        vol_items.append(_analysis_box('虚涨预警 ⚠️', 
            f'涨幅榜中有{fake_up}只涨幅>8%但竞价成交额<100万，缺乏真实买盘支撑，谨防高开低走'))
    if real_up > 0:
        vol_items.append(_analysis_box('真实封板 ✅', 
            f'涨幅榜中有{real_up}只涨幅>8%且竞价成交额>500万，有真实买盘支撑'))
    
    warning = volume_div.get('warning')
    if warning:
        vol_items.append(_analysis_box('量能警告', warning))
    
    if not fake_up and not real_up and not warning:
        vol_items.append('<p class="slide-text muted">竞价量能指标温和，无明显异常。</p>')
    
    slides.append(_build_slide("量能分析", vol_items, icon="📊"))
    
    # ============ 幻灯片5: 情绪判断 ============
    signal_items = []
    total_score = signal_matrix.get('total_score', 0)
    verdict = signal_matrix.get('verdict', '分析中')
    signals = signal_matrix.get('signals', [])
    
    signal_items.append(f'<p class="slide-subtitle">综合评分: {total_score:+.4f}</p>')
    
    # 胜负判断大标签
    verdict_map = {
        '偏多': ('偏多 ✅', 'green'),
        '偏空': ('偏空 ❌', 'red'),
        '分歧': ('分歧 ⚠️', 'yellow'),
        '高位博弈': ('高位博弈 🎲', 'yellow'),
        '超跌反弹': ('超跌反弹 🔄', 'green'),
    }
    verdict_label, verdict_cls = verdict_map.get(verdict, (verdict, ''))
    signal_items.append(f'<p class="slide-text" style="color:var(--{verdict_cls});font-size:18px;font-weight:800;text-align:center;">{verdict_label}</p>')
    
    # 信号权重表
    if signals:
        sig_rows = []
        for sig in signals:
            name = sig.get('name', '')
            w = sig.get('weight', 0) * 100
            d = sig.get('direction', 0)
            s = sig.get('strength', 0)
            val = sig.get('value', '')
            dir_str = '📈 看多' if d > 0 else ('📉 看空' if d < 0 else '➖ 中性')
            sig_rows.append((name, f'{w:.0f}%', dir_str, f'{s:.2f}', str(val)))
        signal_items.append(_data_table(["信号", "权重", "方向", "强度", "数值"], sig_rows))
        signal_items.append(f'<p class="slide-text small muted">加权总分 = Σ(权重×方向×强度), 得分>0.3=偏多, <-0.3=偏空, 中间=分歧</p>')
    
    slides.append(_build_slide("情绪判断", signal_items, icon="🎯"))
    
    # ============ 幻灯片6: 支撑压力分析 ============
    sr_items = []
    core_low = support_resist.get('core_low', 0)
    core_high = support_resist.get('core_high', 0)
    s1 = support_resist.get('support1', 0)
    s2 = support_resist.get('support2', 0)
    r1 = support_resist.get('resist1', 0)
    r2 = support_resist.get('resist2', 0)
    atr = support_resist.get('atr', 0)
    range_w = support_resist.get('range_width', 0)
    validity = support_resist.get('range_validity', 'unknown')
    
    if s1 > 0 and r1 > 0:
        sr_items.append('<p class="slide-subtitle">关键点位</p>')
        
        # 支撑
        sr_items.append(_analysis_box('🟢 支撑位', f'初级支撑: {s1:.1f}  |  强支撑: {s2:.1f}'))
        # 压力
        sr_items.append(_analysis_box('🔴 压力位', f'初级压力: {r1:.1f}  |  强压力: {r2:.1f}'))
        # 核心区间
        sr_items.append(_analysis_box('📊 核心震荡区间', 
            f'[{core_low:.1f} ~ {core_high:.1f}]  宽度约{range_w:.1f}点  5日ATR={atr:.1f}点'))
        
        # 区间合理性
        validity_text = '✅ 区间宽度合理' if validity == 'valid' else '⚠️ 区间宽度已调整'
        sr_items.append(f'<p class="slide-text small muted">{validity_text}</p>')
        
        # 开盘价位置评估
        open_price = data.get('竞价指数价', data.get('开盘价', 0))
        if open_price > 0 and core_high > core_low:
            pos = (open_price - core_low) / (core_high - core_low) * 100 if core_high != core_low else 50
            if pos < 15:
                pos_assessment = '⚠️ 开盘价紧贴区间下边界，区间可能过窄，关注下边界支撑有效性'
            elif pos > 85:
                pos_assessment = '⚠️ 开盘价紧贴区间上边界，区间可能过窄，关注上边界突破概率'
            else:
                pos_assessment = f'✅ 开盘价在区间中位偏{"上" if pos > 50 else "下"}位置({pos:.0f}%), 区间设定合理'
            sr_items.append(_analysis_box('开盘价位置评估', pos_assessment))
    else:
        sr_items.append('<p class="slide-text muted">历史数据不足，无法计算支撑压力位</p>')
    
    slides.append(_build_slide("支撑压力分析", sr_items, icon="📐"))
    
    # ============ 幻灯片7: 风险提示 ============
    risk_items = []
    risk_list = risks.get('risks', [])
    must_show = risks.get('must_show', False)
    
    if risk_list:
        for r in risk_list:
            level = r.get('level', 'info')
            warning = r.get('warning', '')
            level_icon = '🔴 高风险' if level == 'high' else ('🟡 中风险' if level == 'medium' else '🔵 提示')
            risk_items.append(_warning_box(level_icon, warning))
    elif must_show:
        risk_items.append('<p class="slide-text muted">当前未触发数据驱动的风险条件。</p>')
    
    if not risk_items:
        risk_items.append('<p class="slide-text muted">风险检测模块启用中，数据不足或异常阈值未触发。</p>')
    
    slides.append(_build_slide("风险提示", risk_items, icon="⚠️"))
    
    # ============ 幻灯片8: 盘前资讯 ============
    news_items = []
    if news_list:
        news_items.append('<p class="slide-subtitle">今日重要资讯</p>')
        for item in news_list:
            source = item.get('source', '东方财富')
            content = item.get('content', item.get('title', ''))
            tag = item.get('tag', item.get('tag', ''))
            news_items.append(_news_item(source, content, tag))
    else:
        news_items.append('<p class="slide-text muted">暂无盘前资讯数据。</p>')
    
    slides.append(_build_slide("盘前资讯", news_items, icon="📰"))
    
    # Footer/disclaimer slide
    slides.append(_build_slide("免责声明", [
        '<p class="slide-text small muted">',
        '本报告内容仅基于集合竞价阶段公开数据及AI分析生成，不构成任何投资建议或荐股行为。',
        '投资者据此操作，风险自担。证券市场有风险，投资需谨慎。',
        '</p>',
        f'<p class="slide-text small muted">报告生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}</p>',
        '<div class="slide-footer">Data: 东方财富·腾讯·AKShare | A股集合竞价报告</div>',
    ], icon="⚖️"))
    
    return slides


def _add_morning_prefix(slides):
    """为早盘报告添加 morning- 前缀类名"""
    import re as _re
    result = []
    for slide in slides:
        modified = slide

        # 替换 class 属性中的特定类名（处理复合类名，如 slide-text small）
        # slide-title -> morning-section-title
        modified = _re.sub(
            r'class="slide-title(\s[^"]*)?"',
            lambda m: f'class="morning-section-title{m.group(1) or ""}"',
            modified
        )
        # slide-text -> morning-slide-text
        modified = _re.sub(
            r'class="slide-text(\s[^"]*)?"',
            lambda m: f'class="morning-slide-text{m.group(1) or ""}"',
            modified
        )
        # slide-subtitle -> morning-slide-subtitle
        modified = _re.sub(
            r'class="slide-subtitle(\s[^"]*)?"',
            lambda m: f'class="morning-slide-subtitle{m.group(1) or ""}"',
            modified
        )
        # slide-footer -> morning-slide-footer
        modified = _re.sub(
            r'class="slide-footer(\s[^"]*)?"',
            lambda m: f'class="morning-slide-footer{m.group(1) or ""}"',
            modified
        )
        # data-table -> morning-table
        modified = _re.sub(
            r'class="data-table(\s[^"]*)?"',
            lambda m: f'class="morning-table{m.group(1) or ""}"',
            modified
        )
        result.append(modified)
    return result


def generate(data, output=None, report_type="replay"):
    """生成HTML报告"""
    date_str = data.get("date", data.get("日期", datetime.now().strftime("%Y-%m-%d")))
    
    # Determine what to generate
    if report_type == "text":
        text = data.get("text", "")
        slides = _generate_text_slides(text, "replay", date_str)
    elif report_type == "auction":
        slides = _generate_auction_slides(data, date_str)
    elif report_type == "replay":
        slides = _generate_replay_slides(data, date_str)
    elif report_type == "morning":
        slides = _generate_text_slides(data.get("text", str(data)), report_type, date_str)
        # 为早盘报告添加 morning- 前缀类名
        slides = _add_morning_prefix(slides)
        # 追加 morning-footer-gap
        slides.append('<div class="morning-footer-gap"></div>')
    else:
        slides = _generate_text_slides(data.get("text", str(data)), report_type, date_str)
    
    # Build slides HTML
    slides_html = "\n".join(slides)

    # --- 免责声明去重 (v4.0) ---
    # 检测并移除正文中的重复免责声明，只保留footer中的
    disclaimer_marker = '本报告内容仅基于公开数据及AI分析生成'
    # 查找所有包含免责声明的slide块
    slide_pattern = re.compile(r'(<div class="slide[^"]*"[^>]*>.*?</div>\s*)', re.DOTALL)
    slides_matches = slide_pattern.findall(slides_html)
    
    disclaimer_slides = []
    others = []
    for s in slides_matches:
        if disclaimer_marker in s:
            disclaimer_slides.append(s)
        else:
            others.append(s)
    
    # 如果有2个及以上免责声明slide，只保留最后一个
    if len(disclaimer_slides) >= 2:
        # 保留最后一个（footer），丢弃前面的
        kept_disclaimer = disclaimer_slides[-1]
        slides_html = "".join(others) + "\n" + kept_disclaimer
    
    # 另外，如果单个slide内有重复的免责声明段落，移除正文中的重复
    # 检查最终HTML（防止免责声明文本出现在非disclaimer slide中）
    if slides_html.count(disclaimer_marker) > 1:
        # 保留第一次出现的免责声明，移除后续重复
        parts = slides_html.split(disclaimer_marker)
        slides_html = disclaimer_marker.join([parts[0]] + [p for p in parts[1:]])
    
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
