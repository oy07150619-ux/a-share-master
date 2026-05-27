#!/usr/bin/env python3
"""
🔍 实时模式匹配器 — 当前市场 vs 历史相似行情
===========================================
功能：
- 将当前市场数据与历史相似日进行匹配
- 找出历史上最相似的交易日
- 预测"历史重演"的可能性
- 为复盘报告提供「历史相似行情对比」模块

用法:
  python pattern_analyzer.py match [--date YYYY-MM-DD]         # 匹配历史相似日
  python pattern_analyzer.py predict [--date YYYY-MM-DD]       # 预测次日走势
  python pattern_analyzer.py sector_cluster                    # 板块结构聚类
  python pattern_analyzer.py anomaly [--date ...]              # 检测今日异常信号
  python pattern_analyzer.py report [--date ...]               # 完整匹配报告
"""

import json, os, sys, math, re
from datetime import datetime, timedelta
from collections import defaultdict, Counter

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY_FILE = os.path.join(SKILL_DIR, "data", "trading_memory.json")


class PatternAnalyzer:
    """模式匹配器"""
    
    def __init__(self, memory_file=None):
        self.memory_file = memory_file or MEMORY_FILE
        self.memory = self._load()
        self.snapshots = self.memory.get("daily_snapshots", {})
        self.signals = self.memory.get("signals", {})
    
    def _load(self):
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return {"daily_snapshots": {}, "signals": {}, "patterns": {}}
    
    # ==================== 相似度匹配 ====================
    
    def _compute_similarity(self, today_data, hist_data):
        """计算两个交易日的多维相似度 (0~1)"""
        
        # 如果没有数据，返回低相似度
        if not today_data or not hist_data:
            return 0.0
        
        scores = []
        weights = []
        
        # 1. 涨跌家数比相似度 (权重0.25)
        t_senti = today_data.get("sentiment", {})
        h_senti = hist_data.get("sentiment", {})
        if isinstance(t_senti, dict) and isinstance(h_senti, dict):
            t_up = t_senti.get("上涨", 0) or t_senti.get("up", 0)
            t_down = t_senti.get("下跌", 0) or t_senti.get("down", 1)
            h_up = h_senti.get("上涨", 0) or h_senti.get("up", 0)
            h_down = h_senti.get("下跌", 0) or h_senti.get("down", 1)
            
            if t_down > 0 and h_down > 0:
                t_ratio = t_up / t_down
                h_ratio = h_up / h_down
                max_ratio = max(t_ratio, h_ratio, 0.1)
                ratio_sim = 1 - min(abs(t_ratio - h_ratio) / max_ratio, 1)
                scores.append(ratio_sim)
                weights.append(0.25)
        
        # 2. 涨停数相似度 (权重0.15)
        t_lu = t_senti.get("涨停", 0) if isinstance(t_senti, dict) else 0
        h_lu = h_senti.get("涨停", 0) if isinstance(h_senti, dict) else 0
        max_lu = max(t_lu, h_lu, 1)
        lu_sim = 1 - min(abs(t_lu - h_lu) / max_lu, 1)
        scores.append(lu_sim)
        weights.append(0.15)
        
        # 3. 成交量相似度 (权重0.15)
        t_vol = today_data.get("volume", 0) or 1
        h_vol = hist_data.get("volume", 0) or 1
        vol_sim = 1 - min(abs(t_vol - h_vol) / max(t_vol, h_vol, 0.1), 1)
        scores.append(vol_sim)
        weights.append(0.15)
        
        # 4. 板块结构相似度 (权重0.25)
        t_sectors = {s.get("板块名称", s.get("name", "")): s.get("涨跌幅", s.get("change%", 0))
                    for s in today_data.get("top_sectors", [])}
        h_sectors = {s.get("板块名称", s.get("name", "")): s.get("涨跌幅", s.get("change%", 0))
                    for s in hist_data.get("top_sectors", [])}
        
        if t_sectors and h_sectors:
            common = set(t_sectors.keys()) & set(h_sectors.keys())
            if common:
                sector_scores = []
                for name in common:
                    diff = abs(t_sectors[name] - h_sectors[name])
                    sector_scores.append(1 - min(diff / 5, 1))  # 5%差异=完全不相似
                scores.append(sum(sector_scores) / len(sector_scores))
                weights.append(0.25)
            else:
                scores.append(0.1)
                weights.append(0.25)
        
        # 5. 大盘指数涨跌幅相似度 (权重0.20)
        t_idx = {i.get("指数",""): i.get("涨跌幅",0) for i in today_data.get("indexes", [])}
        h_idx = {i.get("指数",""): i.get("涨跌幅",0) for i in hist_data.get("indexes", [])}
        
        if t_idx and h_idx:
            common_idx = set(t_idx.keys()) & set(h_idx.keys())
            if common_idx:
                idx_scores = []
                for name in common_idx:
                    diff = abs(t_idx[name] - h_idx[name])
                    idx_scores.append(1 - min(diff / 3, 1))
                scores.append(sum(idx_scores) / len(idx_scores))
                weights.append(0.20)
        
        # 计算加权平均
        if not scores or not weights:
            return 0.0
        
        total_score = sum(s * w for s, w in zip(scores, weights))
        total_weight = sum(weights)
        
        return round(total_score / total_weight, 3)
    
    def match_similar_days(self, date_str=None, top_k=5, min_similarity=0.4):
        """匹配历史上最相似的交易日
        
        参数:
            date_str: 目标日期（默认今天）
            top_k: 返回最相似的k个
            min_similarity: 最低相似度阈值
        
        返回: [(date_str, similarity_score, hist_snapshot), ...]
        """
        date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        
        # 获取目标日的数据
        target = self.snapshots.get(date_str)
        if not target:
            return []
        
        target_data = target.get("data", {})
        
        # 遍历历史
        matches = []
        for hist_date, hist_snapshot in self.snapshots.items():
            if hist_date == date_str:
                continue
            
            hist_data = hist_snapshot.get("data", {})
            sim = self._compute_similarity(target_data, hist_data)
            
            if sim >= min_similarity:
                matches.append((hist_date, sim, hist_snapshot))
        
        # 按相似度排序
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[:top_k]
    
    # ==================== 预测 ====================
    
    def predict_next_day(self, date_str=None):
        """基于历史相似日的次日表现，预测今日的次日走势
        
        返回:
            {
                "date": "YYYY-MM-DD",
                "similar_days_count": N,
                "next_day_positive_probability": 0.65,
                "next_day_avg_change": +0.35,
                "confidence": "高/中/低",
                "similar_days": [...]
            }
        """
        date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        
        matches = self.match_similar_days(date_str, top_k=10, min_similarity=0.4)
        
        if not matches:
            return {
                "date": date_str,
                "similar_days_count": 0,
                "prediction": "数据不足",
                "next_day_positive_probability": 0.5,
                "next_day_avg_change": 0,
                "confidence": "低",
                "similar_days": [],
            }
        
        # 获取每个相似日的次日数据
        next_day_results = []
        for hist_date, sim, snapshot in matches:
            # 找到该历史日的下一个交易日
            dates = sorted(self.snapshots.keys())
            try:
                idx = dates.index(hist_date)
                if idx + 1 < len(dates):
                    next_date = dates[idx + 1]
                    next_snap = self.snapshots.get(next_date)
                    if next_snap:
                        next_data = next_snap.get("data", {})
                        n_idx = next_data.get("indexes", [])
                        n_sh = next((i for i in n_idx if "上证" in i.get("指数","")), {})
                        n_change = n_sh.get("涨跌幅", 0)
                        n_lu = (next_data.get("sentiment", {}) or {}).get("涨停", 0)
                        
                        next_day_results.append({
                            "hist_date": hist_date,
                            "next_date": next_date,
                            "similarity": sim,
                            "next_change": n_change,
                            "next_limit_up": n_lu,
                            "positive": n_change > 0,
                        })
            except (ValueError, IndexError):
                continue
        
        if not next_day_results:
            return {
                "date": date_str,
                "similar_days_count": len(matches),
                "prediction": "次日数据不足",
                "next_day_positive_probability": 0.5,
                "confidence": "低",
                "similar_days": [],
            }
        
        # 统计
        positive_count = sum(1 for r in next_day_results if r["positive"])
        total = len(next_day_results)
        positive_prob = positive_count / total if total > 0 else 0.5
        avg_change = sum(r["next_change"] for r in next_day_results) / total
        
        # 置信度
        avg_sim = sum(r["similarity"] for r in next_day_results) / total
        if total >= 5 and avg_sim >= 0.6:
            confidence = "高"
        elif total >= 3 and avg_sim >= 0.5:
            confidence = "中"
        else:
            confidence = "低"
        
        return {
            "date": date_str,
            "similar_days_count": total,
            "prediction": "偏多" if positive_prob > 0.55 else ("偏空" if positive_prob < 0.45 else "中性"),
            "next_day_positive_probability": round(positive_prob, 3),
            "next_day_avg_change": round(avg_change, 2),
            "confidence": confidence,
            "similar_days": next_day_results[:5],
        }
    
    # ==================== 板块结构分析 ====================
    
    def sector_cluster_analysis(self, date_str=None):
        """分析今日板块结构，看属于哪种历史模式"""
        date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        
        target = self.snapshots.get(date_str)
        if not target:
            return {"status": "没有今日数据"}
        
        target_data = target.get("data", {})
        t_sectors = target_data.get("top_sectors", [])
        
        results = []
        
        # 遍历历史，找板块结构最相似的
        for hist_date, hist_snapshot in self.snapshots.items():
            if hist_date == date_str:
                continue
            
            hist_data = hist_snapshot.get("data", {})
            h_sectors = hist_data.get("top_sectors", [])
            
            if not t_sectors or not h_sectors:
                continue
            
            # 比较TOP5板块
            t_top5 = [(s.get("板块名称", s.get("name", "")), s.get("涨跌幅", s.get("change%", 0)))
                     for s in t_sectors[:5]]
            h_top5 = [(s.get("板块名称", s.get("name", "")), s.get("涨跌幅", s.get("change%", 0)))
                     for s in h_sectors[:5]]
            
            t_names = set(n for n, _ in t_top5)
            h_names = set(n for n, _ in h_top5)
            
            common = t_names & h_names
            overlap_rate = len(common) / 5.0 if common else 0
            
            if overlap_rate >= 0.4:  # 至少2个板块相同
                results.append({
                    "hist_date": hist_date,
                    "overlap": f"{len(common)}/5",
                    "common_sectors": list(common),
                    "overlap_rate": round(overlap_rate, 2),
                })
        
        results.sort(key=lambda x: x["overlap_rate"], reverse=True)
        
        return {
            "status": "完成",
            "today": date_str,
            "today_top5": [n for n, _ in [(s.get("板块名称", s.get("name", "")), None) for s in t_sectors[:5]]],
            "matches": results[:5],
        }
    
    # ==================== 异常检测 ====================
    
    def detect_anomalies(self, date_str=None):
        """检测今日数据中的异常信号
        
        包括：
        - 涨停数异常偏离近期均值
        - 成交量异常放大/缩小
        - 板块涨跌幅极端值
        """
        date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        
        target = self.snapshots.get(date_str)
        if not target:
            return {"status": "没有今日数据", "anomalies": []}
        
        target_data = target.get("data", {})
        anomalies = []
        
        # 获取近期均值
        dates = sorted([d for d in self.snapshots.keys() if d != date_str])
        recent = dates[-min(30, len(dates)):]
        
        if not recent:
            return {"status": "历史数据不足", "anomalies": []}
        
        # 1. 涨停数异常
        t_senti = target_data.get("sentiment", {})
        if isinstance(t_senti, dict):
            t_lu = t_senti.get("涨停", 0) or t_senti.get("limit_up", 0)
            
            recent_lu = []
            for d in recent:
                s = self.snapshots[d].get("data", {}).get("sentiment", {})
                if isinstance(s, dict):
                    lu = s.get("涨停", 0) or s.get("limit_up", 0)
                    if lu:
                        recent_lu.append(lu)
            
            if recent_lu:
                avg_lu = sum(recent_lu) / len(recent_lu)
                std_lu = (sum((x - avg_lu)**2 for x in recent_lu) / len(recent_lu)) ** 0.5
                
                if std_lu > 0 and abs(t_lu - avg_lu) > 2 * std_lu:
                    anomalies.append({
                        "type": "涨停数异常",
                        "current": t_lu,
                        "avg": round(avg_lu, 1),
                        "std": round(std_lu, 1),
                        "severity": "极端" if abs(t_lu - avg_lu) > 3 * std_lu else "明显",
                        "direction": "偏高" if t_lu > avg_lu else "偏低",
                    })
        
        # 2. 成交量异常
        t_vol = target_data.get("volume", 0)
        if t_vol:
            recent_vol = []
            for d in recent:
                v = self.snapshots[d].get("data", {}).get("volume", 0)
                if v:
                    recent_vol.append(v)
            
            if recent_vol:
                avg_vol = sum(recent_vol) / len(recent_vol)
                std_vol = (sum((x - avg_vol)**2 for x in recent_vol) / len(recent_vol)) ** 0.5
                
                if std_vol > 0 and abs(t_vol - avg_vol) > 1.5 * std_vol:
                    anomalies.append({
                        "type": "成交量异常",
                        "current": f"{t_vol/1e8:.0f}亿" if t_vol > 1e8 else f"{t_vol:.0f}",
                        "avg": f"{avg_vol/1e8:.0f}亿" if avg_vol > 1e8 else f"{avg_vol:.0f}",
                        "severity": "极端" if abs(t_vol - avg_vol) > 3 * std_vol else "明显",
                        "direction": "放量" if t_vol > avg_vol else "缩量",
                    })
        
        # 3. 板块极端涨跌
        sectors = target_data.get("top_sectors", [])
        for s in sectors:
            name = s.get("板块名称", s.get("name", ""))
            change = abs(s.get("涨跌幅", s.get("change%", 0)))
            if change > 5:
                anomalies.append({
                    "type": "板块极端",
                    "sector": name,
                    "change": f"{s.get('涨跌幅', s.get('change%', 0)):+.2f}%",
                    "severity": "极端" if change > 7 else "明显",
                })
        
        return {
            "status": "完成",
            "date": date_str,
            "anomalies": anomalies,
            "total_anomalies": len(anomalies),
        }
    
    # ==================== 完整匹配报告 ====================
    
    def full_report(self, date_str=None):
        """生成完整的模式匹配报告"""
        date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        
        similar_days = self.match_similar_days(date_str, top_k=5, min_similarity=0.3)
        prediction = self.predict_next_day(date_str)
        anomalies = self.detect_anomalies(date_str)
        sector_cluster = self.sector_cluster_analysis(date_str)
        
        return {
            "date": date_str,
            "generated_at": datetime.now().isoformat(),
            "similar_days": [
                {
                    "date": d,
                    "similarity": round(s, 3),
                    "next_day": {
                        "change": self._get_next_day_change(d),
                        "is_positive": self._get_next_day_change(d, "positive"),
                    }
                }
                for d, s, snap in similar_days
            ],
            "prediction": {
                "direction": prediction.get("prediction"),
                "probability": prediction.get("next_day_positive_probability", 0.5),
                "avg_change": prediction.get("next_day_avg_change", 0),
                "confidence": prediction.get("confidence", "低"),
                "samples": prediction.get("similar_days_count", 0),
            },
            "anomalies": anomalies.get("anomalies", []),
            "sector_cluster": sector_cluster.get("matches", []),
        }
    
    def _get_next_day_change(self, date_str, mode="value"):
        """获取某日期的次日涨跌幅"""
        dates = sorted(self.snapshots.keys())
        try:
            idx = dates.index(date_str)
            if idx + 1 < len(dates):
                next_date = dates[idx + 1]
                next_snap = self.snapshots.get(next_date)
                if next_snap:
                    next_data = next_snap.get("data", {})
                    n_idx = next_data.get("indexes", [])
                    n_sh = next((i for i in n_idx if "上证" in i.get("指数","")), {})
                    if mode == "value":
                        return n_sh.get("涨跌幅", 0)
                    else:
                        return n_sh.get("涨跌幅", 0) > 0
        except:
            pass
        return 0 if mode == "value" else False
    
    def get_top_risk_signals(self, date_str=None):
        """获取今日的风险信号"""
        date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        
        anomalies = self.detect_anomalies(date_str)
        prediction = self.predict_next_day(date_str)
        
        risks = []
        
        # 异常检测中的风险
        for a in anomalies.get("anomalies", []):
            if a["type"] == "涨停数异常" and a["direction"] == "偏低":
                risks.append({
                    "signal": "情绪冰点",
                    "detail": f"涨停数仅{a['current']}家，远低于均值{a['avg']}家",
                    "severity": a["severity"],
                })
            if a["type"] == "成交量异常" and a["direction"] == "缩量":
                risks.append({
                    "signal": "量能萎缩",
                    "detail": f"成交量{a['current']}低于均值{a['avg']}",
                    "severity": a["severity"],
                })
        
        # 预测风险
        if prediction.get("prediction") == "偏空":
            risks.append({
                "signal": "历史重演偏空",
                "detail": f"基于{prediction['similar_days_count']}个相似交易日的次日统计，偏空概率较高",
                "severity": prediction.get("confidence", "中"),
            })
        
        return risks


