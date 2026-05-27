#!/usr/bin/env python3
"""
🧠 策略学习引擎 — 从历史数据中发现交易模式
========================================
功能：
- 分析历史知识库，提取可重复的交易模式
- 计算各种信号的胜率/赔率/置信度
- 生成"如果A→那么B"形式的交易规则
- 市场状态分类（强/弱/震荡/极端）
- 输出最优策略推荐（供复盘报告使用）

用法:
  python strategy_learner.py learn                     # 学习新模式
  python strategy_learner.py rules [--min-confidence 0.6]  # 输出学习到的规则
  python strategy_learner.py top_strategies [--top-k 5]    # 最优策略排行
  python strategy_learner.py sector_patterns               # 板块轮动模式
  python strategy_learner.py market_state_classify          # 市场状态分类
  python strategy_learner.py daily_strategy [--date ...]    # 当日推荐策略
"""

import json, os, sys, math
from datetime import datetime, timedelta
from collections import defaultdict, Counter

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY_FILE = os.path.join(SKILL_DIR, "data", "trading_memory.json")


# =====================================================================
# 策略学习引擎
# =====================================================================

class StrategyLearner:
    """策略学习引擎"""
    
    def __init__(self, memory_file=None):
        self.memory_file = memory_file or MEMORY_FILE
        self.memory = self._load_memory()
        self.snapshots = self.memory.get("daily_snapshots", {})
        self.signals = self.memory.get("signals", {})
        self.patterns = self.memory.get("patterns", {})
    
    def _load_memory(self):
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return {"daily_snapshots": {}, "signals": {}, "patterns": {}}
    
    # ==================== 核心学习算法 ====================
    
    def learn_all(self):
        """执行全部学习任务"""
        results = {
            "timestamp": datetime.now().isoformat(),
            "learned_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "sector_flow_patterns": self._learn_sector_flow_patterns(),
            "limit_up_patterns": self._learn_limit_up_patterns(),
            "market_correlation": self._learn_market_correlation(),
            "volume_patterns": self._learn_volume_patterns(),
            "sector_rotation": self._learn_sector_rotation(),
            "day_of_week_effect": self._learn_day_of_week_effect(),
            "signal_strategy_performance": self._learn_from_signals(),
            "rules": [],
        }
        
        # 将学习到的规则存入持久化
        rules = self._generate_rules(results)
        results["rules"] = rules
        self._store_rules(rules)
        
        return results
    
    def _learn_sector_flow_patterns(self):
        """学习板块资金流向模式
        
        核心逻辑：板块当日资金流入TOP3，次日是否持续
        """
        if len(self.snapshots) < 2:
            return {"status": "数据不足", "patterns": []}
        
        dates = sorted(self.snapshots.keys())
        patterns = []
        
        for i in range(len(dates) - 1):
            today = dates[i]
            tomorrow = dates[i + 1]
            
            today_data = self.snapshots[today].get("data", {})
            tomorrow_data = self.snapshots[tomorrow].get("data", {})
            
            today_sectors = today_data.get("top_sectors", [])[:5]
            tomorrow_sectors = {s.get("name",""): s.get("change%",0) 
                               for s in tomorrow_data.get("top_sectors", [])}
            
            for sector in today_sectors:
                name = sector.get("板块名称", sector.get("name", ""))
                change = sector.get("涨跌幅", sector.get("change%", 0))
                # 获取板块资金流入
                flow = sector.get("主力净流入", sector.get("flow", 0))
                
                if name and name in tomorrow_sectors:
                    next_change = tomorrow_sectors[name]
                    continued = (change > 0 and next_change > 0) or (change < 0 and next_change < 0)
                    
                    patterns.append({
                        "sector": name,
                        "today_change": change,
                        "tomorrow_change": next_change,
                        "flow": flow,
                        "continued": continued,
                        "date": today,
                    })
        
        # 按板块统计持续性概率
        sector_stats = defaultdict(list)
        for p in patterns:
            sector_stats[p["sector"]].append(p)
        
        result_patterns = []
        for sector, pts in sector_stats.items():
            if len(pts) >= 2:  # 至少2个样本
                continued = sum(1 for p in pts if p["continued"])
                continuity_rate = continued / len(pts) * 100
                avg_change_today = sum(p["today_change"] for p in pts) / len(pts)
                avg_change_tomorrow = sum(p["tomorrow_change"] for p in pts) / len(pts)
                avg_flow = sum(p["flow"] for p in pts if isinstance(p["flow"], (int, float))) / len(pts)
                
                result_patterns.append({
                    "sector": sector,
                    "samples": len(pts),
                    "continuity_rate": round(continuity_rate, 1),
                    "avg_change": round(avg_change_today, 2),
                    "avg_next_day_change": round(avg_change_tomorrow, 2),
                    "avg_flow": round(avg_flow / 1e8, 2) if isinstance(avg_flow, (int, float)) else 0,
                    "direction": "持续性强" if continuity_rate >= 60 else ("持续性一般" if continuity_rate >= 40 else "持续性差"),
                })
        
        result_patterns.sort(key=lambda x: x["continuity_rate"], reverse=True)
        
        return {
            "status": "完成",
            "total_samples": len(patterns),
            "patterns": result_patterns[:20],  # TOP20
        }
    
    def _learn_limit_up_patterns(self):
        """学习涨停密度对次日的影响
        
        规律：涨停数多/少 → 次日情绪延续还是反转
        """
        if len(self.snapshots) < 3:
            return {"status": "数据不足", "patterns": []}
        
        dates = sorted(self.snapshots.keys())
        patterns = []
        
        for i in range(len(dates) - 1):
            today = dates[i]
            tomorrow = dates[i + 1]
            
            today_data = self.snapshots[today].get("data", {})
            tomorrow_data = self.snapshots[tomorrow].get("data", {})
            
            t_senti = today_data.get("sentiment", {})
            t_senti = t_senti if isinstance(t_senti, dict) else {}
            
            n_senti = tomorrow_data.get("sentiment", {})
            n_senti = n_senti if isinstance(n_senti, dict) else {}
            
            limit_up = t_senti.get("涨停", 0) or t_senti.get("limit_up", 0)
            limit_down = t_senti.get("跌停", 0) or t_senti.get("limit_down", 0)
            
            tomorrow_lu = n_senti.get("涨停", 0) or n_senti.get("limit_up", 0)
            tomorrow_ld = n_senti.get("跌停", 0) or n_senti.get("limit_down", 0)
            
            # 今日指数
            t_idx = today_data.get("indexes", [])
            n_idx = tomorrow_data.get("indexes", [])
            t_sh = next((i for i in t_idx if "上证" in i.get("指数","")), {})
            n_sh = next((i for i in n_idx if "上证" in i.get("指数","")), {})
            
            patterns.append({
                "date": today,
                "limit_up": limit_up,
                "limit_down": limit_down,
                "tomorrow_limit_up": tomorrow_lu,
                "tomorrow_limit_down": tomorrow_ld,
                "today_sh_change": t_sh.get("涨跌幅", 0),
                "tomorrow_sh_change": n_sh.get("涨跌幅", 0),
            })
        
        # 分析：涨停数阈值
        if len(patterns) < 3:
            return {"status": "样本不足", "patterns": patterns}
        
        # 涨停数分区间统计次日表现
        thresholds = [(0, 20, "涨停<20"), (20, 40, "涨停20-40"), (40, 60, "涨停40-60"), 
                      (60, 80, "涨停60-80"), (80, 200, "涨停>80")]
        
        threshold_analysis = []
        for lo, hi, label in thresholds:
            group = [p for p in patterns if lo <= p["limit_up"] < hi]
            if len(group) >= 2:
                avg_tomorrow_chg = sum(p["tomorrow_sh_change"] for p in group) / len(group)
                avg_tomorrow_lu = sum(p["tomorrow_limit_up"] for p in group) / len(group)
                pos_days = sum(1 for p in group if p["tomorrow_sh_change"] > 0)
                pos_rate = pos_days / len(group) * 100
                threshold_analysis.append({
                    "range": label,
                    "samples": len(group),
                    "avg_tomorrow_change": round(avg_tomorrow_chg, 2),
                    "avg_tomorrow_limit_up": round(avg_tomorrow_lu, 1),
                    "positive_rate": round(pos_rate, 1),
                    "verdict": "偏多" if pos_rate > 55 else ("偏空" if pos_rate < 45 else "中性"),
                })
        
        # 分析：涨停/跌停比
        ratio_analysis = []
        for ratio_threshold in [1.5, 2.0, 3.0, 5.0]:
            group = [p for p in patterns if p["limit_up"] > 0 and p["limit_down"] > 0 
                    and p["limit_up"] / p["limit_down"] >= ratio_threshold]
            if len(group) >= 2:
                avg_tomorrow_chg = sum(p["tomorrow_sh_change"] for p in group) / len(group)
                pos_days = sum(1 for p in group if p["tomorrow_sh_change"] > 0)
                pos_rate = pos_days / len(group) * 100
                ratio_analysis.append({
                    "condition": f"涨停/跌停≥{ratio_threshold}",
                    "samples": len(group),
                    "avg_tomorrow_change": round(avg_tomorrow_chg, 2),
                    "positive_rate": round(pos_rate, 1),
                })
        
        return {
            "status": "完成",
            "total_samples": len(patterns),
            "threshold_analysis": threshold_analysis,
            "ratio_analysis": ratio_analysis,
        }
    
    def _learn_market_correlation(self):
        """学习市场关联性
        
        今日XX板块涨 → 明日YY板块可能涨
        """
        if len(self.snapshots) < 5:
            return {"status": "数据不足", "correlations": []}
        
        dates = sorted(self.snapshots.keys())
        
        # 构建板块日收益率矩阵
        sector_returns = {}  # {sector_name: [returns_by_day]}  
        sector_dates = []
        
        for date_str in dates:
            data = self.snapshots[date_str].get("data", {})
            sectors = data.get("top_sectors", [])
            if not sectors:
                continue
            sector_dates.append(date_str)
            for s in sectors:
                name = s.get("板块名称", s.get("name", ""))
                change = s.get("涨跌幅", s.get("change%", 0))
                if name:
                    if name not in sector_returns:
                        sector_returns[name] = []
                    sector_returns[name].append((date_str, change))
        
        # 计算滞后相关性（当日A板块→次日B板块）
        correlations = []
        sectors_list = list(sector_returns.keys())
        
        for a in sectors_list:
            a_data = sector_returns[a]
            a_map = dict(a_data)
            
            for b in sectors_list:
                if a == b:
                    continue
                b_data = sector_returns[b]
                b_map = dict(b_data)
                
                matched_pairs = []
                for i in range(len(sector_dates) - 1):
                    today = sector_dates[i]
                    tomorrow = sector_dates[i + 1]
                    if today in a_map and tomorrow in b_map:
                        matched_pairs.append((a_map[today], b_map[tomorrow]))
                
                if len(matched_pairs) >= 3:
                    # 简单相关性：A涨时B次日也涨的概率
                    a_up_days = [(a_chg, b_chg) for a_chg, b_chg in matched_pairs if a_chg > 0]
                    a_down_days = [(a_chg, b_chg) for a_chg, b_chg in matched_pairs if a_chg < 0]
                    
                    if a_up_days:
                        b_follow_up = sum(1 for _, b_chg in a_up_days if b_chg > 0)
                        follow_rate = b_follow_up / len(a_up_days) * 100
                    else:
                        follow_rate = 0
                    
                    if len(a_up_days) >= 3:
                        correlations.append({
                            "from": a,
                            "to": b,
                            "samples": len(a_up_days),
                            "follow_rate": round(follow_rate, 1),
                            "verdict": "强正相关" if follow_rate > 60 else ("弱正相关" if follow_rate > 50 else "无显著相关"),
                        })
        
        correlations.sort(key=lambda x: x["follow_rate"], reverse=True)
        return {
            "status": "完成",
            "total_correlations": len(correlations),
            "top_correlations": correlations[:15],
        }
    
    def _learn_volume_patterns(self):
        """学习成交量模式"""
        if len(self.snapshots) < 3:
            return {"status": "数据不足"}
        
        dates = sorted(self.snapshots.keys())
        volumes = []
        
        for date_str in dates:
            data = self.snapshots[date_str].get("data", {})
            vol = data.get("volume", 0)
            if vol and vol > 0:
                volumes.append((date_str, vol))
        
        if len(volumes) < 3:
            return {"status": "数据不足"}
        
        # 计算放量缩量对次日的影响
        vol_changes = []
        for i in range(len(volumes) - 2):
            today_vol = volumes[i][1]
            prev_vol = volumes[i-1][1] if i > 0 else today_vol
            
            if prev_vol > 0:
                vol_change = (today_vol - prev_vol) / prev_vol * 100
            else:
                vol_change = 0
            
            tomorrow_data = self.snapshots.get(volumes[i+1][0], {}).get("data", {})
            t_idx = tomorrow_data.get("indexes", [])
            t_sh = next((i for i in t_idx if "上证" in i.get("指数","")), {})
            tomorrow_chg = t_sh.get("涨跌幅", 0)
            
            vol_changes.append({
                "date": volumes[i][0],
                "volume": today_vol,
                "vol_change_pct": round(vol_change, 1),
                "tomorrow_sh_change": tomorrow_chg,
            })
        
        # 放量>15%时的次日表现
        big_vol = [v for v in vol_changes if abs(v["vol_change_pct"]) > 15]
        shrink_vol = [v for v in vol_changes if v["vol_change_pct"] < -15]
        
        big_vol_positive = sum(1 for v in big_vol if v["tomorrow_sh_change"] > 0) / max(len(big_vol), 1) * 100
        shrink_vol_positive = sum(1 for v in shrink_vol if v["tomorrow_sh_change"] > 0) / max(len(shrink_vol), 1) * 100
        
        return {
            "status": "完成",
            "total_samples": len(vol_changes),
            "big_volume_next_day_positive_rate": round(big_vol_positive, 1),
            "shrink_volume_next_day_positive_rate": round(shrink_vol_positive, 1),
            "insight": f"放量日次日上涨概率{big_vol_positive:.0f}%，缩量日次日上涨概率{shrink_vol_positive:.0f}%"
        }
    
    def _learn_sector_rotation(self):
        """学习板块轮动模式（T日TOP板块 → T+1日新TOP板块）"""
        if len(self.snapshots) < 3:
            return {"status": "数据不足", "rotation_patterns": []}
        
        dates = sorted(self.snapshots.keys())
        rotation_count = defaultdict(int)
        
        for i in range(len(dates) - 1):
            today = dates[i]
            tomorrow = dates[i + 1]
            
            today_data = self.snapshots[today].get("data", {})
            tomorrow_data = self.snapshots[tomorrow].get("data", {})
            
            t_sectors = [s.get("板块名称", s.get("name", "")) for s in today_data.get("top_sectors", [])[:3]]
            n_sectors = [s.get("板块名称", s.get("name", "")) for s in tomorrow_data.get("top_sectors", [])[:3]]
            
            # 计算轮换：今日TOP中有几个明日还在TOP
            retained = set(t_sectors) & set(n_sectors)
            
            # 新出现的板块
            new_sectors = [s for s in n_sectors if s not in t_sectors]
            
            rotation_count["same_count"] = rotation_count.get("same_count", 0) + len(retained)
            rotation_count["total_count"] = rotation_count.get("total_count", 0) + 3
            
            for ns in new_sectors:
                key = f"切换至{ns}"
                rotation_count[key] = rotation_count.get(key, 0) + 1
        
        total_checks = rotation_count.get("total_count", 1)
        same_rate = rotation_count.get("same_count", 0) / total_checks * 100
        
        return {
            "status": "完成",
            "total_days": len(dates),
            "top3_retention_rate": round(same_rate, 1),
            "insight": f"TOP3板块次日留存率{same_rate:.0f}%，说明板块持续性{'强' if same_rate > 40 else '一般' if same_rate > 25 else '弱'}"
        }
    
    def _learn_day_of_week_effect(self):
        """学习星期效应"""
        if len(self.snapshots) < 5:
            return {"status": "数据不足"}
        
        dow_stats = defaultdict(list)
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        
        for date_str, snapshot in self.snapshots.items():
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                dow = dt.weekday()
                data = snapshot.get("data", {})
                indexes = data.get("indexes", [])
                sh = next((i for i in indexes if "上证" in i.get("指数","")), {})
                change = sh.get("涨跌幅", 0)
                if change != 0:
                    dow_stats[dow].append(change)
            except:
                continue
        
        results = []
        for dow in range(5):  # 周一到周五
            changes = dow_stats.get(dow, [])
            if len(changes) >= 2:
                avg_chg = sum(changes) / len(changes)
                pos_days = sum(1 for c in changes if c > 0)
                pos_rate = pos_days / len(changes) * 100
                results.append({
                    "day": weekdays[dow],
                    "samples": len(changes),
                    "avg_change": round(avg_chg, 2),
                    "positive_rate": round(pos_rate, 1),
                })
        
        return {
            "status": "完成",
            "patterns": results,
        }
    
    def _learn_from_signals(self):
        """从历史信号中学习策略表现"""
        from collections import defaultdict
        stats = defaultdict(lambda: {"total": 0, "correct": 0, "wrong": 0, "partial": 0})
        
        for sid, signal in self.signals.items():
            st = signal["signal_type"]
            outcomes = signal.get("outcome")
            if outcomes:
                latest = outcomes[-1]["result"]
                stats[st]["total"] += 1
                if latest == "correct":
                    stats[st]["correct"] += 1
                elif latest == "wrong":
                    stats[st]["wrong"] += 1
                elif latest == "partial":
                    stats[st]["partial"] += 1
        
        result = []
        for st, s in stats.items():
            total_valid = s["correct"] + s["wrong"]
            if total_valid >= 2:
                win_rate = s["correct"] / total_valid * 100
                result.append({
                    "signal_type": st,
                    "total": s["total"],
                    "correct": s["correct"],
                    "wrong": s["wrong"],
                    "partial": s["partial"],
                    "win_rate": round(win_rate, 1),
                })
        
        result.sort(key=lambda x: x["win_rate"], reverse=True)
        return result
    
    def _generate_rules(self, learn_results):
        """生成可执行的交易规则"""
        rules = []
        
        # 从板块资金流模式生成规则
        flow_patterns = learn_results.get("sector_flow_patterns", {}).get("patterns", [])
        for p in flow_patterns[:5]:
            if p["continuity_rate"] >= 60:
                rules.append({
                    "rule": f"当{p['sector']}板块涨幅>0且主力净流入>0",
                    "action": f"关注{p['sector']}板块次日持续性机会",
                    "confidence": round(p["continuity_rate"] / 100, 2),
                    "sample_size": p["samples"],
                    "source": "sector_flow_continuity"
                })
        
        # 从涨停模式生成规则
        limit_analysis = learn_results.get("limit_up_patterns", {})
        for r in limit_analysis.get("ratio_analysis", []):
            if r["positive_rate"] > 55:
                rules.append({
                    "rule": r["condition"],
                    "action": "次日市场偏多概率较高，可积极操作",
                    "confidence": round(r["positive_rate"] / 100, 2),
                    "sample_size": r["samples"],
                    "source": "limit_up_ratio"
                })
        
        # 从板块关联生成规则
        corr = learn_results.get("market_correlation", {}).get("top_correlations", [])
        for c in corr[:5]:
            if c["follow_rate"] >= 60:
                rules.append({
                    "rule": f"当{c['from']}板块上涨",
                    "action": f"关注{c['to']}板块次日的跟涨机会",
                    "confidence": round(c["follow_rate"] / 100, 2),
                    "sample_size": c["samples"],
                    "source": "sector_correlation"
                })
        
        # 从星期效应生成规则
        dow = learn_results.get("day_of_week_effect", {}).get("patterns", [])
        for d in dow:
            if d["positive_rate"] >= 60:
                rules.append({
                    "rule": f"{d['day']}效应",
                    "action": f"历史上{d['day']}上涨概率{d['positive_rate']:.0f}%，可偏多操作",
                    "confidence": round(d["positive_rate"] / 100, 2),
                    "sample_size": d["samples"],
                    "source": "day_of_week"
                })
            elif d["positive_rate"] <= 40:
                rules.append({
                    "rule": f"{d['day']}效应",
                    "action": f"历史上{d['day']}上涨概率仅{d['positive_rate']:.0f}%，需谨慎",
                    "confidence": round((100 - d["positive_rate"]) / 100, 2),
                    "sample_size": d["samples"],
                    "source": "day_of_week"
                })
        
        # 从成交量学习结果生成规则
        vol = learn_results.get("volume_patterns", {})
        if vol.get("big_volume_next_day_positive_rate", 0) > 0:
            rules.append({
                "rule": "放量日次日",
                "action": f"放量超15%次日上涨概率{vol['big_volume_next_day_positive_rate']:.0f}%",
                "confidence": round(vol.get("big_volume_next_day_positive_rate", 50) / 100, 2),
                "source": "volume_pattern"
            })
        
        # 从历史信号绩效生成规则
        sig_perf = learn_results.get("signal_strategy_performance", [])
        for s in sig_perf[:3]:
            if s["win_rate"] >= 60:
                rules.append({
                    "rule": f"信号类型 '{s['signal_type']}'",
                    "action": f"历史胜率{s['win_rate']:.0f}%（{s['correct']}/{s['correct']+s['wrong']}）",
                    "confidence": round(s["win_rate"] / 100, 2),
                    "sample_size": s["total"],
                    "source": "signal_history"
                })
        
        # 按置信度排序
        rules.sort(key=lambda x: x["confidence"], reverse=True)
        return rules
    
    def _store_rules(self, rules):
        """将规则存入持久化"""
        self.memory["patterns"]["learned_rules"] = rules
        self.memory["meta"]["last_learning"] = datetime.now().isoformat()
        os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
        with open(self.memory_file, "w", encoding="utf-8") as f:
            json.dump(self.memory, f, ensure_ascii=False, indent=2)
    
    # ==================== 输出接口 ====================
    
    def get_rules(self, min_confidence=0.6):
        """获取学习到的规则"""
        rules = self.memory.get("patterns", {}).get("learned_rules", [])
        return [r for r in rules if r.get("confidence", 0) >= min_confidence]
    
    def get_top_strategies(self, top_k=5):
        """获取最优策略（整合所有来源）"""
        rules = self.get_rules(0.6)
        strategies = []
        
        for r in rules[:top_k]:
            strategies.append({
                "rank": len(strategies) + 1,
                "strategy": r["action"],
                "condition": r["rule"],
                "confidence": r.get("confidence", 0),
                "samples": r.get("sample_size", 0),
                "source": r.get("source", ""),
            })
        
        return strategies
    
    def get_sector_patterns(self):
        """获取板块轮动模式"""
        patterns = self.memory.get("patterns", {}).get("sector_flow_continuity", [])
        if patterns:
            return patterns[-5:]
        return []
    
    def get_daily_strategy(self, date_str=None):
        """生成当日策略推荐
        
        综合所有学习到的规则，结合当前市场状态，推荐今日具体策略
        """
        date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        
        # 1. 获取今天的市场快照（如果已记录）
        today_snapshot = self.snapshots.get(date_str, {})
        today_data = today_snapshot.get("data", {})
        
        # 2. 获取所有规则
        rules = self.get_rules()
        
        # 3. 获取星期效应
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][dt.weekday()]
        except:
            weekday = ""
        
        # 4. 构造策略
        strategies = []
        
        # 星期策略
        try:
            learner_result = self._learn_day_of_week_effect()
            dow_patterns = learner_result.get("patterns", [])
            for d in dow_patterns:
                if d["day"] == weekday:
                    strategies.append({
                        "type": "星期效应",
                        "name": f"{weekday}策略",
                        "actions": f"历史上{weekday}平均涨跌{d['avg_change']:+.2f}%，上涨概率{d['positive_rate']:.0f}%",
                        "confidence": round(d["positive_rate"] / 100, 2),
                    })
        except:
            pass
        
        # 高置信度规则
        for r in rules[:3]:
            strategies.append({
                "type": r.get("source", "历史模式"),
                "name": r["rule"],
                "actions": r["action"],
                "confidence": r.get("confidence", 0.5),
            })
        
        # 今日板块建议
        today_sectors = today_data.get("top_sectors", [])
        if today_sectors:
            top_sectors_name = [s.get("板块名称", s.get("name", "")) for s in today_sectors[:3]]
            strategies.append({
                "type": "当日追踪",
                "name": "今日领涨板块追踪",
                "actions": f"重点关注: {'、'.join(top_sectors_name)} 的持续性",
                "confidence": 0.6,
            })
        
        return {
            "date": date_str,
            "weekday": weekday,
            "total_rules_available": len(rules),
            "strategies": strategies,
        }
    
    def classify_market_state(self):
        """市场状态分类（强/弱/震荡/极端）"""
        if len(self.snapshots) < 3:
            return {"status": "数据不足"}
        
        dates = sorted(self.snapshots.keys())
        recent = dates[-min(20, len(dates)):]  # 最近20个交易日
        
        changes = []
        limit_ups = []
        up_ratios = []
        
        for date_str in recent:
            data = self.snapshots[date_str].get("data", {})
            indexes = data.get("indexes", [])
            sh = next((i for i in indexes if "上证" in i.get("指数","")), {})
            change = sh.get("涨跌幅", 0)
            if change != 0:
                changes.append(change)
            
            senti = data.get("sentiment", {})
            if isinstance(senti, dict):
                lu = senti.get("涨停", 0) or senti.get("limit_up", 0)
                ld = senti.get("跌停", 0) or senti.get("limit_down", 0)
                up = senti.get("上涨", 0) or senti.get("up", 0)
                down = senti.get("下跌", 0) or senti.get("down", 1)
                limit_ups.append(lu)
                up_ratios.append(up / (up + down) if (up + down) > 0 else 0.5)
        
        if not changes:
            return {"status": "数据不足"}
        
        avg_change = sum(changes) / len(changes)
        avg_lu = sum(limit_ups) / max(len(limit_ups), 1)
        avg_up_ratio = sum(up_ratios) / max(len(up_ratios), 1)
        
        # 波动率
        variance = sum((c - avg_change) ** 2 for c in changes) / len(changes)
        volatility = math.sqrt(variance)
        
        # 分类
        if avg_change > 0.5 and avg_lu > 50 and avg_up_ratio > 0.6:
            state = "强势"
            description = "近期市场赚钱效应明显，可积极参与"
        elif avg_change > 0.2 and avg_lu > 40:
            state = "偏多"
            description = "市场情绪偏暖，结构性机会较多"
        elif avg_change < -0.5 and avg_up_ratio < 0.4:
            state = "弱势"
            description = "市场持续走弱，需控制仓位"
        elif avg_change < -0.2:
            state = "偏空"
            description = "市场承压，观望为主"
        elif volatility > 1.0:
            state = "高波动"
            description = "市场波动加大，注意风险管理"
        else:
            state = "震荡"
            description = "市场震荡整理，适合高抛低吸"
        
        return {
            "state": state,
            "avg_daily_change": round(avg_change, 2),
            "avg_limit_up": round(avg_lu, 1),
            "avg_up_ratio": round(avg_up_ratio * 100, 1),
            "volatility": round(volatility, 3),
            "period": f"{recent[0]}~{recent[-1]}",
            "description": description,
        }
    
    def summary_for_report(self, date_str=None):
        """生成复盘报告用的策略总结（供html_ppt.py调用）"""
        date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        
        market_state = self.classify_market_state()
        top_strategies = self.get_top_strategies(5)
        daily_strategy = self.get_daily_strategy(date_str)
        sector_patterns = self._learn_sector_flow_patterns()
        
        return {
            "generated_at": datetime.now().isoformat(),
            "market_state": market_state,
            "top_strategies": top_strategies,
            "daily_strategies": daily_strategy.get("strategies", []),
            "sector_flow_insights": sector_patterns.get("patterns", [])[:5],
            "rules_count": len(self.get_rules()),
        }


