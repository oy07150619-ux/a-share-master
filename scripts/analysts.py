#!/usr/bin/env python3
"""
👥 三身份协作系统 — 小A·小C·小V
==================================
三人各司其职，协同完成从数据到输出的全流程：

  🅰️ 小A — 数据分析师 (Data Analyst)
      身份：金融数据分析专家
      能力：
        - 调用市场分析agent收集行情/板块/资金数据
        - 分析交易知识库中的历史数据
        - 识别市场模式、板块轮动、情绪变化
        - 输出结构化分析报告和策略建议
      合作：分析结果交给小C实现、小V包装
  
  🅲 小C — 程序员 (Programmer)  
      身份：全栈开发工程师
      能力：
        - 调用代码agent开发和维护Python脚本
        - 搭建数据管道、自动化流程
        - 代码自测、错误修复、优化性能
        - 实现小A提出的策略计算逻辑
      合作：实现小A的分析逻辑、为小V提供输出接口

  🆅 小V — 自媒体运营 (Content Creator)
      身份：内容创作与视觉设计专家
      能力：
        - 调用图像/视频生成agent制作专业内容
        - 编写HTML报告、信息图表、视频脚本
        - 数据分析可视化（K线图、热力图等）
        - 以最高专业水准包装分析结果
      合作：将小A的分析成果包装成可直接传播的内容

用法:
  python analysts.py run <task>           # 启动三人协作完成某任务
  python analysts.py role <A|C|V>         # 查看某个角色的详细档案
  python analysts.py spawn <A|C|V> <task> # 派生子agent执行任务
  python analysts.py daily                # 执行每日全流程（数据→分析→代码→输出）
"""

