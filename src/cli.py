"""科研模拟面试 Agent Skill — 命令行入口（agent-agnostic，可被各大主流 Agent 调用）。

子命令：
  intake    生成面试前调查文件（问清场景/面试官/岗位/目标）
  persona   基于调查（+可选调研笔记）构建面试官/公司画像
  run       开始一场模拟面试（材料收集 → 硬阻塞追问 → 按 rubric 评分 → 报告）
  rubric    查看/导出评分标准（扣分点目录）
  materials 管理一场面试的提交材料
  list      列出本 tenant 的面试记录
  report    查看某场面试复盘报告
  weakness  查看短板库
  analyze   短板库跨场聚合分析
  purge     owner 删除权：清除本 tenant 全部本地数据
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# 让直接运行 cli.py 也能 import 兄弟模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm_backend import LLMBackend
from storage import Store
from interview_engine import InterviewSession
from voice_io import DuplexVoice
from analytics import aggregate_weaknesses, render_aggregate_report
from persona import generate_intake_survey, render_intake_markdown, build_persona
from rubric import default_rubric, load_rubric

DEFAULT_CONFIG = {
    "skill": {
        "name": "research-mock-interview",
        "tenant_id": "local",
        "data_dir": "./data_store",
        "no_telemetry": True,
    },
    "llm": {
        "backend": "mock",
        "mock": {},
        "ollama": {"base_url": "http://localhost:11434", "model": "qwen2.5:7b", "temperature": 0.7},
        "cloud": {
            "api_base": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
            "api_key_env": "RMI_LLM_API_KEY",
            "temperature": 0.7,
        },
    },
    "interview": {
        "default_scenario": "保研",
        "hard_block_followup": True,
        "auto_report": True,
        "required_materials": ["简历", "项目/论文", "成绩单"],
    },
    "voice": {
        "enabled": False,
        "backend": "mock",
        "stt": {
            "backend": "mock",
            "mock": {"script": [
                "我在这个项目里主要负责特征工程和模型训练，用的 PyTorch 和 DGL。",
                "整体效果还行吧，具体指标我记不太清了。",
                "/finish",
            ]},
            "vosk": {"model_path": "", "rate": 16000, "phrase_timeout": 3.0, "language": "cn"},
            "whisper": {"model_size": "base", "device": "cpu", "compute_type": "int8", "language": "zh"},
        },
        "tts": {
            "backend": "mock",
            "pyttsx3": {"rate": 150, "volume": 0.9, "voice": ""},
            "edge": {"voice": "zh-CN-XiaoxiaoNeural", "rate": "+0%", "volume": "+0%"},
        },
    },
}


def _deep_merge(base, override):
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def load_config(path: str | None) -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if not path:
        return cfg
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            user = yaml.safe_load(f) or {}
        _deep_merge(cfg, user)
        return cfg
    except ImportError:
        print("[warn] 未安装 PyYAML，使用内置默认配置（如需 YAML 配置请 pip install pyyaml）。", file=sys.stderr)
        return cfg
    except FileNotFoundError:
        print(f"[warn] 配置文件 {path} 不存在，使用内置默认配置。", file=sys.stderr)
        return cfg


def _here() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _data_dir() -> str:
    return os.path.join(_here(), "..", "data")


def load_questions(questions_path: str) -> dict:
    try:
        with open(questions_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


VOICE_STOP = ("/finish", "/quit", "结束", "退出", "stop")


def run_voice_loop(sess, voice, max_rounds: int = 12) -> int:
    print("=== 语音模式（mock 离线 / 真实需可选依赖）===\n")
    q = sess.ask_first()
    voice.speak(q)
    print(f"考官：{q}\n")
    rounds = 0
    while rounds < max_rounds:
        try:
            ans = voice.listen()
        except RuntimeError as e:
            print(f"[voice error] {e}", file=sys.stderr)
            return 1
        print(f"候选人（语音识别）：{ans}")
        if any(s in ans.lower() for s in VOICE_STOP):
            break
        res = sess.answer(ans)
        try:
            voice.speak(res["content"])
        except RuntimeError as e:
            print(f"[voice tts error] {e}", file=sys.stderr)
        print(f"考官：{res['content']}\n")
        rounds += 1
    report = sess.finish()
    try:
        voice.speak("面试结束，正在生成复盘报告。")
    except RuntimeError:
        pass
    print("=== 复盘报告 ===")
    print(report)
    print(f"\n[done] session_id={sess.session_id}（数据已落盘到 {sess.store.data_dir}）")
    return 0


# ---------------- intake / persona / rubric / materials ----------------

def cmd_intake(args):
    survey = generate_intake_survey()
    md = render_intake_markdown(survey)
    out_md = args.out or os.path.join(_data_dir(), "intake_survey.md")
    out_json = os.path.splitext(out_md)[0] + ".json"
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(md)
    payload = {"meta": survey["meta"], "fields": survey["fields"],
               "answers": {f["key"]: "" for f in survey["fields"]}}
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[done] 调查文件已生成：\n  - {out_md}（可读，填写后）\n  - {out_json}（结构化，供 `persona` 读取）")
    return 0


def cmd_persona(args):
    cfg = load_config(args.config)
    path = args.intake or os.path.join(_data_dir(), "intake_survey.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        answers = data.get("answers", data)
    except Exception as e:
        print(f"[error] 无法读取调查文件 {path}：{e}", file=sys.stderr)
        return 1
    notes = None
    if args.notes and os.path.exists(args.notes):
        with open(args.notes, "r", encoding="utf-8") as f:
            notes = f.read()
    backend = LLMBackend.from_config(cfg) if (cfg["llm"]["backend"] != "mock") else None
    persona = build_persona(answers, research_notes=notes, llm=backend)
    out = args.out or os.path.join(_data_dir(), "persona.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(persona, f, ensure_ascii=False, indent=2)
    print(f"[done] 面试官画像已生成 → {out}")
    print(f"  身份：{persona.get('identity','')}")
    print(f"  风格：{persona.get('style','')} —— {persona.get('style_desc','')}")
    print(f"  关注点：{', '.join(persona.get('focus_areas', []))}")
    return 0


def cmd_rubric(args):
    rb = load_rubric(args.file)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(rb, f, ensure_ascii=False, indent=2)
        print(f"[done] 评分标准已导出 → {args.out}")
        return 0
    print("=== 评分标准（扣分点目录）===")
    for r in rb:
        tag = " [材料]" if r.get("material") else ""
        print(f"- {r['id']} {r['dimension']}（最大扣 {r['max_deduction']}）{tag}")
        print(f"    合格标准：{r['criterion']}")
    return 0


def cmd_materials(args):
    cfg = load_config(args.config)
    store = Store(args.data_dir or cfg["skill"]["data_dir"], cfg["skill"]["tenant_id"])
    sid = store.resolve_session_id(args.id) if args.id else None
    if not sid:
        print(f"（找不到匹配 {args.id} 的 session）", file=sys.stderr)
        return 1
    if args.add:
        store.add_material(sid, args.add, True)
        print(f"[done] 已标记材料「{args.add}」为已提交。")
        return 0
    rows = store.get_materials(sid)
    if not rows:
        print("（该 session 暂无材料记录）")
        return 0
    for r in rows:
        print(f"- [{'✓' if r['provided'] else '✗'}] {r['name']}")
    return 0


# ---------------- run ----------------

def _load_profile(profile_path):
    with open(profile_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_json_optional(path):
    if not path:
        return None
    if not os.path.exists(path):
        print(f"[warn] 文件不存在：{path}，忽略。", file=sys.stderr)
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def cmd_run(args):
    cfg = load_config(args.config)
    skill = cfg["skill"]
    interview = cfg["interview"]
    tenant_id = skill["tenant_id"]
    data_dir = args.data_dir or skill["data_dir"]
    scenario = args.scenario or interview["default_scenario"]
    hard_block = interview.get("hard_block_followup", True)

    backend = LLMBackend.from_config(cfg)
    store = Store(data_dir, tenant_id)

    profile_path = args.profile or os.path.join(_data_dir(), "sample_profile.json")
    try:
        profile = _load_profile(profile_path)
    except Exception as e:
        print(f"[error] 无法读取资料文件 {profile_path}: {e}", file=sys.stderr)
        return 1
    profile_name = profile.get("name", "示例候选人")

    persona = _load_json_optional(args.persona)
    if persona is None and args.demo:
        persona = _load_json_optional(os.path.join(_data_dir(), "persona_example.json"))
    rubric = load_rubric(args.rubric)
    required_materials = interview.get("required_materials", ["简历", "项目/论文", "成绩单"])
    submitted_materials = profile.get("materials", [])

    questions = load_questions(os.path.join(_data_dir(), "sample_questions.json"))
    bank = questions.get(scenario, questions.get("保研", []))
    followup_bank = questions.get("followup", [])

    sess = InterviewSession(
        backend, store, tenant_id, profile_name, profile, scenario, bank, followup_bank,
        persona=persona, rubric=rubric,
        required_materials=required_materials, submitted_materials=submitted_materials,
        hard_block=hard_block,
    )
    print(f"=== 科研模拟面试启动 ===\n场景：{scenario} | 候选人：{profile_name} | 后端：{cfg['llm']['backend']}")
    if persona:
        print(f"面试官画像：{persona.get('identity','')}（{persona.get('style','')}）")
    print()

    # 材料收集阶段（demo 非交互，按已提交材料判定；交互模式会追问缺失项）
    sess.collect_materials(interactive=bool(args.interactive))

    voice_enabled = bool(getattr(args, "voice", False) or cfg.get("voice", {}).get("enabled", False))
    if voice_enabled:
        try:
            voice = DuplexVoice.from_config(cfg)
        except RuntimeError as e:
            print(f"[voice init error] {e}", file=sys.stderr)
            return 1
        return run_voice_loop(sess, voice)

    q = sess.ask_first()
    print(f"考官：{q}\n")

    if args.demo:
        sample_answers = profile.get("demo_answers", ["我在某课题中负责模型设计，但细节记不太清。", "我们使用了主流方法，效果还不错。"])
        for ans in sample_answers:
            print(f"候选人：{ans}")
            res = sess.answer(ans)
            print(f"考官：{res['content']}\n")
        report = sess.finish()
        print("=== 复盘报告 ===")
        print(report)
        print(f"\n[done] session_id={sess.session_id}（数据已落盘到 {data_dir}）")
        return 0

    try:
        while True:
            ans = input("候选人（输入 /finish 结束并出报告，/quit 退出，/material 补充材料）：").strip()
            if ans == "/quit":
                print("已退出，未结束的记录仍保存在本地。")
                return 0
            if ans == "/finish":
                report = sess.finish()
                print("\n=== 复盘报告 ===")
                print(report)
                return 0
            if ans == "/material":
                m = input("材料名称：").strip()
                if m:
                    sess.store.add_material(sess.session_id, m, True)
                    print(f"已记录材料「{m}」为已提交。")
                continue
            if not ans:
                continue
            res = sess.answer(ans)
            print(f"考官：{res['content']}\n")
    except (EOFError, KeyboardInterrupt):
        print("\n已中断。")
        return 0


def cmd_list(args):
    cfg = load_config(args.config)
    store = Store(args.data_dir or cfg["skill"]["data_dir"], cfg["skill"]["tenant_id"])
    rows = store.list_sessions()
    if not rows:
        print("（无面试记录）")
        return 0
    for r in rows:
        print(f"{r['id'][:8]} | {r['scenario']} | {r['status']} | {r['name']} | {r['created_at']}")
    return 0


def cmd_report(args):
    cfg = load_config(args.config)
    store = Store(args.data_dir or cfg["skill"]["data_dir"], cfg["skill"]["tenant_id"])
    sid = store.resolve_session_id(args.id)
    if not sid:
        print(f"（找不到匹配 {args.id} 的 session）", file=sys.stderr)
        return 1
    rep = store.get_report(sid)
    if not rep:
        print(f"（session {sid} 暂无报告，可能尚未结束）", file=sys.stderr)
        return 1
    print(rep)
    return 0


def cmd_weakness(args):
    cfg = load_config(args.config)
    store = Store(args.data_dir or cfg["skill"]["data_dir"], cfg["skill"]["tenant_id"])
    sid = store.resolve_session_id(args.id) if args.id else None
    rows = store.get_weaknesses(sid)
    if not rows:
        print("（短板库为空）")
        return 0
    for r in rows:
        print(f"- [{r.get('severity', '')}] {r['category']}: {r['detail']}")
    return 0


def cmd_purge(args):
    cfg = load_config(args.config)
    if not args.yes:
        print("⚠️ 此操作将清除当前 tenant 的全部本地数据（owner 删除权闭环）。")
        print("若确认，请加 --yes 参数。")
        return 1
    store = Store(args.data_dir or cfg["skill"]["data_dir"], cfg["skill"]["tenant_id"])
    n = store.purge_owner()
    print(f"[done] 已清除 {n} 行本地数据（tenant={cfg['skill']['tenant_id']}）。")
    return 0


def cmd_analyze(args):
    cfg = load_config(args.config)
    store = Store(args.data_dir or cfg["skill"]["data_dir"], cfg["skill"]["tenant_id"])
    agg = aggregate_weaknesses(store, cfg["skill"]["tenant_id"], scenario=args.scenario)
    report = render_aggregate_report(agg)
    print(report)
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(report)
            print(f"\n[done] 聚合报告已写入 {args.out}")
        except Exception as e:
            print(f"[warn] 写入 {args.out} 失败：{e}", file=sys.stderr)
    return 0


def build_parser():
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--config", default=None, help="config.yaml 路径（可选，缺失则用内置默认）")
    parent.add_argument("--data-dir", default=None, help="本地数据目录，覆盖配置")

    p = argparse.ArgumentParser(description="科研模拟面试 Agent Skill CLI", parents=[parent])
    sub = p.add_subparsers(dest="cmd")

    i = sub.add_parser("intake", parents=[parent], help="生成面试前调查文件")
    i.add_argument("--out", default=None, help="调查文件输出路径（.md/.json 各一份）")
    i.set_defaults(func=cmd_intake)

    pe = sub.add_parser("persona", parents=[parent], help="构建面试官/公司画像")
    pe.add_argument("--intake", default=None, help="调查 JSON 路径（默认 data/intake_survey.json）")
    pe.add_argument("--notes", default=None, help="可选：调研笔记文本文件路径")
    pe.add_argument("--out", default=None, help="画像输出 JSON 路径")
    pe.set_defaults(func=cmd_persona)

    ru = sub.add_parser("rubric", parents=[parent], help="查看/导出评分标准")
    ru.add_argument("--file", default=None, help="评分标准 JSON 路径（默认内置）")
    ru.add_argument("--out", default=None, help="导出到该 JSON 路径")
    ru.set_defaults(func=cmd_rubric)

    mt = sub.add_parser("materials", parents=[parent], help="管理一场面试的提交材料")
    mt.add_argument("--id", required=True, help="session id（完整或前8位前缀）")
    mt.add_argument("--add", default=None, help="标记某材料为已提交（填材料名称）")
    mt.set_defaults(func=cmd_materials)

    r = sub.add_parser("run", parents=[parent], help="开始一场模拟面试")
    r.add_argument("--profile", default=None, help="候选人资料 JSON 路径（缺省用示例数据）")
    r.add_argument("--persona", default=None, help="面试官画像 JSON 路径")
    r.add_argument("--rubric", default=None, help="评分标准 JSON 路径（默认内置）")
    r.add_argument("--scenario", default=None, help="场景：保研/申博/求职/答辩/组会/海外phd")
    r.add_argument("--demo", action="store_true", help="无交互演示模式（自动跑通闭环）")
    r.add_argument("--interactive", action="store_true", help="交互模式（含材料追问）")
    r.add_argument("--voice", action="store_true", help="启用语音双工模式")
    r.set_defaults(func=cmd_run)

    l = sub.add_parser("list", parents=[parent], help="列出本 tenant 的面试记录")
    l.set_defaults(func=cmd_list)

    rp = sub.add_parser("report", parents=[parent], help="查看某场面试复盘报告")
    rp.add_argument("--id", required=True, help="session id（完整或前8位前缀）")
    rp.set_defaults(func=cmd_report)

    w = sub.add_parser("weakness", parents=[parent], help="查看短板库")
    w.add_argument("--id", default=None, help="可选：只看某场 session")
    w.set_defaults(func=cmd_weakness)

    pg = sub.add_parser("purge", parents=[parent], help="清除本 tenant 全部本地数据（owner 删除权）")
    pg.add_argument("--yes", action="store_true", help="确认清除")
    pg.set_defaults(func=cmd_purge)

    a = sub.add_parser("analyze", parents=[parent], help="短板库跨场聚合分析")
    a.add_argument("--scenario", default=None, help="可选：仅分析某场景（如 保研）")
    a.add_argument("--out", default=None, help="可选：将报告写入该 Markdown 文件路径")
    a.set_defaults(func=cmd_analyze)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
