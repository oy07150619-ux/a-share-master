#!/usr/bin/env python3
"""
A股集合竞价分析引擎
======================
封装集合竞价报告所需的核心分析函数，包括：
1. classify_limit_status  — 涨停/跌停分类（封板/触板/接近）
2. calc_volume_divergence — 量能分化指数计算
3. calc_support_resistance — 支撑压力位计算
4. signal_weight_matrix   — 情绪信号权重矩阵
5. detect_risks           — 风险条件检测

所有分析函数均以数据为输入，返回结构化结果，便于LLM直接引用。
"""

import json
import math
import os
from datetime import datetime


# ========================================================================
# 函数1: 涨停/跌停分类
# ========================================================================

def classify_limit_status(price, prev_close, limit_up_price=None, limit_down_price=None):
    """
    根据竞价价、昨收价、涨跌停价，返回精确的分类标签。

    参数:
        price (float): 竞价价格（最新价）
        prev_close (float): 昨收价
        limit_up_price (float, optional): 涨停价（精确计算值）
        limit_down_price (float, optional): 跌停价（精确计算值）

    返回:
        str: 分类标签:
            - 'limit_up_sealed'   — 封板涨停（竞价价精确等于涨停价，容忍±0.005元）
            - 'limit_up_touched'  — 触板涨停（涨幅≥9.90%但未精确封板）
            - 'near_limit_up'     — 接近涨停（涨幅8%~9.89%）
            - 'limit_down_sealed' — 封板跌停
            - 'limit_down_touched'— 触板跌停（跌幅≤-9.90%但未精确封板）
            - 'near_limit_down'   — 接近跌停（跌幅-8%~-9.89%）
            - 'normal'            — 普通
            - 'unknown'           — 无法判断
    """
    if price is None or prev_close is None or prev_close == 0:
        return 'unknown'

    pct = (price - prev_close) / prev_close * 100

    # 涨停方向判断
    # 使用四舍五入避免浮点精度问题
    price_r = round(price, 2)
    up_r = round(limit_up_price, 2) if limit_up_price is not None else None
    down_r = round(limit_down_price, 2) if limit_down_price is not None else None

    if up_r is not None and abs(price_r - up_r) <= 0.005:
        return 'limit_up_sealed'
    if pct >= 9.90:
        return 'limit_up_touched'
    if pct >= 8.0:
        return 'near_limit_up'

    # 跌停方向判断
    if down_r is not None and abs(price_r - down_r) <= 0.005:
        return 'limit_down_sealed'
    if pct <= -9.90:
        return 'limit_down_touched'
    if pct <= -8.0:
        return 'near_limit_down'

    return 'normal'


def classify_batch(stocks, price_key='最新价', pct_key='涨跌幅'):
    """
    批量分类股票涨停状态。

    参数:
        stocks (list[dict]): 股票数据列表
        price_key (str): 价格字段名
        pct_key (str): 涨跌幅字段名

    返回:
        list[dict]: 每项新增 'limit_status' 和 'limit_label' 字段
    """
    result = []
    for s in stocks:
        price = s.get(price_key, 0)
        pct = s.get(pct_key, 0)
        # 如果只有涨跌幅没有价格，用涨跌幅反推
        if price == 0 and pct != 0:
            # 无法精确判断封板，仅用涨跌幅判断
            status = 'unknown'
            if pct >= 9.90:
                status = 'limit_up_touched'
            elif pct >= 8.0:
                status = 'near_limit_up'
            elif pct <= -9.90:
                status = 'limit_down_touched'
            elif pct <= -8.0:
                status = 'near_limit_down'
            else:
                status = 'normal'
        else:
            prev_close = s.get('昨收', price / (1 + pct / 100)) if pct != 0 else price
            status = classify_limit_status(
                price=price,
                prev_close=prev_close,
                limit_up_price=s.get('涨停价'),
                limit_down_price=s.get('跌停价')
            )

        # 中文标签
        label_map = {
            'limit_up_sealed': '封板涨停',
            'limit_up_touched': '触板涨停',
            'near_limit_up': '接近涨停',
            'limit_down_sealed': '封板跌停',
            'limit_down_touched': '触板跌停',
            'near_limit_down': '接近跌停',
            'normal': '普通',
            'unknown': '未知',
        }
        entry = dict(s)
        entry['limit_status'] = status
        entry['limit_label'] = label_map.get(status, '未知')
        result.append(entry)
    return result


# ========================================================================
# 函数2: 量能分化指数
# ========================================================================

def calc_volume_divergence(stocks_data):
    """
    计算量能分化指数。

    参数:
        stocks_data (list[dict]): 股票数据列表，每项应有 '涨跌幅' 和 '成交额' 字段

    返回:
        dict: {
            'ratio': float,           # 涨幅TOP5总成交额/跌幅TOP5总成交额
            'label': str,             # 标签
            'warning': str or None    # 触发警告
        }
    """
    # 按涨跌幅排序
    sorted_stocks = sorted(stocks_data, key=lambda s: float(s.get('涨跌幅', 0) or 0), reverse=True)

    # 涨幅TOP5
    gainers = [s for s in sorted_stocks if float(s.get('涨跌幅', 0) or 0) > 0][:5]
    # 跌幅TOP5
    losers = [s for s in reversed(sorted_stocks) if float(s.get('涨跌幅', 0) or 0) < 0][:5]

    # 计算总成交额
    def _safe_vol(s):
        v = s.get('成交额', 0)
        if v is None:
            return 0
        try:
            return float(v)
        except (ValueError, TypeError):
            return 0

    gainers_vol = sum(_safe_vol(s) for s in gainers)
    losers_vol = sum(_safe_vol(s) for s in losers)

    if gainers_vol == 0 and losers_vol == 0:
        return {
            'ratio': 1.0,
            'label': 'balanced',
            'warning': None
        }

    if losers_vol == 0:
        return {
            'ratio': 99.9,
            'label': 'extremely_bullish',
            'warning': '⚠️ 涨幅TOP5成交额占绝对优势，但跌幅TOP5近乎零成交，警惕无量阴跌股被忽略'
        }

    ratio = gainers_vol / losers_vol

    warning = None
    if ratio > 5:
        label = 'extremely_bullish'
        warning = '⚠️ 量能严重偏多：涨幅TOP5成交额是跌幅TOP5的{:.1f}倍，追涨力量远强于抛压'.format(ratio)
    elif ratio > 3:
        label = 'bullish'
        warning = '⚠️ 量能偏多：涨幅TOP5成交额是跌幅TOP5的{:.1f}倍，做多量能占优'.format(ratio)
    elif ratio < 0.2:
        label = 'extremely_bearish'
        warning = '⚠️ 量能严重偏空：跌幅TOP5成交额远超涨幅TOP5，抛压需警惕'.format(ratio)
    elif ratio < 0.33:
        label = 'bearish'
        warning = '⚠️ 量能偏空：跌幅TOP5成交额是涨幅TOP5的{:.1f}倍，空头力量占优'.format(1/ratio)
    else:
        label = 'balanced'

    return {
        'ratio': round(ratio, 2),
        'label': label,
        'warning': warning
    }


