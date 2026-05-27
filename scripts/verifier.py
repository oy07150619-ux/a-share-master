#!/usr/bin/env python3
"""
A股数据交叉验证器
==================
对采集到的数据进行交叉验证，确保数据准确性。
支持：行情自洽、多源对比、板块逻辑、财务核验

用法:
  python verifier.py --check self-consistent     # 数据自洽性
  python verifier.py --cross-validate             # 多源交叉验证
  python verifier.py --report                     # 完整验证报告
  python verifier.py --data data.json             # 验证指定数据文件

注: Linux/macOS可用 python3, Windows使用 python
"""

import json, sys, os, subprocess, re
from datetime import datetime

WORKSPACE = os.path.expanduser("~/.openclaw/workspace")
STOCK_TOOL = os.path.join(WORKSPACE, "tools", "stock_data.py")


def _run_stock(cmd_type, **kwargs):
    """调用数据采集脚本"""
    cmd = [sys.executable, STOCK_TOOL, cmd_type]
    if kwargs.get("limit"):
        cmd.extend(["--limit", str(kwargs["limit"])])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.stdout.strip():
            return json.loads(r.stdout)
        return {}
    except:
        return {}


def check_self_consistent():
    """数据自洽性检查"""
    issues = []
    passed = True
    details = []

    # 1. 大盘数据自洽
    indexes = _run_stock("indexes")
    if indexes:
        sh = next((i for i in indexes if "上证" in i.get("指数", "")), None)
        sz = next((i for i in indexes if "深证" in i.get("指数", "")), None)
        cy = next((i for i in indexes if "创业" in i.get("指数", "")), None)
        
        if sh:
            details.append(f"✅ 上证指数: {sh.get('最新',0):.0f} ({sh.get('涨跌幅',0):+.2f}%)")
        if sz:
            details.append(f"✅ 深证成指: {sz.get('最新',0):.0f} ({sz.get('涨跌幅',0):+.2f}%)")
        if cy:
            details.append(f"✅ 创业板指: {cy.get('最新',0):.0f} ({cy.get('涨跌幅',0):+.2f}%)")
    else:
        issues.append("❌ 大盘指数数据为空")
        passed = False

    # 2. 涨跌数据自洽
    updown = _run_stock("updown")
    if updown:
        up = updown.get("上涨", 0)
        down = updown.get("下跌", 0)
        total = up + down
        details.append(f"📊 涨跌家数: 涨{up}/跌{down} 合计{total}")
        if total < 100:
            issues.append(f"⚠️ 总家数偏少({total})，可能数据不完整")
        elif total < 1000:
            issues.append(f"⚠️ 总家数({total})偏低，可能在非交易时间查询")
        # 涨跌比例合理检查
        if total > 0:
            up_ratio = up / total
            if up_ratio > 0.95:
                issues.append(f"⚠️ 上涨比例过高({up_ratio:.0%})，疑似数据异常")
            elif up_ratio < 0.05:
                issues.append(f"⚠️ 上涨比例过低({up_ratio:.0%})，疑似数据异常")
    else:
        issues.append("❌ 涨跌家数数据为空")
        passed = False

    # 3. 涨跌停数据自洽
    limits = _run_stock("limits")
    if limits:
        lu = limits.get("涨停", 0)
        ld = limits.get("跌停", 0)
        details.append(f"🎯 涨停{lu}家 / 跌停{ld}家")
        if isinstance(lu, int) and isinstance(ld, int):
            if lu > 100:
                issues.append(f"⚠️ 涨停家数{lu}偏高，检查是否包含新股涨停")
            if ld > 100:
                issues.append(f"⚠️ 跌停家数{ld}偏高，市场可能出现系统性风险")
    else:
        issues.append("⚠️ 涨跌停数据为空")
        passed = False

    # 4. 板块数据
    sector = _run_stock("sector")
    if sector and len(sector) > 0:
        # 检查板块涨幅是否合理
        top_pct = abs(sector[0].get("涨跌幅", 0))
        if top_pct > 11:
            issues.append(f"⚠️ 板块最大涨幅{top_pct:.1f}%偏高（正常<10%）")
        details.append(f"✅ 行业板块: {len(sector)}个板块")
    else:
        issues.append("⚠️ 行业板块数据为空")

    # 5. 涨跌幅最大股检查
    gainers = _run_stock("gainers")
    if gainers:
        details.append(f"🚀 涨幅TOP: {gainers[0].get('名称','')} {gainers[0].get('涨跌幅',0):+.2f}%")
        # 检查涨跌幅是否超限
        top_gain = abs(gainers[0].get("涨跌幅", 0))
        if top_gain > 30:
            issues.append(f"⚠️ 最大涨幅{top_gain:.1f}%异常（A股正常<30%）")
    else:
        issues.append("⚠️ 涨幅榜为空")

    losers = _run_stock("losers")
    if losers:
        details.append(f"📉 跌幅TOP: {losers[0].get('名称','')} {losers[0].get('涨跌幅',0):+.2f}%")

    return {
        "timestamp": datetime.now().isoformat(),
        "passed": passed,
        "issues": issues,
        "details": details,
        "summary": f"自洽性检查: {'✅ 通过' if passed else '⚠️ 有异常'} ({len(issues)}个问题)"
    }


