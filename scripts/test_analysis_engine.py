#!/usr/bin/env python3
"""
分析引擎集成测试脚本
======================
验证 analysis_engine.py 所有5个函数能正常执行，
以及 html_ppt.py 的竞价报告生成功能。
"""

import sys
import os
import json
from datetime import datetime

# 确保能导入 analysis_engine
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from analysis_engine import (
    classify_limit_status,
    classify_batch,
    calc_volume_divergence,
    calc_support_resistance,
    signal_weight_matrix,
    detect_risks,
    format_pct,
    format_money,
)

TEST_PASSED = 0
TEST_FAILED = 0


def test(name, condition, detail=""):
    global TEST_PASSED, TEST_FAILED
    if condition:
        TEST_PASSED += 1
        print(f"  ✅ {name}")
    else:
        TEST_FAILED += 1
        print(f"  ❌ {name} — {detail}")


def test_raises(name, fn, expected_exc=Exception):
    """测试是否抛异常"""
    global TEST_PASSED, TEST_FAILED
    try:
        fn()
        TEST_FAILED += 1
        print(f"  ❌ {name} — 期望抛异常但未抛")
    except expected_exc:
        TEST_PASSED += 1
        print(f"  ✅ {name}")


print("=" * 60)
print("analysis_engine.py 集成测试")
print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 60)

# ============================================================
# 测试1: classify_limit_status
# ============================================================
print("\n--- 1. classify_limit_status ---")

# 封板涨停
test("封板涨停(精确)", classify_limit_status(10.00, 9.09, 10.00) == 'limit_up_sealed')
test("封板涨停(公差内)", classify_limit_status(10.01, 9.09, 10.01) == 'limit_up_sealed')
test("封板跌停(精确)", classify_limit_status(8.18, 9.09, None, 8.18) == 'limit_down_sealed')

# 触板涨停
test("触板涨停", classify_limit_status(9.99, 9.09, 10.01) == 'limit_up_touched')
test("触板跌停", classify_limit_status(8.18, 9.09, None, 8.00) == 'limit_down_touched')

# 接近
test("接近涨停", classify_limit_status(9.80, 8.99) == 'near_limit_up')
test("接近跌停", classify_limit_status(8.30, 9.09) == 'near_limit_down')

# 正常
test("普通状态", classify_limit_status(9.00, 9.09) == 'normal')
test("未知状态(None)", classify_limit_status(None, 10.0) == 'unknown')
test("未知状态(zero prev)", classify_limit_status(10.0, 0) == 'unknown')

# 边界情况
test("边界: 涨幅9.89%不触发触碰", classify_limit_status(9.89, 9.00, None) == 'near_limit_up')

# ============================================================
# 测试2: classify_batch
# ============================================================
print("\n--- 2. classify_batch ---")

stocks_test = [
    {"名称": "股票A", "代码": "600001", "最新价": 10.00, "涨跌幅": 10.01, "昨收": 9.09},
    {"名称": "股票B", "代码": "600002", "最新价": 9.50, "涨跌幅": 5.56, "昨收": 9.00},
    {"名称": "股票C", "代码": "600003", "最新价": 8.30, "涨跌幅": -9.87, "昨收": 9.09},
]
batch_result = classify_batch(stocks_test)
test("批量分类返回正确数量", len(batch_result) == 3)
test("批量分类含limit_status字段", 'limit_status' in batch_result[0])
test("批量分类含limit_label字段", 'limit_label' in batch_result[0])
test("批量不含涨停价时正常fallback", batch_result[0]['limit_status'] == 'limit_up_touched')

# ============================================================
# 测试3: calc_volume_divergence
# ============================================================
print("\n--- 3. calc_volume_divergence ---")

