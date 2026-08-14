"""评分逻辑修复验证测试（无网络、无第三方依赖）。

验证三个 bug 修复：
1. 维度分与总分自洽（旧实现：维度分 85-97 但总分 12/100）
2. '英语/海外适配' 维度在 rubric 定义中存在（R8）
3. '英语/海外适配' 仅在海外phd场景下 judge
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from llm_backend import MockBackend
from storage import Store
from interview_engine import InterviewSession
from rubric import default_rubric, answer_items, answer_items_for_scenario, material_item


def test_rubric_has_english_dimension():
    """R8 '英语/海外适配' 必须在默认 rubric 中。"""
    rb = default_rubric()
    dims = [r["dimension"] for r in rb]
    assert "英语/海外适配" in dims, f"'英语/海外适配' 缺失于维度列表: {dims}"
    r8 = [r for r in rb if r["dimension"] == "英语/海外适配"][0]
    assert r8["id"] == "R8"
    assert r8["max_deduction"] == 10


def test_scenario_filtering():
    """非海外phd场景下，'英语/海外适配' 不参与 judge。"""
    rb = default_rubric()
    domestic = answer_items_for_scenario(rb, "保研")
    overseas = answer_items_for_scenario(rb, "海外phd")
    all_dims_domestic = [r["dimension"] for r in domestic]
    all_dims_overseas = [r["dimension"] for r in overseas]
    assert "英语/海外适配" not in all_dims_domestic, "保研场景不应 judge 英语维度"
    assert "英语/海外适配" in all_dims_overseas, "海外phd场景应 judge 英语维度"
    # 默认（无 scenario）也不含
    default_items = answer_items_for_scenario(rb, None)
    assert "英语/海外适配" not in [r["dimension"] for r in default_items]


def test_overall_score_consistent_with_dimensions():
    """总分 ≈ 各维度分均值，不会出现「维度分 85-97 但总分 12」。"""
    tmp = tempfile.mkdtemp()
    backend = MockBackend({})
    store = Store(tmp, "score-test")
    profile = {"name": "测试候选人"}
    sess = InterviewSession(
        backend, store, "score-test", "测试候选人", profile, "保研",
        ["Q1 介绍项目。", "Q2 未来规划？"], ["FU 讲细节。"],
        rubric=default_rubric(),
        required_materials=["简历", "项目/论文", "成绩单"],
        submitted_materials=["简历", "项目/论文", "成绩单"],  # 材料齐全
        hard_block=True,
    )
    sess.collect_materials(interactive=False)
    sess.ask_first()
    # 两个浅回答
    sess.answer("还行吧")
    sess.answer("具体细节我记不清了")
    report = sess.finish()

    dims = sess._dimension_scores()
    overall = sess._overall()

    # 核心断言：总分必须在维度分的合理范围内
    dim_values = list(dims.values())
    dim_min = min(dim_values)
    dim_max = max(dim_values)
    dim_avg = sum(dim_values) / len(dim_values) if dim_values else 100

    print(f"  维度分: {dims}")
    print(f"  总分: {overall}")
    print(f"  维度均值: {dim_avg:.1f}, 维度最低: {dim_min}, 维度最高: {dim_max}")

    # 总分必须 >= 维度最低分 - 5（允许微小四舍五入误差）
    assert overall >= dim_min - 5, (
        f"总分 {overall} 远低于维度最低分 {dim_min}，"
        f"说明总分计算与维度分不自洽"
    )
    # 总分必须 <= 维度最高分 + 5
    assert overall <= dim_max + 5, (
        f"总分 {overall} 远高于维度最高分 {dim_max}，不自洽"
    )
    # 旧 bug: 浅回答下总分应远高于 12
    assert overall > 30, f"总分 {overall} 过低，旧 bug 可能仍存在"

    # 保研场景下不应含 '英语/海外适配' 维度
    assert "英语/海外适配" not in dims, "保研场景的维度分不应含'英语/海外适配'"


def test_overseas_phd_includes_english():
    """海外phd场景下维度分应包含'英语/海外适配'。"""
    tmp = tempfile.mkdtemp()
    backend = MockBackend({})
    store = Store(tmp, "phd-test")
    profile = {"name": "PhD候选人"}
    sess = InterviewSession(
        backend, store, "phd-test", "PhD候选人", profile, "海外phd",
        ["Q1 Research experience."], ["FU Details?"],
        rubric=default_rubric(),
        required_materials=["简历"],
        submitted_materials=["简历"],
        hard_block=True,
    )
    sess.collect_materials(interactive=False)
    sess.ask_first()
    sess.answer("I worked on graph neural networks with PyTorch and DGL.")
    sess.finish()

    dims = sess._dimension_scores()
    assert "英语/海外适配" in dims, f"海外phd场景应含'英语/海外适配'维度，实际: {list(dims.keys())}"


if __name__ == "__main__":
    test_rubric_has_english_dimension()
    print("PASS: test_rubric_has_english_dimension")
    test_scenario_filtering()
    print("PASS: test_scenario_filtering")
    test_overall_score_consistent_with_dimensions()
    print("PASS: test_overall_score_consistent_with_dimensions")
    test_overseas_phd_includes_english()
    print("PASS: test_overseas_phd_includes_english")
    print("\nALL SCORING FIX TESTS PASSED")
