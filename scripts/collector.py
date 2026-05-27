#!/usr/bin/env python3
"""
A股综合数据采集器 - 多源数据采集
==============================
整合：
- 腾讯API实时行情
- AKShare板块/资金
- 浏览器采集接口
- 搜索结果结构化

用法:
  python collector.py all               # 采集全部
  python collector.py market            # 大盘指数+涨跌
  python collector.py sector            # 板块数据
  python collector.py flow              # 资金流向
  python collector.py stock <code>      # 单只股票数据
  python collector.py news <keyword>    # 搜索新闻
  python collector.py verify            # 数据交叉验证

注: 在Linux/macOS上可使用 python3, Windows使用 python
本脚本自动适应当前解释器。
"""

import json, sys, os, re, time, subprocess
from datetime import datetime, timedelta

WORKSPACE = os.path.expanduser("~/.openclaw/workspace")
STOCK_TOOL = os.path.join(WORKSPACE, "tools", "stock_data.py")

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}


def _run_stock_tool(cmd_type, **kwargs):
    """调用 stock_data.py"""
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


def collect_market():
    """采集大盘概况"""
    result = {
        "timestamp": datetime.now().isoformat(),
        "indexes": _run_stock_tool("indexes"),
        "updown": _run_stock_tool("updown"),
        "limits": _run_stock_tool("limits"),
    }
    return result


def collect_sector(limit=30):
    """采集板块数据"""
    result = {
        "sector_flow": _run_stock_tool("sector_flow", limit=limit),
        "sector": _run_stock_tool("sector"),
        "concept": _run_stock_tool("concept"),
    }
    return result


def collect_flow(limit=30):
    """采集资金流向"""
    flow = _run_stock_tool("sector_flow", limit=limit)
    if isinstance(flow, dict):
        return flow
    
    # fallback: 直接计算
    sector = _run_stock_tool("sector")
    return {"涨幅榜": sector[:10] if sector else [],
            "资金流入榜": [],
            "资金流出榜": []}


def collect_top(limit=20):
    """采集排行数据"""
    return {
        "gainers": _run_stock_tool("gainers", limit=limit),
        "losers": _run_stock_tool("losers", limit=limit),
    }


def collect_stock(code):
    """采集个股数据（基础行情）
    返回结构化的行情摘要，用于后续搜索扩展。
    """
    # 这里调用腾讯API直接获取，不依赖AKShare的个股函数
    prefix = "sh" if code.startswith("6") else "sz"
    import requests
    try:
        r = requests.get(f"https://qt.gtimg.cn/q={prefix}{code}", 
                        headers=HEADERS, timeout=10)
        r.encoding = "gbk"
        for line in r.text.strip().split("\n"):
            m = re.match(r'v_(\w+)="(.+)"', line)
            if m:
                f = m.group(2).split("~")
                stock_data = {
                    "代码": code,
                    "名称": f[1] if len(f) > 1 else "",
                    "最新价": float(f[3]) if len(f) > 3 and f[3] else 0,
                    "昨收": float(f[4]) if len(f) > 4 and f[4] else 0,
                    "开盘": float(f[5]) if len(f) > 5 and f[5] else 0,
                    "成交量": f[6] if len(f) > 6 else "",
                    "成交额": f[37] if len(f) > 37 and f[37] else "0",
                    "最高": float(f[33]) if len(f) > 33 and f[33] else 0,
                    "最低": float(f[34]) if len(f) > 34 and f[34] else 0,
                    "涨跌幅": float(f[32]) if len(f) > 32 and f[32] else 0,
                    "涨跌额": float(f[31]) if len(f) > 31 and f[31] else 0,
                    "换手率": f[38] if len(f) > 38 else "",
                    "市盈率": f[39] if len(f) > 39 else "",
                    "振幅": f[43] if len(f) > 43 else "",
                    "流通市值": f[44] if len(f) > 44 else "",
                    "总市值": f[45] if len(f) > 45 else "",
                    "市净率": f[46] if len(f) > 46 else "",
                    "涨停价": float(f[48]) if len(f) > 48 and f[48] else 0,
                    "跌停价": float(f[49]) if len(f) > 49 and f[49] else 0,
                }
                return stock_data
    except Exception as e:
        return {"error": str(e), "code": code}
    return {"error": "not_found", "code": code}


