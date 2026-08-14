"""persona 模块测试（调查生成 + 画像模板构建，无网络）。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from persona import generate_intake_survey, render_intake_markdown, build_persona


def test_intake_survey():
    s = generate_intake_survey()
    assert "fields" in s and len(s["fields"]) >= 8
    md = render_intake_markdown(s)
    assert "调查" in md and "goal_type" in md


def test_build_persona_template():
    intake = {
        "goal_type": "保研",
        "org_name": "某985高校",
        "position_or_program": "计算机学硕",
        "interviewer_name": "李教授",
        "interviewer_style": "严厉压力型",
        "known_focus": "科研深度",
    }
    p = build_persona(intake)  # 无 llm → 模板兜底
    assert p["identity"] and "李教授" in p["identity"]
    assert p["style"] == "严厉压力型"
    assert any("科研深度" in f for f in p["focus_areas"])


if __name__ == "__main__":
    test_intake_survey()
    test_build_persona_template()
    print("ALL PERSONA TESTS PASSED")
