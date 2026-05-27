#!/usr/bin/env python3
"""
复盘报告v3代码层修复 — 测试脚本
==================================
测试覆盖：
1. classify_market_divergence — 极端撕裂/虚假修复/正常场景
2. check_volume_qualitative — 放量下跌/缩量上涨/量平价升
3. check_intra_report_consistency — 数据一致/数据矛盾场景
4. check_close_position — 上/中/下1/3各场景

用法:
  python scripts/test_v3_fixes.py
"""

import sys
import os

# 将 scripts 目录加入路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analysis_engine import classify_market_divergence, check_volume_qualitative
from verifier import check_intra_report_consistency, check_close_position


# ========================================================================
# 测试套件
# ========================================================================

pass_count = 0
fail_count = 0


def test(name, func, expected_keys=None, check_fn=None):
    """通用测试 runner"""
    global pass_count, fail_count
    try:
        result = func
        prefix = f"  ✗ [{name}]"
        ok = False

        if expected_keys:
            # 检查返回的 key 集合
            if isinstance(expected_keys, dict):
                # 精确匹配多字段
                ok = all(
                    result.get(k) == v for k, v in expected_keys.items()
                )
            elif isinstance(expected_keys, (list, tuple)):
                ok = all(k in result for k in expected_keys)
            else:
                ok = result == expected_keys

        if check_fn and callable(check_fn):
            ok = check_fn(result)

        if ok:
            print(f"  ✓ [{name}] PASS")
            pass_count += 1
        else:
            print(f"  ✗ [{name}] FAIL — got={result}")
            fail_count += 1
    except Exception as e:
        print(f"  ✗ [{name}] EXCEPTION — {e}")
        fail_count += 1


def test_classify_market_divergence():
    print("\n" + "=" * 60)
    print("1. classify_market_divergence — 市场极端撕裂行情判断")
    print("=" * 60)

    # --- 场景1: 极端撕裂 ---
    # 涨跌比<30%且涨停>跌停
    r = classify_market_divergence(up_ratio=0.245, limit_up=35, limit_down=12, index_changed=-0.17)
    test("极端撕裂-涨跌比低+涨停居多",
         r,
         expected_keys={'verdict': 'extreme_divergence', 'level': 'high'})

    # --- 场景2: 虚假修复 ---
    # 指数涨>0但涨跌比<30%
    r = classify_market_divergence(up_ratio=0.18, limit_up=15, limit_down=22, index_changed=0.35)
    test("虚假修复-指数红但涨跌比<30%",
         r,
         expected_keys={'verdict': 'fake_recovery', 'level': 'high'})

    # --- 场景3: 正常偏多 ---
    r = classify_market_divergence(up_ratio=0.65, limit_up=48, limit_down=10, index_changed=1.2)
    test("正常偏多-上涨占优",
         r,
         expected_keys={'verdict': 'normal_bull', 'level': 'medium'})

    # --- 场景4: 正常偏空 ---
    r = classify_market_divergence(up_ratio=0.22, limit_up=5, limit_down=8, index_changed=-0.8)
    test("正常偏空-涨跌比<30%+跌停不多",
         r,
         expected_keys={'verdict': 'normal_bear', 'level': 'medium'})

    # --- 场景5: 正常市场 ---
    r = classify_market_divergence(up_ratio=0.45, limit_up=20, limit_down=15, index_changed=0.0)
    test("正常市场-涨跌比适中",
         r,
         expected_keys={'verdict': 'normal', 'level': 'none'})

    # --- 场景6: 极端撕裂边界条件 ---
    r = classify_market_divergence(up_ratio=0.299, limit_up=18, limit_down=12, index_changed=-0.5)
    test("极端撕裂-边界条件-涨跌比29.9%",
         r,
         expected_keys={'verdict': 'extreme_divergence', 'level': 'high'})

    # --- 场景7: 虚假修复边界条件 ---
    r = classify_market_divergence(up_ratio=0.299, limit_up=10, limit_down=18, index_changed=0.1)
    test("虚假修复-边界-指数微涨+涨跌比29.9%",
         r,
         expected_keys={'verdict': 'fake_recovery', 'level': 'high'})


