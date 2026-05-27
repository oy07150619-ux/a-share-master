#!/usr/bin/env python3
"""
V2修复测试验证脚本
==================
测试范围：
1. save_report_snapshot → 保存和读取测试
2. check_cross_report_consistency → 数据一致/不一致场景
3. check_sector_concentration → 个股行情/正常板块场景
4. check_data_source → 白名单/黑名单/未知来源
5. check_html_syntax → 正确HTML/错误HTML
6. morning CSS 存在性检查
"""

import sys
import os
import json
import tempfile
import shutil

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'scripts'))

# ========================================================================
# 测试1: analysis_engine.py - save_report_snapshot
# ========================================================================
def test_save_report_snapshot():
    print("=" * 60)
    print("测试1: save_report_snapshot")
    print("=" * 60)

    from analysis_engine import save_report_snapshot

    # Create temp directory for testing
    original_memory = os.path.join(PROJECT_ROOT, 'memory')
    os.makedirs(original_memory, exist_ok=True)

    # Test data
    data = {
        'indexes': [
            {'指数': '上证指数', '最新': 3350.12},
            {'指数': '科创50', '最新': 1020.56},
        ],
        'limits': {'涨停': 25, '跌停': 3},
        'sector_flow': {
            '涨幅榜': [
                {'板块名称': '半导体', '主力净流入': 1500000000, '涨跌幅': 3.5},
                {'板块名称': '人工智能', '主力净流入': 800000000, '涨跌幅': 2.8},
                {'板块名称': '新能源', '主力净流入': 500000000, '涨跌幅': 2.1},
            ]
        },
    }

    # Save snapshot
    result = save_report_snapshot('morning', data, '申万一级')
    print(f"  snapshot result: {json.dumps(result, ensure_ascii=False)}")

    # Verify key fields
    assert result['report_type'] == 'morning', f"Expected 'morning', got {result['report_type']}"
    assert result['data_scope'] == '申万一级', f"Expected '申万一级', got {result['data_scope']}"
    assert result['key_indicators']['sh_index'] == 3350.12, f"sh_index mismatch"
    assert result['key_indicators']['sci50_index'] == 1020.56, f"sci50_index mismatch"
    assert result['key_indicators']['limit_up_count'] == 25, f"limit_up_count mismatch"
    assert len(result['key_indicators']['sector_top3']) == 3, f"Expected 3 sectors, got {len(result['key_indicators']['sector_top3'])}"

    # Verify file was created
    snapshot_file = os.path.join(original_memory, 'report_snapshot.json')
    assert os.path.exists(snapshot_file), f"Snapshot file not found: {snapshot_file}"

    with open(snapshot_file, 'r', encoding='utf-8') as f:
        file_content = json.load(f)
    assert 'morning' in file_content['snapshots'], "Snapshot key 'morning' not found"
    assert file_content['snapshots']['morning']['report_type'] == 'morning'

    print("  ✅ save_report_snapshot 测试通过")
    return True


# ========================================================================
# 测试2: check_cross_report_consistency
# ========================================================================
def test_check_cross_report_consistency():
    print("\n" + "=" * 60)
    print("测试2: check_cross_report_consistency")
    print("=" * 60)

    from analysis_engine import check_cross_report_consistency

    # Test 1: Consistent data (should pass)
    print("\n  --- 场景1: 数据一致 ---")
    snapshot = {
        'key_indicators': {
            'sh_index': 3350.12,
            'limit_up_count': 25,
            'sector_top3': [
                {'name': '半导体', 'flow': 1500000000, 'scope': '申万一级'},
            ]
        }
    }
    new_data = {
        'indexes': [{'指数': '上证指数', '最新': 3355.50}],
        'limits': {'涨停': 25},
        'sector_flow': {
            '涨幅榜': [{'板块名称': '半导体', '主力净流入': 1600000000}]
        }
    }
    result = check_cross_report_consistency(new_data, snapshot, report_type='morning')
    print(f"  warnings: {result['warnings']}")
    print(f"  passes: {result['passes']}")
    # Consistent scenario: sh_index diff 0.16% (<1%), limit_up 25 same, sector flow diff 6.67% (<20%)
    # So 0 warnings is correct
    assert len(result['warnings']) == 0, f"Expected 0 warnings for consistent data, got {len(result['warnings'])}: {result['warnings']}"
    print("  ✅ 一致场景测试通过")

    # Test 2: Inconsistent data (should trigger warnings)
    print("\n  --- 场景2: 数据不一致 ---")
    snapshot2 = {
        'key_indicators': {
            'sh_index': 3300.00,
            'limit_up_count': 10,
            'sector_top3': [
                {'name': '银行', 'flow': 1000000000, 'scope': '申万一级'},
            ]
        }
    }
    new_data2 = {
        'indexes': [{'指数': '上证指数', '最新': 3400.00}],
        'limits': {'涨停': 30},
        'sector_flow': {
            '涨幅榜': [{'板块名称': '半导体', '主力净流入': 200000000}]
        }
    }
    result2 = check_cross_report_consistency(new_data2, snapshot2, report_type='morning')
    print(f"  warnings: {result2['warnings']}")
    print(f"  passes: {result2['passes']}")
    # sh_index: 3400 vs 3300 => diff = 100/3300 = 3.03% > 1% => warning
    # limit_up_count: 30 vs 10 => diff > 0 => warning
    # sector_top3[0]: flow 100M vs 200M => diff = 100% > 20% => warning
    assert len(result2['warnings']) >= 2, f"Expected >=2 warnings, got {len(result2['warnings'])}"
    print("  ✅ 不一致场景测试通过")

    # Test 3: Empty snapshot (no history)
    print("\n  --- 场景3: 无历史快照 ---")
    result3 = check_cross_report_consistency(new_data, {}, report_type='morning')
    assert len(result3['passes']) == 1 and '无历史快照' in result3['passes'][0]
    print("  ✅ 无历史快照测试通过")

    print("  ✅ check_cross_report_consistency 测试通过")
    return True