# ========================================================================
# 函数3: 支撑压力位计算
# ========================================================================

def calc_support_resistance(index_data, days=5):
    """
    基于前N日数据计算支撑压力位。

    参数:
        index_data (list[dict]): 指数历史数据列表
            每项格式: {'日期':str, '最高':float, '最低':float, '收盘':float, '昨收':float(可选)}
        days (int): 使用的交易日数

    返回:
        dict: {
            'support1': float, 'support2': float,   # 支撑位
            'resist1': float, 'resist2': float,      # 压力位
            'core_low': float, 'core_high': float,   # 核心区间
            'range_width': float, 'atr': float,      # 区间宽度和ATR
            'range_validity': str                     # 'valid' 或 'adjusted'
        }
    """
    if not index_data or len(index_data) < 2:
        return {
            'support1': 0, 'support2': 0,
            'resist1': 0, 'resist2': 0,
            'core_low': 0, 'core_high': 0,
            'range_width': 0, 'atr': 0,
            'range_validity': 'invalid'
        }

    # 截取最近days天
    data = index_data[-days:] if len(index_data) > days else index_data

    # 1. 计算ATR (Average True Range)
    trs = []
    for i, d in enumerate(data):
        high = float(d.get('最高', 0))
        low = float(d.get('最低', 0))
        close = float(d.get('收盘', 0))

        if i == 0:
            prev_close = float(d.get('昨收', close))
        else:
            prev_close = float(data[i - 1].get('收盘', close))

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        trs.append(tr)

    atr = sum(trs) / len(trs) if trs else 50

    # 2. 计算支撑压力
    latest = data[-1]
    prev = data[-2] if len(data) > 1 else latest

    latest_high = float(latest.get('最高', 0))
    latest_low = float(latest.get('最低', 0))
    prev_high = float(prev.get('最高', 0))
    prev_low = float(prev.get('最低', 0))

    # 支撑位1 = min(昨日最低×0.995, 前日最低)
    support1 = min(latest_low * 0.995, prev_low)
    # 压力位1 = max(昨日最高×1.005, 前日最高)
    resist1 = max(latest_high * 1.005, prev_high)

    # 支撑位2 = 支撑位1 - ATR×0.3
    support2 = support1 - atr * 0.3
    # 压力位2 = 压力位1 + ATR×0.3
    resist2 = resist1 + atr * 0.3

    core_low = support1
    core_high = resist1
    range_width = core_high - core_low

    # 3. 合理性检查：区间宽度应在ATR×0.5 ~ ATR×1.5之间
    min_width = atr * 0.5
    max_width = atr * 1.5

    if range_width < min_width:
        # 扩宽到最小合理宽度
        expand = (min_width - range_width) / 2
        core_low = core_low - expand
        core_high = core_high + expand
        range_width = core_high - core_low
        range_validity = 'adjusted'

    elif range_width > max_width:
        # 缩窄到最大合理宽度
        shrink = (range_width - max_width) / 2
        core_low = core_low + shrink
        core_high = core_high - shrink
        range_width = core_high - core_low
        range_validity = 'adjusted'

    else:
        range_validity = 'valid'

    return {
        'support1': round(support1, 2),
        'support2': round(support2, 2),
        'resist1': round(resist1, 2),
        'resist2': round(resist2, 2),
        'core_low': round(core_low, 2),
        'core_high': round(core_high, 2),
        'range_width': round(range_width, 2),
        'atr': round(atr, 2),
        'range_validity': range_validity
    }


# ========================================================================
# 函数4: 信号权重矩阵（情绪判断）
# ========================================================================