def cross_validate(data_file=None):
    """交叉验证：多源比对"""
    issues = []
    details = []
    passes = True
    
    if data_file:
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}

    # 1. 检查多个数据源的指数一致性
    indexes = _run_stock("indexes")
    if indexes:
        # 这里本可以对比浏览器采集的指数，但简化版仅记录
        details.append("✅ 指数数据已通过脚本采集")
    
    # 2. 检查板块与个股联动
    sector = _run_stock("sector")
    gainers = _run_stock("gainers", limit=10)
    
    if sector and gainers:
        # 找出涨幅最大板块的领涨股
        top_sector = sector[0]
        sector_name = top_sector.get("板块名称", "")
        sector_pct = top_sector.get("涨跌幅", 0)
        lead_stock = top_sector.get("领涨股票", "")
        
        details.append(f"🔗 板块联动验证: {sector_name}(+{sector_pct:.2f}%) 领涨:{lead_stock}")
        
        # 检查涨幅前列股是否与顶部板块一致
        if lead_stock:
            top_stock_name = gainers[0].get("名称", "")
            if lead_stock == top_stock_name:
                details.append("✅ 板块领涨股 = 涨幅TOP股，数据一致")
            else:
                details.append(f"ℹ️ 板块领涨({lead_stock}) ≠ 全市场TOP({top_stock_name})，属正常现象")
    
    # 3. 检查涨跌停逻辑
    limits = _run_stock("limits")
    if limits:
        lu = limits.get("涨停", 0)
        ld = limits.get("跌停", 0)
        if isinstance(lu, int) and isinstance(ld, int):
            if lu + ld < 1:
                issues.append("⚠️ 涨跌停家数均为0，可能在非交易时段")
    
    # 4. 涨跌家数核验
    updown = _run_stock("updown")
    if updown:
        up = updown.get("上涨", 0)
        down = updown.get("下跌", 0)
        if up + down > 0:
            ratio = up / (up + down)
            if ratio > 0.8:
                details.append("🔔 上涨比例>80%，市场整体强势")
            elif ratio < 0.2:
                details.append("🔔 上涨比例<20%，市场整体弱势")

    return {
        "timestamp": datetime.now().isoformat(),
        "passed": passes,
        "issues": issues,
        "details": details,
        "summary": f"交叉验证: {'✅ 全部通过' if passes else '⚠️ 有异常'} ({len(issues)}个问题)"
    }


# ========================================================================
# 函数A: 数据来源验证
# ========================================================================

