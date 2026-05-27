#!/usr/bin/env python3
"""
📀 交易知识库 — 每日市场数据持久化存储
====================================
功能：
- 每日记录市场快照（指数、板块、情绪、个股TOP）
- 存储交易信号（板块资金异动、连板梯队、模式匹配）
- 记录次日结果（验证信号有效性）
- 积累长期知识库，供策略学习引擎训练

数据存储在: ~/.openclaw/workspace/skills/a-share-master/data/trading_memory.json

用法:
  python trading_memory.py record [--date YYYY-MM-DD]        # 记录今日快照
  python trading_memory.py record_signal <signal_type> ...    # 记录交易信号
  python trading_memory.py record_outcome <signal_id> <result> # 记录信号结果
  python trading_memory.py query [--date YYYY-MM-DD]          # 查询历史
  python trading_memory.py stats                              # 知识库统计
  python trading_memory.py export [--format json|csv]         # 导出训练数据
"""

import json, os, sys, time, copy
from datetime import datetime, timedelta

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(SKILL_DIR, "data")
MEMORY_FILE = os.path.join(DATA_DIR, "trading_memory.json")

# 确保data目录存在
os.makedirs(DATA_DIR, exist_ok=True)

# =====================================================================
# 知识库核心类
# =====================================================================

class TradingMemory:
    """交易知识库"""
    
    def __init__(self, memory_file=None):
        self.memory_file = memory_file or MEMORY_FILE
        self._data = self._load()
    
    def _load(self):
        """加载持久化数据"""
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, Exception):
                pass
        return self._empty_db()
    
    def _empty_db(self):
        """返回空数据库结构"""
        return {
            "meta": {
                "created": datetime.now().isoformat(),
                "version": "2.0",
                "last_updated": datetime.now().isoformat(),
                "total_days_recorded": 0,
                "total_signals_recorded": 0,
                "total_outcomes_recorded": 0,
            },
            "daily_snapshots": {},    # key: YYYY-MM-DD
            "signals": {},            # key: signal_id (auto-gen)
            "patterns": {
                "sector_flow_continuity": [],   # 板块资金连续流入天数模式
                "limit_up_density": [],         # 涨停密度关联模式
                "index_correlation": [],        # 大盘关联模式
                "learned_rules": [],            # 学习到的规则
            },
            "strategy_stats": {
                "by_signal_type": {},
                "by_sector": {},
                "by_market_state": {},
            }
        }
    
    def _save(self):
        """持久化到磁盘"""
        self._data["meta"]["last_updated"] = datetime.now().isoformat()
        # 确保data目录存在
        os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
        with open(self.memory_file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
    
    # ==================== 每日快照 ====================
    
    def record_snapshot(self, date_str=None, snapshot_data=None):
        """记录每日市场快照
        
        参数:
            date_str: YYYY-MM-DD格式，默认今天
            snapshot_data: dict, 含以下字段:
                - indexes: 大盘指数列表 [{name, close, change%}...]
                - sentiment: 情绪数据 {up, down, limit_up, limit_down}
                - volume: 成交量(亿)
                - top_sectors: 板块TOP10 [{name, change%, flow}...]
                - top_gainers: 涨幅TOP10 [{code, name, pct}...]
                - top_losers: 跌幅TOP10 [{code, name, pct}...]
                - big_flow_stocks: 资金异动个股 [{code, name, net_flow}...]
                - market_state: "strong"/"neutral"/"weak"
                - summary: 文字总结
        """
        date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        
        if snapshot_data is None:
            snapshot_data = {}
        
        # 添加时间戳
        record = {
            "recorded_at": datetime.now().isoformat(),
            "date": date_str,
            "data": snapshot_data,
        }
        
        # 合并到已有记录（如当天已存在）
        if date_str in self._data["daily_snapshots"]:
            existing = self._data["daily_snapshots"][date_str]
            existing["data"].update(snapshot_data)
            existing["recorded_at"] = datetime.now().isoformat()
        else:
            self._data["daily_snapshots"][date_str] = record
            self._data["meta"]["total_days_recorded"] = len(self._data["daily_snapshots"])
        
        self._save()
        return True
    
    def get_snapshot(self, date_str):
        """获取指定日期的快照"""
        return self._data["daily_snapshots"].get(date_str, None)
    
    def get_recent_snapshots(self, days=30):
        """获取最近N天的快照（按日期倒序）"""
        dates = sorted(self._data["daily_snapshots"].keys(), reverse=True)
        return [(d, self._data["daily_snapshots"][d]) for d in dates[:days]]
    
    # ==================== 交易信号 ====================
    
    def record_signal(self, date_str, signal_type, signal_data):
        """记录一个交易信号
        
        信号类型 (signal_type):
            - sector_flow_alert: 板块资金异动
            - pattern_match: 形态匹配
            - limit_up_analysis: 涨停梯队分析
            - reversal_signal: 反转信号
            - volume_breakout: 放量突破
            - gap_analysis: 缺口分析
            - sentiment_extreme: 情绪极端
            - custom: 自定义
        
        signal_data 示例:
            {
                "sector": "半导体",
                "direction": "bullish",
                "confidence": 0.75,         # 0~1
                "description": "半导体板块连续3日主力资金净流入TOP3",
                "trigger_reason": "资金面",
                "expected_outcome": "板块次日继续走强",
                "related_stocks": ["688981", ...] 
            }
        
        返回 signal_id
        """
        date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        signal_id = f"{date_str}_{signal_type}_{int(time.time())}"
        
        signal = {
            "signal_id": signal_id,
            "date": date_str,
            "recorded_at": datetime.now().isoformat(),
            "signal_type": signal_type,
            "data": signal_data,
            "outcome": None,     # 待填充
            "outcome_date": None,
            "verified": False,
        }
        
        self._data["signals"][signal_id] = signal
        self._data["meta"]["total_signals_recorded"] = len(self._data["signals"])
        
        # 更新signal_type统计
        st = signal_type
        if st not in self._data["strategy_stats"]["by_signal_type"]:
            self._data["strategy_stats"]["by_signal_type"][st] = {
                "total": 0, "correct": 0, "wrong": 0, "pending": 0
            }
        self._data["strategy_stats"]["by_signal_type"][st]["total"] += 1
        self._data["strategy_stats"]["by_signal_type"][st]["pending"] += 1
        
        self._save()
        return signal_id
    
    def record_outcome(self, signal_id, result, details=None):
        """记录信号的实际结果
        
        参数:
            signal_id: 信号ID
            result: "correct" / "wrong" / "partial" / "insufficient_data"
            details: 额外说明
        """
        if signal_id not in self._data["signals"]:
            print(f"⚠️ 信号 {signal_id} 不存在", file=sys.stderr)
            return False
        
        signal = self._data["signals"][signal_id]
        
        # 更新结果
        record = {
            "result": result,
            "recorded_at": datetime.now().isoformat(),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "details": details or "",
        }
        
        if signal["outcome"] is None:
            signal["outcome"] = []
        signal["outcome"].append(record)
        signal["verified"] = True
        
        self._data["meta"]["total_outcomes_recorded"] += 1
        
        # 更新统计
        st = signal["signal_type"]
        stats = self._data["strategy_stats"]["by_signal_type"].get(st)
        if stats:
            stats["pending"] = max(0, stats["pending"] - 1)
            if result == "correct":
                stats["correct"] += 1
            elif result == "wrong":
                stats["wrong"] += 1
            # partial 不加到correct/wrong
        
        # 更新板块统计
        sector = signal["data"].get("sector", "未知")
        if sector not in self._data["strategy_stats"]["by_sector"]:
            self._data["strategy_stats"]["by_sector"][sector] = {
                "total": 0, "correct": 0, "wrong": 0
            }
        s_stats = self._data["strategy_stats"]["by_sector"][sector]
        s_stats["total"] += 1
        if result == "correct":
            s_stats["correct"] += 1
        elif result == "wrong":
            s_stats["wrong"] += 1
        
        self._save()
        return True
    
    # ==================== 模式学习 ====================
    
    def learn_pattern(self, pattern_type, pattern_data):
        """记录学习到的模式"""
        pattern = {
            "learned_at": datetime.now().isoformat(),
            "type": pattern_type,
            "data": pattern_data,
            "confidence": pattern_data.get("confidence", 0.5),
            "sample_size": pattern_data.get("sample_size", 1),
        }
        if pattern_type in self._data["patterns"]:
            self._data["patterns"][pattern_type].append(pattern)
        self._save()
    
    # ==================== 查询/分析 ====================
    
    def get_signal_stats(self):
        """获取信号统计"""
        stats = self._data["strategy_stats"]
        result = {}
        for st, s in stats.get("by_signal_type", {}).items():
            total = s["total"]
            correct = s["correct"]
            wrong = s["wrong"]
            pending = s["pending"]
            win_rate = correct / (correct + wrong) * 100 if (correct + wrong) > 0 else 0
            result[st] = {
                "total": total,
                "correct": correct,
                "wrong": wrong,
                "pending": pending,
                "win_rate": round(win_rate, 1),
            }
        return result
    
    def get_top_performing_strategies(self, min_samples=3):
        """获取表现最好的策略（按胜率排序）"""
        stats = self.get_signal_stats()
        ranked = []
        for st, s in stats.items():
            if s["total"] >= min_samples and (s["correct"] + s["wrong"]) > 0:
                ranked.append((st, s["win_rate"], s["total"], s["correct"], s["wrong"]))
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked
    
    def get_worst_performing_strategies(self, min_samples=3):
        """获取表现最差的策略"""
        stats = self.get_signal_stats()
        ranked = []
        for st, s in stats.items():
            if s["total"] >= min_samples and (s["correct"] + s["wrong"]) > 0:
                ranked.append((st, s["win_rate"], s["total"], s["correct"], s["wrong"]))
        ranked.sort(key=lambda x: x[1])
        return ranked
    
    def get_sector_win_rates(self, min_samples=3):
        """按板块统计信号胜率"""
        stats = self._data["strategy_stats"]["by_sector"]
        result = []
        for sector, s in stats.items():
            if s["total"] >= min_samples and (s["correct"] + s["wrong"]) > 0:
                win_rate = s["correct"] / (s["correct"] + s["wrong"]) * 100
                result.append({
                    "sector": sector,
                    "total": s["total"],
                    "correct": s["correct"],
                    "wrong": s["wrong"],
                    "win_rate": round(win_rate, 1),
                })
        result.sort(key=lambda x: x["win_rate"], reverse=True)
        return result
    
    def get_pending_signals(self):
        """获取待验证的信号"""
        pending = []
        for sid, signal in self._data["signals"].items():
            if signal["outcome"] is None:
                pending.append(signal)
        return pending
    
    def find_similar_days(self, target_data, top_k=5):
        """寻找历史上相似的市场日（基于多个维度量化匹配）
        
        参数:
            target_data: dict, 包含 indexes/sentiment/volume/top_sectors 等
            top_k: 返回最相似的k个交易日
        
        返回: [(date, similarity_score, snapshot), ...]
        """
        if not self._data["daily_snapshots"]:
            return []
        
        scores = []
        target_sectors = {s.get("name",""): s.get("change%",0) for s in target_data.get("top_sectors", [])}
        
        for date_str, snapshot in self._data["daily_snapshots"].items():
            data = snapshot.get("data", {})
            score = 0.0
            
            # 1. 涨跌家数比相似度 (权重 0.3)
            t_up = target_data.get("sentiment", {}).get("up", 0)
            t_down = target_data.get("sentiment", {}).get("down", 0) or 1
            t_ratio = t_up / t_down
            
            h_up = data.get("sentiment", {}).get("up", 0)
            h_down = data.get("sentiment", {}).get("down", 0) or 1
            h_ratio = h_up / h_down
            
            ratio_diff = abs(t_ratio - h_ratio) / max(t_ratio, h_ratio, 0.1)
            score += 0.3 * (1 - min(ratio_diff, 1))
            
            # 2. 成交量相似度 (权重 0.2)
            t_vol = target_data.get("volume", 0) or 1
            h_vol = data.get("volume", 0) or 1
            vol_diff = abs(t_vol - h_vol) / max(t_vol, h_vol, 0.1)
            score += 0.2 * (1 - min(vol_diff, 1))
            
            # 3. 板块结构相似度 (权重 0.3)
            h_sectors = {s.get("name",""): s.get("change%",0) for s in data.get("top_sectors", [])}
            common = set(target_sectors.keys()) & set(h_sectors.keys())
            if common:
                sector_score = 0
                for name in common:
                    t_pct = abs(target_sectors.get(name, 0))
                    h_pct = abs(h_sectors.get(name, 0))
                    diff = abs(t_pct - h_pct) / max(t_pct, h_pct, 0.1)
                    sector_score += (1 - min(diff, 1))
                score += 0.3 * (sector_score / len(common)) if common else 0
            
            # 4. 涨停数相似度 (权重 0.2)
            t_lim = target_data.get("sentiment", {}).get("limit_up", 0)
            h_lim = data.get("sentiment", {}).get("limit_up", 0)
            lim_diff = abs(t_lim - h_lim) / max(t_lim, h_lim, 0.1) if max(t_lim, h_lim) > 0 else 0
            score += 0.2 * (1 - min(lim_diff, 1))
            
            scores.append((date_str, round(score, 3), snapshot))
        
        # 按相似度排序
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]
    
    def cleanup_old_data(self, keep_days=365):
        """清理过于陈旧的数据（可选）"""
        # 目前保留所有数据，不做清理
        pass
    
    def export_training_data(self, output_format="json"):
        """导出为训练数据
        
        格式:
            json: 完整导出
            csv: 信号-结果扁平化（适合ML训练）
        """
        if output_format == "json":
            return self._data
        elif output_format == "csv":
            lines = ["date,signal_type,sector,direction,confidence,result"]
            for sid, signal in self._data["signals"].items():
                d = signal["data"]
                outcome = "unknown"
                if signal["outcome"]:
                    outcome = signal["outcome"][-1]["result"]
                lines.append(
                    f"{signal['date']},{signal['signal_type']},"
                    f"{d.get('sector','')},{d.get('direction','')},"
                    f"{d.get('confidence',0)},{outcome}"
                )
            return "\n".join(lines)
        return None