def signal_weight_matrix(market_data):
    """
    基于多信号加权计算市场情绪判断。

    参数:
        market_data (dict): 包含竞价、昨日、外盘等市场数据
            必要字段:
                - '竞价涨跌幅': float   (上证竞价涨跌幅)
                - '涨停数': int         (当下涨停家数)
                - '跌停数': int         (当下跌停家数)
                - '昨日上证涨跌幅': float
                - '昨日涨停数': int
                - '昨日跌停数': int
                - '隔夜美股涨跌幅': float (道指/标普)
                - '竞价量能标签': str    (bullish/balanced/bearish)
                - '板块涨跌比': float    (上涨板块/总板块)

    返回:
        dict: {
            'total_score': float,   # -1.0 ~ 1.0
            'verdict': str,         # '偏多' / '偏空' / '分歧' / '高位博弈' / '超跌反弹'
            'signals': [{'name':str, 'weight':float, 'direction':int(1/-1), 'strength':float}]
        }
    """
    signals = []
    total_score = 0.0

    # --- 信号1: 竞价高开/低开幅度 (权重15%) ---
    bid_pct = market_data.get('竞价涨跌幅', 0)
    if bid_pct > 0:
        direction = 1
        strength = min(abs(bid_pct) / 2.0, 1.0)
    elif bid_pct < 0:
        direction = -1
        strength = min(abs(bid_pct) / 2.0, 1.0)
    else:
        direction = 0
        strength = 0

    signals.append({
        'name': '竞价涨跌幅',
        'weight': 0.15,
        'direction': direction,
        'strength': round(strength, 2),
        'value': bid_pct
    })
    total_score += 0.15 * direction * strength

    # --- 信号2: 涨停/跌停比 (权重15%) ---
    lu = market_data.get('涨停数', 0)
    ld = market_data.get('跌停数', 0)
    if lu > ld:
        direction = 1
        ratio = lu / max(ld, 1)
        strength = min(ratio / 3.0, 1.0)
    elif ld > lu:
        direction = -1
        ratio = ld / max(lu, 1)
        strength = min(ratio / 3.0, 1.0)
    else:
        direction = 0
        strength = 0

    signals.append({
        'name': '涨停/跌停比',
        'weight': 0.15,
        'direction': direction,
        'strength': round(strength, 2),
        'value': lu if lu >= ld else -ld
    })
    total_score += 0.15 * direction * strength

    # --- 信号3: 昨日收盘涨跌 (权重20%) ---
    yesterday_pct = market_data.get('昨日上证涨跌幅', 0)
    if yesterday_pct > 0:
        direction = 1
        strength = min(abs(yesterday_pct) / 3.0, 1.0)
    elif yesterday_pct < 0:
        direction = -1
        strength = min(abs(yesterday_pct) / 3.0, 1.0)
    else:
        direction = 0
        strength = 0

    signals.append({
        'name': '昨日涨跌幅',
        'weight': 0.20,
        'direction': direction,
        'strength': round(strength, 2),
        'value': yesterday_pct
    })
    total_score += 0.20 * direction * strength

    # --- 信号4: 昨日涨停/跌停比 (权重10%) ---
    y_lu = market_data.get('昨日涨停数', 0)
    y_ld = market_data.get('昨日跌停数', 0)
    if y_lu > y_ld:
        direction = 1
        ratio = y_lu / max(y_ld, 1)
        strength = min(ratio / 3.0, 1.0)
    elif y_ld > y_lu:
        direction = -1
        ratio = y_ld / max(y_lu, 1)
        strength = min(ratio / 3.0, 1.0)
    else:
        direction = 0
        strength = 0

    signals.append({
        'name': '昨日涨停/跌停比',
        'weight': 0.10,
        'direction': direction,
        'strength': round(strength, 2),
        'value': y_lu if y_lu >= y_ld else -y_ld
    })
    total_score += 0.10 * direction * strength

    # --- 信号5: 隔夜外盘(美股) (权重15%) ---
    us_pct = market_data.get('隔夜美股涨跌幅', 0)
    if us_pct > 0:
        direction = 1
        strength = min(abs(us_pct) / 2.0, 1.0)
    elif us_pct < 0:
        direction = -1
        strength = min(abs(us_pct) / 2.0, 1.0)
    else:
        direction = 0
        strength = 0

    signals.append({
        'name': '隔夜美股',
        'weight': 0.15,
        'direction': direction,
        'strength': round(strength, 2),
        'value': us_pct
    })
    total_score += 0.15 * direction * strength

    # --- 信号6: 竞价量能特征 (权重15%) ---
    vol_label = market_data.get('竞价量能标签', 'balanced')
    if vol_label in ('extremely_bullish', 'bullish'):
        direction = 1
        strength = 0.8 if vol_label == 'extremely_bullish' else 0.5
    elif vol_label in ('extremely_bearish', 'bearish'):
        direction = -1
        strength = 0.8 if vol_label == 'extremely_bearish' else 0.5
    else:
        direction = 0
        strength = 0

    signals.append({
        'name': '竞价量能',
        'weight': 0.15,
        'direction': direction,
        'strength': strength,
        'value': vol_label
    })
    total_score += 0.15 * direction * strength

    # --- 信号7: 板块结构 (权重10%) ---
    sector_ratio = market_data.get('板块涨跌比', 0.5)
    if sector_ratio > 0.6:
        direction = 1
        strength = min((sector_ratio - 0.5) * 2, 1.0)
    elif sector_ratio < 0.4:
        direction = -1
        strength = min((0.5 - sector_ratio) * 2, 1.0)
    else:
        direction = 0
        strength = 0

    signals.append({
        'name': '板块结构',
        'weight': 0.10,
        'direction': direction,
        'strength': round(strength, 2),
        'value': sector_ratio
    })
    total_score += 0.10 * direction * strength

    total_score = round(total_score, 4)

    # ===== 二元对立处理 =====
    yesterday_pct = market_data.get('昨日上证涨跌幅', 0)
    bid_pct = market_data.get('竞价涨跌幅', 0)

    # 昨日大涨(>2%) + 今日竞价低开(<-0.3%) → 高位博弈
    if yesterday_pct > 2.0 and bid_pct < -0.3:
        verdict = '高位博弈'
    # 昨日大跌(<-2%) + 今日竞价高开(>0.3%) → 超跌反弹
    elif yesterday_pct < -2.0 and bid_pct > 0.3:
        verdict = '超跌反弹'
    # 正常加权判断
    elif total_score > 0.3:
        verdict = '偏多'
    elif total_score < -0.3:
        verdict = '偏空'
    else:
        verdict = '分歧'

    return {
        'total_score': total_score,
        'verdict': verdict,
        'signals': signals
    }


# ========================================================================
# 函数5: 风险检测
# ========================================================================