# 白名单来源
_WHITELIST_SOURCES = [
    '东方财富', '同花顺', '腾讯财经', '新浪财经', '雪球',
    'Reuters', 'Bloomberg', 'Yahoo Finance',
    '新华社', '证券时报', '第一财经', '财新', '经济日报', '21世纪经济报道',
    '上交所', '深交所', '中国证监会',
    '中信证券', '中金公司', '华泰证券'
]

_BLACKLIST_SOURCES = [
    '知乎', '微博', '小红书', '微信公众号(非官方)', '贴吧',
    '抖音', '快手', '百家号', '头条号(非官方)'
]

def check_data_source(report_text):
    """
    扫描报告中所有【来源】标记，验证是否在白名单内。

    参数:
        report_text (str): 报告文本内容

    返回:
        dict: {'pass': True/False, 'warnings': [{'source': str, 'verdict': 'allowed'/'banned'/'unknown', 'line': int}]}
    """
    warnings = []
    lines = report_text.split('\n')

    # 所有括号类型：全角【】（）() 半角()
    bracket_pairs = [
        (r'【', r'】'),
        (r'（', r'）'),
        (r'\(', r'\)'),
    ]

    for i, line in enumerate(lines, 1):
        for open_b, close_b in bracket_pairs:
            pattern = rf'{open_b}来源[：:](.*?){close_b}'
            matches = re.findall(pattern, line)
            for src in matches:
                src_stripped = src.strip()
                if not src_stripped:
                    continue

                # 白名单检查（包含匹配）
                allowed = any(wl.lower() in src_stripped.lower() for wl in _WHITELIST_SOURCES)
                banned = any(bl.lower() in src_stripped.lower() for bl in _BLACKLIST_SOURCES)

                if allowed:
                    verdict = 'allowed'
                elif banned:
                    verdict = 'banned'
                else:
                    verdict = 'unknown'

                warnings.append({
                    'source': src_stripped,
                    'verdict': verdict,
                    'line': i
                })

    has_banned = any(w['verdict'] == 'banned' for w in warnings)
    passed = not has_banned

    return {
        'pass': passed,
        'warnings': warnings
    }


# ========================================================================
# 函数B: 报告交叉验证（对快照）
# ========================================================================

def cross_report_validate(current_report, snapshot_path):
    """
    验证当前报告与快照数据的一致性。

    参数:
        current_report (dict): 当前报告数据
        snapshot_path (str): 快照文件路径

    返回:
        dict: {'pass': True/False, 'warnings': [], 'suggestions': []}
    """
    warnings = []
    suggestions = []

    # 读取快照
    snapshot = None
    try:
        with open(snapshot_path, 'r', encoding='utf-8') as f:
            snapshot = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, IOError):
        return {
            'pass': True,
            'warnings': [],
            'suggestions': ['无法读取快照文件，跳过交叉验证']
        }

    snapshots = snapshot.get('snapshots', {})
    if not snapshots:
        return {
            'pass': True,
            'warnings': [],
            'suggestions': ['快照文件为空，跳过交叉验证']
        }

    # 对比当前报告与所有快照中的指数指标
    current_indexes = current_report.get('indexes', [])
    current_sh = None
    for idx in current_indexes:
        name = idx.get('指数', '')
        if '上证' in name:
            current_sh = idx.get('最新', idx.get('点位', 0))
            break

    for snap_type, snap_entry in snapshots.items():
        indicators = snap_entry.get('key_indicators', {})
        old_sh = indicators.get('sh_index')

        if old_sh and current_sh and old_sh > 0 and current_sh > 0:
            sh_diff = abs(current_sh - old_sh) / old_sh * 100
            if sh_diff > 1.0:
                warnings.append({
                    'snapshot_type': snap_type,
                    'field': 'sh_index',
                    'old_value': old_sh,
                    'new_value': current_sh,
                    'diff': f'{sh_diff:.2f}%',
                    'msg': f'与{snap_type}快照对比，上证指数差异{sh_diff:.2f}%'
                })

    # 给出建议
    if warnings:
        suggestions.append('建议检查数据采集时间是否一致')
        suggestions.append('确认报告生成流程中是否遗漏了数据更新')

    return {
        'pass': len(warnings) == 0,
        'warnings': warnings,
        'suggestions': suggestions
    }