# ========================================================================
# 测试3: check_sector_concentration
# ========================================================================
def test_check_sector_concentration():
    print("\n" + "=" * 60)
    print("测试3: check_sector_concentration")
    print("=" * 60)

    from analysis_engine import check_sector_concentration

    # Test 1: high warning - <1亿 flow, >3% pct
    print("\n  --- 场景1: high warning ---")
    result = check_sector_concentration(4.5, 50000000, '概念板块A')
    print(f"  result: {json.dumps(result, ensure_ascii=False)}")
    assert result['warning_level'] == 'high', f"Expected 'high', got {result['warning_level']}"
    assert result['is_concentrated'] == True
    print("  ✅")

    # Test 2: medium warning - <3亿 flow, >5% pct
    print("\n  --- 场景2: medium warning ---")
    result = check_sector_concentration(6.0, 200000000, '概念板块B')
    print(f"  result: {json.dumps(result, ensure_ascii=False)}")
    assert result['warning_level'] == 'medium', f"Expected 'medium', got {result['warning_level']}"
    assert result['is_concentrated'] == True
    print("  ✅")

    # Test 3: none - normal scenario
    print("\n  --- 场景3: 正常板块 ---")
    result = check_sector_concentration(2.0, 500000000, '半导体')
    print(f"  result: {json.dumps(result, ensure_ascii=False)}")
    assert result['warning_level'] == 'none', f"Expected 'none', got {result['warning_level']}"
    assert result['is_concentrated'] == False
    print("  ✅")

    # Test 4: edge case - big flow, big pct
    print("\n  --- 场景4: 大资金大涨幅 ---")
    result = check_sector_concentration(7.0, 800000000, 'AI板块')
    print(f"  result: {json.dumps(result, ensure_ascii=False)}")
    assert result['warning_level'] == 'none', f"Expected 'none', got {result['warning_level']}"
    print("  ✅")

    # Test 5: None values
    print("\n  --- 场景5: None值 ---")
    result = check_sector_concentration(None, None, '测试')
    print(f"  result: {json.dumps(result, ensure_ascii=False)}")
    assert result['warning_level'] == 'none', f"Expected 'none', got {result['warning_level']}"
    print("  ✅")

    print("  ✅ check_sector_concentration 测试通过")
    return True