def collect_stock_flow(code):
    """采集个股资金流向数据（尝试多数据源）

    优先顺序：
    1. AKShare stock_individual_fund_flow（如果可用）
    2. 东方财富push2 API（备用）
    3. 返回空数据（如果都不可用，不报错）

    返回：
    {
        "代码": code,
        "主力净流入": float,  # 亿
        "特大单净流入": float,  # 亿
        "大单净流入": float,  # 亿
        "中单净流入": float,  # 亿
        "小单净流入": float,  # 亿
        "来源": "akshare/东方财富API/暂无数据",
        "采集时间": str
    }
    或 {"error": str, "code": code}
    """
    import requests

    ts = datetime.now().isoformat()
    market = "1" if code.startswith("6") else "0"

    # --- 尝试1: AKShare ---
    try:
        import akshare as ak
        df = ak.stock_individual_fund_flow(stock=code, market=market)
        if df is not None and not df.empty:
            # 取最新一行
            last = df.iloc[-1]
            # AKShare返回的列名可能有变体，尝试匹配
            main_net = None
            for col in ["主力净流入-净额", "主力净流入", "净流入", "main_net_inflow"]:
                if col in df.columns:
                    main_net = float(last[col])
                    break
            mega_net = None
            for col in ["特大单净流入-净额", "特大单净流入", "mega_order_net"]:
                if col in df.columns:
                    mega_net = float(last[col])
                    break
            large_net = None
            for col in ["大单净流入-净额", "大单净流入", "large_order_net"]:
                if col in df.columns:
                    large_net = float(last[col])
                    break
            mid_net = None
            for col in ["中单净流入-净额", "中单净流入", "medium_order_net"]:
                if col in df.columns:
                    mid_net = float(last[col])
                    break
            small_net = None
            for col in ["小单净流入-净额", "小单净流入", "small_order_net"]:
                if col in df.columns:
                    small_net = float(last[col])
                    break

            # 至少需要主力净流入
            if main_net is not None:
                return {
                    "代码": code,
                    "主力净流入": round(main_net / 1e8, 4),
                    "特大单净流入": round(mega_net / 1e8, 4) if mega_net is not None else 0,
                    "大单净流入": round(large_net / 1e8, 4) if large_net is not None else 0,
                    "中单净流入": round(mid_net / 1e8, 4) if mid_net is not None else 0,
                    "小单净流入": round(small_net / 1e8, 4) if small_net is not None else 0,
                    "来源": "akshare",
                    "采集时间": ts
                }
    except ImportError:
        pass  # akshare未安装
    except Exception:
        pass  # AKShare其他错误，降级

    # --- 尝试2: 东方财富push2 API ---
    try:
        url = (
            f"https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get"
            f"?secid={market}.{code}"
            f"&fields1=f1,f2,f3,f7"
            f"&fields2=f51,f52,f53,f54,f55,f56"
        )
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()
        klines = data.get("data", {}).get("klines", [])
        if klines:
            # 取最新一条
            last_line = klines[-1]
            parts = last_line.split(",")
            # f51=日期, f52=主力, f53=特大单, f54=大单, f55=中单, f56=小单
            if len(parts) >= 6:
                main_net = float(parts[1]) if parts[1] else 0
                mega_net = float(parts[2]) if parts[2] else 0
                large_net = float(parts[3]) if parts[3] else 0
                mid_net = float(parts[4]) if parts[4] else 0
                small_net = float(parts[5]) if parts[5] else 0
                return {
                    "代码": code,
                    "主力净流入": round(main_net / 1e8, 4),
                    "特大单净流入": round(mega_net / 1e8, 4),
                    "大单净流入": round(large_net / 1e8, 4),
                    "中单净流入": round(mid_net / 1e8, 4),
                    "小单净流入": round(small_net / 1e8, 4),
                    "来源": "东方财富API",
                    "采集时间": ts
                }
    except Exception:
        pass

    # --- 都不可用，返回空数据 ---
    return {
        "代码": code,
        "主力净流入": 0,
        "特大单净流入": 0,
        "大单净流入": 0,
        "中单净流入": 0,
        "小单净流入": 0,
        "来源": "暂无数据",
        "采集时间": ts
    }