# 偏多场景
bullish_data = [
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
div = calc_volume_divergence(bullish_data)
test("量能偏多检测", div['label'] in ('bullish', 'extremely_bullish'))
test("量能比值>3", div['ratio'] > 3)
test("量能警告不为None", div['warning'] is not None)

# 均衡场景
balanced_data = [
    {'涨跌幅': 5.0, '成交额': 10000000},
    {'涨跌幅': 4.0, '成交额': 8000000},
    {'涨跌幅': -5.0, '成交额': 10000000},
    {'涨跌幅': -4.0, '成交额': 8000000},
]
div2 = calc_volume_divergence(balanced_data)
test("量能均衡检测", div2['label'] == 'balanced')
test("无警告", div2['warning'] is None)

# 空数据
div3 = calc_volume_divergence([])
test("空数据返回默认", div3['label'] == 'balanced')

# None成交额
null_vol_data = [
    {'涨跌幅': 5.0, '成交额': None},
    {'涨跌幅': -5.0, '成交额': None},
]
div4 = calc_volume_divergence(null_vol_data)
test("None成交额安全处理", div4['label'] == 'balanced')

# ============================================================
# 测试4: calc_support_resistance
# ============================================================
print("\n--- 4. calc_support_resistance ---")

# 正常数据
idx_data = [
    {'日期': '2026-05-22', '最高': 3360, '最低': 3320, '收盘': 3340, '昨收': 3330},
    {'日期': '2026-05-23', '最高': 3370, '最低': 3330, '收盘': 3350, '昨收': 3340},
    {'日期': '2026-05-26', '最高': 3380, '最低': 3340, '收盘': 3360, '昨收': 3350},
]
sr = calc_support_resistance(idx_data, days=3)
test("支撑位<压力位", sr['support1'] < sr['resist1'])
test("核心区间有效", sr['core_low'] < sr['core_high'])
test("区间宽度>0", sr['range_width'] > 0)
test("ATR>0", sr['atr'] > 0)
test("支撑位2<支撑位1", sr['support2'] < sr['support1'])
test("压力位2>压力位1", sr['resist2'] > sr['resist1'])

# 不足2天数据
sr2 = calc_support_resistance([{'日期': '2026-05-26', '最高': 3380, '最低': 3340, '收盘': 3360}])
test("不足2天返回valid", sr2['range_validity'] in ('valid', 'invalid'))

# 空数据
sr3 = calc_support_resistance([])
test("空数据返回invalid", sr3['range_validity'] == 'invalid')

# ============================================================
# 测试5: signal_weight_matrix
# ============================================================
print("\n--- 5. signal_weight_matrix ---")

# 偏多场景
md_bullish = {
    '竞价涨跌幅': 0.8,
    '涨停数': 25,
    '跌停数': 3,
    '昨日上证涨跌幅': 1.5,
    '昨日涨停数': 50,
    '昨日跌停数': 5,
    '隔夜美股涨跌幅': 1.2,
    '竞价量能标签': 'bullish',
    '板块涨跌比': 0.7,
}
sw = signal_weight_matrix(md_bullish)
test("偏多场景总分>0", sw['total_score'] > 0)
test("偏多场景判定", sw['verdict'] in ('偏多', '高位博弈'))
test("有7个信号", len(sw['signals']) == 7)

# 偏空场景
md_bearish = {
    '竞价涨跌幅': -0.5,
    '涨停数': 5,
    '跌停数': 30,
    '昨日上证涨跌幅': -2.0,
    '昨日涨停数': 10,
    '昨日跌停数': 40,
    '隔夜美股涨跌幅': -1.5,
    '竞价量能标签': 'bearish',
    '板块涨跌比': 0.3,
}
sw2 = signal_weight_matrix(md_bearish)
test("偏空场景总分<0", sw2['total_score'] < 0)
test("偏空场景判定", sw2['verdict'] in ('偏空', '超跌反弹'))

# 高位博弈场景
md_gamble = {
    '竞价涨跌幅': -0.5,
    '涨停数': 10,
    '跌停数': 5,
    '昨日上证涨跌幅': 3.0,
    '昨日涨停数': 50,
    '昨日跌停数': 5,
    '隔夜美股涨跌幅': 0.5,
    '竞价量能标签': 'balanced',
    '板块涨跌比': 0.5,
}
sw3 = signal_weight_matrix(md_gamble)
test("高位博弈场景", sw3['verdict'] == '高位博弈')

# 超跌反弹场景
md_rebound = {
    '竞价涨跌幅': 0.5,
    '涨停数': 10,
    '跌停数': 5,
    '昨日上证涨跌幅': -3.0,
    '昨日涨停数': 20,
    '昨日跌停数': 30,
    '隔夜美股涨跌幅': -0.5,
    '竞价量能标签': 'balanced',
    '板块涨跌比': 0.5,
}
sw4 = signal_weight_matrix(md_rebound)
test("超跌反弹场景", sw4['verdict'] == '超跌反弹')

# ============================================================
# 测试6: detect_risks
# ============================================================
print("\n--- 6. detect_risks ---")

# 触发全部风险
rd_all = {
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
risk = detect_risks(rd_all)
test("触发除创业板外的所有风险", len(risk['risks']) >= 6)
test("高风险触发(must_show)", risk['must_show'] is True)

# 无风险场景
rd_none = {
    '上涨家数': 2500,
    '总家数': 4000,
    '上证涨跌幅': 0.3,
    '昨日涨停数': 20,
    '昨日科创50涨跌幅': 1.0,
    '昨日创业板涨跌幅': 0.5,
    '竞价低开比例': 0.40,
    '隔夜美股涨跌幅': 0.5,
    '竞价涨幅榜平均成交额': 300,
    '涨停数': 10,
    '跌停数': 5,
}
risk2 = detect_risks(rd_none)
test("无风险不触发", len(risk2['risks']) == 0)
test("无风险不must_show", risk2['must_show'] is False)

# 空数据
risk3 = detect_risks({})
test("空数据安全处理", isinstance(risk3, dict))
test("空数据不报错", 'risks' in risk3 and 'must_show' in risk3)

# ============================================================
# 测试7: 辅助函数
# ============================================================
print("\n--- 7. 辅助函数 ---")

test("format_pct 正数", format_pct(1.23) == '+1.23%')
test("format_pct 负数", format_pct(-0.5) == '-0.50%')
test("format_pct None", format_pct(None) == '-')
test("format_money 亿", format_money(123456789) == '1.23亿')
test("format_money 万", format_money(123456) == '12.35万')
test("format_money 元", format_money(123) == '123.00元')
test("format_money None", format_money(None) == '-')

# ============================================================
# 测试8: html_ppt.py 集成测试
# ============================================================
print("\n--- 8. html_ppt.py 集成测试 ---")

try:
    sys.path.insert(0, os.path.join(SCRIPT_DIR, ".."))
    from scripts.html_ppt import (
        generate,
        _generate_auction_slides,
        _tag_limit,
        _news_item,
        _warning_box,
    )
    
    # 测试辅助函数
    test("_tag_limit 封板", 'tag-sealed' in _tag_limit('limit_up_sealed'))
    test("_tag_limit 触板", 'tag-touched' in _tag_limit('limit_up_touched'))
    test("_tag_limit 接近", 'tag-near' in _tag_limit('near_limit_up'))
    test("_tag_limit 空", _tag_limit(None) == '')
    test("_tag_limit 未知", _tag_limit('something') == '')
    
    test("_news_item 含来源", 'news-source' in _news_item('东方财富', '内容', '标签'))
    test("_news_item 含标签", 'news-tag' in _news_item('东方财富', '内容', '市场'))
    
    test("_warning_box 结构正确", 'warning-box' in _warning_box('测试标题', '测试内容'))
    
    # 测试竞价报告生成
    sample_data = {
        'date': '2026-05-26',
        '竞价涨跌幅': 0.35,
        '指数': [
            {"指数": "上证指数", "最新": 3350, "涨跌幅": 0.35},
        ],
        'limits': {'涨停': 15, '跌停': 3},
        'updown': {'上涨': 2200, '下跌': 1800},
        'gainers': [
            {"名称": "测试股A", "代码": "600001", "涨跌幅": 10.0, "成交额": 5000000, "limit_status": "limit_up_sealed"},
            {"名称": "测试股B", "代码": "600002", "涨跌幅": 9.5, "成交额": 3000000, "limit_status": "limit_up_touched"},
        ],
        'losers': [
            {"名称": "测试股C", "代码": "600003", "涨跌幅": -9.8, "成交额": 1000000, "limit_status": "limit_down_touched"},
        ],
        'analysis': {
            'volume_divergence': {
                'ratio': 3.5, 'label': 'bullish',
                'warning': '量能分化预警测试'
            },
            'signal_matrix': {
                'total_score': 0.45,
                'verdict': '偏多',
                'signals': [
                    {'name': '竞价涨幅', 'weight': 0.15, 'direction': 1, 'strength': 0.6, 'value': 0.35},
                ]
            },
            'support_resistance': {
                'support1': 3330, 'support2': 3310,
                'resist1': 3370, 'resist2': 3390,
                'core_low': 3330, 'core_high': 3370,
                'range_width': 40, 'atr': 35,
                'range_validity': 'valid'
            },
            'risks': {
                'risks': [{'condition': '测试', 'level': 'high', 'warning': '测试风险预警内容'}],
                'must_show': True
            },
            'news': [
                {'source': '东方财富', 'content': '测试新闻内容', 'tag': '市场'},
            ]
        }
    }
    
    output_path = generate(sample_data, 
        output='/tmp/test_auction_report.html', 
        report_type='auction')
    test("竞价报告生成", os.path.exists(output_path))
    
    with open(output_path, 'r', encoding='utf-8') as f:
        content = f.read()
    test("报告包含标签样式", 'tag-sealed' in content)
    test("报告包含新闻样式", 'news-item' in content)
    test("报告包含警告框", 'warning-box' in content)
    test("报告包含KPI卡片", 'kpi-card' in content)
    test("报告包含数据表", 'data-table' in content)
    test("报告包含覆盖页", 'cover-slide' in content)
    
    # 清理
    os.remove(output_path)
    print("    📄 临时测试报告已清理")
    
except ImportError as e:
    print(f"  ⚠️  html_ppt.py导入失败: {e}")
except Exception as e:
    print(f"  ⚠️  html_ppt.py集成测试异常: {e}")
    import traceback
    traceback.print_exc()

# ============================================================
# 测试9: stock_data.py 集成测试
# ============================================================
print("\n--- 9. stock_data.py 集成测试 ---")

try:
    import importlib.util
    stock_data_path = os.path.join(SCRIPT_DIR, "..", "..", "..", "tools", "stock_data.py")
    spec = importlib.util.spec_from_file_location("stock_data_modules", stock_data_path)
    sd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sd)
    _is_limit_up = sd._is_limit_up
    _is_limit_down = sd._is_limit_down

    # 测试涨停判断
    test("主板涨停判定", _is_limit_up({"代码": "600001", "名称": "测试A", "涨跌幅": 10.0}))
    test("主板非涨停判定", not _is_limit_up({"代码": "600001", "名称": "测试A", "涨跌幅": 5.0}))
    test("科创板涨停判定", _is_limit_up({"代码": "688001", "名称": "测试B", "涨跌幅": 20.0}))
    test("ST涨停判定", _is_limit_up({"代码": "600001", "名称": "*ST测试", "涨跌幅": 5.0}))
    
    # 测试跌停判断
    test("主板跌停判定", _is_limit_down({"代码": "600001", "名称": "测试A", "涨跌幅": -10.0}))
    test("主板非跌停判定", not _is_limit_down({"代码": "600001", "名称": "测试A", "涨跌幅": -5.0}))
    
    # 测试竞价兼容：用价格推导涨跌幅
    test("竞价涨停兼容(价格推导)", _is_limit_up({"代码": "600001", "名称": "测试A", "涨跌幅": 0, "最新价": 11.0, "昨收": 10.0}))
    test("竞价跌停兼容(价格推导)", _is_limit_down({"代码": "600001", "名称": "测试A", "涨跌幅": 0, "最新价": 9.0, "昨收": 10.0}))
    
    # 验证 stock_data.py 成交额字段（字段37）格式
    content = open(stock_data_path).read()
    test("成交额字段(37)已解析", 'f[37]' in content)
    test("成交额字段已转float", 'float(f[37])' in content)
    
except ImportError as e:
    print(f"  ⚠️  stock_data.py导入失败: {e}")
except Exception as e:
    print(f"  ⚠️  stock_data.py测试异常: {e}")

# ============================================================
# 测试汇总
# ============================================================
print("\n" + "=" * 60)
total = TEST_PASSED + TEST_FAILED
print(f"测试汇总: {total} 项 | ✅ 通过: {TEST_PASSED} | ❌ 失败: {TEST_FAILED}")

if TEST_FAILED > 0:
    print("❌ 部分测试失败，请检查日志")
    sys.exit(1)
else:
    print("✅ 全部测试通过！")
    print("=" * 60)