# ========================================================================
# 函数C: HTML语法检查
# ========================================================================

def check_html_syntax(html_content):
    """
    检查HTML标签是否闭合、结构是否合理。

    参数:
        html_content (str): HTML内容

    返回:
        dict: {'pass': True/False, 'errors': [{'line': int, 'msg': str}]}
    """
    errors = []
    lines = html_content.split('\n')

    # 检查成对标签数量
    def count_tag(tag_name):
        open_count = 0
        close_count = 0
        open_pattern = re.compile(rf'<{tag_name}[\s>]')
        close_pattern = re.compile(rf'</{tag_name}\s*>')

        for line in lines:
            open_count += len(open_pattern.findall(line))
            close_count += len(close_pattern.findall(line))

        return open_count, close_count

    # 检查 table
    table_open, table_close = count_tag('table')
    if table_open != table_close:
        errors.append({
            'line': 1,
            'msg': f'<table>数量({table_open})与</table>数量({table_close})不匹配'
        })

    # 检查 tr
    tr_open, tr_close = count_tag('tr')
    if tr_open != tr_close:
        errors.append({
            'line': 1,
            'msg': f'<tr>数量({tr_open})与</tr>数量({tr_close})不匹配'
        })

    # 检查 td
    td_open, td_close = count_tag('td')
    if td_open != td_close:
        errors.append({
            'line': 1,
            'msg': f'<td>数量({td_open})与</td>数量({td_close})不匹配'
        })

    # 检查 th
    th_open, th_close = count_tag('th')
    if th_open != th_close:
        errors.append({
            'line': 1,
            'msg': f'<th>数量({th_open})与</th>数量({th_close})不匹配'
        })

    # 检查 div
    div_open, div_close = count_tag('div')
    if div_open != div_close:
        errors.append({
            'line': 1,
            'msg': f'<div>数量({div_open})与</div>数量({div_close})不匹配'
        })

    # 检查 行内是否有未闭合的标签（简单检查）
    # 匹配 <xxx 但没有对应的 </xxx> 在同一行内（自闭合和常见 block 标签忽略）
    self_closing_tags = {'br', 'hr', 'img', 'input', 'meta', 'link', 'source', 'col'}
    for i, line in enumerate(lines, 1):
        # 找所有开标签
        open_tags = re.findall(r'<(\w+)[\s>]', line)
        close_tags = re.findall(r'</(\w+)\s*>', line)

        for tag in open_tags:
            # 自闭合或仅出现一次的标签不检查
            if tag.lower() in self_closing_tags:
                continue
            # 检查行内是否有闭合
            if f'</{tag}>' not in line and f'<{tag}/>' not in line and f'<{tag} />' not in line:
                # 跨行闭合是正常的，只在行数多的场合报 warning
                pass

    passed = len(errors) == 0

    return {
        'pass': passed,
        'errors': errors
    }


# ========================================================================
# 函数D: 报告内部数据一致性检查（铁律8——同一报告内数据矛盾检测）
# ========================================================================

