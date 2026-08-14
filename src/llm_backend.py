"""可插拔 LLM 后端：mock / ollama / cloud。

设计原则（来自架构文档「可插拔 LLM 后端」小节）：
- 统一抽象接口 LLMBackend.generate(prompt, system=None, task=None, context=None) -> str
- mock：纯标准库规则引擎，离线零依赖，用于 demo 与无网环境
- ollama：本地默认生产后端，走 http://localhost:11434/api/generate（urllib，无额外依赖）
- cloud：BYOK，密钥仅来自环境变量，绝不落盘 / 硬编码
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error


class LLMBackend:
    """所有后端的统一抽象。业务代码只依赖此接口。"""

    def generate(self, prompt: str, system: str | None = None, task: str | None = None, context: dict | None = None) -> str:
        raise NotImplementedError

    @staticmethod
    def from_config(cfg: dict) -> "LLMBackend":
        llm = cfg.get("llm", {}) if isinstance(cfg, dict) else {}
        backend = (llm.get("backend") or "mock").lower()
        if backend == "mock":
            return MockBackend(llm.get("mock", {}) or {})
        if backend == "ollama":
            return OllamaBackend(llm.get("ollama", {}) or {})
        if backend == "cloud":
            return CloudBackend(llm.get("cloud", {}) or {})
        raise ValueError(f"未知 LLM backend: {backend!r}（可选 mock|ollama|cloud）")


class MockBackend(LLMBackend):
    """离线规则引擎。不调用任何网络/模型，返回可解析的结构化占位内容。

    它忠实模拟真实后端会在各 task 下产出的「形状」，使上层引擎与持久化逻辑
    在没有任何模型/网络时也能被完整验证。
    """

    def __init__(self, opts: dict | None = None):
        self.opts = opts or {}
        self._ask_idx = 0
        self._follow_idx = 0

    def generate(self, prompt: str, system: str | None = None, task: str | None = None, context: dict | None = None) -> str:
        ctx = context or {}
        bank = ctx.get("bank") or []
        follow_bank = ctx.get("followup_bank") or []
        profile_name = ctx.get("profile_name", "候选人")
        scenario = ctx.get("scenario", "")

        if task == "ask":
            if bank:
                q = bank[self._ask_idx % len(bank)]
                self._ask_idx += 1
                return f"【{profile_name}，第{self._ask_idx}题】{q}"
            return f"【{profile_name}】请介绍一下你的科研背景与最自豪的一个项目。"

        if task == "followup":
            if follow_bank:
                q = follow_bank[self._follow_idx % len(follow_bank)]
                self._follow_idx += 1
                return f"（硬阻塞追问）{q}"
            return "（硬阻塞追问）能具体讲讲你在这个项目里亲手做的部分、踩过的坑和怎么解决的吗？"

        if task == "evaluate":
            is_phd = scenario == "海外phd"
            # 维度名与 rubric.default_rubric() 对齐（含'英语/海外适配'）
            return json.dumps({
                "overall": 78,
                "dimensions": {
                    "项目深度": 75,
                    "技术细节": 72,
                    "量化成果": 68,
                    "动机匹配": 80,
                    "表达清晰": 82,
                    "诚实度": 85,
                    "材料完整度": 90,
                    "英语/海外适配": 82 if is_phd else 76,
                },
                "summary": f"{profile_name} 整体表现中等偏上，项目细节需进一步打磨。",
            }, ensure_ascii=False)

        if task == "report":
            weaknesses = ctx.get("weaknesses") or []
            wk = "\n".join(f"- {w}" for w in weaknesses) or "- 暂无明显短板"
            overall = ctx.get("overall", 78)
            is_phd = scenario == "海外phd"
            return (
                f"# 模拟面试复盘报告（{profile_name}）\n\n"
                f"## 总体评分：{overall}/100\n\n"
                f"## 维度评分\n- 项目深度 75\n- 技术细节 72\n- 量化成果 68\n"
                f"- 动机匹配 80\n- 表达清晰 82\n- 诚实度 85\n- 材料完整度 90\n"
                f"- 英语/海外适配 {82 if is_phd else 76}\n\n"
                f"## 短板清单\n{wk}\n\n"
                f"## 改进建议\n"
                f"1. 针对硬阻塞追问，提前准备项目中的「亲手实现 + 踩坑 + 解决」三段式素材。\n"
                f"2. 用数据量化科研成果（如指标提升%、论文贡献度）。\n"
            )

        if task == "judge":
            item = ctx.get("rubric_item") or {}
            ans = ctx.get("answer", "")
            t = (ans or "").strip()
            shallow = ["不太清楚", "记不清", "忘了", "不知道", "不太了解", "没太关注",
                       "大概", "好像", "还行吧", "不太行", "不太", "不太确定", "没太"]
            hit = len(t) < 45 or any(m in t for m in shallow)
            points = item.get("max_deduction", 0) if hit else 0
            reason = (
                f"作答缺乏可验证的具体细节，未达合格标准「{item.get('criterion', '')}」。"
                if hit else "作答包含具体细节，视为达标。"
            )
            return json.dumps({"hit": bool(hit), "points": int(points), "reason": reason}, ensure_ascii=False)

        # 默认回声，便于调试
        return f"[mock] {prompt[:120]}"


class OllamaBackend(LLMBackend):
    """本地 Ollama 后端（默认生产后端）。使用标准库 urllib，无额外依赖。"""

    def __init__(self, opts: dict | None = None):
        o = opts or {}
        self.base_url = (o.get("base_url") or "http://localhost:11434").rstrip("/")
        self.model = o.get("model", "qwen2.5:7b")
        self.temperature = float(o.get("temperature", 0.7))

    def generate(self, prompt: str, system: str | None = None, task: str | None = None, context: dict | None = None) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        if system:
            payload["system"] = system
        resp = self._post(f"{self.base_url}/api/generate", payload)
        return resp.get("response", "")

    def _post(self, url: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"无法连接 Ollama（{self.base_url}）。请确认本地已启动 Ollama 且模型 {self.model} 已拉取。"
            ) from e


class CloudBackend(LLMBackend):
    """云端 API 后端（BYOK）。密钥仅来自环境变量，绝不落盘 / 硬编码。"""

    def __init__(self, opts: dict | None = None):
        import os
        o = opts or {}
        self.api_base = (o.get("api_base") or "https://api.openai.com/v1").rstrip("/")
        self.model = o.get("model", "gpt-4o-mini")
        self.temperature = float(o.get("temperature", 0.7))
        self.api_key_env = o.get("api_key_env", "RMI_LLM_API_KEY")
        self.api_key = os.environ.get(self.api_key_env, "")
        if not self.api_key:
            raise RuntimeError(
                f"Cloud backend 需要环境变量 {self.api_key_env}（BYOK，密钥不落盘）。"
                f"请先导出后重试，例如：export {self.api_key_env}=sk-xxx"
            )

    def generate(self, prompt: str, system: str | None = None, task: str | None = None, context: dict | None = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(f"{self.api_base}/chat/completions", data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"]
        except urllib.error.URLError as e:
            raise RuntimeError(f"Cloud backend 调用失败（{self.api_base}）：{e}") from e
