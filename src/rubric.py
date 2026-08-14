"""评分标准 / 扣分点目录（Rubric）。

设计理念（来自产品愿景）：
- agent 事先把「一场合格的标准面试」长什么样写清楚——即下面的扣分点目录。
- 面试结束后，agent 把候选人的每一段作答与这些合格标准**逐条对比**，命中即扣分。
- 报告据此指出「错在哪里、为何错、如何改进」。

每个扣分点包含：
- id / dimension（维度）/ criterion（合格标准）/ max_deduction（该项最大扣分）
- evidence_hint（期望看到的证据）/ improvement（改进建议）
- material（True 表示属于「材料完整度」，由材料收集阶段单独计分，不逐条 judge）
"""
from __future__ import annotations

import json
import os


def default_rubric() -> list[dict]:
    """合格标准面试的默认扣分点目录。可经 data/sample_rubric.json 覆盖。"""
    return [
        {
            "id": "R1", "dimension": "项目深度", "max_deduction": 15,
            "criterion": "能讲清项目背景、你的具体角色与亲手实现的部分",
            "evidence_hint": "是否出现具体技术栈、模块名、你的贡献占比",
            "improvement": "用「背景→你的角色→亲手实现→结果」四段式复述项目，明确贡献占比。",
        },
        {
            "id": "R2", "dimension": "技术细节", "max_deduction": 15,
            "criterion": "关键实现细节、工程权衡与踩过的坑可被追问验证",
            "evidence_hint": "是否讲得出选型理由、失败尝试、复盘",
            "improvement": "为每个项目准备 1 个「踩坑→定位→解决」故事，含具体代码/参数。",
        },
        {
            "id": "R3", "dimension": "量化成果", "max_deduction": 10,
            "criterion": "用数据量化成果（指标提升%、论文/专利贡献）",
            "evidence_hint": "是否给出可验证的数字与对比基线",
            "improvement": "为每个成果配「起点→手段→终点」的量化对比，避免「效果不错」这类空话。",
        },
        {
            "id": "R4", "dimension": "动机匹配", "max_deduction": 10,
            "criterion": "申请动机/方向与导师或岗位高度匹配且有依据",
            "evidence_hint": "是否引用对方具体研究方向/岗位要求来佐证",
            "improvement": "把对方方向/岗位 JD 与自己的经历点状对齐，准备 3 条匹配论据。",
        },
        {
            "id": "R5", "dimension": "表达清晰", "max_deduction": 10,
            "criterion": "逻辑清晰、重点突出、不绕弯",
            "evidence_hint": "结构（结论先行/STAR）是否清楚",
            "improvement": "练习「结论先行 + 三点支撑」的回答结构，控制时长。",
        },
        {
            "id": "R6", "dimension": "诚实度", "max_deduction": 15,
            "criterion": "不夸大、不编造；不会的部分坦诚并说明学习路径",
            "evidence_hint": "是否出现无法自洽的夸大表述",
            "improvement": "遇到不会的，坦诚 + 给出「我将如何补齐」的路径，反而加分。",
        },
        {
            "id": "R7", "dimension": "材料完整度", "max_deduction": 10, "material": True,
            "criterion": "提交的简历/论文/代码/成绩单等材料齐全",
            "evidence_hint": "对照必需材料清单逐项核对",
            "improvement": "面试前按清单备齐材料；缺失项主动说明补救计划。",
        },
        {
            "id": "R8", "dimension": "英语/海外适配", "max_deduction": 10,
            "criterion": "海外phd/英文面试下，英语表达与学术写作可读",
            "evidence_hint": "是否出现明显语法/术语错误（仅海外phd等场景计）",
            "improvement": "针对海外场景练习英文叙述研究经历，熟记专业术语。",
        },
    ]


def load_rubric(path: str | None = None) -> list[dict]:
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                return data
        except Exception:
            pass
    return default_rubric()


def answer_items(rubric: list[dict]) -> list[dict]:
    """返回需要逐条 judge 的条目（排除材料类）。"""
    return [r for r in rubric if not r.get("material")]


def answer_items_for_scenario(rubric: list[dict], scenario: str | None = None) -> list[dict]:
    """返回该场景下需要 judge 的条目（排除材料类 + 不适用维度）。

    - '英语/海外适配' 仅在海外phd等英文面试场景下生效。
    """
    items = answer_items(rubric)
    if not scenario or scenario not in ("海外phd",):
        items = [r for r in items if r.get("dimension") != "英语/海外适配"]
    return items


def material_item(rubric: list[dict]) -> dict | None:
    for r in rubric:
        if r.get("material"):
            return r
    return None


def judge(backend, answer: str, item: dict, context: dict | None = None) -> dict:
    """对单条作答就该 rubric 项判定是否扣分。

    优先用后端（真实模型）产出结构化判定；解析失败则回退到本地启发式，
    保证离线 / mock 下也能稳定产出『命中 / 扣分 / 原因』。
    """
    ctx = {**(context or {}), "rubric_item": item, "answer": answer}
    try:
        raw = backend.generate(
            "请根据评分项对候选人作答判定是否扣分，返回 JSON："
            '{"hit": true/false, "points": <int>, "reason": "<string>"}',
            system="你是严格的面试评分员，只依据合格标准判定，不臆测。",
            task="judge",
            context=ctx,
        )
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and "hit" in parsed:
            parsed["points"] = int(parsed.get("points", 0))
            return parsed
    except Exception:
        pass
    return _heuristic(answer, item)


def _heuristic(answer: str, item: dict) -> dict:
    t = (answer or "").strip()
    shallow = ["不太清楚", "记不清", "忘了", "不知道", "不太了解", "没太关注",
               "大概", "好像", "还行吧", "不太行", "不太", "不太确定", "没太"]
    hit = len(t) < 45 or any(m in t for m in shallow)
    points = item.get("max_deduction", 0) if hit else 0
    reason = (
        f"作答缺乏可验证的具体细节，未达合格标准「{item.get('criterion', '')}」。"
        if hit else "作答包含具体细节，视为达标。"
    )
    return {"hit": bool(hit), "points": int(points), "reason": reason}