import json, os, sys, subprocess
from datetime import datetime

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(SKILL_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# =====================================================================
# 角色定义
# =====================================================================

ROLES = {
    "A": {
        "name": "小A",
        "emoji": "🅰️",
        "title": "数据分析师",
        "color": "#3498db",
        "motto": "数据会说话，关键在于你会不会听",
        "description": "金融数据分析专家，擅长从海量数据中发现规律和趋势。",
        "skills": [
            "a-share-master — A股市场分析",
            "a-stock-analysis-pro — 个股深度研报",
            "stock-analysis-agent — 全球股市分析",
            "financial-report — 财务报告生成",
            "多源搜索 — web_search/tavily-search/brave-search",
        ],
        "tools": [
            "web_search, web_fetch — 采集外部数据",
            "trading_memory — 查询历史知识库",
            "strategy_learner — 策略模式学习",
            "pattern_analyzer — 历史模式匹配",
        ],
        "workflow": [
            "1. 收集原始数据（行情/板块/资金/消息）",
            "2. 分析市场结构和情绪",
            "3. 输出结构化分析结论和策略建议",
            "4. 将结论传递给小C（实现）和小V（包装）",
        ],
        "collaboration": {
            "给C": "提供需要实现的算法逻辑和计算需求",
            "给V": "提供分析结论、关键数据点、图表需求",
        },
        "prompt_template": """你是一个专业的数据分析师，你的名字是小A 🅰️。
你的任务是分析以下市场数据，输出结构化的分析结论。

可用数据：
{data}

请从以下维度进行分析：
1. 市场整体状况评估
2. 板块资金流向解读
3. 关键信号识别
4. 风险提示
5. 明日策略建议

输出格式：JSON结构化数据""",
    },
    "C": {
        "name": "小C",
        "emoji": "🅲",
        "title": "程序员",
        "color": "#27ae60",
        "motto": "代码不会撒谎，但bug会",
        "description": "全栈开发工程师，专注于代码实现、自动化和系统优化。",
        "skills": [
            "auto-coder — 自动代码生成与修复",
            "web-generator — 网页/工具开发",
            "diagram-maker — 架构图/流程图制作",
            "node-inspect-debugger — Node.js调试",
            "python-debugpy — Python调试",
            "skill-creator — 技能创建与优化",
        ],
        "tools": [
            "auto-coder — 根据需求自动编写代码",
            "exec — 运行和测试代码",
            "read/write/edit — 代码文件操作",
        ],
        "workflow": [
            "1. 接收小A的算法需求",
            "2. 实现代码/脚本/工具",
            "3. 运行测试验证正确性",
            "4. 修复bug直到通过",
            "5. 为小V的输出提供数据接口",
        ],
        "collaboration": {
            "从A接收": "分析算法、计算逻辑、策略规则",
            "给V提供": "数据导出接口、生成的图表HTML、自动化脚本",
        },
        "prompt_template": """你是一个专业的全栈程序员，你的名字是小C 🅲。
你的任务是实现以下编码需求。

需求描述：
{task}

要求：
1. 先理解需求，然后设计方案
2. 编写清晰、有注释的代码
3. 运行测试验证代码正确性
4. 如果出错，修复后重新测试
5. 最多尝试3次，成功后输出结果

输出格式：代码+运行结果""",
    },
    "V": {
        "name": "小V",
        "emoji": "🆅",
        "title": "自媒体运营",
        "color": "#e74c3c",
        "motto": "好的内容自己会传播",
        "description": "内容创作与视觉设计专家，擅长把数据变成故事。",
        "skills": [
            "ai-image-generation — AI图像生成（FLUX/SD/OpenAI）",
            "ai-video-generation — AI视频生成（Kling/Seedance/Wan）",
            "video-studio — AI影视工作室",
            "meme-maker — 梗图制作",
            "canvas — HTML画布呈现",
            "compdf-conversion-cli — PDF/图片格式转换",
        ],
        "tools": [
            "canvas — 在画布上展示HTML报告",
            "ai-image-generation — 生成分析配图",
            "ai-video-generation — 生成短视频分析",
            "message — 发送图文消息",
        ],
        "workflow": [
            "1. 接收小A的分析结论和小C的数据接口",
            "2. 设计视觉呈现方案",
            "3. 制作HTML报告/信息图/短视频",
            "4. 输出最终可传播的内容",
        ],
        "collaboration": {
            "从A接收": "分析结论、关键数据、策略建议",
            "从C接收": "数据接口、生成的图表代码、自动化脚本",
        },
        "prompt_template": """你是一个专业的自媒体创作者，你的名字是小V 🆅。
你的任务是将以下分析内容包装成专业、美观的可传播内容。

分析数据：
{data}

请制作：
1. 专业的HTML信息图报告
2. 配套的视觉元素（图表/图片）
3. 适合传播的文案

输出格式：HTML报告/图片/视频""",
    },
}


# =====================================================================
# 核心功能
# =====================================================================

def get_role(role_id):
    """获取角色信息"""
    role_id = role_id.upper()
    if role_id in ROLES:
        return ROLES[role_id]
    return None


def spawn_task(role_id, task_description):
    """生成一个子agent执行任务（返回会话指令）
    
    返回用于 sessions_spawn 的配置
    """
    role = get_role(role_id)
    if not role:
        return None
    
    agent_prompt = f"""你正在以{role['emoji']} {role['name']}（{role['title']}）的身份执行任务。

## 角色档案
- 名字：{role['name']} {role['emoji']}
- 身份：{role['title']}
- 信条：「{role['motto']}」
- 简介：{role['description']}

## 可用技能
{chr(10).join(f'- {s}' for s in role['skills'])}

## 协作说明
- 小A 🅰️ 负责数据分析和策略研究
- 小C 🅲 负责代码实现和系统搭建
- 小V 🆅 负责内容创作和视觉包装
- 你是 {role['name']} {role['emoji']}，请完成你的那部分工作

## 当前任务
{task_description}

## 要求
1. 以{role['name']}的身份思考和行动
2. 调用当前身份技能范围内的工具
3. 输出完成的任务成果
4. 如果是协作任务，标注需要传递给哪个角色
"""
    
    return {
        "role": role,
        "spawn_config": {
            "task": agent_prompt,
            "taskName": f"role_{role_id.lower()}",
            "mode": "run",
            "cleanup": "keep",
        }
    }


def get_daily_collaboration_plan(date_str=None):
    """生成每日协作计划"""
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    
    return {
        "date": date_str,
        "pipeline": [
            {
                "step": 1,
                "role": "A",
                "name": "小A 🅰️",
                "task": "数据采集与市场分析",
                "description": "收集今日市场数据，分析板块/资金/情绪，输出分析结论",
                "tools": ["web_search", "trading_memory.py record", "strategy_learner.py"],
            },
            {
                "step": 2,
                "role": "C",
                "name": "小C 🅲",
                "task": "策略实现与系统维护",
                "description": "根据小A的分析需求实现代码，验证数据管道正常运行",
                "tools": ["auto-coder", "exec", "read/write/edit"],
                "depends_on": [1],
            },
            {
                "step": 3,
                "role": "V",
                "name": "小V 🆅",
                "task": "内容制作与输出包装",
                "description": "将分析结果制作成HTML报告/信息图/视频",
                "tools": ["canvas", "ai-image-generation", "html_ppt.py"],
                "depends_on": [1, 2],
            },
        ],
    }


def get_pipeline_summary():
    """输出三角色协作流程总览"""
    return {
        "system": "三身份协作系统",
        "description": "小A·小C·小V各司其职，从数据到分析到实现到输出，全链路打通",
        "flow": """
  📡 原始数据
     │
     ▼
  🅰️ 小A（数据分析师）
     │  → 采集分析 → 结构化结论
     │
     ├──→ 🅲 小C（程序员）
     │       → 代码实现 → 自动化工具
     │
     └──→ 🆅 小V（自媒体）
             → 视觉包装 → 可传播内容
     │
     ▼
  📊 最终输出（报告/图表/视频）
        """,
    }


# =====================================================================
# 输出工具
# =====================================================================

def format_role_card(role):
    """输出角色卡片"""
    lines = [
        f"{role['emoji']} {role['name']} — {role['title']}",
        f"{'═' * 50}",
        f"  信条: 「{role['motto']}」",
        f"  简介: {role['description']}",
        f"",
        f"  🛠️ 可用技能:",
    ]
    for s in role['skills']:
        lines.append(f"    • {s}")
    
    lines.extend([
        f"",
        f"  📋 工作流程:",
    ])
    for w in role['workflow']:
        lines.append(f"    {w}")
    
    lines.extend([
        f"",
        f"  🤝 协作方式:",
    ])
    for k, v in role['collaboration'].items():
        lines.append(f"    {k}: {v}")
    
    return "\n".join(lines)


# =====================================================================
# 命令行接口
# =====================================================================

def cmd_run(args):
    """运行协作流程"""
    task = args.task or "每日市场分析"
    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    
    plan = get_daily_collaboration_plan(date_str)
    pipeline = plan["pipeline"]
    
    print(f"📋 三身份协作启动 — {date_str}")
    print(f"  任务: {task}")
    print(f"  {'='*50}")
    
    for step in pipeline:
        print(f"\n  步骤{step['step']}: {step['name']}")
        print(f"    任务: {step['description']}")
        print(f"    工具: {step['tools']}")
        if step.get('depends_on'):
            print(f"    依赖: 步骤{step['depends_on']}")
    
    print(f"\n  🅰️ → 🅲 → 🆅 全链路协作")
    print(f"\n  ℹ️  使用以下命令派生子agent执行:")
    for step in pipeline:
        print(f"     python analysts.py spawn {step['role']} \"{step['description']}\"")
    print(f"\n  📁 或通过 sessions_spawn 在对话中启动")


def cmd_role(args):
    """查看角色档案"""
    if args.role_id and args.role_id.upper() in ROLES:
        role = get_role(args.role_id)
        print(format_role_card(role))
    else:
        print(f"👥 三身份系统 — 可用角色:\n")
        for rid in ["A", "C", "V"]:
            role = get_role(rid)
            print(f"  {role['emoji']} {role['name']} — {role['title']}")
            print(f"    信条: 「{role['motto']}」")
            print()


def cmd_spawn(args):
    """生成子agent启动配置"""
    role_id = args.role_id.upper()
    task = args.task
    
    if role_id not in ROLES:
        print(f"❌ 未知角色: {role_id}，可用: A, C, V")
        return
    
    spawn = spawn_task(role_id, task)
    if not spawn:
        print("❌ 生成失败")
        return
    
    role = spawn["role"]
    config = spawn["spawn_config"]
    
    print(f"🧬 子agent配置 — {role['emoji']} {role['name']} ({role['title']})")
    print(f"{'='*60}\n")
    print(f"📌 任务: {task}\n")
    print(f"📋 请复制以下配置启动子agent:\n")
    print(f"  sessions_spawn:")
    print(f"    taskName: {config['taskName']}")
    print(f"    mode: run")
    print(f"    cleanup: keep")
    print(f"    task: |")
    for line in config['task'].strip().split('\n'):
        print(f"      {line}")


def cmd_daily(args):
    """每日全流程预览"""
    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    
    plan = get_daily_collaboration_plan(date_str)
    
    print(f"📅 {date_str} 每日协作流程")
    print(f"{'='*60}")
    print(f"\n🔄 流水线:")
    print(f"   🅰️ 小A（数据分析）→ 🅲 小C（代码实现）→ 🆅 小V（内容包装）\n")
    
    for step in plan["pipeline"]:
        print(f"  [{step['step']}] {step['name']}")
        print(f"     任务: {step['description']}")
        print(f"     工具: {', '.join(step['tools'])}")
        if step.get('depends_on'):
            print(f"     依赖前序步骤: {step['depends_on']}")
        print()
    
    print(f"  执行命令:")
    print(f"    # 全流程一句话")
    print(f"    python scripts/trading_memory.py record \\")
    print(f"      && python scripts/strategy_learner.py learn \\")
    print(f"      && python scripts/analysts.py run")  # corrected tool name


def cmd_flow(args):
    """输出流程图"""
    summary = get_pipeline_summary()
    print(summary["flow"])


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="👥 三身份协作系统 — 小A·小C·小V")
    sub = parser.add_subparsers(dest="command", required=True)
    
    p_run = sub.add_parser("run", help="启动协作流程")
    p_run.add_argument("task", nargs="?", default="每日市场分析", help="任务描述")
    p_run.add_argument("--date")
    p_run.set_defaults(func=cmd_run)
    
    p_role = sub.add_parser("role", help="查看角色档案")
    p_role.add_argument("role_id", nargs="?", help="A/C/V")
    p_role.set_defaults(func=cmd_role)
    
    p_spawn = sub.add_parser("spawn", help="生成子agent配置")
    p_spawn.add_argument("role_id", help="A/C/V")
    p_spawn.add_argument("task", help="任务描述")
    p_spawn.set_defaults(func=cmd_spawn)
    
    p_daily = sub.add_parser("daily", help="每日全流程预览")
    p_daily.add_argument("--date")
    p_daily.set_defaults(func=cmd_daily)
    
    p_flow = sub.add_parser("flow", help="输出协作流程图")
    p_flow.set_defaults(func=cmd_flow)
    
    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()
