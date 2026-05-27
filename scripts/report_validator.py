#!/usr/bin/env python3
"""
A股报告后置校验器 v1.0
在邮件发送前执行，检查报告内容中的常见错误：
- 日期格式异常（如"5月127日"）
- 涨跌幅逻辑矛盾
- 数据重复堆砌
- 中英文混排问题
- 数字格式规范

用法: python3 report_validator.py <报告HTML文件路径>
返回0=通过, 1=需人工检查, 2=存在严重错误
"""

import sys
import re
import os


PASS = 0
WARN = 1
FAIL = 2


def check_date_format(text):
    """检查日期格式是否异常"""
    issues = []
    # 检查"5月127日" 这种三位数日期
    bad_dates = re.findall(r'(\d+)月(\d{3,})日', text)
    for month, day in bad_dates:
        issues.append((FAIL, f"日期异常: {month}月{day}日 (日期超过31天)"))
    
    # 检查同一天内的日期矛盾
    # 查找"5月26日（周二）"格式
    date_weekday = re.findall(r'(\d+)月(\d+)日[（(]周[一二三四五六日][）)]', text)
    
    # 检查"2026年5月127日"格式
    bad_full_dates = re.findall(r'2026年\d+月\d{3,}日', text)
    for d in bad_full_dates:
        issues.append((FAIL, f"完整日期异常: {d}"))
    
    return issues


def check_profit_loss_contradiction(text):
    """检查涨跌幅描述是否自相矛盾"""
    issues = []
    
    # "高开低走" + "+X%" 矛盾检测
    high_open_low = re.findall(r'(高开低走|冲高回落).*?([+-]\d+\.?\d*%)', text)
    for trend, pct in high_open_low:
        pct_num = float(pct.replace('%', '').replace('+', ''))
        if pct_num > 0.5:
            issues.append((WARN, f"涨跌矛盾: '{trend}' 但标注涨幅 {pct}"))
        elif pct_num < -0.5:
            issues.append((WARN, f"涨跌可能合理: '{trend}' + 跌幅 {pct}"))
    
    # "低开高走" + "-X%" 矛盾检测
    low_open_high = re.findall(r'(低开高走|探底回升).*?([+-]\d+\.?\d*%)', text)
    for trend, pct in low_open_high:
        pct_num = float(pct.replace('%', '').replace('+', ''))
        if pct_num < -0.5:
            issues.append((WARN, f"涨跌矛盾: '{trend}' 但标注跌幅 {pct}"))
    
    return issues


def check_garbled_text(text):
    """检查是否存在文字拼接/乱码"""
    issues = []
    
    # 检查重复段落（连续两段一模一样）
    paragraphs = re.split(r'\n\s*\n', text)
    seen = {}
    for i, p in enumerate(paragraphs):
        p_clean = p.strip()
        if len(p_clean) > 20:
            if p_clean in seen:
                issues.append((WARN, f"段落重复: 第{seen[p_clean]+1}段和第{i+1}段内容相同"))
            else:
                seen[p_clean] = i
    
    # 检查无空格英文拼接（中英文混排问题）
    bad_eng = re.findall(r'[a-z]+[A-Z]', text)
    if len(bad_eng) > 3:
        issues.append((WARN, f"中英文混排问题: 发现{len(bad_eng)}处驼峰式拼接"))
    
    # 检查残缺句子（以标点结尾的极短段落）
    short_sentences = re.findall(r'^[^。！？\n]{2,15}[。！？]$', text, re.MULTILINE)
    if len(short_sentences) > 3:
        issues.append((WARN, f"发现{len(short_sentences)}个过短句子，可能是文字断裂"))
    
    return issues


def check_numeric_reasonability(text):
    """检查数字合理性"""
    issues = []
    
    # 检查成交额的量级（A股日成交通常2000-50000亿）
    amounts = re.findall(r'成交[额量][约]?(\d+\.?\d*)\s*亿', text)
    for amt in amounts:
        num = float(amt)
        if num > 100000:
            issues.append((FAIL, f"成交额数据异常: {num}亿 (超过10万亿)"))
    
    # 检查涨停家数合理性（通常0-300）
    limits_up = re.findall(r'涨停[约]?(\d+)\s*家', text)
    for lu in limits_up:
        num = int(lu)
        if num > 500:
            issues.append((FAIL, f"涨停家数异常: {num}家 (超过500)"))
    
    # 检查跌停家数
    limits_down = re.findall(r'跌停[约]?(\d+)\s*家', text)
    for ld in limits_down:
        num = int(ld)
        if num > 500:
            issues.append((FAIL, f"跌停家数异常: {num}家 (超过500)"))
    
    return issues