_RISK_RULES = [
    {
        'condition': '上涨家数/总家数 < 45% 且 指数>+1%',
        'level': 'high',
        'check': lambda d: (
            d.get('上涨家数', 0) / max(d.get('总家数', 1), 1) < 0.45
            and abs(d.get('上证涨跌幅', 0)) > 1.0
        ),
        'format_warning': lambda d: (
            f'指数失真预警：上证涨幅{d.get("上证涨跌幅", 0):+.2f}%，'
            f'但上涨家数仅占{d.get("上涨家数", 0)/max(d.get("总家数", 1), 1)*100:.1f}%，'
            f'指数上涨由少数权重股拉动，多数个股赚钱效应差'
        )
    },
    {
        'condition': '昨日涨停 > 60',
        'level': 'medium',
        'check': lambda d: d.get('昨日涨停数', 0) > 60,
        'format_warning': lambda d: (
            f'过热警示：昨日涨停{d.get("昨日涨停数", 0)}家，'
            f'市场情绪阶段性过热，今日谨防获利兑现和分化回落'
        )
    },
    {
        'condition': '昨日科创50/创业板 > 5%',
        'level': 'medium',
        'check': lambda d: (
            abs(d.get('昨日科创50涨跌幅', 0)) > 5.0
            or abs(d.get('昨日创业板涨跌幅', 0)) > 5.0
        ),
        'format_warning': lambda d: (
            f'追高风险：{"科创50" if abs(d.get("昨日科创50涨跌幅", 0)) > 5.0 else "创业板"}'
            f'昨日大涨{max(abs(d.get("昨日科创50涨跌幅", 0)), abs(d.get("昨日创业板涨跌幅", 0))):+.2f}%，'
            f'历史统计单日涨幅超5%后次日回调概率较高'
        )
    },
    {
        'condition': '竞价低开个股 > 60%',
        'level': 'medium',
        'check': lambda d: d.get('竞价低开比例', 0) > 0.60,
        'format_warning': lambda d: (
            f'竞价抛压警示：竞价阶段{d.get("竞价低开比例", 0)*100:.0f}%个股低开，'
            f'开盘后抛压需警惕，关注指数能否在10分钟内企稳'
        )
    },
    {
        'condition': '隔夜美股 < -2%',
        'level': 'high',
        'check': lambda d: d.get('隔夜美股涨跌幅', 0) < -2.0,
        'format_warning': lambda d: (
            f'外盘拖累：隔夜美股大跌{d.get("隔夜美股涨跌幅", 0):+.2f}%，'
            f'A股或受情绪传导低开，关注开盘价能否快速修复'
        )
    },
    {
        'condition': '竞价涨幅榜成交额偏低',
        'level': 'info',
        'check': lambda d: d.get('竞价涨幅榜平均成交额', float('inf')) < 100,
        'format_warning': lambda d: (
            f'竞价量能偏弱：涨幅榜个股竞价平均成交额不足{d.get("竞价涨幅榜平均成交额", 0):.0f}万，'
            f'缺乏真实买盘支撑，谨防高开低走'
        )
    },
    {
        'condition': '跌停数 > 涨停数 × 2',
        'level': 'high',
        'check': lambda d: (
            d.get('跌停数', 0) > 0
            and d.get('涨停数', 0) > 0
            and d.get('跌停数', 0) > d.get('涨停数', 0) * 2
        ),
        'format_warning': lambda d: (
            f'恐慌信号：跌停{d.get("跌停数", 0)}家远超涨停{d.get("涨停数", 0)}家，'
            f'空头情绪占压倒性优势'
        )
    },
]


def detect_risks(market_data):
    """
    检测市场风险条件，返回风险清单。

    参数:
        market_data (dict): 市场数据，包含以下字段:
            - '上涨家数', '总家数'
            - '上证涨跌幅'
            - '昨日涨停数'
            - '昨日科创50涨跌幅', '昨日创业板涨跌幅'
            - '竞价低开比例'
            - '隔夜美股涨跌幅'
            - '竞价涨幅榜平均成交额'
            - '涨停数', '跌停数'
            以及 _RISK_RULES 中各 check 函数所需的其他字段

    返回:
        dict: {
            'risks': [{'condition':str, 'level':'high'/'medium'/'info', 'warning':str}],
            'must_show': bool   # 是否必须展示风险模块
        }
    """
    risks = []

    for rule in _RISK_RULES:
        try:
            if rule['check'](market_data):
                warning = rule['format_warning'](market_data)
                risks.append({
                    'condition': rule['condition'],
                    'level': rule['level'],
                    'warning': warning
                })
        except Exception as e:
            # 数据缺失时跳过该条件
            pass

    # 检查是否必须展示风险模块
    high_count = sum(1 for r in risks if r['level'] == 'high')
    must_show = high_count >= 1 or len(risks) >= 2

    return {
        'risks': risks,
        'must_show': must_show
    }


# ========================================================================
# 函数6: 报告快照保存
# ========================================================================