# =====================================================================
# 命令行接口
# =====================================================================

def cmd_learn(args):
    learner = StrategyLearner()
    print("🧠 开始学习...", file=sys.stderr)
    results = learner.learn_all()
    
    # 输出摘要
    rules = results.get("rules", [])
    print(f"\n📋 已学习 {len(rules)} 条交易规则")
    print(f"\n🏆 高置信度规则 (confidence ≥ 0.6):")
    for r in rules:
        if r.get("confidence", 0) >= 0.6:
            print(f"  🔹 [{r['source']}] {r['rule']}")
            print(f"     → {r['action']} (置信度: {r['confidence']:.0%}, 样本: {r.get('sample_size','?')})")
    
    print(f"\n📈 板块连续性分析:")
    flow = results.get("sector_flow_patterns", {})
    for p in flow.get("patterns", [])[:5]:
        print(f"  {p['sector']}: 连续性{p['continuity_rate']:.0f}% (样本{p['samples']})")
    
    print(f"\n📊 涨停密度分析:")
    lim = results.get("limit_up_patterns", {})
    for r in lim.get("ratio_analysis", []):
        print(f"  {r['condition']}: 次日偏多概率{r['positive_rate']:.0f}%")
    
    print(f"\n📅 星期效应:")
    dow = results.get("day_of_week_effect", {}).get("patterns", [])
    for d in dow:
        print(f"  {d['day']}: 均值{d['avg_change']:+.2f}%, 上涨概率{d['positive_rate']:.0f}%")
    
    # 输出完整JSON if requested
    if args.json:
        print("\n" + "="*50)
        print(json.dumps(results, ensure_ascii=False, indent=2))
    
    # 保存完整学习结果
    out_file = os.path.join(SKILL_DIR, "data", "last_learn_result.json")
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 完整学习结果已保存至 {out_file}", file=sys.stderr)