def test_check_volume_qualitative():
    print("\n" + "=" * 60)
    print("2. check_volume_qualitative — 量能定性一致性校验")
    print("=" * 60)

    # --- 场景A: 放量上涨 ---
    r = check_volume_qualitative(volume_change_pct=1.2, index_change_pct=0.85)
    test("放量上涨-成交额增+指数涨",
         r,
         expected_keys={'expected': '放量上涨'})

    # --- 场景B: 放量下跌 ---
    r = check_volume_qualitative(volume_change_pct=2.5, index_change_pct=-1.2)
    test("放量下跌-成交额增+指数跌",
         r,
         expected_keys={'expected': '放量下跌'})

    # --- 场景C: 缩量上涨 ---
    r = check_volume_qualitative(volume_change_pct=-0.8, index_change_pct=0.5)
    test("缩量上涨-成交额减+指数涨",
         r,
         expected_keys={'expected': '缩量上涨'})

    # --- 场景D: 缩量下跌 ---
    r = check_volume_qualitative(volume_change_pct=-1.5, index_change_pct=-0.7)
    test("缩量下跌-成交额减+指数跌",
         r,
         expected_keys={'expected': '缩量下跌'})

    # --- 场景E: 量平价升 ---
    r = check_volume_qualitative(volume_change_pct=0.03, index_change_pct=0.2)
    test("量平价升-成交额微增+指数涨",
         r,
         expected_keys={'expected': '量平价升/跌'})

    # --- 场景F: 量平价跌 ---
    r = check_volume_qualitative(volume_change_pct=-0.02, index_change_pct=-0.3)
    test("量平价跌-成交额微减+指数跌",
         r,
         expected_keys={'expected': '量平价升/跌'})

    # --- 场景G: 边界逼近零 ---
    r = check_volume_qualitative(volume_change_pct=0.0, index_change_pct=0.0)
    test("量平价升-双零",
         r,
         expected_keys={'expected': '量平价升/跌'})

    # --- 验证 verify_rule 字段 ---
    r = check_volume_qualitative(volume_change_pct=1.2, index_change_pct=0.85)
    test("verify_rule存在且含铁律7字样",
         r,
         check_fn=lambda x: 'verify_rule' in x and '铁律7' in x['verify_rule'])

    # --- 验证 check_passed 初始为 False ---
    r = check_volume_qualitative(volume_change_pct=1.2, index_change_pct=0.85)
    test("check_passed初始为False",
         r,
         check_fn=lambda x: x.get('check_passed') is False)


def test_check_intra_report_consistency():
    print("\n" + "=" * 60)
    print("3. check_intra_report_consistency — 报告内部数据一致性")
    print("=" * 60)

    # --- 场景A: 数据一致（无矛盾） ---
    # 注意：不同主体使用不同措辞，避免实体名撞车
    text_consistent = """
【大盘综述】上证指数收于3360点，涨0.85%。市场成交额374亿，较昨日略有放大。
【板块热点】半导体净流入25亿，涨幅居前。新能源板块活跃，板块流入45亿。
【涨停分析】今日涨停35家，跌停12家，市场情绪中性偏多。
"""
    r = check_intra_report_consistency(text_consistent)
    test("数据一致-无矛盾",
         r,
         expected_keys={'pass': True})

    # --- 场景B: 数据矛盾（同一主体不同值） ---
    text_conflict = """
【大盘综述】上证指数收于3360点，今日成交374亿。
【板块热点】半导体流入25亿，涨幅居前。
【资金统计】半导体流出45亿，需警惕回调风险。
"""
    r = check_intra_report_consistency(text_conflict)
    test("数据矛盾-半导体有25亿和45亿两个值",
         r,
         expected_keys={'pass': False})

    # --- 场景C: 多个矛盾 ---
    text_multi_conflict = """
【涨停统计】今日涨停35家，跌停12家。
【封板率】实际涨停25家，封板率约71%。
"""
    r = check_intra_report_consistency(text_multi_conflict)
    test("数据矛盾-涨停有35家和25家",
         r,
         expected_keys={'pass': False})

    # --- 场景D: 空文本 ---
    r = check_intra_report_consistency("")
    test("空文本",
         r,
         expected_keys={'pass': True})

    # --- 场景E: 无数字文本 ---
    r = check_intra_report_consistency("今天市场表现不错，个股普涨。")
    test("无数字文本",
         r,
         expected_keys={'pass': True})

    # --- 场景F: 验证warnings结构 ---
    r = check_intra_report_consistency(text_conflict)
    test("矛盾场景-返回值含warnings字段",
         r,
         check_fn=lambda x: 'warnings' in x and len(x['warnings']) > 0)

    r = check_intra_report_consistency(text_conflict)
    test("矛盾场景-warnings含field/values/positions",
         r,
         check_fn=lambda x: all(
             'field' in w and 'values' in w and 'positions' in w
             for w in x['warnings']
         ))


