"""rubric 模块测试（无网络、无第三方依赖）。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from llm_backend import MockBackend
from rubric import default_rubric, answer_items, material_item, judge


def test_default_rubric_shape():
    rb = default_rubric()
    assert len(rb) == 8, "默认应有 8 个扣分点"
    for it in rb:
        assert {"id", "dimension", "criterion", "max_deduction"} <= set(it), f"字段缺失: {it}"


def test_answer_vs_material_split():
    rb = default_rubric()
    items = answer_items(rb)
    mi = material_item(rb)
    assert mi is not None and mi.get("material") is True
    assert mi not in items
    assert all(not i.get("material") for i in items)


def test_judge_heuristic_hit_and_miss():
    backend = MockBackend({})
    item = default_rubric()[0]
    hit = judge(backend, "还行吧，具体我记不清了", item, context={})
    assert hit["hit"] is True and hit["points"] == item["max_deduction"]
    miss = judge(backend, "我亲手实现了特征工程模块，用 PyTorch 写了 Dataset 与训练循环，消融显示提升 3.2%。", item, context={})
    assert miss["hit"] is False and miss["points"] == 0


if __name__ == "__main__":
    test_default_rubric_shape()
    test_answer_vs_material_split()
    test_judge_heuristic_hit_and_miss()
    print("ALL RUBRIC TESTS PASSED")