def collect_all():
    """采集全部数据"""
    result = {
        "日期": datetime.now().strftime("%Y-%m-%d"),
        "时间": datetime.now().strftime("%H:%M"),
        "market": collect_market(),
        "sector": collect_sector(),
        "tops": collect_top(20),
        "flow": collect_flow(),
    }
    return result


def verify():
    """简单交叉验证数据"""
    result = {"checked_fields": [], "issues": [], "passed": True}
    
    # 1. 检查大盘指数
    market = collect_market()
    indexes = market.get("indexes", [])
    sh = next((i for i in indexes if "上证" in i.get("指数", "")), {})
    if sh:
        result["checked_fields"].append("上证指数")
        # 记录但暂不做cross-validation
        result["sh_index"] = sh
    
    # 2. 检查涨跌与涨跌停逻辑
    updown = market.get("updown", {})
    limits = market.get("limits", {})
    up = updown.get("上涨", 0)
    down = updown.get("下跌", 0)
    lu = limits.get("涨停", 0)
    ld = limits.get("跌停", 0)
    
    if up + down > 0:
        result["checked_fields"].append(f"涨跌家数: 涨{up}/跌{down}/涨停{lu}/跌停{ld}")
        if up + down < 100:
            result["issues"].append(f"总家数偏少(仅{up+down})，可能数据不完整")
            result["passed"] = False
    
    # 3. 检查板块数据
    sector_flow = _run_stock_tool("sector_flow")
    if isinstance(sector_flow, dict):
        gain_board = sector_flow.get("涨幅榜", [])
        in_board = sector_flow.get("资金流入榜", [])
        if gain_board:
            result["checked_fields"].append(f"板块数据数: {len(gain_board)}个板块")
    
    result["timestamp"] = datetime.now().isoformat()
    return result


# ========================================================================
# 函数: 计算炸板率 (v4.0)
# ========================================================================

def calc_limit_board_rate(total_limit_up, broken_limit_count):
    """
    计算炸板率（打开涨停比例）。

    Parameters:
        total_limit_up (int): 总涨停家数
        broken_limit_count (int): 炸板家数（涨停后打开）

    Returns:
        dict: {
            'rate': float or None,
            'level': 'low' | 'medium' | 'high' | 'unknown',
            'note': str or None
        }
    """
    if total_limit_up is None or broken_limit_count is None:
        return {
            'rate': None,
            'level': 'unknown',
            'note': '数据源不支持炸板率计算'
        }

    try:
        total_limit_up = int(total_limit_up)
        broken_limit_count = int(broken_limit_count)
    except (ValueError, TypeError):
        return {
            'rate': None,
            'level': 'unknown',
            'note': '数据源不支持炸板率计算'
        }

    if total_limit_up <= 0:
        return {
            'rate': 0.0,
            'level': 'low',
            'note': '无涨停数据'
        }

    rate = broken_limit_count / total_limit_up * 100
    rate = round(rate, 2)

    if rate < 20:
        level = 'low'
    elif rate <= 40:
        level = 'medium'
    else:
        level = 'high'

    return {
        'rate': rate,
        'level': level,
        'note': None
    }


