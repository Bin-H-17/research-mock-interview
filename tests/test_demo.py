"""科研模拟面试 Skill — 闭环冒烟测试（无网络、无第三方依赖）。

运行：
  python tests/test_demo.py
或：
  python -m tests.test_demo
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from llm_backend import MockBackend
from storage import Store
from interview_engine import InterviewSession


def test_closed_loop():
    tmp = tempfile.mkdtemp()
    backend = MockBackend({})
    store = Store(tmp, "test-tenant")

    profile = {
        "name": "测试候选人",
        "demo_answers": ["还行吧", "具体细节我记不清了"],
    }
    questions = {
        "保研": ["Q1 请介绍你的项目。", "Q2 你的未来规划？"],
        "followup": ["FU 请讲讲你亲手实现的细节。"],
    }

    sess = InterviewSession(
        backend, store, "test-tenant", "测试候选人", profile, "保研",
        questions["保研"], questions["followup"], hard_block=True,
    )
    q = sess.ask_first()
    assert q, "首题不应为空"

    r1 = sess.answer("还行吧")  # 过短 → 应触发硬阻塞追问
    assert r1["type"] == "followup", f"期望 followup，实际 {r1['type']}"

    r2 = sess.answer("具体细节我记不清了")  # 含浅层标记 → 应触发硬阻塞追问
    assert r2["type"] == "followup", f"期望 followup，实际 {r2['type']}"

    report = sess.finish()
    assert "复盘报告" in report, "复盘报告缺失"

    wk = store.get_weaknesses()
    assert len(wk) >= 1, "短板库应至少记录一项"

    sessions = store.list_sessions()
    assert len(sessions) == 1 and sessions[0]["status"] == "finished"

    # owner 删除权闭环
    n = store.purge_owner()
    assert n >= 1, "purge 应删除数据"
    assert store.get_weaknesses() == [], "purge 后短板库应为空"
    assert store.list_sessions() == [], "purge 后记录应为空"

    print("ALL TESTS PASSED")


if __name__ == "__main__":
    test_closed_loop()