# =====================================================================
# 命令行接口
# =====================================================================

def cmd_match(args):
    analyzer = PatternAnalyzer()
    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    
    matches = analyzer.match_similar_days(date_str, top_k=args.top_k)
    
    print(f"🔍 [{date_str}] 历史相似交易日 TOP{args.top_k}:")
    print("=" * 60)
    
    if not matches:
        print("  无匹配结果（数据不足或相似度低于阈值）")
        return
    
    for i, (d, sim, snap) in enumerate(matches, 1):
        data = snap.get("data", {})
        indexes = data.get("indexes", [])
        sh = next((i for i in indexes if "上证" in i.get("指数","")), {})
        senti = data.get("sentiment", {})
        senti = senti if isinstance(senti, dict) else {}
        
        print(f"\n  #{i} {d}")
        print(f"     相似度: {sim:.1%}")
        print(f"     上证: {sh.get('最新','?')} ({sh.get('涨跌幅','?'):+.2f}%)")
        print(f"     涨跌: 涨{senti.get('上涨','?')}跌{senti.get('下跌','?')}")
        print(f"     涨停{senti.get('涨停','?')}跌停{senti.get('跌停','?')}")
        
        # 次日走势
        nd_change = analyzer._get_next_day_change(d)
        print(f"     次日上证: {'涨' if nd_change > 0 else '跌'} {nd_change:+.2f}%")