# =====================================================================
# 命令行接口
# =====================================================================

def cmd_record(args):
    """记录今日快照"""
    import subprocess, sys as _sys
    
    memory = TradingMemory()
    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    
    print(f"📀 记录 {date_str} 市场快照...", file=_sys.stderr)
    
    # 尝试通过stock_data.py获取数据
    collector_path = os.path.join(SKILL_DIR, "scripts", "collector.py")
    stock_tool_path = os.path.join(os.path.dirname(SKILL_DIR), "tools", "stock_data.py")
    
    snapshot = {
        "indexes": [],
        "sentiment": {},
        "volume": 0,
        "top_sectors": [],
        "top_gainers": [],
        "top_losers": [],
        "big_flow_stocks": [],
        "market_state": "neutral",
    }
    
    # 1. 采集大盘指数
    try:
        r = subprocess.run([_sys.executable, stock_tool_path, "indexes"],
                          capture_output=True, text=True, timeout=30)
        if r.stdout.strip():
            indexes = json.loads(r.stdout)
            snapshot["indexes"] = indexes if isinstance(indexes, list) else []
    except Exception as e:
        print(f"  ⚠️ 指数采集失败: {e}", file=_sys.stderr)
    
    # 2. 采集涨跌家数
    try:
        r = subprocess.run([_sys.executable, stock_tool_path, "updown"],
                          capture_output=True, text=True, timeout=30)
        if r.stdout.strip():
            snapshot["sentiment"] = json.loads(r.stdout)
    except Exception as e:
        print(f"  ⚠️ 涨跌家数采集失败: {e}", file=_sys.stderr)
    
    # 3. 采集涨跌停
    try:
        r = subprocess.run([_sys.executable, stock_tool_path, "limits"],
                          capture_output=True, text=True, timeout=30)
        if r.stdout.strip():
            try:
                limits = json.loads(r.stdout)
                if isinstance(snapshot["sentiment"], dict):
                    snapshot["sentiment"].update(limits)
                else:
                    snapshot["sentiment"] = limits
            except:
                pass
    except Exception as e:
        print(f"  ⚠️ 涨跌停采集失败: {e}", file=_sys.stderr)
    
    # 4. 采集板块
    try:
        r = subprocess.run([_sys.executable, stock_tool_path, "sector_flow"],
                          capture_output=True, text=True, timeout=30)
        if r.stdout.strip():
            sectors = json.loads(r.stdout)
            if isinstance(sectors, dict):
                snapshot["top_sectors"] = sectors.get("涨幅榜", [])[:10]
    except:
        pass
    
    # 5. 采集涨幅榜
    try:
        r = subprocess.run([_sys.executable, stock_tool_path, "gainers", "--limit", "10"],
                          capture_output=True, text=True, timeout=30)
        if r.stdout.strip():
            snapshot["top_gainers"] = json.loads(r.stdout)
    except:
        pass
    
    # 6. 采集跌幅榜
    try:
        r = subprocess.run([_sys.executable, stock_tool_path, "losers", "--limit", "5"],
                          capture_output=True, text=True, timeout=30)
        if r.stdout.strip():
            snapshot["top_losers"] = json.loads(r.stdout)
    except:
        pass
    
    memory.record_snapshot(date_str, snapshot)
    print(f"✅ 已记录 {date_str} 市场快照", file=_sys.stderr)
    print(f"   大盘指数: {len(snapshot['indexes'])}个, 板块: {len(snapshot['top_sectors'])}个")


