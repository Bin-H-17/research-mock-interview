---
name: research-mock-interview
description: 本地优先的「科研模拟面试」Hermes Skill。面向保研/申博/科研岗求职/答辩组会/海外 PhD 场景，基于候选人真实科研资料进行 AI 模拟面试，含讲项目·代码硬阻塞追问、评分、短板库沉淀与复盘报告。本地单租户、可删除、无遥测、不出域；LLM 后端可插拔（mock 离线 / ollama 本地 / cloud BYOK）。当用户提到「模拟面试」「科研面试」「保研面试」「申博面试」「面试复盘」「短板库」「科研背题」或希望用 AI 演练科研类面试时使用本 Skill。
---

# 科研模拟面试（Research Mock Interview）Hermes Skill

## 1. 这是什么

一个**本地优先**的科研场景模拟面试系统，以 Hermes Skill 形态交付。它读取候选人的真实科研资料（简历 / 项目 / 论文），
针对保研、申博、科研岗求职、答辩、组会、海外 PhD 等场景，用可插拔的 LLM 后端扮演严谨考官，进行多轮对话式模拟面试，
并在候选人「讲项目 / 代码」回答过浅时发起**硬阻塞追问**，结束后产出评分 + 短板库 + 复盘报告。

### 1.1 与架构方案的一致性（已锁定决策）
- **X1 目标用户**：全方向（保研/申博 + 求职轻量版），本 v1 题库覆盖保研/申博/求职/答辩/组会/海外phd 六类场景。
- **X2 形态**：本地 Hermes Skill + 公域内容引流；本仓库即 Skill 本体。
- **X3 语音**：v1.1 已落地「可插拔语音双工」——`mock` 离线零依赖跑通整条链路；真实 STT（`vosk`/`whisper`）+ 真实 TTS（`pyttsx3`/`edge-tts`）为可选后端，全部懒加载，缺失依赖时运行时明确报错（不破坏核心零依赖）。
- **X4 公众号采集**：已放弃，本 Skill 不采集任何外部内容源。
- **X5 Python 版本**：目标 **3.12**，最低 **3.11**（详见 `requirements.txt` 与 §6）。
- **可插拔 LLM 后端**：抽象接口 + `mock`（离线零依赖）/ `ollama`（本地默认）/ `cloud`（BYOK，密钥不落盘）。
- **冷启动资料**：示例脱敏数据先行（`data/sample_profile.json`），预留真实资料导入入口（`cli run --profile`）。
- **隐私铁律**：本地单租户、可删除、无遥测、不出域；`tenant_id=local`；`purge` 一键清除 owner 全部数据。

## 2. 何时触发
- 用户想练习 / 复盘科研类面试（保研、申博、科研岗、答辩、组会、海外 PhD）。
- 用户希望基于自己的项目经历做「讲清楚、讲细节」的压力测试。
- 用户需要一份结构化复盘报告与可沉淀的短板清单。

## 3. 工作流（主理人 / 使用者执行顺序）

### 第一步：环境准备（一次性）
```bash
cd research-mock-interview
python --version            # 需 >=3.11，推荐 3.12
pip install -r requirements.txt   # 可选：仅当你要用 config.yaml 时才需 PyYAML
```

### 第二步：跑通演示（无网也能跑）
```bash
python src/cli.py run --demo
```
`--demo` 使用内置示例资料 + `mock` 后端，自动跑完「提问→作答→硬阻塞追问→评分→复盘报告」闭环，
证明系统离线可运行、数据已落盘本地 SQLite。

### 第三步：接入真实资料
把你的真实简历/项目整理成一个 JSON（参考 `data/sample_profile.json` 字段），然后：
```bash
python src/cli.py run --profile /path/to/your_profile.json --scenario 保研
```
进入交互模式，逐轮作答；输入 `/finish` 结束并生成报告，`/quit` 中途退出（记录仍保留）。

### 第四步：切换 LLM 后端（可选）
复制 `config.example.yaml` 为 `config.yaml`，把 `llm.backend` 改成：
- `mock`：离线零依赖（默认，适合演示 / 无网）。
- `ollama`：本地默认生产后端，填 `base_url` / `model`（如 `qwen2.5:7b`）。
- `cloud`：云端 API（BYOK），密钥只来自环境变量（如 `RMI_LLM_API_KEY`），绝不硬编码 / 落盘。

### 第五步：查看沉淀与删除权
```bash
python src/cli.py list          # 列出本 tenant 全部面试
python src/cli.py report --id <session_id前8位或完整>   # 看复盘报告
python src/cli.py weakness      # 看短板库
python src/cli.py purge --yes   # owner 删除权：清除本 tenant 全部本地数据
```

### 第六步（v1.1 新增）：语音双工模式（可插拔）
```bash
# 离线自检：mock 双工，无需麦克风/网络，证明语音编排链路闭环
python src/cli.py run --demo --voice

# 接入真实语音（需先 pip install 对应可选依赖，见 requirements.txt）
# 复制 config.example.yaml 为 config.yaml，设 voice.enabled=true 或运行时加 --voice，
# 并把 voice.stt/tts 的 backend 改为 vosk/whisper/pyttsx3/edge，填好模型路径。
```

### 第七步（v1.1 新增）：短板库跨场聚合分析
```bash
python src/cli.py analyze                 # 全部场景聚合
python src/cli.py analyze --scenario 保研   # 只看某场景
python src/cli.py analyze --out report.md  # 导出 Markdown 报告
```
聚合维度：分类分布、严重度分布、跨场趋势（改善/恶化/持平）、反复出现的短板（≥2 次）与行动建议。

## 4. 模块职责（src/）
- `llm_backend.py`：`LLMBackend` 抽象 + `MockBackend` / `OllamaBackend` / `CloudBackend`，`from_config(cfg)` 工厂按配置切换。
- `storage.py`：`Store` 封装 SQLite 本地持久化，tenant 作用域隔离，`purge_owner()` 实现删除权闭环。
- `interview_engine.py`：`InterviewSession` 驱动「导入→提问→硬阻塞追问→评分→短板库→复盘报告」。
- `voice_io.py`（v1.1）：`STTProvider` / `TTSProvider` / `DuplexVoice` 可插拔语音；`mock` 离线零依赖，真实后端懒加载 + 缺失依赖守卫。
- `analytics.py`（v1.1）：`aggregate_weaknesses` / `render_aggregate_report` 短板跨场聚合（纯标准库）。
- `cli.py`：argparse 入口（`run` / `list` / `report` / `weakness` / `purge` / `analyze`，`run` 支持 `--voice`）。

## 5. 设计纪律（不可违反）
1. **不出域**：任何数据只在本地 SQLite；cloud 后端只把面试文本发往用户配置的 API，密钥仅来自环境变量。
2. **无遥测**：不收集、不上报任何使用行为。
3. **可删除**：`data_dir` 可整体删除；`purge` 提供程序化一键清除。
4. **后端可插拔**：业务代码只依赖 `LLMBackend` 抽象，新增后端只需实现 `generate()`。
5. **冷启动友好**：示例数据保证开箱即跑；真实资料通过 `--profile` 导入，格式向后兼容。

## 6. 运行环境
- 目标 Python **3.12**；最低 **3.11**（见 `requirements.txt` 注释）。
- 核心依赖仅标准库；`PyYAML` 为可选（启用 `config.yaml` 时才需要）。
- 语音为**可选增强**：核心仍零硬性第三方依赖；真实 STT/TTS 依赖仅在启用语音且选择真实引擎时需要（见 `requirements.txt` 注释）。