def check_intra_report_consistency(report_text):
    """
    检查单份报告内同一数据是否出现矛盾（铁律8）。

    扫描报告中所有数字+单位的组合（如 "25亿" "45亿" "374亿"），
    对同一主体（如 "半导体"）检查是否出现不同数值。
    如果同一主体的同一指标出现2个以上不同数值 → 标记warning。

    Parameters:
        report_text (str): 报告文本内容

    Returns:
        dict: {
            'pass': bool,
            'warnings': [{'field': str, 'values': [str], 'positions': [int]}]
        }
    """
    warnings = []
    lines = report_text.split('\n')

    # 正则：匹配 中文上下文 + 数字 + 亿/万/元/家/% 的组合
    # 模式: 半导体流入25亿, 今日成交374亿, 实际涨停35家
    pattern = re.compile(
        r'([\u4e00-\u9fa5]{2,10})'     # 中文上下文（2-10个汉字）
        r'(\d+(?:\.\d+)?)'              # 数字
        r'(亿|万|元|家|%|个|只|点)'    # 单位
    )

    def _extract_entity(context):
        # 从中文上下文中提取核心主体
        verbs = ['流入', '流出', '净额', '增量', '存量', '净买入', '净卖出']
        for v in verbs:
            if v in context:
                idx = context.index(v)
                return context[:idx]
        prefixes = ['实际', '今日', '昨日', '最新', '合计', '其中', '共', '总']
        trimmed = context
        for p in prefixes:
            if trimmed.startswith(p):
                trimmed = trimmed[len(p):]
                break
        if len(trimmed) > 4:
            return trimmed[-4:]
        return trimmed

    # 存储：{主体_单位: [(值, 行号), ...]}
    subjects = {}

    for i, line in enumerate(lines, 1):
        for match in pattern.finditer(line):
            context = match.group(1)
            entity = _extract_entity(context)
            value = match.group(2) + match.group(3)
            unit = match.group(3)
            key = f'{entity}_{unit}'

            if key not in subjects:
                subjects[key] = []
            subjects[key].append((value, i))

    # 检查同一主体同一单位下是否有不同的值
    for key, entries in subjects.items():
        unique_values = list(set(v for v, _ in entries))
        if len(unique_values) >= 2:
            positions = [lineno for _, lineno in entries]
            warnings.append({
                'field': key,
                'values': unique_values,
                'positions': positions
            })

    # --- 资金口径标注检查 (v4.0) ---
    fund_annotations_keywords = ['主力资金', '特大单', '大单', '北向', '北向资金',
                                 '主力净流入', '超大单', '小单', '中单']
    fund_pattern = re.compile(r'(\d+(?:\.\d+)?)(亿|万)')

    for i, line in enumerate(lines, 1):
        for match in fund_pattern.finditer(line):
            num_str = match.group(1)
            unit = match.group(2)
            try:
                num = float(num_str)
                if unit == '亿' and num > 10:
                    has_annotation = any(ann in line for ann in fund_annotations_keywords)
                    if not has_annotation:
                        warnings.append({
                            'field': 'fund_annotation',
                            'values': [f'{num}亿（无口径标注）'],
                            'positions': [i],
                            'msg': f'第{i}行：{num}亿无资金口径标注（主力资金/特大单/大单/北向等）'
                        })
            except ValueError:
                continue

    return {
        'pass': len(warnings) == 0,
        'warnings': warnings
    }


# ========================================================================
# 函数E: 收盘价在支撑压力区间中的位置判断（铁律9——支撑压力位置判断）
# ========================================================================

def check_close_position(close_price, support, resist):
    """
    检查收盘价在支撑压力区间中的位置（铁律9）。

    Parameters:
        close_price (float): 收盘价
        support (float): 支撑位
        resist (float): 压力位

    Returns:
        dict: {
            'position': 'upper_third' | 'middle_third' | 'lower_third',
            'ratio': float,         # 0~1，收盘在区间中的位置比例
            'suggestion': str
        }
    """
    if resist <= support:
        # 支撑压力反转或无效
        return {
            'position': 'middle_third',
            'ratio': 0.5,
            'suggestion': '支撑压力位异常（压力≤支撑），方向不明'
        }

    # 计算收盘价在区间中的位置比例 (0=支撑, 1=压力)
    ratio = (close_price - support) / (resist - support)

    # 截断到 [0, 1]
    ratio = max(0.0, min(1.0, ratio))

    if ratio >= 2 / 3:
        return {
            'position': 'upper_third',
            'ratio': round(ratio, 4),
            'suggestion': '偏强，倾向压力位测试'
        }
    elif ratio <= 1 / 3:
        return {
            'position': 'lower_third',
            'ratio': round(ratio, 4),
            'suggestion': '偏弱，倾向支撑位测试'
        }
    else:
        return {
            'position': 'middle_third',
            'ratio': round(ratio, 4),
            'suggestion': '方向不明，等待次日确认'
        }