def cmd_record_signal(args):
    """记录交易信号"""
    memory = TradingMemory()
    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    
    signal_data = {
        "direction": args.direction or "bullish",
        "confidence": float(args.confidence or 0.6),
        "sector": args.sector or "未知",
        "description": args.description or "",
        "trigger_reason": args.reason or "",
    }
    
    sid = memory.record_signal(date_str, args.type, signal_data)
    print(f"✅ 已记录信号: {sid}")


def cmd_record_outcome(args):
    """记录信号结果"""
    memory = TradingMemory()
    ok = memory.record_outcome(args.signal_id, args.result, args.details or "")
    if ok:
        print(f"✅ 已记录信号 {args.signal_id} 的结果: {args.result}")
    else:
        print(f"❌ 信号 {args.signal_id} 不存在")


def cmd_query(args):
    """查询历史数据"""
    memory = TradingMemory()
    if args.date:
        snap = memory.get_snapshot(args.date)
        if snap:
            print(json.dumps(snap, ensure_ascii=False, indent=2))
        else:
            print(f"⚠️ 没有 {args.date} 的数据")
    else:
        recent = memory.get_recent_snapshots(args.days or 30)
        print(f"📀 最近 {len(recent)} 个交易日记录:")
        for date_str, snap in recent:
            data = snap.get("data", {})
            sentiment = data.get("sentiment", {})
            up = sentiment.get("上涨", "?")
            down = sentiment.get("下跌", "?")
            lu = sentiment.get("涨停", "?")
            ld = sentiment.get("跌停", "?")
            idx = data.get("indexes", [])
            sh = next((i for i in idx if "上证" in i.get("指数","")), {})
            sh_str = f" 上证{sh.get('最新','?')}({sh.get('涨跌幅','?'):+.2f}%)" if sh.get('最新') else ""
            print(f"  {date_str}: 涨{up}/跌{down} | 涨停{lu}/跌停{ld} {sh_str}")