def cmd_predict(args):
    analyzer = PatternAnalyzer()
    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    
    prediction = analyzer.predict_next_day(date_str)
    
    print(f"🔮 [{date_str}] 次日走势预测:")
    print("=" * 60)
    print(f"  方向: {prediction.get('prediction', '未知')}")
    print(f"  上涨概率: {prediction.get('next_day_positive_probability', 0.5):.0%}")
    print(f"  平均涨幅: {prediction.get('next_day_avg_change', 0):+.2f}%")
    print(f"  置信度: {prediction.get('confidence', '低')}")
    print(f"  相似样本: {prediction.get('similar_days_count', 0)}个交易日")
    
    similar = prediction.get("similar_days", [])
    if similar:
        print(f"\n  相似日次日表现:")
        for r in similar:
            print(f"    {r['hist_date']}→{r['next_date']}: {r['next_change']:+.2f}% "
                  f"({'📈' if r['positive'] else '📉'})")


def cmd_anomaly(args):
    analyzer = PatternAnalyzer()
    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    
    result = analyzer.detect_anomalies(date_str)
    
    print(f"🚨 [{date_str}] 异常信号检测:")
    print("=" * 60)
    
    anomalies = result.get("anomalies", [])
    if not anomalies:
        print("  未检测到明显异常信号 ✓")
        return
    
    for a in anomalies:
        if a["type"] == "板块极端":
            print(f"  {a['severity']} | {a['sector']} {a['change']}")
        else:
            print(f"  {a['severity']} | {a['type']}: 当前{a['direction']} "
                  f"(当前{a['current']}, 均值{a['avg']})")


