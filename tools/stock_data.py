#!/usr/bin/env python3
"""
A股数据采集 v5 - 腾讯API直接算（最可靠）
======
腾讯API batch查询所有A股，自行计算涨跌停
"""

import akshare as ak
import requests, re, json, sys, time
from datetime import datetime

HEADERS = {"User-Agent": "Mozilla/5.0"}

def get_all_stocks():
    """获取所有A股代码列表"""
    df = ak.stock_info_a_code_name()
    return df['code'].tolist()

def batch_query(stocks):
    """批量查询腾讯API获取实时行情"""
    results = []
    for i in range(0, len(stocks), 100):
        batch = stocks[i:i+100]
        q = [f"sh{c}" if c.startswith("6") else f"sz{c}" for c in batch]
        try:
            r = requests.get(f"https://qt.gtimg.cn/q={','.join(q)}", headers=HEADERS, timeout=15)
            r.encoding = "gbk"
            for line in r.text.strip().split("\n"):
                m = re.match(r'v_(\w+)="(.+)"', line)
                if m:
                    f = m.group(2).split("~")
                    code = f[2] if len(f)>2 else ""
                    name = f[1] if len(f)>1 else ""
                    price = float(f[3]) if len(f)>3 and f[3] else 0
                    pct = float(f[32]) if len(f)>32 and f[32] else 0
                    volume = f[6] if len(f)>6 else ""
                    turnover = float(f[37]) if len(f)>37 and f[37] else 0  # 字段37: 成交额
                    results.append({"代码":code,"名称":name,"最新价":price,"涨跌幅":pct,"成交量":volume,"成交额":turnover})
        except Exception:
            pass
    return results

def _is_limit_up(s):
    """按板块判断是否封死涨停（含板宽容忍±0.5%）"""
    code=str(s.get('代码','')) if isinstance(s, dict) else ''
    name=str(s.get('名称','')) if isinstance(s, dict) else ''
    pct=s.get('涨跌幅', 0) if isinstance(s, dict) else s.get('涨跌幅', 0)
    pct = float(pct) if pct else 0
    
    # 竞价阶段兼容：如果涨跌幅为0但有竞价价格，尝试通过价格判断
    price = float(s.get('最新价', 0)) if isinstance(s, dict) else 0
    prev_close = float(s.get('昨收', 0)) if isinstance(s, dict) else 0
    if pct == 0 and price > 0 and prev_close > 0:
        pct = (price - prev_close) / prev_close * 100
    
    if 'ST' in name.upper(): return 4.9 <= pct <= 5.1
    if code.startswith('8'): return 29.5 <= pct <= 30.5
    if code.startswith('688') or code.startswith('30'): return 19.5 <= pct <= 20.5
    return 9.5 <= pct <= 10.5


def _is_limit_down(s):
    """按板块判断是否封死跌停"""
    code=str(s.get('代码','')) if isinstance(s, dict) else ''
    name=str(s.get('名称','')) if isinstance(s, dict) else ''
    pct=s.get('涨跌幅', 0) if isinstance(s, dict) else s.get('涨跌幅', 0)
    pct = float(pct) if pct else 0
    
    # 竞价阶段兼容
    price = float(s.get('最新价', 0)) if isinstance(s, dict) else 0
    prev_close = float(s.get('昨收', 0)) if isinstance(s, dict) else 0
    if pct == 0 and price > 0 and prev_close > 0:
        pct = (price - prev_close) / prev_close * 100
    
    if 'ST' in name.upper(): return -5.1 <= pct <= -4.9
    if code.startswith('8'): return -30.5 <= pct <= -29.5
    if code.startswith('688') or code.startswith('30'): return -20.5 <= pct <= -19.5
    return -10.5 <= pct <= -9.5

def get_indexes():
    """腾讯大盘指数"""
    r = requests.get("https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688,sz399300", headers=HEADERS, timeout=10)
    r.encoding = "gbk"
    nm={"SH000001":"上证指数","SZ399001":"深证成指","SZ399006":"创业板指","SH000688":"科创50","SZ399300":"沪深300"}
    result=[]; seen=set()
    for line in r.text.strip().split("\n"):
        m=re.match(r'v_(\w+)="(.+)"',line)
        if not m: continue
        f=m.group(2).split("~")
        n=nm.get(m.group(1).upper(),"")
        if n in seen or not n: continue
        seen.add(n)
        result.append({"指数":n,"最新":float(f[3]) if f[3] else 0,"涨跌幅":float(f[32]) if len(f)>32 and f[32] else 0})
    return result

_COLLECTED = None

def _collect():
    global _COLLECTED
    if _COLLECTED is None:
        print("[采集] 获取股票列表...", file=sys.stderr)
        codes = get_all_stocks()
        print(f"[采集] 查询{len(codes)}只股票行情...", file=sys.stderr)
        _COLLECTED = batch_query(codes)
        print(f"[采集] 获取到{len(_COLLECTED)}只数据", file=sys.stderr)
    return _COLLECTED

def get_limits():
    stocks = _collect()
    lu = sum(1 for s in stocks if _is_limit_up(s))
    ld = sum(1 for s in stocks if _is_limit_down(s))
    return {"涨停": lu, "跌停": ld}

def get_updown():
    stocks = _collect()
    up = sum(1 for s in stocks if s['涨跌幅'] > 0)
    down = sum(1 for s in stocks if s['涨跌幅'] < 0)
    return {"上涨": up, "下跌": down}