def cmd_stats(args):
    """知识库统计"""
    memory = TradingMemory()
    meta = memory._data["meta"]
    print(f"📊 交易知识库统计")
    print(f"════════════════════════")
    print(f"  记录天数:     {meta['total_days_recorded']}")
    print(f"  总信号数:     {meta['total_signals_recorded']}")
    print(f"  已验证信号数: {meta['total_outcomes_recorded']}")
    print(f"  最后更新:     {meta['last_updated']}")
    print()
    
    stats = memory.get_signal_stats()
    if stats:
        print(f"📈 各信号类型胜率:")
        for st, s in sorted(stats.items(), key=lambda x: x[1]["win_rate"], reverse=True):
            print(f"  {st:20s} 总{s['total']:3d} 正确{s['correct']:3d} 错误{s['wrong']:2d} 待验证{s['pending']:3d} 胜率{s['win_rate']:5.1f}%")
    
    print()
    sector_rates = memory.get_sector_win_rates()
    if sector_rates:
        print(f"📈 板块信号胜率TOP10:")
        for s in sector_rates[:10]:
            print(f"  {s['sector']:12s} 总{s['total']:3d} 正确{s['correct']:3d} 胜率{s['win_rate']:5.1f}%")


def cmd_export(args):
    """导出训练数据"""
    memory = TradingMemory()
    fmt = args.format or "json"
    data = memory.export_training_data(fmt)
    if data:
        print(data)
    else:
        print("⚠️ 导出失败", file=sys.stderr)


