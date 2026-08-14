"""面试前调查（Intake）+ 面试官/公司画像（Persona）。

产品愿景落点：
- 用户使用本功能前，先生成一份「调查文件」，问清场景、面试官、岗位、目标学校/公司。
- agent 据此**全方面、全维度**搜集信息（人工填写 + 可选调研笔记），定制
  「公司 / 面试官画像」，真正从面试官视角模拟其风格与关注点。
"""
from __future__ import annotations

import json


def generate_intake_survey() -> dict:
    """返回调查文件结构（问卷），用于生成 markdown / 让用户填写。"""
    return {
        "meta": {"version": 2, "desc": "面试前信息调查，用于定制面试官/公司画像"},
        "fields": [
            {"key": "applicant_name", "q": "你的称呼？", "type": "text"},
            {"key": "goal_type", "q": "申请类型？",
             "type": "choice", "options": ["保研", "申博", "科研岗求职", "答辩", "组会汇报", "海外phd"]},
            {"key": "org_name", "q": "目标学校 / 公司 / 实验室名称？", "type": "text"},
            {"key": "position_or_program", "q": "申请的具体岗位 / 项目 / 导师？", "type": "text"},
            {"key": "interviewer_name", "q": "已知面试官姓名？（可空，能具体到人则画像更准）", "type": "text"},
            {"key": "interviewer_style", "q": "你了解面试官的风格？",
             "type": "choice", "options": ["严厉压力型", "温和引导型", "技术深挖型", "不确定"]},
            {"key": "known_focus", "q": "面试官 / 岗位特别看重的方面？（可空）", "type": "text"},
            {"key": "timeline", "q": "面试时间线 / 轮次？", "type": "text"},
            {"key": "materials_available", "q": "你已有哪些材料？（多选）",
             "type": "multichoice", "options": ["简历", "论文/专利", "项目代码", "成绩单", "推荐信", "其他"]},
            {"key": "extra_notes", "q": "其他想让面试官关注或回避的点？", "type": "text"},
        ],
    }


def render_intake_markdown(survey: dict) -> str:
    lines = [
        "# 面试前信息调查（Intake Survey）",
        "",
        "> 填写后用于全方位搜集信息并定制面试官 / 公司画像。可直接在下方补充答案，或另存为 JSON 供 `persona` 命令读取。",
        "",
    ]
    for f in survey["fields"]:
        opts = f.get("options")
        opt_txt = f"（选项：{opts}）" if opts else ""
        lines.append(f"- **{f['key']}**：{f['q']} {opt_txt}")
    return "\n".join(lines) + "\n"


_STYLE_DESC = {
    "严厉压力型": "偏好高压追问，常用连续 why/how 逼出真实水平，不容含糊。",
    "温和引导型": "先建立信任，再逐步深入，给候选人发挥空间。",
    "技术深挖型": "紧盯技术实现细节、数学推导与工程权衡。",
    "不确定": "风格未知，按标准严谨技术面试官处理。",
}


def build_persona(intake: dict, research_notes: str | None = None, llm=None) -> dict:
    """从面试官视角定制画像。

    - 若有真实后端 llm，则综合 intake + 调研笔记生成更丰富的画像；
    - 否则用模板兜底，保证离线可用。
    """
    g = intake.get("goal_type", "unknown")
    org = intake.get("org_name") or "某机构"
    pos = intake.get("position_or_program") or "相关岗位"
    iv = intake.get("interviewer_name") or "面试官"
    style = intake.get("interviewer_style") or "技术深挖型"
    focus = intake.get("known_focus") or "科研深度与项目真实贡献"

    if llm is not None:
        prompt = (
            f"请基于以下面试前调查与（可选）调研笔记，从『面试官视角』生成一张面试画像 JSON，"
            f"字段：identity, style, style_desc, focus_areas(list), sample_questions(list), "
            f"scoring_bias, background。\n调查：{json.dumps(intake, ensure_ascii=False)}\n"
            f"调研笔记：{research_notes or '（无）'}"
        )
        try:
            raw = llm.generate(prompt, system="你是从面试官视角撰写面试画像的专家。", task="persona",
                               context={"intake": intake, "research_notes": research_notes})
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and parsed.get("identity"):
                return parsed
        except Exception:
            pass

    style_desc = _STYLE_DESC.get(style, "标准严谨技术面试官。")
    return {
        "identity": f"{org} 的 {pos} 面试官（{iv}）",
        "style": style,
        "style_desc": style_desc,
        "focus_areas": [focus, "项目真实贡献占比", "技术细节与权衡", "量化成果"],
        "sample_questions": [
            f"请讲讲你申请 {pos} 最匹配的一段科研经历。",
            "这个项目里哪些是你亲自实现的？踩过什么坑、怎么解决的？",
            f"为什么选择 {org} / 这个方向？你的长期规划是什么？",
        ],
        "scoring_bias": f"对『{focus}』权重更高；重视诚实与可验证细节。",
        "background": f"申请类型={g}；机构={org}；岗位/项目={pos}；面试官={iv}。",
    }


def persona_system_prompt(persona: dict) -> str:
    """把画像注入面试系统提示，使考官像该面试官本人。"""
    p = persona or {}
    return (
        "你是一位严谨的科研面试考官，正在扮演以下面试官画像进行模拟：\n"
        f"- 身份：{p.get('identity', '资深科研考官')}\n"
        f"- 风格：{p.get('style', '技术深挖型')} —— {p.get('style_desc', '')}\n"
        f"- 关注点：{', '.join(p.get('focus_areas', [])) or '科研深度与项目真实贡献'}\n"
        f"- 评分偏好：{p.get('scoring_bias', '重视诚实与可验证细节')}\n"
        "请基于候选人资料进行针对性提问；对讲项目/代码类回答，必须坚持硬阻塞式深挖。"
    )
