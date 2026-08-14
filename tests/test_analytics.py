"""短板跨场聚合分析离线测试（纯标准库）。

验证 aggregate_weaknesses / render_aggregate_report：
- 多场面试沉淀的短板能被正确聚合（分类计数、严重度、趋势、反复短板）
- 场景过滤生效
- 空库渲染友好
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from llm_backend import MockBackend
from storage import Store
from interview_engine import InterviewSession
from analytics import aggregate_weaknesses, render_aggregate_report


def _run_session(store, scenario, answers):
    backend = MockBackend({})
    profile = {"name": "测试候选人", "demo_answers": answers}
    qbank = ["Q1 请介绍项目。", "Q2 你的规划？"]
    fubank = ["FU 讲讲你亲手实现的细节。"]
    sess = InterviewSession(
        backend, store, "analytics-tenant", "测试候选人", profile, scenario,
        qbank, fubank, hard_block=True,
    )
    sess.ask_first()
    for a in answers:
        sess.answer(a)
    sess.finish()
    return sess


def test_aggregate():
    tmp = tempfile.mkdtemp()
    store = Store(tmp, "analytics-tenant")
    tenant = "analytics-tenant"

    # 保研 2 场 + 申博 1 场，每场用浅回答触发硬阻塞短板
    shallow = ["还行吧", "具体细节我记不清了"]
    _run_session(store, "保研", shallow)
    _run_session(store, "保研", shallow)
    _run_session(store, "申博", shallow)

    agg = aggregate_weaknesses(store, tenant)
    assert agg["session_count"] == 3
    assert agg["weakness_count"] >= 6, f"期望≥6条短板，实际 {agg['weakness_count']}"
    assert "项目/代码细节" in agg["category_counts"]
    assert agg["category_counts"]["项目/代码细节"] >= 6
    assert "medium" in agg["severity_counts"]
    # 跨场趋势结构
    trend = agg["category_trends"]["项目/代码细节"]
    assert trend["count"] >= 6
    assert trend["direction"] in ("improving", "worsening", "stable", "insufficient")
    # 反复短板（≥2 次）
    assert any(r["category"] == "项目/代码细节" for r in agg["top_recurring"])

    # 场景过滤：保研 2 场，弱点数应为单场的 2 倍（与 rubric 规模解耦，避免硬断言）
    ref_store = Store(tempfile.mkdtemp(), "ref-tenant")
    ref_sess = _run_session(ref_store, "保研", shallow)
    per = len(ref_store.get_weaknesses(ref_sess.session_id))
    agg_baoyan = aggregate_weaknesses(store, tenant, scenario="保研")
    assert agg_baoyan["session_count"] == 2
    assert agg_baoyan["weakness_count"] == 2 * per

    # 渲染可读
    md = render_aggregate_report(agg)
    assert "短板库聚合分析报告" in md
    assert "反复出现的短板" in md

    # 空库友好
    empty_store = Store(tempfile.mkdtemp(), "empty-tenant")
    md_empty = render_aggregate_report(aggregate_weaknesses(empty_store, "empty-tenant"))
    assert "暂无短板数据" in md_empty

    # owner 删除权后仍为空
    store.purge_owner()
    assert aggregate_weaknesses(store, tenant)["weakness_count"] == 0

    print("ALL ANALYTICS TESTS PASSED")


if __name__ == "__main__":
    test_aggregate()
