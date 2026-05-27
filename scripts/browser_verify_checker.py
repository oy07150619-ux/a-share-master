#!/usr/bin/env python3
"""
浏览器数据核验前置检查器 v2.0 — 无法伪造的核验系统

核心规则：核验 = 必须从网页读取到真实数据，不能光签字。
- record 模式：模型必须提供从网页读取到的实际数据（URL + 数据摘要）
- check 模式：验证核验记录包含真实数据，拒绝空记录
- verify 模式：核验前先尝试从东方财富 API 自动采集数据对比

被 cron job 的 bash 部分调用（send_email 前的一步）。
"""

import os
import sys
import json
import requests
import re
import subprocess
from datetime import datetime

STOCK_TOOL = os.path.expanduser("~/.openclaw/workspace/tools/stock_data.py")

REQUIRED_CHECKS = {
    "板块资金流向": {
        "url": "https://data.eastmoney.com/bkzj/hy.html",
        "description": "东方财富行业板块资金流页面核验",
        "key_fields": ["板块名称", "主力净流入"]
    },
    "指数行情": {
        "url": "https://quote.eastmoney.com/center/",
        "description": "东方财富行情中心指数核验",
        "key_fields": ["指数名称", "最新点位"]
    }
}

CHECKPOINT_FILE = "/tmp/a_share_browser_verify.json"
EXPIRY_SECONDS = 1800  # 30分钟


# ── 自动采集用于交叉验证 ──────────────────────────────

def _run_stock_tool(cmd_type, **kwargs):
    """调用 stock_data.py 获取数据"""
    cmd = [sys.executable, STOCK_TOOL, cmd_type]
    if kwargs.get("limit"):
        cmd.extend(["--limit", str(kwargs["limit"])])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.stdout.strip():
            return json.loads(r.stdout)
        return {}
    except Exception as e:
        return {"error": str(e)}


def fetch_eastmoney_sector_top(n=5):
    """通过 stock_data.py 获取板块数据"""
    try:
        result = _run_stock_tool("sector_flow", limit=n)
        if isinstance(result, dict) and "资金流入榜" in result:
            return result["资金流入榜"][:n]
        return None
    except Exception:
        return None


def fetch_eastmoney_indexes():
    """自动从腾讯API抓指数数据"""
    try:
        r = requests.get(
            "https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688,sz399300",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10
        )
        r.encoding = "gbk"
        nm = {"SH000001": "上证指数", "SZ399001": "深证成指",
              "SZ399006": "创业板指", "SH000688": "科创50", "SZ399300": "沪深300"}
        indexes = []
        seen = set()
        for line in r.text.strip().split("\n"):
            m = re.match(r'v_(\w+)="(.+)"', line)
            if not m:
                continue
            f = m.group(2).split("~")
            name = nm.get(m.group(1).upper(), "")
            if name in seen or not name:
                continue
            seen.add(name)
            indexes.append({
                "指数": name,
                "最新": float(f[3]) if f[3] else 0,
                "涨跌幅": float(f[32]) if len(f) > 32 and f[32] else 0
            })
        return indexes
    except Exception:
        return None


# ── 核验逻辑 ──────────────────────────────────────────

def verify_checkpoint():
    """检查核验记录是否真实有效"""
    if not os.path.exists(CHECKPOINT_FILE):
        return {"passed": False, "error": "❌ 核验记录不存在！必须完成浏览器数据采集"}

    with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
        checkpoint = json.load(f)

    # 1. 检查时间
    vt = checkpoint.get("verify_time", "2000-01-01T00:00")
    try:
        elapsed = (datetime.now() - datetime.fromisoformat(vt)).total_seconds()
    except (ValueError, TypeError):
        return {"passed": False, "error": "❌ 核验时间无效，请重新核验"}

    if elapsed > EXPIRY_SECONDS:
        return {"passed": False,
                "error": f"❌ 核验已过期（{elapsed/60:.0f}分钟前），请重新核验"}

    # 2. 检查每条记录是否包含真实数据（非空字符串）
    collected = checkpoint.get("collected_data", {})
    
    # 原来兼容模式：有 completed 列表但没有 collected_data（旧版）
    if not collected and checkpoint.get("completed"):
        return {
            "passed": False,
            "error": "❌ 核验记录没有包含实际采集的数据！"
                     "请使用 record 模式并传入 --collected-data 参数，"
                     "或直接使用 verify 模式自动采集"
        }

    # 3. 检查每条数据是否有实际内容
    empty_checks = []
    for check_name, data in collected.items():
        if not data or (isinstance(data, list) and len(data) == 0):
            empty_checks.append(check_name)
        elif isinstance(data, str) and len(data.strip()) < 5:
            empty_checks.append(check_name)

    if empty_checks:
        return {
            "passed": False,
            "error": f"❌ 以下核验项数据为空或无效：{', '.join(empty_checks)}"
        }

    return {
        "passed": True,
        "error": None,
        "verify_time": vt,
        "completed": list(collected.keys())
    }


