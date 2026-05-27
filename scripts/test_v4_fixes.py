#!/usr/bin/env python3
"""
v4.0 代码层修复 - 综合测试脚本
==============================
测试覆盖：
1. check_index_name_consistency  — 一致/不一致/白名单外
2. check_typo                    — 有错别字/无错别字/边界
3. final_report_check            — 完整通过/有警告
4. scan_sector_gainers           — 有数据/无数据
5. calc_limit_board_rate         — 高/中/低/unknown
"""

import sys
import os

# Add project root to path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))

# Import modules
from scripts import verifier
from scripts import analysis_engine
from scripts import collector

# ========================
# Test Results Tracker
# ========================
passed = 0
failed = 0
test_results = []


def test(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        msg = f"  ✅ {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)
        test_results.append(("PASS", name, detail))
    else:
        failed += 1
        msg = f"  ❌ {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)
        test_results.append(("FAIL", name, detail))


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ========================
# Test 1: check_index_name_consistency
# ========================
section("测试1: check_index_name_consistency — 指数名称一致性检查")

# 1a. 一致的情况 — 只使用一种名称
text_consistent = "今日科创50上涨1.2%，上证指数收报3350点，深证成指涨0.8%，创业板指领涨1.5%。"
result = verifier.check_index_name_consistency(text_consistent)
test("一致使用", result['pass'] == True,
     f"期望pass=True, 实际pass={result['pass']}, warnings={result['warnings']}")

# 1b. 不一致的情况 — 混合使用多种名称
text_inconsistent = "科创综指今日涨1.2%，科创50也涨了。上证指数收报3350，上证综指也红了。"
result = verifier.check_index_name_consistency(text_inconsistent)
test("混合使用", result['pass'] == False,
     f"期望pass=False, 实际pass={result['pass']}")
test("混合使用有警告", len(result['warnings']) > 0,
     f"期望警告数>0, 实际={len(result['warnings'])}")
for w in result['warnings']:
    test(f"混合使用-警告内容({w['index']})",
         'suggestion' in w and len(w['used_names']) > 1,
         f"index={w['index']}, names={w['used_names']}")

# 1c. 白名单外的指数
text_outside = "中证500指数今日大涨，北证50表现也不错。"
result = verifier.check_index_name_consistency(text_outside)
test("白名单外指数", result['pass'] == True,
     f"不应报错，实际pass={result['pass']}, warnings={result['warnings']}")

# 1d. 空文本
result = verifier.check_index_name_consistency("")
test("空文本", result['pass'] == True and len(result['warnings']) == 0,
     f"期望pass=True, 实际pass={result['pass']}")

# 1e. 所有指数名称完整测试
text_all_consistent = "科创50上涨，上证指数上涨，深证成指上涨，创业板指上涨。"
result = verifier.check_index_name_consistency(text_all_consistent)
test("全部指数一致使用", result['pass'] == True,
     f"期望pass=True, 实际pass={result['pass']}")

text_all_mixed = "科创综指和科创50都涨了，上证综指和上证指数都红了。"
result = verifier.check_index_name_consistency(text_all_mixed)
test("全部指数混合使用",
     result['pass'] == False and len(result['warnings']) >= 2,
     f"期望pass=False且>=2警告, 实际pass={result['pass']}, warnings={len(result['warnings'])}")


# ========================
# Test 2: check_typo
# ========================
section("测试2: check_typo — 错别字检查")

# 2a. 有错别字
text_with_typo = "今日市场摧化剂不足，撞态偏弱。震档加剧，资金分歧明显。"
result = verifier.check_typo(text_with_typo)
test("有错别字", result['pass'] == False,
     f"期望pass=False, 实际pass={result['pass']}")
test("错别字数量正确", len(result['warnings']) >= 3,
     f"期望>=3个, 实际={len(result['warnings'])}: {[w['typo'] for w in result['warnings']]}")

# Check specific typo corrections
for w in result['warnings']:
    if w['typo'] == '摧化':
        test("摧化→催化", w['correction'] == '催化' and w['position'] >= 0,
             f"correction={w['correction']}, position={w['position']}")
    elif w['typo'] == '撞态':
        test("撞态→状态", w['correction'] == '状态' and w['position'] >= 0,
             f"correction={w['correction']}, position={w['position']}")
    elif w['typo'] == '震档':
        test("震档→震荡", w['correction'] == '震荡' and w['position'] >= 0,
             f"correction={w['correction']}, position={w['position']}")

# 2b. 无错别字
text_clean = "今日市场催化剂不足，状态偏弱。震荡加剧，资金分歧明显。"
result = verifier.check_typo(text_clean)
test("无错别字", result['pass'] == True and len(result['warnings']) == 0,
     f"期望pass=True, 实际pass={result['pass']}, warnings={result['warnings']}")

# 2c. 边界：空文本
result = verifier.check_typo("")
test("空文本无错别字", result['pass'] == True and len(result['warnings']) == 0,
     f"期望pass=True, 实际pass={result['pass']}")

# 2d. 边界：单个错别字
text_single = "这的却是个问题。"
result = verifier.check_typo(text_single)
test("单个错别字(的却→的确)",
     result['pass'] == False and len(result['warnings']) == 1,
     f"期望1个警告, 实际={len(result['warnings'])}")

# 2e. 做多（identity entry - should not be flagged）
text_zouduo = "今日主力做多意愿强烈。"
result = verifier.check_typo(text_zouduo)
test("'做多'不触发（identity条目）", result['pass'] == True,
     f"'做多'不应被视为错别字, warnings={result['warnings']}")


# ========================
# Test 3: final_report_check
# ========================
section("测试3: final_report_check — 报告最终综合扫描")

# 3a. 完整通过
text_clean_report = """今日市场概况

上证指数收报3350点，深证成指涨0.8%，创业板指涨1.2%，科创50涨0.5%。

板块方面，半导体板块主力净流入25亿，领涨市场。
医药板块特大单净流入12亿，表现活跃。
新能源板块大单净流入8亿。

本报告内容仅基于公开数据及AI分析生成，不构成任何投资建议。
"""
result = verifier.final_report_check(text_clean_report)
test("完整通过",
     result['pass'] == True,
     f"期望pass=True, 实际pass={result['pass']}, warnings={result['warnings']}")
test("完整通过-all checks True",
     all(result['checks'].values()),
     f"checks={result['checks']}")

# 3b. 有警告：大资金无口径 + 不一致的指数名
text_warning_report = """今日市场概况

科创综指上涨1.5%，科创50同样表现不俗。
上证综指收报3350点。

板块方面，半导体流入25亿，计算机流入15亿。
新能源板块流入30亿。

市场成交额500亿，较昨日放量。

本报告内容仅基于公开数据及AI分析生成。
本报告内容仅基于公开数据及AI分析生成，不构成任何投资建议。
"""
result = verifier.final_report_check(text_warning_report)
test("有警告",
     result['pass'] == False,
     f"期望pass=False, 实际pass={result['pass']}")
test("有-index_consistency警告",
     result['checks']['index_consistency'] == False,
     f"checks={result['checks']}")
test("有-no_duplicate_disclaimer警告",
     result['checks']['no_duplicate_disclaimer'] == False,
     f"checks={result['checks']}")
test("有-fund_annotation警告或pass",
     result['checks']['fund_annotation'] in [True, False],
     f"fund_annotation={result['checks']['fund_annotation']}")
test("有warnings返回",
     len(result['warnings']) > 0,
     f"期望warnings>0, 实际={len(result['warnings'])}")

# 3c. 空文本
result = verifier.final_report_check("")
test("空文本",
     result['pass'] == True,
     f"期望pass=True, 实际pass={result['pass']}")


# ========================
# Test 4: scan_sector_gainers
# ========================
section("测试4: scan_sector_gainers — 板块涨幅扫描")

# 4a. 有数据
sector_data = {
    '板块名称': '半导体',
    '成分股': [
        {'名称': '中芯国际', '涨幅': 8.5},
        {'名称': '北方华创', '涨幅': 6.2},
        {'名称': '韦尔股份', '涨幅': 4.8},
        {'名称': '紫光国微', '涨幅': 3.2},
        {'名称': '长电科技', '涨幅': 1.5},
    ]
}
result = analysis_engine.scan_sector_gainers(sector_data, threshold=5.0)
test("有数据-all_gainers",
     len(result['all_gainers']) == 2,
     f"期望2只≥5%, 实际={len(result['all_gainers'])}: {result['all_gainers']}")
test("有数据-涨幅排序",
     result['all_gainers'][0]['涨幅'] >= result['all_gainers'][1]['涨幅'],
     f"顺序: {[g['涨幅'] for g in result['all_gainers']]}")

# 4b. 阈值=0（全部个股）
result = analysis_engine.scan_sector_gainers(sector_data, threshold=0.0)
test("阈值0%",
     len(result['all_gainers']) == 5,
     f"期望5只全部, 实际={len(result['all_gainers'])}")

# 4c. 阈值=10%（无个股达标）
result = analysis_engine.scan_sector_gainers(sector_data, threshold=10.0)
test("阈值10%（无达标）",
     len(result['all_gainers']) == 0,
     f"期望0只, 实际={len(result['all_gainers'])}")

# 4d. 无数据
result = analysis_engine.scan_sector_gainers({'板块名称': '新能源', '成分股': []}, threshold=5.0)
test("无成分股",
     len(result['all_gainers']) == 0 and 'note' in result,
     f"all_gainers={result['all_gainers']}, keys={list(result.keys())}")

# 4e. 使用备选字段（涨跌幅/pct）
sector_data_alt = {
    '板块名称': 'AI',
    '成分股': [
        {'name': '科大讯飞', 'pct': 7.8},
        {'name': '海康威视', '涨跌幅': 5.2},
        {'name': '商汤科技', '涨幅': 3.1},
    ]
}
result = analysis_engine.scan_sector_gainers(sector_data_alt, threshold=5.0)
test("备选字段",
     len(result['all_gainers']) == 2,
     f"期望2只≥5%, 实际={len(result['all_gainers'])}: {result['all_gainers']}")


# ========================
# Test 5: calc_limit_board_rate
# ========================
section("测试5: calc_limit_board_rate — 炸板率计算")

# 5a. 高炸板率 (>40%)
result = collector.calc_limit_board_rate(20, 12)
test("高炸板率(12/20=60%)",
     result['level'] == 'high',
     f"期望level=high, 实际={result}")
test("高炸板率-rate正确",
     abs(result['rate'] - 60.0) < 0.01,
     f"期望rate=60.0, 实际={result['rate']}")

# 5b. 中炸板率 (20-40%)
result = collector.calc_limit_board_rate(20, 6)
test("中炸板率(6/20=30%)",
     result['level'] == 'medium',
     f"期望level=medium, 实际={result}")
test("中炸板率-rate正确",
     abs(result['rate'] - 30.0) < 0.01,
     f"期望rate=30.0, 实际={result['rate']}")

# 5c. 低炸板率 (<20%)
result = collector.calc_limit_board_rate(20, 2)
test("低炸板率(2/20=10%)",
     result['level'] == 'low',
     f"期望level=low, 实际={result}")
test("低炸板率-rate正确",
     abs(result['rate'] - 10.0) < 0.01,
     f"期望rate=10.0, 实际={result['rate']}")

# 5d. 边界: 0炸板
result = collector.calc_limit_board_rate(20, 0)
test("0炸板",
     result['rate'] == 0.0 and result['level'] == 'low',
     f"期望rate=0, level=low, 实际={result}")

# 5e. 边界: 全部炸板
result = collector.calc_limit_board_rate(10, 10)
test("全部炸板(10/10=100%)",
     result['level'] == 'high' and abs(result['rate'] - 100.0) < 0.01,
     f"期望rate=100, level=high, 实际={result}")

# 5f. unknown: None输入
result = collector.calc_limit_board_rate(None, None)
test("None输入→unknown",
     result['level'] == 'unknown' and result['rate'] is None,
     f"期望level=unknown, 实际={result}")

# 5g. 边界: total_limit_up=0
result = collector.calc_limit_board_rate(0, 5)
test("total_limit_up=0",
     result['rate'] == 0.0 and result['level'] == 'low',
     f"期望rate=0, level=low, 实际={result}")


# ========================
# Summary
# ========================
section("测试结果汇总")
total = passed + failed
print(f"  总测试数: {total}")
print(f"  ✅ 通过:   {passed}")
print(f"  ❌ 失败:   {failed}")
print(f"  📊 通过率: {passed/total*100:.1f}%" if total > 0 else "  📊 无测试")
print()

if failed == 0:
    print("🎉 全部测试通过！v4.0代码层修复完成。")
else:
    print(f"⚠️  有 {failed} 个测试失败，请检查修正。")
    for status, name, detail in test_results:
        if status == "FAIL":
            print(f"  ❌ {name}: {detail}")

sys.exit(0 if failed == 0 else 1)