def cmd_rules(args):
    learner = StrategyLearner()
    rules = learner.get_rules(min_confidence=args.min_confidence)
    
    print(f"📋 学习到的交易规则 (置信度 ≥ {args.min_confidence}):")
    print("=" * 60)
    for i, r in enumerate(rules, 1):
        print(f"\n  {i}. [{r.get('source','?')}] {r['rule']}")
        print(f"     → {r['action']}")
        print(f"     置信度: {r.get('confidence',0):.0%} | 样本量: {r.get('sample_size','?')} | {'✅ 可用' if r.get('confidence',0)>=0.6 else '⚠️ 仅供参考'}")


def cmd_top_strategies(args):
    learner = StrategyLearner()
    strategies = learner.get_top_strategies(args.top_k)
    
    print(f"🏆 TOP{args.top_k} 最优策略:")
    print("=" * 60)
    for s in strategies:
        print(f"\n  #{s['rank']} [{s['source']}]")
        print(f"  条件: {s['condition']}")
        print(f"  动作: {s['strategy']}")
        print(f"  置信度: {s['confidence']:.0%} (样本{s['samples']})")


def cmd_sector_patterns(args):
    learner = StrategyLearner()
    sector = learner._learn_sector_flow_patterns()
    
    print("📈 板块持续性分析:")
    print(f"{'板块':12s} {'样本':>5s} {'连续性':>8s} {'平均涨幅':>8s} {'次日涨幅':>8s} {'评分':>6s}")
    print("-" * 55)
    for p in sector.get("patterns", []):
        print(f"{p['sector']:12s} {p['samples']:5d} {p['continuity_rate']:7.1f}% {p['avg_change']:7.2f}% {p.get('avg_next_day_change',0):7.2f}% {p['direction'][:4]:>6s}")