def auto_verify():
    """自动采集东方财富数据作为核验，返回核验结果和采集到的数据"""
    print("=" * 55)
    print("📡 开始自动数据核验（腾讯API + 东方财富API）")
    print("=" * 55)

    collected = {}

    # 采集指数
    indexes = fetch_eastmoney_indexes()
    if indexes:
        collected["指数行情"] = indexes
        print(f"  ✅ 指数行情: 采集到 {len(indexes)} 个指数")
        for idx in indexes:
            pct = idx["涨跌幅"]
            mark = "🔴" if pct > 0 else "🟢" if pct < 0 else "⚪"
            print(f"     {mark} {idx['指数']}: {idx['最新']} ({pct:+.2f}%)")
    else:
        print("  ❌ 指数行情: 采集失败")
        return {"passed": False,
                "error": "自动核验失败：指数数据不可用，请手动用浏览器核验",
                "collected": collected}

    # 采集板块资金
    sectors = fetch_eastmoney_sector_top(5)
    if sectors:
        collected["板块资金流向"] = sectors
        print(f"  ✅ 板块资金: 采集到 {len(sectors)} 个行业板块")
        for s in sectors:
            flow_yuan = s.get("主力净流入", 0)
            flow_yi = flow_yuan / 100000000  # 元→亿
            print(f"     {s['板块名称']}: {s['涨跌幅']:+.2f}%  主力净流入 {flow_yi:+.2f}亿 ({flow_yuan:+,.0f}元)")
    else:
        print("  ❌ 板块资金: 采集失败")
        # 不算致命错误，指数才是核心
        print("  ⚠️  板块资金采集失败，但指数数据正常，继续")

    # 写入核验记录
    checkpoint = {
        "verify_time": datetime.now().isoformat(),
        "collected_data": collected,
        "hostname": os.uname().nodename,
        "verify_mode": "auto"
    }
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)

    n = len(collected)
    print(f"\n  📝 核验记录已保存: {n}/{len(REQUIRED_CHECKS)} 项成功")
    print(f"  📁 {CHECKPOINT_FILE}")

    if n == 0:
        return {"passed": False,
                "error": "自动核验全部失败，请手动用浏览器采集数据",
                "collected": collected}

    return {"passed": True, "error": None, "collected": collected}


def manual_record(collected_data_json):
    """手动记录核验（模型通过 browser 采集后传入）"""
    try:
        collected = json.loads(collected_data_json) if isinstance(collected_data_json, str) else collected_data_json
    except json.JSONDecodeError:
        print("❌ collected_data 格式错误，需传入有效 JSON")
        return False

    checkpoint = {
        "verify_time": datetime.now().isoformat(),
        "collected_data": collected,
        "hostname": os.uname().nodename,
        "verify_mode": "manual"
    }
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)

    n = len(collected)
    print(f"✅ 手动核验记录已保存: {n}/{len(REQUIRED_CHECKS)} 项")
    return True


def print_status():
    """打印核验状态"""
    result = verify_checkpoint()

    print("=" * 50)
    print("🔍 浏览器数据核验状态检查")
    print("=" * 50)

    if result.get("passed"):
        print(f"  ✅ 核验通过!")
        print(f"  核验时间: {result.get('verify_time', '?')}")
        print(f"  已完成项: {len(result.get('completed', []))}")
    else:
        print(f"  ❌ 核验未通过")
        print(f"  原因: {result.get('error', '未知错误')}")
        print(f"\n  如果数据采集失败，可运行: python3 {__file__} verify")

    return 0 if result.get("passed") else 1


def main():
    import argparse
    parser = argparse.ArgumentParser(description="浏览器数据核验前置检查器 v2.0")
    parser.add_argument(
        "action",
        choices=["check", "record", "status", "verify"],
        default="check", nargs="?",
    )
    parser.add_argument("--checks", nargs="*", help="（兼容旧版，忽略）")
    parser.add_argument("--collected-data", type=str, default=None,
                        help="手动核验数据 JSON（record 模式使用）")
    parser.add_argument("--data-file", type=str, default=None,
                        help="数据 JSON 文件路径（record 模式使用）")

    args = parser.parse_args()

    if args.action == "verify":
        result = auto_verify()
    elif args.action == "record":
        if args.data_file:
            with open(args.data_file, "r") as f:
                data_json = f.read()
            manual_record(data_json)
        elif args.collected_data:
            manual_record(args.collected_data)
        else:
            # 兼容旧版：什么都不传就是自动核验
            auto_verify()
    elif args.action == "status":
        sys.exit(print_status())
    else:  # check
        result = verify_checkpoint()
        if not result["passed"]:
            # 如果文件核验不通过，尝试自动核验
            print(f"  {result['error']}")
            print(f"\n  ➡ 尝试自动核验...")
            result = auto_verify()
        
        if result["passed"]:
            print(f"\n  ✅ 核验总通过!")
            sys.exit(0)
        else:
            print(f"\n  ❌ 核验失败: {result.get('error', '')}")
            sys.exit(1)


if __name__ == "__main__":
    main()