# ========================================================================
# 测试4: check_data_source
# ========================================================================
def test_check_data_source():
    print("\n" + "=" * 60)
    print("测试4: check_data_source")
    print("=" * 60)

    from verifier import check_data_source

    # Test 1: Allowed sources
    print("\n  --- 场景1: 白名单来源 ---")
    text = """
    上证指数今日上涨0.5%（来源：东方财富）
    科创50上涨2.1%（来源：同花顺）
    北向资金净买入（来源：新华社）
    """
    result = check_data_source(text)
    print(f"  pass={result['pass']}, warnings={len(result['warnings'])}")
    assert result['pass'] == True
    for w in result['warnings']:
        assert w['verdict'] == 'allowed', f"Expected 'allowed', got {w['verdict']} for {w['source']}"
    print("  ✅")

    # Test 2: Banned sources
    print("\n  --- 场景2: 黑名单来源 ---")
    text2 = """
    有传闻称公司将重组（来源：知乎）
    据内部人士透露（来源：微博）
    """
    result2 = check_data_source(text2)
    print(f"  pass={result2['pass']}, warnings={len(result2['warnings'])}")
    assert result2['pass'] == False
    has_banned = any(w['verdict'] == 'banned' for w in result2['warnings'])
    assert has_banned, "Expected at least one banned source"
    print("  ✅")

    # Test 3: Unknown sources
    print("\n  --- 场景3: 未知来源 ---")
    text3 = """
    据消息人士分析（来源：某内部报告）
    数据显示（来源：未知公众号）
    """
    result3 = check_data_source(text3)
    print(f"  pass={result3['pass']}, warnings={len(result3['warnings'])}")
    assert result3['pass'] == True  # unknown is not banned, so pass
    has_unknown = any(w['verdict'] == 'unknown' for w in result3['warnings'])
    assert has_unknown, "Expected at least one unknown source"
    print("  ✅")

    # Test 4: Mixed sources
    print("\n  --- 场景4: 混合来源 ---")
    text4 = """
    上证指数走势（来源：东方财富）
    市场情绪分析（来源：知乎）
    板块资金流向（来源：同花顺）
    """
    result4 = check_data_source(text4)
    print(f"  pass={result4['pass']}, warnings={len(result4['warnings'])}")
    assert result4['pass'] == False  # has banned source
    verdicts = [(w['source'], w['verdict']) for w in result4['warnings']]
    print(f"  verdicts: {verdicts}")
    assert ('知乎', 'banned') in verdicts, "Expected banned verdict for 知乎"
    allowed_count = sum(1 for v in verdicts if v[1] == 'allowed')
    assert allowed_count >= 2, f"Expected >=2 allowed sources, got {allowed_count}"
    print("  ✅")

    # Test 5: No sources
    print("\n  --- 场景5: 无来源标记 ---")
    text5 = "今日市场表现良好，各大指数普遍上涨。"
    result5 = check_data_source(text5)
    print(f"  pass={result5['pass']}, warnings={len(result5['warnings'])}")
    assert result5['pass'] == True
    assert len(result5['warnings']) == 0
    print("  ✅")

    print("  ✅ check_data_source 测试通过")
    return True


# ========================================================================
# 测试5: check_html_syntax
# ========================================================================
def test_check_html_syntax():
    print("\n" + "=" * 60)
    print("测试5: check_html_syntax")
    print("=" * 60)

    from verifier import check_html_syntax

    # Test 1: Valid HTML
    print("\n  --- 场景1: 正确HTML ---")
    html = """
    <div class="content">
        <table>
            <thead><tr><th>名称</th><th>涨幅</th></tr></thead>
            <tbody>
                <tr><td>上证指数</td><td>+0.5%</td></tr>
                <tr><td>深证成指</td><td>+1.2%</td></tr>
            </tbody>
        </table>
        <p>结束</p>
    </div>
    """
    result = check_html_syntax(html)
    print(f"  pass={result['pass']}, errors={len(result['errors'])}")
    assert result['pass'] == True, f"Expected pass=True, got errors: {result['errors']}"
    print("  ✅")

    # Test 2: Unclosed table
    print("\n  --- 场景2: 未闭合table ---")
    html2 = """
    <div>
        <table>
            <tr><td>数据</td></tr>
        </div>
    """
    result2 = check_html_syntax(html2)
    print(f"  pass={result2['pass']}, errors={result2['errors']}")
    assert result2['pass'] == False, "Expected pass=False for unclosed table"
    has_table_error = any('table' in e['msg'] for e in result2['errors'])
    assert has_table_error, "Expected table count mismatch error"
    print("  ✅")

    # Test 3: Unclosed tr
    print("\n  --- 场景3: 未闭合tr ---")
    html3 = """
    <table>
        <tr><td>数据1</td></tr>
        <tr><td>数据2</td>
    </table>
    """
    result3 = check_html_syntax(html3)
    print(f"  pass={result3['pass']}, errors={result3['errors']}")
    assert result3['pass'] == False
    has_tr_error = any('tr' in e['msg'] for e in result3['errors'])
    assert has_tr_error, "Expected tr count mismatch error"
    print("  ✅")

    # Test 4: Unclosed td
    print("\n  --- 场景4: 未闭合td ---")
    html4 = """
    <table>
        <tr><td>数据1</td><td>数据2</td></tr>
        <tr><td>数据3</tr>
    </table>
    """
    result4 = check_html_syntax(html4)
    print(f"  pass={result4['pass']}, errors={result4['errors']}")
    assert result4['pass'] == False
    has_td_error = any('td' in e['msg'] for e in result4['errors'])
    assert has_td_error, "Expected td count mismatch error"
    print("  ✅")

    # Test 5: Balanced but malformed
    print("\n  --- 场景5: 复杂完全闭合 ---")
    html5 = """
    <div class="slide">
        <div class="slide-title">标题</div>
        <table class="data-table">
            <thead><tr><th>列1</th><th>列2</th></tr></thead>
            <tbody><tr><td>值1</td><td>值2</td></tr></tbody>
        </table>
        <div class="footer">页脚</div>
    </div>
    <br/><hr/>
    <img src="test.jpg"/>
    """
    result5 = check_html_syntax(html5)
    print(f"  pass={result5['pass']}, errors={len(result5['errors'])}")
    assert result5['pass'] == True, f"Expected pass=True for balanced HTML, got: {result5['errors']}"
    print("  ✅")

    print("  ✅ check_html_syntax 测试通过")
    return True