def cmd_report(args):
    """生成完整匹配报告（用于复盘报告）"""
    analyzer = PatternAnalyzer()
    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    
    report = analyzer.full_report(date_str)
    
    print(f"📊 [{date_str}] 模式匹配报告")
    print("=" * 60)
    
    # 相似日
    print(f"\n📋 历史相似日 ({len(report['similar_days'])}个):")
    for d in report["similar_days"]:
        nd = d.get("next_day", {})
        nd_str = f"次日{nd.get('change', 0):+.2f}% {'📈' if nd.get('is_positive') else '📉'}" if nd.get('change') else "次日数据不足"
        print(f"  🔹 {d['date']} (相似度{d['similarity']:.0%}) → {nd_str}")
    
    # 预测
    pred = report.get("prediction", {})
    print(f"\n🔮 次日预测: {pred.get('direction', '?')} "
          f"(概率{pred.get('probability', 0):.0%}, "
          f"均值{pred.get('avg_change', 0):+.2f}%, "
          f"置信度{pred.get('confidence', '低')})")
    
    # 异常
    anomalies = report.get("anomalies", [])
    if anomalies:
        print(f"\n🚨 异常信号 ({len(anomalies)}个):")
        for a in anomalies:
            if a["type"] == "板块极端":
                print(f"  • {a['sector']} {a['change']} - {a['severity']}")
            else:
                print(f"  • {a['type']}: {a.get('direction','')} - {a['severity']}")
    
    # 输出JSON
    if args.json:
        print("\n" + "=" * 50)
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="🔍 模式匹配器")
    sub = parser.add_subparsers(dest="command", required=True)
    
    p_m = sub.add_parser("match", help="匹配历史相似日")
    p_m.add_argument("--date")
    p_m.add_argument("--top-k", type=int, default=5)
    p_m.set_defaults(func=cmd_match)
    
    p_p = sub.add_parser("predict", help="预测次日走势")
    p_p.add_argument("--date")
    p_p.set_defaults(func=cmd_predict)
    
    p_a = sub.add_parser("anomaly", help="检测异常信号")
    p_a.add_argument("--date")
    p_a.set_defaults(func=cmd_anomaly)
    
    p_r = sub.add_parser("report", help="完整匹配报告")
    p_r.add_argument("--date")
    p_r.add_argument("--json", action="store_true")
    p_r.set_defaults(func=cmd_report)
    
    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()