def get_top(limit=10, up=True):
    stocks = _collect()
    sorted_s = sorted(stocks, key=lambda s: s['涨跌幅'], reverse=up)
    return [{"名称":s['名称'],"代码":s['代码'],"最新价":s['最新价'],"涨跌幅":round(s['涨跌幅'],2)} for s in sorted_s if s['涨跌幅']!=0][:limit]

def _retry_push2(fn, retries=3, delay=1.5):
    """调用push2 API时带重试"""
    for i in range(retries):
        try:
            return fn()
        except Exception as e:
            if i < retries - 1:
                print(f"[重试{i+1}/{retries}] {e}", file=sys.stderr)
                time.sleep(delay)
    return None

def get_sector():
    """行业板块 - 带fallback链"""
    # 尝试1: AKShare → push2.eastmoney.com
    r1 = _retry_push2(lambda: __import__('akshare').ak.stock_board_industry_name_em())
    if r1 is not None and not r1.empty:
        df = r1.sort_values('涨跌幅', ascending=False)
        return [{"板块名称":r['板块名称'],"涨跌幅":round(r['涨跌幅'],2),"领涨股票":r['领涨股票']} for _,r in df.head(20).iterrows()]
    
    # 尝试2: stock_board_change_em (push2ex, 不同API)
    try:
        df = ak.stock_board_change_em()
        # 过滤出真正的行业板块
        industry_keywords = ['半导体','芯片','通信','光模块','CPO','PCB','计算','电子',
                           '电力','机械','汽车','医药','消费','金融','地产',
                           '设备','材料','化工','军工','能源','环保','有色',
                           '钢铁','煤炭','农业','食品','酒','饮料','家电',
                           '传媒','教育','旅游','运输','建筑','建材','纺织']
        mask = df['板块名称'].str.contains('|'.join(industry_keywords))
        filtered = df[mask].copy()
        if len(filtered) >= 5:
            filtered = filtered.sort_values('涨跌幅', ascending=False)
            return [{"板块名称":r['板块名称'],"涨跌幅":round(r['涨跌幅'],2)} for _,r in filtered.head(20).iterrows()]
    except: pass
    
    # 全部失败
    return []

def get_sector_flow(limit=20):
    """板块涨跌幅+资金流向（从push2ex获取）"""
    try:
        df = ak.stock_board_change_em()
        # 过滤行业相关板块
        industry_keywords = ['半导体','芯片','通信','光模块','CPO','PCB','计算','电子',
                           '电力','机械','汽车','医药','消费','金融','地产',
                           '设备','材料','化工','军工','能源','环保','有色',
                           '钢铁','煤炭','农业','食品','酒','饮料','家电',
                           '传媒','教育','旅游','运输','建筑','建材','纺织','电池','光伏','风电','新能']
        mask = df['板块名称'].str.contains('|'.join(industry_keywords))
        filtered = df[mask].copy()
        if len(filtered) < 5:
            filtered = df  # fallback到全部
        result = []
        for _, r in filtered.head(limit*2).iterrows():
            result.append({
                "板块名称": r['板块名称'],
                "涨跌幅": round(r['涨跌幅'], 2),
                "主力净流入": round(r['主力净流入'], 0)
            })
        # 分别按涨跌幅和资金流向排序，返回top
        by_pct = sorted(result, key=lambda x: x['涨跌幅'], reverse=True)[:limit]
        by_flow = sorted(result, key=lambda x: x['主力净流入'])[:limit]
        return {
            "涨幅榜": by_pct,
            "资金流入榜": sorted(result, key=lambda x: x['主力净流入'], reverse=True)[:limit],
            "资金流出榜": by_flow,
        }
    except Exception as e:
        print(f"[sector_flow异常] {e}", file=sys.stderr)
        return {"涨幅榜": [], "资金流入榜": [], "资金流出榜": []}

def get_concept():
    try:
        df = _retry_push2(lambda: ak.stock_board_concept_name_em())
        if df is not None and not df.empty:
            df = df.sort_values('涨跌幅', ascending=False)
            return [{"板块名称":r['板块名称'],"涨跌幅":round(r['涨跌幅'],2)} for _,r in df.head(20).iterrows()]
    except: pass
    # fallback: from sector_flow
    try:
        sf = get_sector_flow(30)
        return sf.get('涨幅榜', [])[:20]
    except:
        return []

if __name__ == "__main__":
    start = time.time()
    cmds = {
        "indexes": get_indexes, "updown": get_updown,
        "limits": get_limits, "gainers": lambda: get_top(10, True),
        "losers": lambda: get_top(10, False),
        "sector": get_sector, "concept": get_concept,
        "sector_flow": lambda: get_sector_flow(20),
        "all": lambda: {
            "indexes": get_indexes(), "updown": get_updown(),
            "limits": get_limits(), "gainers": get_top(5, True),
            "losers": get_top(5, False),
        }
    }
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("type", choices=list(cmds.keys()))
    parser.add_argument("--limit", type=int, default=20, help="结果数量")
    parser.add_argument("--flow", action="store_true", help="(sector_flow) 按资金流向排序")
    args = parser.parse_args()
    data = cmds[args.type]()
    if isinstance(data, dict):
        print(json.dumps(data, ensure_ascii=False))
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"[耗时: {time.time()-start:.0f}s]", file=sys.stderr)