def save_report_snapshot(report_type, data, data_scope=''):
    """
    保存当前报告的关键指标快照，供后续报告做一致性校验。

    参数:
        report_type (str): 'auction'/'morning'/'premarket'/'replay'
        data (dict): 包含关键指标（指数点位、板块TOP3资金、涨停数等）
        data_scope (str): 数据口径 ('申万一级'/'申万二级'/'混合')

    行为:
        1. 快照路径：memory/report_snapshot.json
        2. 保留当日所有报告快照，键名为 report_type
        3. 每条快照包含：report_type, timestamp, data_scope, key_indicators
        4. key_indicators 至少包含：sh_index, sci50_index, limit_up_count, sector_top3
    """
    snapshot_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '..', 'memory', 'report_snapshot.json'
    )

    # 从 data 中提取关键指标
    indexes = data.get('indexes', [])
    sh_index = None
    sci50_index = None
    for idx in indexes:
        name = idx.get('指数', '')
        if '上证' in name:
            sh_index = idx.get('最新', idx.get('点位', None))
        elif '科创50' in name:
            sci50_index = idx.get('最新', idx.get('点位', None))

    # 涨停数
    limits = data.get('limits', {})
    limit_up_count = limits.get('涨停', limits.get('涨停数', 0))

    # 板块TOP3（按涨跌幅排序）
    sector_data = data.get('sector_flow', data.get('sectors', []))
    sector_top3 = []
    if isinstance(sector_data, dict):
        gain_list = sector_data.get('涨幅榜', sector_data.get('gainers', []))
    else:
        gain_list = sector_data

    for s in gain_list[:3]:
        if isinstance(s, dict):
            sector_top3.append({
                'name': s.get('板块名称', s.get('name', '')),
                'flow': s.get('主力净流入', s.get('flow', 0)),
                'pct': s.get('涨跌幅', s.get('pct', 0)),
                'scope': data_scope
            })

    snapshot_entry = {
        'report_type': report_type,
        'timestamp': datetime.now().isoformat(),
        'data_scope': data_scope,
        'key_indicators': {
            'sh_index': sh_index,
            'sci50_index': sci50_index,
            'limit_up_count': limit_up_count,
            'sector_top3': sector_top3
        }
    }

    # 读取现有快照文件或创建新文件
    existing = {'last_updated': None, 'snapshots': {}}
    try:
        if os.path.exists(snapshot_path):
            with open(snapshot_path, 'r', encoding='utf-8') as f:
                existing = json.load(f)
    except (json.JSONDecodeError, IOError):
        existing = {'last_updated': None, 'snapshots': {}}

    # 保存快照
    existing['snapshots'][report_type] = snapshot_entry
    existing['last_updated'] = datetime.now().isoformat()

    os.makedirs(os.path.dirname(snapshot_path), exist_ok=True)
    with open(snapshot_path, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    return snapshot_entry


# ========================================================================
# 函数7: 跨报告一致性检查
# ========================================================================

def check_cross_report_consistency(new_data, snapshot_data, report_type='morning'):
    """
    检查当前数据与上一份报告数据的差异。

    参数:
        new_data (dict): 当前报告数据
        snapshot_data (dict): 上一份报告的快照数据（包含 key_indicators 字段）
        report_type (str): 报告类型，默认 'morning'

    返回:
        dict: {'warnings': [], 'passes': [], 'changed_fields': []}
            每个warning包含: {'field': 'str', 'old_value': 'str', 'new_value': 'str', 'reason': 'str'}
    """
    result = {'warnings': [], 'passes': [], 'changed_fields': []}

    if not snapshot_data or 'key_indicators' not in snapshot_data:
        result['passes'].append('无历史快照数据，跳过一致性检查')
        return result

    old = snapshot_data['key_indicators']

    # 从 new_data 中提取当前指标
    indexes = new_data.get('indexes', [])
    new_sh = None
    for idx in indexes:
        name = idx.get('指数', '')
        if '上证' in name:
            new_sh = idx.get('最新', idx.get('点位', 0))
            break

    limits = new_data.get('limits', {})
    new_lu = limits.get('涨停', limits.get('涨停数', 0))

    # 检查1: 上证指数差异 > 1%
    old_sh = old.get('sh_index')
    if old_sh and new_sh and old_sh > 0:
        sh_diff = abs(new_sh - old_sh) / old_sh * 100
        if sh_diff > 1.0:
            result['warnings'].append({
                'field': 'sh_index',
                'old_value': f'{old_sh:.2f}',
                'new_value': f'{new_sh:.2f}',
                'reason': f'上证指数差异{sh_diff:.2f}%，超过1%阈值，市场出现显著波动'
            })
            result['changed_fields'].append('sh_index')
        else:
            result['passes'].append(f'上证指数一致性通过（差异{sh_diff:.2f}%）')

    # 检查2: 昨日涨停数差异 > 0
    old_lu = old.get('limit_up_count', 0)
    if old_lu != new_lu:
        diff = abs(new_lu - old_lu)
        result['warnings'].append({
            'field': 'limit_up_count',
            'old_value': str(old_lu),
            'new_value': str(new_lu),
            'reason': f'涨停家数变化{+diff if new_lu > old_lu else -diff}家，表明市场情绪发生变化'
        })
        result['changed_fields'].append('limit_up_count')
    else:
        result['passes'].append('涨停家数一致')

    # 检查3: 板块TOP3资金差异 > 20%
    old_top3 = old.get('sector_top3', [])
    sector_data = new_data.get('sector_flow', new_data.get('sectors', []))
    if isinstance(sector_data, dict):
        new_gain_list = sector_data.get('涨幅榜', sector_data.get('gainers', []))
    else:
        new_gain_list = sector_data

    for i, old_s in enumerate(old_top3):
        if i >= len(new_gain_list):
            break
        new_s = new_gain_list[i]
        old_name = old_s.get('name', '')
        new_name = new_s.get('板块名称', new_s.get('name', ''))
        old_flow = abs(old_s.get('flow', 0))
        new_flow = abs(new_s.get('主力净流入', new_s.get('flow', 0)))

        if old_flow > 0 and new_flow > 0:
            flow_diff = abs(new_flow - old_flow) / old_flow * 100
            if flow_diff > 20:
                old_scope = old_s.get('scope', '未知')
                result['warnings'].append({
                    'field': f'sector_top3[{i}]',
                    'old_value': f'{old_name}(资金:{old_flow/1e8:.2f}亿,口径:{old_scope})',
                    'new_value': f'{new_name}(资金:{new_flow/1e8:.2f}亿)',
                    'reason': f'板块{i+1}[{new_name}]资金差异{flow_diff:.1f}%，可能为数据口径差异（原口径:{old_scope}）'
                })
                result['changed_fields'].append(f'sector_top3[{i}]')

    return result


# ========================================================================
# 函数8: 板块涨幅集中度检测
# ========================================================================

def check_sector_concentration(sector_pct, sector_flow, sector_name=''):
    """
    检测板块涨幅是否由少量个股带动。

    参数:
        sector_pct (float): 板块涨跌幅（%）
        sector_flow (float): 板块资金净流入（元）
        sector_name (str): 板块名称，用于描述

    返回:
        dict: {'is_concentrated': bool, 'reason': str, 'warning_level': 'high'/'medium'/'none'}
    """
    if sector_flow is None:
        sector_flow = 0
    if sector_pct is None:
        sector_pct = 0

    # 统一转成 float
    try:
        flow = float(sector_flow)
        pct = float(sector_pct)
    except (ValueError, TypeError):
        return {
            'is_concentrated': False,
            'reason': '数据格式异常，无法判断',
            'warning_level': 'none'
        }

    pct = abs(pct)

    # 逻辑判断
    if flow < 100_000_000 and pct > 3.0:
        # < 1亿 且 > 3%
        name_part = f'[{sector_name}]' if sector_name else ''
        return {
            'is_concentrated': True,
            'reason': f'{name_part}涨{pct:.2f}%，但主力净流入仅{flow/1e8:.1f}亿，资金严重不足，涨幅由个股行情带动',
            'warning_level': 'high'
        }

    if flow < 300_000_000 and pct > 5.0:
        # < 3亿 且 > 5%
        name_part = f'[{sector_name}]' if sector_name else ''
        return {
            'is_concentrated': True,
            'reason': f'{name_part}涨{pct:.2f}%，但主力净流入仅{flow/1e8:.1f}亿，资金驱动较弱',
            'warning_level': 'medium'
        }

    name_part = f'[{sector_name}]' if sector_name else ''
    return {
        'is_concentrated': False,
        'reason': f'{name_part}资金与涨幅匹配合理，未发现明显个股行情',
        'warning_level': 'none'
    }


# ========================================================================
# 函数9: 市场极端撕裂行情判断（铁律6——市场情绪-极端行情判定）
# ========================================================================

def classify_market_divergence(up_ratio, limit_up, limit_down, index_changed):
    """
    判断市场是否处于极端撕裂行情（铁律6）。

    判断逻辑：
      - extreme_divergence: 涨跌比<30% 且 涨停>跌停 (指数跌但个股局部亢奋)
      - fake_recovery:      指数涨>0 但 涨跌比<30% (指数红但八成个股下跌)
      - normal_bull:        正常偏多行情
      - normal_bear:        正常偏空行情
      - normal:             正常市场

    Parameters:
        up_ratio (float): 上涨家数占比 (0~1, 如 0.245 表示 24.5%)
        limit_up (int): 涨停家数
        limit_down (int): 跌停家数
        index_changed (float): 指数涨跌幅 (如 -0.17)

    Returns:
        dict: {'verdict': str, 'level': str, 'reason': str}
    """
    if up_ratio < 0.30 and limit_up > limit_down:
        return {
            'verdict': 'extreme_divergence',
            'level': 'high',
            'reason': (
                f'极端撕裂行情：上涨占比仅{up_ratio*100:.1f}%（<30%），'
                f'但涨停{limit_up}家 > 跌停{limit_down}家，'
                f'指数跌{index_changed:+.2f}%，个股局部亢奋与普跌并存'
            )
        }

    if index_changed > 0 and up_ratio < 0.30:
        return {
            'verdict': 'fake_recovery',
            'level': 'high',
            'reason': (
                f'虚假修复（指数失真）：上证涨{index_changed:+.2f}%，'
                f'但上涨家数仅占{up_ratio*100:.1f}%（<30%），'
                f'指数由少数权重股拉动，八成个股在跌'
            )
        }

    if up_ratio >= 0.50 and limit_up > limit_down * 1.5:
        return {
            'verdict': 'normal_bull',
            'level': 'medium',
            'reason': (
                f'正常偏多行情：上涨占比{up_ratio*100:.1f}%（≥50%），'
                f'涨停{limit_up}家 > 跌停{limit_down}家，市场整体偏强'
            )
        }

    if up_ratio < 0.30:
        return {
            'verdict': 'normal_bear',
            'level': 'medium',
            'reason': (
                f'正常偏空行情：上涨占比仅{up_ratio*100:.1f}%（<30%），'
                f'市场整体承压' + (
                    f'，跌停{limit_down}家较多' if limit_down > 10 else ''
                )
            )
        }

    return {
        'verdict': 'normal',
        'level': 'none',
        'reason': (
            f'正常市场：上涨占比{up_ratio*100:.1f}%，'
            f'涨停{limit_up}家 / 跌停{limit_down}家，'
            f'指数{index_changed:+.2f}%'
        )
    }


# ========================================================================
# 函数10: 量能定性一致性校验（铁律7——量能定性校验）
# ========================================================================

def check_volume_qualitative(volume_change_pct, index_change_pct):
    """
    检查量能定性是否与数据一致（铁律7）。

    Parameters:
        volume_change_pct (float): 成交额变化百分比（如 1.2 表示同比+1.2%）
        index_change_pct (float): 指数涨跌幅（如 -0.17 表示跌0.17%）

    Returns:
        dict: {
            'expected': str,        # 数据推导出的理论定性
            'check_passed': bool,   # 占位——调用方传入定性后做比对
            'verify_rule': str      # 验证规则说明
        }
    """
    eps = 0.05  # 判断量持平的小阈值

    if volume_change_pct > eps and index_change_pct > eps:
        expected = '放量上涨'
    elif volume_change_pct > eps and index_change_pct < -eps:
        expected = '放量下跌'
    elif volume_change_pct < -eps and index_change_pct > eps:
        expected = '缩量上涨'
    elif volume_change_pct < -eps and index_change_pct < -eps:
        expected = '缩量下跌'
    else:
        # volume ≈ 0 或 index ≈ 0
        if abs(volume_change_pct) <= eps:
            expected = '量平价升/跌'
        elif index_change_pct > eps:
            expected = '缩量上涨'
        elif index_change_pct < -eps:
            expected = '缩量下跌'
        else:
            expected = '量平价升/跌'

    return {
        'expected': expected,
        'check_passed': False,  # 由调用方传入实际定性后比对
        'verify_rule': (
            f'铁律7-量能定性校验：成交额变化{volume_change_pct:+.1f}%，'
            f'指数涨跌幅{index_change_pct:+.2f}%，'
            f'理论预期定性为【{expected}】'
        )
    }


# ========================================================================
# 函数10: 板块涨幅扫描 (v4.0)
# ========================================================================

def scan_sector_gainers(sector_data, threshold=5.0):
    """
    扫描板块内涨幅超过threshold%的所有个股。

    Parameters:
        sector_data (dict): {
            '板块名称': str,
            '成分股': [{'名称': str, '涨幅': float}, ...]
        }
        threshold (float): 涨幅阈值，默认5.0%

    Returns:
        dict: {
            'all_gainers': [{'名称': str, '涨幅': float}],
            'missed_stocks': int
        }
    """
    sector_name = sector_data.get('板块名称', '')
    constituents = sector_data.get('成分股', [])

    if not constituents:
        return {
            'all_gainers': [],
            'missed_stocks': 0,
            'note': f'板块【{sector_name}】成分股数据有限，仅展示已知个股'
        }

    all_gainers = []
    for stock in constituents:
        pct = stock.get('涨幅', stock.get('涨跌幅', stock.get('pct', 0)))
        try:
            pct = float(pct)
        except (ValueError, TypeError):
            continue
        if pct >= threshold:
            all_gainers.append({
                '名称': stock.get('名称', stock.get('name', '')),
                '涨幅': round(pct, 2)
            })

    # 按涨幅降序排列
    all_gainers.sort(key=lambda x: x['涨幅'], reverse=True)

    return {
        'all_gainers': all_gainers,
        'missed_stocks': 0
    }


# ========================================================================
# 函数11: 个股资金流向合理性验证 (v6)
# ========================================================================

def validate_stock_fund_flow(stock_info):
    """个股资金流向合理性验证

    验证维度：
    1. 数值范围：主力净流入绝对值 ≤ 当日成交额 × 40%
    2. 方向合理性：涨跌幅 > 5% 但主力净流入为负 → '资金背离标记'
    3. 涨跌幅 < -3% 但主力净流入为正 → '资金背离标记'
    4. 量级合理性：主力净流入绝对值不应超过流通市值×8%

    stock_info = {
        '代码': str,
        '名称': str,
        '涨跌幅': float,
        '成交额': float (万),
        '流通市值': float (万),
        '主力净流入': float (万),
        ...
    }

    返回：{
        'pass': True/False,
        'confidence': 'high'/'medium'/'low',
        'issues': [str],  # 触发的问题列表
        'warnings': [str]  # 标记的警告列表
    }
    """
    issues = []
    warnings = []

    code = stock_info.get('代码', '')
    name = stock_info.get('名称', '')
    pct = stock_info.get('涨跌幅', 0)
    turnover = stock_info.get('成交额', 0)
    circ_mv = stock_info.get('流通市值', 0)
    main_flow = stock_info.get('主力净流入', 0)

    # 安全转换为float
    try:
        pct = float(pct) if pct is not None else 0
    except (ValueError, TypeError):
        pct = 0
    try:
        turnover = float(turnover) if turnover is not None else 0
    except (ValueError, TypeError):
        turnover = 0
    try:
        circ_mv = float(circ_mv) if circ_mv is not None else 0
    except (ValueError, TypeError):
        circ_mv = 0
    try:
        main_flow = float(main_flow) if main_flow is not None else 0
    except (ValueError, TypeError):
        main_flow = 0

    abs_main_flow = abs(main_flow)

    # --- 维度1: 数值范围（主力净流入 ≤ 成交额 × 40%）---
    if turnover > 0:
        max_reasonable = turnover * 0.40
        if abs_main_flow > max_reasonable:
            issues.append(
                f'{code} {name} 主力净流入绝对值({main_flow/1e4:.2f}万) '
                f'超过成交额({turnover/1e4:.2f}万)的40%({max_reasonable/1e4:.2f}万)，数值异常'
            )

    # --- 维度2: 方向合理性（涨跌幅与主力净流入方向背离）---
    if pct > 5.0 and main_flow < 0:
        warnings.append(
            f'{code} {name} 资金背离标记：涨跌幅+{pct:.2f}% > 5%，'
            f'但主力净流入为{main_flow/1e4:.2f}万（净流出），属于拉高出货形态'
        )
    elif pct < -3.0 and main_flow > 0:
        warnings.append(
            f'{code} {name} 资金背离标记：涨跌幅{pct:.2f}% < -3%，'
            f'但主力净流入为+{main_flow/1e4:.2f}万（净流入），属于护盘诱多形态'
        )

    # --- 维度3: 量级合理性（主力净流入 ≤ 流通市值 × 8%）---
    if circ_mv > 0:
        max_flow_mv = circ_mv * 0.08
        if abs_main_flow > max_flow_mv:
            issues.append(
                f'{code} {name} 主力净流入绝对值({main_flow/1e4:.2f}万) '
                f'超过流通市值({circ_mv/1e4:.2f}万)的8%({max_flow_mv/1e4:.2f}万)，量级异常'
            )

    # --- 综合判定 ---
    has_issues = len(issues) > 0
    has_warnings = len(warnings) > 0

    if has_issues:
        passed = False
        confidence = 'low'
    elif has_warnings:
        passed = True
        confidence = 'medium'
    else:
        passed = True
        confidence = 'high'

    return {
        'pass': passed,
        'confidence': confidence,
        'issues': issues,
        'warnings': warnings
    }


# ========================================================================
# 辅助函数
# ========================================================================

def format_pct(value):
    """格式化涨跌幅显示"""
    if value is None:
        return '-'
    return f'{value:+.2f}%'


def format_money(value):
    """格式化金额（元→万/亿）"""
    if value is None:
        return '-'
    v = abs(float(value))
    if v >= 1e8:
        return f'{v/1e8:.2f}亿'
    elif v >= 1e4:
        return f'{v/1e4:.2f}万'
    else:
        return f'{v:.2f}元'


# ========================================================================
# 主入口 & 测试
# ========================================================================

if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        print("=== analysis_engine.py 自测试 ===")
        ok = True

        # 测试 classify_limit_status
        print("\n--- classify_limit_status ---")
        tests = [
            # 封板涨停 (A股价格精确到0.01元)
            (10.00, 9.09, 10.00, None, 'limit_up_sealed'),
            (10.00, 9.09, 9.99, None, 'limit_up_touched'),  # 不精确封板
            (10.01, 9.10, 10.01, None, 'limit_up_sealed'),  # 精确封板
            # 触板涨停 (涨幅≥9.9%但未精确封板)
            (9.99, 9.09, 10.00, None, 'limit_up_touched'),  # (9.99-9.09)/9.09=9.90%
            (10.00, 9.09, 10.01, None, 'limit_up_touched'),  # (10-9.09)/9.09=10.01% >9.9%
            # 接近涨停 (8%~9.89%)
            (9.80, 8.99, 9.89, None, 'near_limit_up'),  # (9.8-8.99)/8.99=9.01%
            # 普通
            (8.50, 8.00, None, None, 'normal'),
            # 封板跌停
            (8.18, 9.09, None, 8.18, 'limit_down_sealed'),
            # 触板跌停
            (8.18, 9.09, None, 8.00, 'limit_down_touched'),
            # 接近跌停
            (8.30, 9.09, None, None, 'near_limit_down'),  # (8.3-9.09)/9.09=-8.69% ≈ -8.69% <= -8%
            # 普通
            (9.00, 9.09, None, None, 'normal'),
        ]
        for price, prev, up, down, expected in tests:
            result = classify_limit_status(price, prev, up, down)
            if result == expected:
                print(f"  ✓ classify_limit_status({price},{prev},{up},{down}) = {result}")
            else:
                print(f"  ✗ classify_limit_status({price},{prev},{up},{down}) = {result} (期望 {expected})")
                ok = False

        # 测试 calc_volume_divergence
        print("\n--- calc_volume_divergence ---")
        stocks_bullish = [
            {'涨跌幅': 10.0, '成交额': 50000000},
            {'涨跌幅': 9.0, '成交额': 40000000},
            {'涨跌幅': 8.0, '成交额': 30000000},
            {'涨跌幅': 7.0, '成交额': 20000000},
            {'涨跌幅': 6.0, '成交额': 10000000},
            {'涨跌幅': -3.0, '成交额': 5000000},
            {'涨跌幅': -4.0, '成交额': 3000000},
            {'涨跌幅': -5.0, '成交额': 2000000},
            {'涨跌幅': -6.0, '成交额': 1000000},
            {'涨跌幅': -7.0, '成交额': 500000},
        ]
        div = calc_volume_divergence(stocks_bullish)
        print(f"  量能分化: ratio={div['ratio']}, label={div['label']}")
        if div['label'] in ('bullish', 'extremely_bullish'):
            print(f"  ✓ 正确识别为偏多量能")
        else:
            print(f"  ✗ 期望 bullish 或 extremely_bullish, 得到 {div['label']}")
            ok = False

        # 测试 calc_support_resistance
        print("\n--- calc_support_resistance ---")
        idx_data = [
            {'日期': '2026-05-22', '最高': 3360, '最低': 3320, '收盘': 3340, '昨收': 3330},
            {'日期': '2026-05-23', '最高': 3370, '最低': 3330, '收盘': 3350, '昨收': 3340},
            {'日期': '2026-05-26', '最高': 3380, '最低': 3340, '收盘': 3360, '昨收': 3350},
        ]
        sr = calc_support_resistance(idx_data, days=3)
        print(f"  支撑位: {sr['support1']}/{sr['support2']}, 压力位: {sr['resist1']}/{sr['resist2']}")
        print(f"  核心区间: [{sr['core_low']}, {sr['core_high']}], ATR={sr['atr']}")
        if sr['support1'] < sr['resist1'] and sr['range_width'] > 0:
            print(f"  ✓ 支撑压力符合逻辑")
        else:
            print(f"  ✗ 支撑压力计算异常")
            ok = False

        # 测试 signal_weight_matrix
        print("\n--- signal_weight_matrix ---")
        md = {
            '竞价涨跌幅': 0.5,
            '涨停数': 20,
            '跌停数': 5,
            '昨日上证涨跌幅': 1.2,
            '昨日涨停数': 50,
            '昨日跌停数': 8,
            '隔夜美股涨跌幅': 0.8,
            '竞价量能标签': 'bullish',
            '板块涨跌比': 0.65,
        }
        sw = signal_weight_matrix(md)
        print(f"  总分: {sw['total_score']}, 判定: {sw['verdict']}")
        if sw['verdict'] in ('偏多', '高位博弈', '超跌反弹'):
            print(f"  ✓ 情绪判断合理")
        else:
            print(f"  ✗ 期望偏多方向, 得到 {sw['verdict']}")
            ok = False

        # 测试 detect_risks
        print("\n--- detect_risks ---")
        rd = {
            '上涨家数': 1200,
            '总家数': 4000,
            '上证涨跌幅': 1.5,
            '昨日涨停数': 70,
            '昨日科创50涨跌幅': 6.2,
            '昨日创业板涨跌幅': 0,
            '竞价低开比例': 0.65,
            '隔夜美股涨跌幅': -2.5,
            '竞价涨幅榜平均成交额': 50,
            '涨停数': 10,
            '跌停数': 25,
        }
        risk_result = detect_risks(rd)
        print(f"  触发风险数: {len(risk_result['risks'])}, must_show={risk_result['must_show']}")
        if len(risk_result['risks']) >= 2 and risk_result['must_show']:
            print(f"  ✓ 风险检测有效")
        else:
            print(f"  ✗ 期望至少2个风险且must_show=True, 得到 {len(risk_result['risks'])}个/must_show={risk_result['must_show']}")
            ok = False

        print(f"\n{'='*40}")
        if ok:
            print("✅ 全部测试通过！")
        else:
            print("❌ 存在失败的测试")
            sys.exit(1)
    else:
        print("analysis_engine.py v1.0 — A股竞价分析引擎")
        print("用法: python analysis_engine.py test  # 运行自测试")