def cmd_review_outcomes(args):
    """自动验证今日之前的信号（批量处理待验证信号）
    
    对每个pending信号，检查信号发出日期的数据，
    并与后续日期数据进行对比，自动判断信号是否正确。
    """
    memory = TradingMemory()
    pending = memory.get_pending_signals()
    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    
    print(f"🔍 正在验证 {len(pending)} 个待验证信号...", file=sys.stderr)
    
    verified_count = 0
    for signal in pending:
        sig_date = signal["date"]
        signal_data = signal["data"]
        direction = signal_data.get("direction", "")
        sector = signal_data.get("sector", "")
        
        # 获取信号日的次日市场数据（如果存在）
        snapshots = memory._data["daily_snapshots"]
        dates = sorted(snapshots.keys())
        
        try:
            idx = dates.index(sig_date)
            if idx + 1 < len(dates):
                next_date = dates[idx + 1]
                next_snap = snapshots[next_date]
                next_data = next_snap.get("data", {})
                
                # 判断：如果方向是bullish，看次日大盘是否涨
                if direction == "bullish":
                    indexes = next_data.get("indexes", [])
                    sh = next((i for i in indexes if "上证" in i.get("指数","")), {})
                    change = sh.get("涨跌幅", 0)
                    if change > 0.3:
                        result = "correct"
                    elif change < -0.3:
                        result = "wrong"
                    else:
                        result = "partial"
                elif direction == "bearish":
                    indexes = next_data.get("indexes", [])
                    sh = next((i for i in indexes if "上证" in i.get("指数","")), {})
                    change = sh.get("涨跌幅", 0)
                    if change < -0.3:
                        result = "correct"
                    elif change > 0.3:
                        result = "wrong"
                    else:
                        result = "partial"
                else:
                    result = "insufficient_data"
                
                details = f"自动验证: 信号日{sig_date}→验证日{next_date}，大盘涨幅{sh.get('涨跌幅',0):+.2f}%"
                memory.record_outcome(signal["signal_id"], result, details)
                verified_count += 1
        except (ValueError, IndexError):
            pass
    
    print(f"✅ 已验证 {verified_count} 个信号")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="📀 交易知识库")
    sub = parser.add_subparsers(dest="command", required=True)
    
    # record
    p_record = sub.add_parser("record", help="记录每日快照")
    p_record.add_argument("--date", help="日期 YYYY-MM-DD")
    p_record.set_defaults(func=cmd_record)
    
    # record_signal
    p_sig = sub.add_parser("record_signal", help="记录交易信号")
    p_sig.add_argument("--type", required=True, help="信号类型")
    p_sig.add_argument("--direction", choices=["bullish","bearish","neutral"])
    p_sig.add_argument("--confidence", default="0.6")
    p_sig.add_argument("--sector", help="关联板块")
    p_sig.add_argument("--description", help="描述")
    p_sig.add_argument("--reason", help="触发原因")
    p_sig.add_argument("--date")
    p_sig.set_defaults(func=cmd_record_signal)
    
    # record_outcome
    p_out = sub.add_parser("record_outcome", help="记录信号结果")
    p_out.add_argument("signal_id")
    p_out.add_argument("--result", required=True, choices=["correct","wrong","partial","insufficient_data"])
    p_out.add_argument("--details")
    p_out.set_defaults(func=cmd_record_outcome)
    
    # query
    p_q = sub.add_parser("query", help="查询历史")
    p_q.add_argument("--date", help="具体日期")
    p_q.add_argument("--days", type=int, default=30, help="最近N天")
    p_q.set_defaults(func=cmd_query)
    
    # stats
    p_st = sub.add_parser("stats", help="知识库统计")
    p_st.set_defaults(func=cmd_stats)
    
    # export
    p_exp = sub.add_parser("export", help="导出训练数据")
    p_exp.add_argument("--format", choices=["json","csv"], default="json")
    p_exp.set_defaults(func=cmd_export)
    
    # review_outcomes
    p_rv = sub.add_parser("review_outcomes", help="自动验证待处理信号")
    p_rv.add_argument("--date")
    p_rv.set_defaults(func=cmd_review_outcomes)
    
    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()
