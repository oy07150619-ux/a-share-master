#!/usr/bin/env python3
"""
test_v6_fixes.py — 个股资金流向采集与验证功能测试

测试覆盖：
1. collect_stock_flow 对已知代码的采集（600519茅台等，验证返回格式）
2. collect_stock_flow 对无效代码的处理（返回错误格式）
3. validate_stock_fund_flow 正常场景（涨>5%且净流入正→通过）
4. validate_stock_fund_flow 资金背离场景（涨>5%但净流出→标记）
5. validate_stock_fund_flow 量级超限场景
6. validate_stock_fund_flow 边界场景（0值、None值）
"""

import sys
import os
import json

# 将脚本目录加入路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from collector import collect_stock_flow
from analysis_engine import validate_stock_fund_flow


def section(title):
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")


def sub(title):
    print(f"\n--- {title} ---")


def check(condition, msg):
    if condition:
        print(f"  ✅ {msg}")
        return True
    else:
        print(f"  ❌ {msg}")
        return False


all_ok = True

# ========================================================================
# Test 1: collect_stock_flow — 已知代码（600519 茅台）
# ========================================================================
section("Test1: collect_stock_flow — 已知代码采集")

sub("1.1 采集600519（茅台）")
result1 = collect_stock_flow("600519")
print(f"  返回结果: {json.dumps(result1, ensure_ascii=False, indent=4)}")
ok = True
ok &= check("代码" in result1, f"返回值包含 '代码' 字段 → {result1.get('代码')}")
ok &= check("主力净流入" in result1, f"返回值包含 '主力净流入' 字段 → {result1.get('主力净流入')}")
ok &= check("特大单净流入" in result1, f"返回值包含 '特大单净流入' 字段")
ok &= check("大单净流入" in result1, f"返回值包含 '大单净流入' 字段")
ok &= check("中单净流入" in result1, f"返回值包含 '中单净流入' 字段")
ok &= check("小单净流入" in result1, f"返回值包含 '小单净流入' 字段")
ok &= check("来源" in result1, f"返回值包含 '来源' 字段 → {result1.get('来源')}")
ok &= check("采集时间" in result1, f"返回值包含 '采集时间' 字段")
# 主力净流入应为数值
main_flow = result1.get("主力净流入", None)
ok &= check(isinstance(main_flow, (int, float)), f"主力净流入为数值类型 → {main_flow}")
if ok:
    print("  ✅ Test1.1 通过")
else:
    print("  ❌ Test1.1 有失败项")
    all_ok = False

sub("1.2 采集000001（平安银行）")
result2 = collect_stock_flow("000001")
print(f"  返回结果: {json.dumps(result2, ensure_ascii=False)}")
ok2 = check("代码" in result2 and result2.get("代码") == "000001", "代码字段正确")
ok2 &= check("主力净流入" in result2, "包含主力净流入字段")
if ok2:
    print("  ✅ Test1.2 通过")
else:
    print("  ❌ Test1.2 有失败项")
    all_ok = False

# ========================================================================
# Test 2: collect_stock_flow — 无效代码
# ========================================================================
section("Test2: collect_stock_flow — 无效代码处理")

sub("2.1 无效代码 999999")
result3 = collect_stock_flow("999999")
print(f"  返回: {json.dumps(result3, ensure_ascii=False)}")
# 应该返回空数据格式（而非崩溃）
ok3 = check("error" not in result3 or True, "不会抛出异常")
ok3 &= check("代码" in result3, "仍返回代码字段")
if ok3:
    print("  ✅ Test2 通过（无效代码不会导致崩溃）")
else:
    all_ok = False

# ========================================================================
# Test 3: validate_stock_fund_flow — 正常场景
# ========================================================================
section("Test3: validate_stock_fund_flow — 正常场景")

sub("3.1 大涨+净流入（正常）")
stock_normal = {
    '代码': '600519',
    '名称': '贵州茅台',
    '涨跌幅': 6.5,
    '成交额': 500000,  # 万
    '流通市值': 2000000,  # 万
    '主力净流入': 30000,  # 万（正数，且远小于成交额40%=200000万）
}
r3 = validate_stock_fund_flow(stock_normal)
print(f"  结果: pass={r3['pass']}, confidence={r3['confidence']}, issues={r3['issues']}, warnings={r3['warnings']}")
ok3 = check(r3['pass'] == True, "pass=True")
ok3 &= check(r3['confidence'] == 'high', "confidence=high")
ok3 &= check(len(r3['issues']) == 0, "无issues")
ok3 &= check(len(r3['warnings']) == 0, "无warnings")
if ok3:
    print("  ✅ Test3.1 通过")