# ========================================================================
# 测试6: morning CSS 存在性检查
# ========================================================================
def test_morning_css_exists():
    print("\n" + "=" * 60)
    print("测试6: morning CSS 存在性检查")
    print("=" * 60)

    template_path = os.path.join(PROJECT_ROOT, 'templates', 'report_template.html')
    assert os.path.exists(template_path), f"Template not found: {template_path}"

    with open(template_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check morning-table CSS
    assert '.morning-table' in content, "Missing .morning-table CSS"
    assert '.morning-section-title' in content, "Missing .morning-section-title CSS"
    assert '.morning-footer-gap' in content, "Missing .morning-footer-gap CSS"
    assert 'morning-table th' in content, "Missing morning-table th CSS"
    assert 'morning-table td' in content, "Missing morning-table td CSS"

    print("  ✅ morning CSS 全部存在")

    # Check morning table standard structure
    assert 'table-layout: fixed' in content, "Missing table-layout: fixed"
    assert 'position: sticky' in content, "Missing position: sticky for th"
    print("  ✅ morning table 标准结构CSS存在")

    print("  ✅ morning CSS 存在性检查通过")
    return True


# ========================================================================
# 测试7: html_ppt morning 逻辑
# ========================================================================
def test_html_ppt_morning_generate():
    print("\n" + "=" * 60)
    print("测试7: html_ppt morning generate 逻辑")
    print("=" * 60)

    # We'll test that the generate function handles morning type
    # by checking that morning- prefix classes are added
    from html_ppt import _add_morning_prefix, _build_slide

    # Create test slides
    slides = [
        _build_slide("测试标题", ['<p class="slide-text">测试内容</p>'], icon="📊"),
        _build_slide("数据表格", ['<table class="data-table"><tr><td>数据</td></tr></table>'], icon="📈"),
    ]

    # Apply morning prefix
    morning_slides = _add_morning_prefix(slides)

    # Check that class names were replaced
    import re as _re
    summary_html = "\n".join(morning_slides)
    assert 'morning-section-title' in summary_html, "Missing morning-section-title"
    assert 'morning-slide-text' in summary_html, "Missing morning-slide-text"
    assert 'morning-table' in summary_html, "Missing morning-table"
    # Use regex to ensure the original class name is gone as a standalone class
    assert not _re.search(r'class="slide-text[\s"]', summary_html), "slide-text should be replaced (fully)"
    assert not _re.search(r'class="data-table[\s"]', summary_html), "data-table should be replaced (fully)"

    print("  ✅ morning- 前缀类名替换正确")

    # Test that morning-footer-gap is appended
    assert '<div class="morning-footer-gap">' not in summary_html, "footer-gap should NOT be in slides directly"

    print("  ✅ html_ppt morning 逻辑测试通过")
    return True


# ========================================================================
# 主函数
# ========================================================================
def main():
    print("=" * 60)
    print("  A股早盘报告 V2 修复测试验证")
    print(f"  时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    results = []
    tests = [
        ("save_report_snapshot", test_save_report_snapshot),
        ("check_cross_report_consistency", test_check_cross_report_consistency),
        ("check_sector_concentration", test_check_sector_concentration),
        ("check_data_source", test_check_data_source),
        ("check_html_syntax", test_check_html_syntax),
        ("morning CSS 存在性检查", test_morning_css_exists),
        ("html_ppt morning 日志", test_html_ppt_morning_generate),
    ]

    all_pass = True
    for name, test_fn in tests:
        try:
            test_fn()
            results.append((name, "✅ 通过"))
        except Exception as e:
            import traceback
            print(f"\n  ❌ 测试失败: {name}")
            print(f"  错误: {e}")
            traceback.print_exc()
            results.append((name, f"❌ 失败: {e}"))
            all_pass = False

    # Summary
    print("\n" + "=" * 60)
    print("  测试汇总")
    print("=" * 60)
    for name, status in results:
        print(f"  {name:40s} {status}")

    print("\n" + "=" * 60)
    if all_pass:
        print("  🎉 全部测试通过！")
    else:
        failed = [name for name, s in results if '失败' in s or '❌' in s]
        print(f"  ❌ {len(failed)} 个测试未通过: {', '.join(failed)}")

    print("=" * 60)
    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())