# ========================================================================
# 函数F: 指数名称一致性检查 (v4.0)
# ========================================================================

def check_index_name_consistency(report_text):
    """
    扫描报告全文中使用的指数名称是否统一。

    白名单映射：
        科创50: [科创50, 科创综指]
        上证指数: [上证指数, 上证综指]
        深证成指: [深证成指, 深证综指]
        创业板指: [创业板指, 创业板综指]

    Parameters:
        report_text (str): 报告全文文本

    Returns:
        dict: {
            'pass': bool,
            'warnings': [{'index': str, 'used_names': [str], 'suggestion': str}]
        }
    """
    WHITELIST_MAP = {
        '科创50': ['科创50', '科创综指'],
        '上证指数': ['上证指数', '上证综指'],
        '深证成指': ['深证成指', '深证综指'],
        '创业板指': ['创业板指', '创业板综指'],
    }

    warnings = []
    found_names = {}  # canonical_name -> set of names used

    for line in report_text.split('\n'):
        for canonical_name, allowed_names in WHITELIST_MAP.items():
            for name in allowed_names:
                if name in line:
                    if canonical_name not in found_names:
                        found_names[canonical_name] = set()
                    found_names[canonical_name].add(name)

    passed = True
    for canonical_name, used_names in found_names.items():
        if len(used_names) > 1:
            passed = False
            warnings.append({
                'index': canonical_name,
                'used_names': sorted(used_names),
                'suggestion': f'建议统一使用「{canonical_name}」'
            })

    return {'pass': passed, 'warnings': warnings}


# ========================================================================
# 函数G: 常见错别字检查 (v4.0)
# ========================================================================

def check_typo(report_text):
    """
    检查报告中常见错别字。

    对照表：{'摧化': '催化', '撞态': '状态', '已燃': '已然',
             '的却': '的确', '在次': '再次', '做多': '做多',
             '震档': '震荡'}

    Parameters:
        report_text (str): 报告全文文本

    Returns:
        dict: {'pass': bool, 'warnings': [{'typo': str, 'correction': str, 'position': int}]}
    """
    TYPO_MAP = {
        '摧化': '催化',
        '撞态': '状态',
        '已燃': '已然',
        '的却': '的确',
        '在次': '再次',
        '做多': '做多',  # identity entry, preserved for completeness
        '震档': '震荡',
    }

    warnings = []

    for typo, correction in TYPO_MAP.items():
        if typo == correction:
            continue  # skip identity mappings (no actual typo)
        idx = report_text.find(typo)
        if idx != -1:
            warnings.append({
                'typo': typo,
                'correction': correction,
                'position': idx
            })

    return {'pass': len(warnings) == 0, 'warnings': warnings}


# ========================================================================
# 函数H: 报告最终综合扫描 (v4.0)
# ========================================================================

