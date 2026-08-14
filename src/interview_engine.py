"""核心面试引擎 v2：调查→画像→材料收集→硬阻塞追问→按 rubric 评分→报告(错误分析+改进)。

差异化护城河：
- 像真面试一样：先收材料，材料不足 agent 主动追问；给不出则按「材料完整度」扣分。
- 硬阻塞追问：讲项目/代码过浅时强制深挖，并把薄弱点写入短板库。
- 评分对比：agent 事先写好合格标准（rubric），结束后逐条对比候选人作答，命中即扣分，
  报告明确指出「错在哪、为何错、如何改」。
"""
from __future__ import annotations

import json

from rubric import default_rubric, answer_items, answer_items_for_scenario, material_item, judge
from persona import persona_system_prompt


def _severity(points: int) -> str:
    if points >= 10:
        return "high"
    if points >= 5:
        return "medium"
    return "low"


class InterviewSession:
    def __init__(self, backend, store, tenant_id, profile_name, profile_raw, scenario,
                 question_bank, followup_bank, persona=None, rubric=None,
                 required_materials=None, submitted_materials=None, hard_block=True):
        self.backend = backend
        self.store = store
        self.tenant_id = tenant_id
        self.profile_name = profile_name
        self.scenario = scenario
        self.bank = question_bank or []
        self.followup_bank = followup_bank or []
        self.persona = persona or {}
        self.rubric = rubric or default_rubric()
        self.required_materials = required_materials or ["简历", "项目/论文", "成绩单"]
        self.submitted_materials = set(submitted_materials or [])
        self.hard_block = hard_block
        self.asked = []
        self.weaknesses = []
        self.scoring_log = []          # 逐题命中扣分记录（供报告/测试）
        self.material_gaps = []        # 缺失的必需材料
        self._profile_id = store.save_profile(profile_name, profile_raw)
        self._persona_id = store.save_persona(profile_name + "-persona", self.persona) if self.persona else None
        self._session_id = store.create_session(self._profile_id, scenario, self._persona_id)
        self._done = False

    @property
    def session_id(self) -> str:
        return self._session_id

    # ---- 材料收集阶段 ----
    def collect_materials(self, interactive: bool = False, input_fn=input) -> list[str]:
        """对照必需材料清单收集；缺失项在交互模式下主动追问，给不出则记录为缺口。

        返回缺失材料列表（material_gaps）。缺口会在 finish() 时按 rubric 的『材料完整度』项扣分。
        """
        print("\n=== 材料收集 ===")
        for name in self.required_materials:
            provided = name in self.submitted_materials
            if not provided and interactive:
                ans = (input_fn(f"需要材料「{name}」：请提供路径/说明（输入 skip 跳过）：").strip())
                provided = bool(ans) and ans.lower() != "skip"
                if provided:
                    print(f"  ✓ 已收到「{name}」")
                else:
                    print(f"  ✗ 未提供「{name}」（将按材料完整度扣分）")
            self.store.add_material(self._session_id, name, provided)
            if not provided:
                self.material_gaps.append(name)
        if not self.material_gaps:
            print("  材料齐全，进入面试。\n")
        else:
            print(f"  缺失：{', '.join(self.material_gaps)}\n")
        return self.material_gaps

    # ---- 对话阶段 ----
    def _system(self) -> str:
        if self.persona:
            return persona_system_prompt(self.persona)
        return (
            f"你是一位严谨的科研面试考官，场景={self.scenario}，候选人={self.profile_name}。"
            f"请基于候选人资料进行针对性提问；对讲项目/代码类回答，必须坚持硬阻塞式深挖。"
        )

    def _ctx(self, extra=None):
        base = {
            "profile_name": self.profile_name,
            "scenario": self.scenario,
            "bank": self.bank,
            "followup_bank": self.followup_bank,
            "weaknesses": self.weaknesses,
            "persona": self.persona,
        }
        if extra:
            base.update(extra)
        return base

    def ask_first(self) -> str:
        q = self.backend.generate(
            "请提出第一个面试问题。", system=self._system(), task="ask", context=self._ctx()
        )
        self.store.append_turn(self._session_id, "interviewer", q, phase="ask")
        self.asked.append(q)
        return q

    def answer(self, text: str) -> dict:
        self.store.append_turn(self._session_id, "interviewee", text, phase="answer")
        if self.hard_block and self._is_shallow(text):
            fu = self.backend.generate(
                "候选人回答过浅，发起硬阻塞追问。", system=self._system(), task="followup", context=self._ctx()
            )
            self.store.append_turn(self._session_id, "interviewer", fu, phase="followup")
            self.weaknesses.append(f"回答缺乏细节：{text[:40]}...")
            self.store.add_weakness(
                self._session_id, "项目/代码细节", f"回答过短或过浅：{text[:60]}", severity="medium"
            )
            return {"type": "followup", "content": fu}
        nq = self.backend.generate(
            "请提出下一个面试问题。", system=self._system(), task="ask", context=self._ctx()
        )
        self.store.append_turn(self._session_id, "interviewer", nq, phase="ask")
        self.asked.append(nq)
        return {"type": "next", "content": nq}

    def _is_shallow(self, text: str) -> bool:
        t = (text or "").strip()
        if len(t) < 40:
            return True
        shallow_markers = ["不太清楚", "记不清", "忘了", "不知道", "不太了解", "没太关注",
                            "大概", "好像", "还行吧", "不太行", "不太", "不太确定"]
        return any(m in t for m in shallow_markers)

    # ---- 评分 + 报告阶段 ----
    def finish(self) -> str:
        if self._done:
            return self.store.get_report(self._session_id) or ""
        transcript = self.store.get_transcript(self._session_id)

        # 1) 材料完整度扣分
        self._score_materials()
        # 2) 逐条作答对比 rubric
        self._score_answers(transcript)
        # 3) 生成报告
        report = self._build_report(transcript)
        self.store.finish_session(self._session_id)
        self.store.save_report(self._session_id, report)
        self._done = True
        return report

    def _score_materials(self):
        mi = material_item(self.rubric)
        if not mi:
            return
        rows = self.store.get_materials(self._session_id)
        missing = [r["name"] for r in rows if not r["provided"]]
        if not missing:
            return
        per = mi["max_deduction"] / max(1, len(self.required_materials))
        pts = round(per * len(missing))
        reason = f"缺少必需材料：{', '.join(missing)}（合格标准：{mi['criterion']}）"
        self.store.add_score(self._session_id, mi["id"], mi["dimension"], pts, reason)
        self.scoring_log.append({"item": mi["id"], "dimension": mi["dimension"],
                                  "points": pts, "reason": reason})
        self.store.add_weakness(self._session_id, mi["dimension"], reason, _severity(pts))

    def _score_answers(self, transcript):
        items = answer_items_for_scenario(self.rubric, self.scenario)
        last_q = ""
        for turn in transcript:
            if turn["role"] == "interviewer" and turn["phase"] == "ask":
                last_q = turn["content"]
            if turn["role"] == "interviewee" and turn["phase"] == "answer":
                for item in items:
                    res = judge(self.backend, turn["content"], item, context=self._ctx())
                    if res.get("hit"):
                        pts = int(res.get("points", 0))
                        reason = res.get("reason", "")
                        self.store.add_score(self._session_id, item["id"], item["dimension"], pts, reason)
                        self.scoring_log.append({
                            "question": last_q, "answer": turn["content"],
                            "item": item["id"], "dimension": item["dimension"],
                            "points": pts, "reason": reason,
                            "improvement": item.get("improvement", ""),
                        })
                        self.store.add_weakness(self._session_id, item["dimension"], reason, _severity(pts))

    def _dimension_scores(self) -> dict:
        # 仅包含该场景下实际 judge 的维度 + 材料维度
        items = answer_items_for_scenario(self.rubric, self.scenario)
        mi = material_item(self.rubric)
        all_items = items + ([mi] if mi else [])
        dims = {r["dimension"]: 100 for r in all_items}
        for s in self.store.get_scores(self._session_id):
            if s["dimension"] in dims:
                dims[s["dimension"]] = dims.get(s["dimension"], 100) - s["points"]
        return {k: max(0, v) for k, v in dims.items()}

    def _overall(self) -> int:
        """总分 = 各维度分的加权平均（与 _dimension_scores 对齐）。

        旧实现直接 100 - sum(全部扣分)，导致多维度×多题时总分被重复扣减，
        出现「维度分 85-97 但总分 12/100」的 bug。
        """
        dims = self._dimension_scores()
        if not dims:
            return 100
        # 材料完整度权重略低（只考一次），其余维度等权
        weights = {}
        mi = material_item(self.rubric)
        mi_dim = mi["dimension"] if mi else None
        for d in dims:
            weights[d] = 0.5 if d == mi_dim else 1.0
        total_w = sum(weights.values())
        if total_w == 0:
            return 100
        return max(0, min(100, round(sum(dims[d] * weights[d] for d in dims) / total_w)))

    def _build_report(self, transcript) -> str:
        overall = self._overall()
        dims = self._dimension_scores()
        log = self.scoring_log

        lines = [f"# 模拟面试复盘报告（{self.profile_name}）", ""]
        if self.persona:
            lines.append(f"> 面试官画像：{self.persona.get('identity','')}（{self.persona.get('style','')}）")
            lines.append("")

        lines.append(f"## 总体评分：{overall}/100")
        lines.append("")
        lines.append("## 维度评分")
        for d, v in dims.items():
            lines.append(f"- {d}：{v}")
        lines.append("")

        # 逐题错误分析
        lines.append("## 逐题错误分析（问题 → 回答 → 命中扣分点 → 改进建议）")
        qa = []
        cur_q = ""
        for turn in transcript:
            if turn["role"] == "interviewer" and turn["phase"] == "ask":
                cur_q = turn["content"]
            if turn["role"] == "interviewee" and turn["phase"] == "answer":
                qa.append((cur_q, turn["content"]))
        if not qa:
            lines.append("- （无作答记录）")
        for i, (q, a) in enumerate(qa, 1):
            hits = [x for x in log if x.get("answer") == a and x.get("question") == q]
            if not hits:
                hits = [x for x in log if x.get("answer") == a]
            lines.append(f"\n### Q{i}")
            lines.append(f"- **问题**：{q}")
            lines.append(f"- **回答**：{a[:120]}{'…' if len(a) > 120 else ''}")
            if hits:
                for h in hits:
                    lines.append(f"  - ❌ 命中「{h['dimension']}」：{h['reason']}")
                    if h.get("improvement"):
                        lines.append(f"  - 💡 改进：{h['improvement']}")
            else:
                lines.append("  - ✅ 该项作答未命中扣分点。")
        lines.append("")

        # 材料完整度
        mi = material_item(self.rubric)
        if mi:
            rows = self.store.get_materials(self._session_id)
            missing = [r["name"] for r in rows if not r["provided"]]
            lines.append("## 材料完整度")
            lines.append(f"- 必需材料：{', '.join(self.required_materials)}")
            lines.append(f"- 缺失：{', '.join(missing) if missing else '无'}")
            if missing:
                lines.append(f"- ❌ 已按「{mi['dimension']}」扣分。改进：{mi.get('improvement','')}")
            lines.append("")

        # 改进建议汇总
        lines.append("## 改进建议汇总")
        seen = set()
        any_improve = False
        for h in log:
            imp = h.get("improvement")
            if imp and imp not in seen:
                seen.add(imp)
                lines.append(f"- [{h['dimension']}] {imp}")
                any_improve = True
        if not any_improve:
            lines.append("- 暂无显著扣分项，保持当前准备节奏。")
        lines.append("")

        # 跨场提示
        lines.append("## 跨场趋势提示")
        lines.append("- 运行 `python src/cli.py analyze` 查看多场面试的短板聚合与趋势，针对性补强。")
        lines.append("")
        return "\n".join(lines)