def check_weekday_match(text):
    """检查日期和星期几是否匹配"""
    issues = []
    
    # 简单的时间线检查
    date_order = re.findall(r'(\d+)月(\d+)日', text)
    for i in range(len(date_order) - 1):
        m1, d1 = int(date_order[i][0]), int(date_order[i][1])
        m2, d2 = int(date_order[i+1][0]), int(date_order[i+1][1])
        # 如果月份相同，日期应该递增
        if m1 == m2 and d1 > d2 and d1 - d2 > 3:
            issues.append((WARN, f"时间线异常: {m1}月{d1}日 出现在 {m2}月{d2}日 之前"))
    
    return issues


def check_stock_code_format(text):
    """检查股票代码格式"""
    issues = []
    
    # A股代码: 6位数字
    # 但"127" 不是完整代码，需要上下文
    lonely_nums = re.findall(r'(?<![0-9])(\d{3,5})(?![0-9])(?!\s*[.。，,；;）\)])', text)
    for num in lonely_nums:
        if 100 < int(num) < 100000:
            issues.append((WARN, f"疑似残缺数据: 孤立数字 '{num}' (可能是遗漏的日期或代码)"))
    
    return issues


def validate_report(filepath):
    """运行全部校验"""
    if not os.path.exists(filepath):
        print(f"❌ 文件不存在: {filepath}")
        return FAIL
    
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read()
    
    all_issues = []
    all_issues.extend(check_date_format(text))
    all_issues.extend(check_profit_loss_contradiction(text))
    all_issues.extend(check_garbled_text(text))
    all_issues.extend(check_numeric_reasonability(text))
    all_issues.extend(check_weekday_match(text))
    all_issues.extend(check_stock_code_format(text))
    
    if not all_issues:
        print("✅ 报告校验通过，无异常")
        return PASS
    
    max_severity = PASS
    print(f"\n📋 发现 {len(all_issues)} 个问题:")
    for severity, msg in all_issues:
        icon = {PASS: "ℹ️", WARN: "⚠️", FAIL: "❌"}[severity]
        print(f"  {icon} [{severity}] {msg}")
        max_severity = max(max_severity, severity)
    
    return max_severity


def main():
    import argparse
    parser = argparse.ArgumentParser(description="A股报告后置校验器")
    parser.add_argument("file", nargs="?", help="报告HTML文件路径", default=None)
    parser.add_argument("--text", type=str, help="直接传入报告文本")
    
    args = parser.parse_args()
    
    if args.text:
        result = validate_report_text(args.text)
    elif args.file:
        result = validate_report(args.file)
    else:
        # 从stdin读取
        text = sys.stdin.read()
        if text.strip():
            result = validate_report_text(text)
        else:
            print("用法: python3 report_validator.py <文件路径> 或 cat报告 | python3 report_validator.py")
            return FAIL
    
    sys.exit(result)


def validate_report_text(text):
    """直接校验文本"""
    all_issues = []
    all_issues.extend(check_date_format(text))
    all_issues.extend(check_profit_loss_contradiction(text))
    all_issues.extend(check_garbled_text(text))
    all_issues.extend(check_numeric_reasonability(text))
    all_issues.extend(check_weekday_match(text))
    all_issues.extend(check_stock_code_format(text))
    
    if not all_issues:
        print("✅ 报告校验通过")
        return PASS
    
    max_severity = PASS
    print(f"📋 发现 {len(all_issues)} 个问题:")
    for severity, msg in all_issues:
        icon = {PASS: "ℹ️", WARN: "⚠️", FAIL: "❌"}[severity]
        print(f"  {icon} {msg}")
        max_severity = max(max_severity, severity)
    
    return max_severity


if __name__ == "__main__":
    sys.exit(main())