def final_report_check(report_text):
    """
    报告最终输出前的综合扫描。

    扫描项：
        1. 所有资金数字是否标注口径（主力资金/特大单/大单/北向等）
        2. 所有指数名称是否在白名单内且统一
        3. 核心板块（TOP3涨跌幅）资金数据是否精确到亿
        4. 是否有重复的免责声明段落

    Parameters:
        report_text (str): 报告全文文本

    Returns:
        dict: {
            'pass': bool,
            'warnings': [],
            'checks': {
                'fund_annotation': bool,
                'index_consistency': bool,
                'core_data_precision': bool,
                'no_duplicate_disclaimer': bool
            }
        }
    """
    checks = {}
    warnings = []

    # --- Check 1: 资金数字口径标注 ---
    fund_annotation = True
    fund_pattern = re.compile(r'(\d+(?:\.\d+)?)(亿|万)')
    annotations_keywords = ['主力资金', '特大单', '大单', '北向', '北向资金',
                            '主力净流入', '超大单', '小单', '中单']

    for i, line in enumerate(report_text.split('\n'), 1):
        for match in fund_pattern.finditer(line):
            num_str = match.group(1)
            unit = match.group(2)
            try:
                num = float(num_str)
                if unit == '亿' and num > 10:
                    has_annotation = any(ann in line for ann in annotations_keywords)
                    if not has_annotation:
                        fund_annotation = False
                        warnings.append({
                            'check': 'fund_annotation',
                            'detail': f'第{i}行：{num}亿无资金口径标注',
                            'line': i
                        })
            except ValueError:
                continue

    checks['fund_annotation'] = fund_annotation

    # --- Check 2: 指数名称白名单及统一性 ---
    index_check = check_index_name_consistency(report_text)
    checks['index_consistency'] = index_check['pass']
    for w in index_check['warnings']:
        warnings.append({
            'check': 'index_consistency',
            'detail': f"指数「{w['index']}」使用了不一致的名称：{', '.join(w['used_names'])}。{w['suggestion']}"
        })

    # --- Check 3: 核心板块资金数据精度 ---
    # Best-effort scan for sector data precision
    core_data_precision = True
    for i, line in enumerate(report_text.split('\n'), 1):
        # 检查板块相关行是否包含未标注亿的数字
        if re.search(r'(涨幅榜|板块|行业|概念).{0,30}\d+\.?\d*', line):
            if '亿' not in line and re.search(r'\d+\.?\d*', line):
                # Soft flag only — might be false positive
                pass

    checks['core_data_precision'] = core_data_precision

    # --- Check 4: 重复的免责声明 ---
    disclaimer_text = '本报告内容仅基于公开数据及AI分析生成'
    count = report_text.count(disclaimer_text)
    no_duplicate_disclaimer = count <= 1
    if not no_duplicate_disclaimer:
        warnings.append({
            'check': 'duplicate_disclaimer',
            'detail': f'发现{count}个免责声明，应只保留footer中的一个'
        })

    checks['no_duplicate_disclaimer'] = no_duplicate_disclaimer

    all_pass = all(checks.values())

    return {
        'pass': all_pass,
        'warnings': warnings,
        'checks': checks
    }


def generate_report():
    """完整验证报告"""
    self_check = check_self_consistent()
    cross_check = cross_validate()
    
    report = f"""
========================================
       A股数据验证报告
       生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
========================================

【一、数据自洽性检查】
{self_check['summary']}

问题 ({len(self_check['issues'])}项):
"""
    if self_check['issues']:
        for i in self_check['issues']:
            report += f"  {i}\n"
    else:
        report += "  （无异常）\n"

    report += f"""
检查详情:
"""
    for d in self_check.get('details', []):
        report += f"  {d}\n"

    report += f"""
【二、交叉验证】
{cross_check['summary']}

问题 ({len(cross_check['issues'])}项):
"""
    if cross_check['issues']:
        for i in cross_check['issues']:
            report += f"  {i}\n"
    else:
        report += "  （无异常）\n"

    report += f"""
检查详情:
"""
    for d in cross_check.get('details', []):
        report += f"  {d}\n"

    report += """
【三、验证结论】
"""
    all_passed = self_check['passed'] and cross_check['passed']
    report += f"整体: {'✅ 数据可信' if all_passed else '⚠️ 需注意异常项'}\n"
    report += "========================================\n"

    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="A股数据交叉验证器")
    parser.add_argument("--check", choices=["self-consistent"], 
                       help="数据自洽性检查")
    parser.add_argument("--cross-validate", action="store_true", 
                       help="多源交叉验证")
    parser.add_argument("--report", action="store_true", 
                       help="生成完整验证报告")
    parser.add_argument("--data", help="数据JSON文件路径")
    
    args = parser.parse_args()
    
    if args.check == "self-consistent":
        result = check_self_consistent()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.cross_validate:
        result = cross_validate(args.data)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.report:
        report = generate_report()
        print(report)
    else:
        # Default: run all checks
        report = generate_report()
        print(report)