def cmd_daily_strategy(args):
    learner = StrategyLearner()
    strategy = learner.get_daily_strategy(args.date)
    
    print(f"📋 {strategy['date']} ({strategy['weekday']}) 当日策略推荐:")
    print(f"   可用规则: {strategy['total_rules_available']}条")
    print()
    
    for s in strategy.get("strategies", []):
        conf_str = f"({s.get('confidence',0):.0%})" if s.get('confidence') else ""
        print(f"  🔹 [{s['type']}] {s['name']} {conf_str}")
        print(f"     → {s['actions']}")
        print()


def cmd_market_state(args):
    learner = StrategyLearner()
    state = learner.classify_market_state()
    
    if state.get("status") == "数据不足":
        print("⚠️ 数据不足，无法分类")
        return
    
    print(f"📊 市场状态分类")
    print(f"   状态: {state['state']}")
    print(f"   周期: {state['period']}")
    print(f"   日均涨跌: {state['avg_daily_change']:+.2f}%")
    print(f"   日均涨停: {state['avg_limit_up']:.0f}家")
    print(f"   日均涨跌比: {state['avg_up_ratio']:.0f}%")
    print(f"   波动率: {state['volatility']}")
    print(f"   判断: {state['description']}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="🧠 策略学习引擎")
    sub = parser.add_subparsers(dest="command", required=True)
    
    p_learn = sub.add_parser("learn", help="执行全部学习任务")
    p_learn.add_argument("--json", action="store_true", help="输出完整JSON")
    p_learn.set_defaults(func=cmd_learn)
    
    p_rules = sub.add_parser("rules", help="输出学习到的规则")
    p_rules.add_argument("--min-confidence", type=float, default=0.6)
    p_rules.set_defaults(func=cmd_rules)
    
    p_top = sub.add_parser("top_strategies", help="最优策略排行")
    p_top.add_argument("--top-k", type=int, default=5)
    p_top.set_defaults(func=cmd_top_strategies)
    
    p_sec = sub.add_parser("sector_patterns", help="板块轮动模式")
    p_sec.set_defaults(func=cmd_sector_patterns)
    
    p_ds = sub.add_parser("daily_strategy", help="当日策略推荐")
    p_ds.add_argument("--date")
    p_ds.set_defaults(func=cmd_daily_strategy)
    
    p_ms = sub.add_parser("market_state", help="市场状态分类")
    p_ms.add_argument("--date")
    p_ms.set_defaults(func=cmd_market_state)
    
    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()
