"""engine v2 测试：材料收集扣分 + 按 rubric 逐题评分 + 报告含错误分析与改进建议。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from llm_backend import MockBackend
from storage import Store
from interview_engine import InterviewSession
from rubric import default_rubric


def test_material_gap_and_rubric_report():
    tmp = tempfile.mkdtemp()
    backend = MockBackend({})
    store = Store(tmp, "t2")
    profile = {
        "name": "候选人乙",
        "materials": ["简历"],  # 缺 项目/论文、成绩单 → 应触发材料扣分
        "demo_answers": [
            "我负责模型训练，具体指标记不太清了。",          # 浅 → 命中
            "整体效果还行吧。",                                # 浅 → 命中
        ],
    }
    required = ["简历", "项目/论文", "成绩单"]
    sess = InterviewSession(
        backend, store, "t2", "候选人乙", profile, "保研",
        ["Q1 介绍项目。", "Q2 未来规划？"], ["FU 讲细节。"],
        rubric=default_rubric(), required_materials=required,
        submitted_materials=profile["materials"], hard_block=True,
    )
    gaps = sess.collect_materials(interactive=False)
    assert set(gaps) == {"项目/论文", "成绩单"}, f"材料缺口应为两项，实际 {gaps}"

    q = sess.ask_first()
    assert q
    r1 = sess.answer(profile["demo_answers"][0])
    r2 = sess.answer(profile["demo_answers"][1])
    assert r1["type"] == "followup" and r2["type"] == "followup"

    report = sess.finish()
    # 报告必须包含错误分析与改进建议章节
    assert "逐题错误分析" in report
    assert "材料完整度" in report
    assert "改进建议汇总" in report
    # 材料缺失应被记录为扣分
    scores = store.get_scores(sess.session_id)
    material_scores = [s for s in scores if s["dimension"] == "材料完整度"]
    assert material_scores, "应存在材料完整度扣分"
    assert material_scores[0]["points"] > 0
    # 结构化评分已落库（roadmap 项的部分实现）
    assert len(scores) >= 1
    # 短板库应有记录（供跨场聚合）
    assert len(store.get_weaknesses()) >= 1

    print("ALL ENGINE v2 TESTS PASSED")


if __name__ == "__main__":
    test_material_gap_and_rubric_report()