def test_check_close_position():
    print("\n" + "=" * 60)
    print("4. check_close_position — 收盘价在支撑压力区间位置")
    print("=" * 60)

    # --- 上1/3: 收盘价靠近压力位（≥2/3位置） ---
    # (84-70)/(90-70) = 14/20 = 0.7 >= 2/3 ✓
    r = check_close_position(close_price=84, support=70, resist=90)
    test("上1/3-收盘84支撑70压力90",
         r,
         expected_keys={'position': 'upper_third', 'suggestion': '偏强，倾向压力位测试'})

    # --- 上1/3边界: 刚好2/3位置 ---
    # (83.34-70)/(90-70) = 13.34/20 = 0.667 >= 2/3(0.6666...) ✓
    r = check_close_position(close_price=83.34, support=70, resist=90)
    test("上1/3-边界-刚好2/3位置-ratio=0.667",
         r,
         expected_keys={'position': 'upper_third'})

    # --- 中1/3: 收盘价在中间 ---
    r = check_close_position(close_price=80, support=70, resist=90)
    test("中1/3-收盘80支撑70压力90",
         r,
         expected_keys={'position': 'middle_third', 'suggestion': '方向不明，等待次日确认'})

    # --- 下1/3: 收盘价靠近支撑位 ---
    r = check_close_position(close_price=72, support=70, resist=90)
    test("下1/3-收盘72支撑70压力90",
         r,
         expected_keys={'position': 'lower_third', 'suggestion': '偏弱，倾向支撑位测试'})

    # --- 下1/3边界: 刚好1/3位置 ---
    r = check_close_position(close_price=76.666, support=70, resist=90)
    test("下1/3-边界-刚好1/3位置-ratio=0.3333",
         r,
         expected_keys={'position': 'lower_third'})

    # --- 超出压力位 ---
    r = check_close_position(close_price=95, support=70, resist=90)
    test("超出压力位-收盘95支撑70压力90",
         r,
         expected_keys={'position': 'upper_third'})

    # --- 低于支撑位 ---
    r = check_close_position(close_price=65, support=70, resist=90)
    test("低于支撑位-收盘65支撑70压力90",
         r,
         expected_keys={'position': 'lower_third'})

    # --- 支撑压力反转 ---
    r = check_close_position(close_price=80, support=90, resist=70)
    test("支撑压力反转-支撑>压力",
         r,
         check_fn=lambda x: x.get('suggestion', '').startswith('支撑压力位异常'))

    # --- ratio值验证 ---
    r = check_close_position(close_price=80, support=70, resist=90)
    test("ratio值验证-中点=0.5",
         r,
         check_fn=lambda x: abs(x.get('ratio', 0) - 0.5) < 0.001)


# ========================================================================
# 主入口
# ========================================================================

def main():
    print("=" * 60)
    print("  复盘报告v3代码层修复 — 测试脚本")
    print("  " + "=" * 50)
    print(f"  开始时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    test_classify_market_divergence()
    test_check_volume_qualitative()
    test_check_intra_report_consistency()
    test_check_close_position()

    print("\n" + "=" * 60)
    print(f"  测试汇总")
    print("=" * 60)
    total = pass_count + fail_count
    print(f"  总用例: {total}")
    print(f"  通过:    {pass_count}")
    print(f"  失败:    {fail_count}")
    print(f"  通过率:  {pass_count / total * 100:.1f}%" if total > 0 else "  N/A")
    print("=" * 60)

    return 0 if fail_count == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