def format_output(data, mode="text"):
    """格式化输出"""
    if mode == "json":
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    lines = []
    if "market" in data:
        m = data["market"]
        idx = m.get("indexes", [])
        lines.append(f"【大盘】{data.get('日期','')} {data.get('时间','')}")
        for i in idx:
            lines.append(f"  {i.get('指数','')} {i.get('最新','')} ({i.get('涨跌幅',''):+.2f}%)")
        ud = m.get("updown", {})
        lm = m.get("limits", {})
        lines.append(f"【涨跌】涨{ud.get('上涨','?')}家 跌{ud.get('下跌','?')}家 | 涨停{lm.get('涨停','?')} 跌停{lm.get('跌停','?')}")
    
    if "sector" in data:
        sf = data["sector"].get("sector_flow", {})
        if isinstance(sf, dict):
            gain_s = sf.get("涨幅榜", [])[:5]
            if gain_s:
                lines.append("【板块涨幅TOP5】")
                for s in gain_s:
                    lines.append(f"  {s.get('板块名称','')} {s.get('涨跌幅',''):+.2f}%")
            flow_in = sf.get("资金流入榜", [])[:5]
            if flow_in:
                lines.append("【资金流入TOP5】")
                for s in flow_in:
                    f = s.get("主力净流入", 0)
                    lines.append(f"  {s.get('板块名称','')} +{f/1e8:.1f}亿")
    
    if "tops" in data:
        t = data["tops"]
        g = t.get("gainers", [])[:5]
        l = t.get("losers", [])[:5]
        if g:
            lines.append("【涨幅TOP5】")
            for s in g:
                lines.append(f"  {s.get('名称','')}({s.get('代码','')}) {s.get('涨跌幅',''):+.2f}%")
        if l:
            lines.append("【跌幅TOP5】")
            for s in l:
                lines.append(f"  {s.get('名称','')}({s.get('代码','')}) {s.get('涨跌幅',''):+.2f}%")
    
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="A股综合数据采集器")
    parser.add_argument("mode", nargs="?", default="all",
                       help="采集模式 (all/market/sector/flow/tops/stock/news/verify; 别名: premarket/morning/closing/auction)")
    parser.add_argument("--code", help="股票代码 (stock模式)")
    parser.add_argument("--keyword", help="搜索关键词 (news模式)")
    parser.add_argument("--limit", type=int, default=20, help="数据数量")
    parser.add_argument("--json", action="store_true", help="JSON格式输出")
    parser.add_argument("--output", help="输出到文件")

    args = parser.parse_args()
    
    # 模式别名映射: 盘前/早盘/收盘 → 有效模式
    MODE_ALIASES = {
        "premarket": "all",
        "morning": "all",
        "closing": "all",
        "auction": "market",
    }
    if args.mode in MODE_ALIASES:
        args.mode = MODE_ALIASES[args.mode]
    
    # 验证模式有效性
    VALID_MODES = ["all", "market", "sector", "flow", "tops", "stock", "news", "verify"]
    if args.mode not in VALID_MODES:
        print(f"错误: 未知模式 '{args.mode}'，可用模式: {', '.join(VALID_MODES)}", file=sys.stderr)
        sys.exit(1)
    start = time.time()

    if args.mode == "all":
        data = collect_all()
    elif args.mode == "market":
        data = collect_market()
    elif args.mode == "sector":
        data = collect_sector(args.limit)
    elif args.mode == "flow":
        data = collect_flow(args.limit)
    elif args.mode == "tops":
        data = collect_top(args.limit)
    elif args.mode == "stock":
        if not args.code:
            print("报错：请指定 --code", file=sys.stderr)
            sys.exit(1)
        data = collect_stock(args.code)
    elif args.mode == "verify":
        data = verify()
    else:
        data = {"error": f"未知模式: {args.mode}"}
    
    # 输出
    if args.json:
        output = json.dumps(data, ensure_ascii=False, indent=2)
    else:
        output = format_output(data, "text")
    
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"✅ 已保存到 {args.output}")
    else:
        print(output)
    
    print(f"[耗时: {time.time()-start:.1f}s]", file=sys.stderr)