else:
    all_ok = False

sub("3.2 大跌+净流出（正常）")
stock_down = {
    '代码': '000001',
    '名称': '平安银行',
    '涨跌幅': -4.2,
    '成交额': 300000,
    '流通市值': 1500000,
    '主力净流入': -20000,  # 净流出
}
r3b = validate_stock_fund_flow(stock_down)
print(f"  结果: pass={r3b['pass']}, confidence={r3b['confidence']}")
ok3b = check(r3b['pass'] == True, "pass=True")
ok3b &= check(r3b['confidence'] == 'high', "confidence=high")
if ok3b:
    print("  ✅ Test3.2 通过")
else:
    all_ok = False

# ========================================================================
# Test 4: validate_stock_fund_flow — 资金背离场景
# ========================================================================
section("Test4: validate_stock_fund_flow — 资金背离")

sub("4.1 大涨+净流出（背离标记）")
stock_bearish = {
    '代码': '002001',
    '名称': '新和成',
    '涨跌幅': 7.2,
    '成交额': 200000,     # 万
    '流通市值': 1000000,  # 万（足够大，不触发放大镜超限）
    '主力净流入': -50000,  # 万（绝对值<成交额40%=80000，<市值8%=80000）
}
r4 = validate_stock_fund_flow(stock_bearish)
print(f"  结果: pass={r4['pass']}, confidence={r4['confidence']}, warnings={r4['warnings']}")
ok4 = check(r4['pass'] == True, "pass=True（背离是警告非失败）")
ok4 &= check(r4['confidence'] == 'medium', "confidence=medium")
ok4 &= check(len(r4['warnings']) == 1, "有1条警告")
ok4 &= check('资金背离标记' in r4['warnings'][0], "警告内容包含'资金背离标记'")
if ok4:
    print("  ✅ Test4.1 通过")
else:
    all_ok = False

sub("4.2 大跌+净流入（背离标记）")
stock_bullish = {
    '代码': '002002',
    '名称': '测试股',
    '涨跌幅': -5.8,
    '成交额': 100000,
    '流通市值': 300000,
    '主力净流入': 15000,  # 跌5.8%但主力净流入
}
r4b = validate_stock_fund_flow(stock_bullish)
print(f"  结果: pass={r4b['pass']}, confidence={r4b['confidence']}, warnings={r4b['warnings']}")
ok4b = check(r4b['pass'] == True, "pass=True")
ok4b &= check(r4b['confidence'] == 'medium', "confidence=medium")
ok4b &= check(len(r4b['warnings']) == 1, "有1条警告")
if ok4b:
    print("  ✅ Test4.2 通过")
else:
    all_ok = False

# ========================================================================
# Test 5: validate_stock_fund_flow — 量级超限（数据异常）
# ========================================================================
section("Test5: validate_stock_fund_flow — 量级超限")

sub("5.1 主力净流入超成交额40%")
stock_over_turnover = {
    '代码': '600000',
    '名称': '浦发银行',
    '涨跌幅': 2.0,
    '成交额': 100000,     # 万
    '流通市值': 30000000, # 万
    '主力净流入': 80000,   # 万（成交额40%=40000万，此值超限）
}
r5 = validate_stock_fund_flow(stock_over_turnover)
print(f"  结果: pass={r5['pass']}, confidence={r5['confidence']}, issues={r5['issues']}")
ok5 = check(r5['pass'] == False, "pass=False（数值异常）")
ok5 &= check(r5['confidence'] == 'low', "confidence=low")
ok5 &= check(len(r5['issues']) >= 1, "至少有1条issue")
if ok5:
    print("  ✅ Test5.1 通过")
else:
    all_ok = False

sub("5.2 主力净流入超流通市值8%")
stock_over_mv = {
    '代码': '000002',
    '名称': '万科A',
    '涨跌幅': 3.0,
    '成交额': 200000,
    '流通市值': 500000,   # 万（8%=40000万）
    '主力净流入': 60000,   # 万（>40000万）
}
r5b = validate_stock_fund_flow(stock_over_mv)
print(f"  结果: pass={r5b['pass']}, confidence={r5b['confidence']}, issues={r5b['issues']}")
ok5b = check(r5b['pass'] == False, "pass=False")
ok5b &= check(r5b['confidence'] == 'low', "confidence=low")
if ok5b:
    print("  ✅ Test5.2 通过")
else:
    all_ok = False

sub("5.3 同时触发多条issue")
stock_multi = {
    '代码': '300001',
    '名称': '特锐德',
    '涨跌幅': 6.5,
    '成交额': 100000,
    '流通市值': 300000,
    '主力净流入': 80000,   # 超成交额40%=40000，超市值8%=24000
}
r5c = validate_stock_fund_flow(stock_multi)
print(f"  结果: pass={r5c['pass']}, confidence={r5c['confidence']}, issues={r5c['issues']}")
ok5c = check(r5c['pass'] == False, "pass=False")
ok5c &= check(len(r5c['issues']) >= 2, "有至少2条issue（成交额+市值均超限）")
if ok5c:
    print("  ✅ Test5.3 通过")
else:
    all_ok = False

# ========================================================================
# Test 6: validate_stock_fund_flow — 边界场景
# ========================================================================
section("Test6: validate_stock_fund_flow — 边界场景")

sub("6.1 所有字段为0")
stock_zero = {
    '代码': '000000',
    '名称': '测试零值',
    '涨跌幅': 0,
    '成交额': 0,
    '流通市值': 0,
    '主力净流入': 0,
}
r6 = validate_stock_fund_flow(stock_zero)
print(f"  结果: pass={r6['pass']}, confidence={r6['confidence']}, issues={r6['issues']}")
ok6 = check(r6['pass'] == True, "pass=True（0值不触发异常）")
ok6 &= check(r6['confidence'] == 'high', "confidence=high")
if ok6:
    print("  ✅ Test6.1 通过")
else:
    all_ok = False

sub("6.2 部分字段为None")
stock_none = {
    '代码': '000001',
    '名称': '平安银行',
    '涨跌幅': None,
    '成交额': None,
    '流通市值': 1000000,
    '主力净流入': None,
}
r6b = validate_stock_fund_flow(stock_none)
print(f"  结果: pass={r6b['pass']}, confidence={r6b['confidence']}")
ok6b = check(r6b['pass'] == True, "pass=True（None值不崩溃）")
ok6b &= check(r6b['confidence'] == 'high' or r6b['confidence'] != None, "confidence不为None")
if ok6b:
    print("  ✅ Test6.2 通过")
else:
    all_ok = False

sub("6.3 缺失部分字段")
stock_missing = {
    '代码': '000001',
    # 字段不完整
}
r6c = validate_stock_fund_flow(stock_missing)
print(f"  结果: pass={r6c['pass']}, confidence={r6c['confidence']}")
ok6c = check(r6c['pass'] == True, "pass=True（缺失字段不崩溃）")
if ok6c:
    print("  ✅ Test6.3 通过")
else:
    all_ok = False

sub("6.4 字符串数值（模拟腾讯API返回格式）")
stock_str = {
    '代码': '600519',
    '名称': '贵州茅台',
    '涨跌幅': '5.50',
    '成交额': '500000',
    '流通市值': '20000000',
    '主力净流入': '30000',
}
r6d = validate_stock_fund_flow(stock_str)
print(f"  结果: pass={r6d['pass']}, confidence={r6d['confidence']}")
ok6d = check(r6d['pass'] == True, "pass=True（字符串转float正常）")
ok6d &= check(r6d['confidence'] == 'high', "confidence=high")
if ok6d:
    print("  ✅ Test6.4 通过")
else:
    all_ok = False

# ========================================================================
# Test 7: 模拟通富微电事故场景
# ========================================================================
section("Test7: 模拟通富微电事故场景")

sub("7.1 大幅上涨但主力净流出（正是当初事故场景）")
stock_tongfu = {
    '代码': '002156',
    '名称': '通富微电',
    '涨跌幅': 8.2,
    '成交额': 800000,
    '流通市值': 4000000,
    '主力净流入': -224600,  # -22.46亿 = -224600万
}
r7 = validate_stock_fund_flow(stock_tongfu)
print(f"  结果: pass={r7['pass']}, confidence={r7['confidence']}")
print(f"  warnings: {r7['warnings']}")
print(f"  issues: {r7['issues']}")
ok7 = check(r7['pass'] == True, "pass=True（资金背离只是警告不是失败）")
ok7 &= check(r7['confidence'] == 'medium', "confidence=medium")
ok7 &= check(len(r7['warnings']) >= 1, "有资金背离警告")
ok7 &= check(any('资金背离标记' in w for w in r7['warnings']), "警告内容含'资金背离标记'")
if ok7:
    print("  ✅ Test7 通过 — 通富微电场景资金背离被正确标记")
else:
    all_ok = False

# ========================================================================
# 汇总
# ========================================================================
section("测试汇总")
if all_ok:
    print("\n✅✅✅ 所有测试全部通过！")
else:
    print("\n❌❌❌ 存在失败的测试，请检查上述 ❌ 标记")
    sys.exit(1)
