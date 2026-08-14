# 科研模拟面试 Hermes Skill — 交付总览

## 这是什么
本地优先的科研场景模拟面试系统（Hermes Skill 形态）。基于候选人的**真实科研资料**，针对
**保研 / 申博 / 科研岗求职 / 答辩 / 组会 / 海外 PhD** 六类场景进行 AI 模拟面试，内含：

- 「讲项目 / 代码」**硬阻塞追问**（回答过浅时强制深挖）——差异化护城河之一；
- 自动评分 + **短板库**沉淀 + **复盘报告**；
- 本地单租户、可删除、无遥测、不出域（隐私铁律）；
- **可插拔 LLM 后端**：`mock`（离线零依赖）/ `ollama`（本地默认）/ `cloud`（BYOK，密钥不落盘）。

## 交付物位置
```
科研模拟面试/research-mock-interview/
├── SKILL.md                 # Hermes Skill 定义（触发词 + 工作流）
├── config.example.yaml      # 配置样例（可选）
├── requirements.txt         # 依赖声明（Python 版本 + 可选 PyYAML）
├── README.md                # 使用说明
├── src/
│   ├── llm_backend.py       # 可插拔后端 mock / ollama / cloud
│   ├── storage.py           # 本地 SQLite + owner 删除权闭环
│   ├── interview_engine.py  # 面试引擎（提问/硬阻塞追问/评分/短板库/报告）
│   ├── voice_io.py          # 可插拔语音双工（v1.1：mock 离线 + 真实 STT/TTS 懒加载）
│   ├── analytics.py         # 短板跨场聚合分析（v1.1：纯标准库）
│   └── cli.py               # 命令行入口（run/list/report/weakness/purge/analyze）
├── data/
│   ├── sample_profile.json  # 脱敏示例资料（冷启动）
│   └── sample_questions.json# 分场景题库 + 硬阻塞追问库
└── tests/
    ├── test_demo.py         # 离线闭环冒烟测试
    ├── test_voice.py        # 语音可插拔离线测试 + 真实后端缺失依赖守卫
    └── test_analytics.py    # 短板聚合离线测试
```

## 已落实的架构决策（X1~X5）
- **X1** 全方向（保研/申博 + 求职轻量版）
- **X2** 本地 Hermes Skill + 公域内容引流
- **X3** 语音已落地：可插拔双工（`mock` 离线零依赖跑通整条链路；真实 `vosk`/`whisper` STT + `pyttsx3`/`edge-tts` TTS 懒加载可选）
- **X4** 放弃公众号采集
- **X5** Python **目标 3.12 / 最低 3.11**

## 隐私铁律（来自架构方案）
本地单租户、可删除、无遥测、不出域；`tenant_id=local`；`python src/cli.py purge --yes`
一键清除该 tenant 全部本地数据（owner 删除权闭环）。

## 验证结果
- ✅ 离线测试 `tests/test_demo.py` 全过
- ✅ `cli.py run --demo` 跑通闭环（保研/申博题库切换、硬阻塞追问命中浅回答、复盘报告生成）
- ✅ `list` / `report`（前缀解析）/ `weakness` / `purge` 全过
- ✅ `ollama` 构造 OK；`cloud` 缺密钥抛 `RuntimeError` 守卫（BYOK 不落盘）
- ✅ 核心零第三方依赖（mock/ollama/cloud 仅用标准库），`PyYAML` 为可选

### v1.1 新增验证
- ✅ 语音可插拔：`tests/test_voice.py` 离线全过；`mock` 双工经 `run --demo --voice` 跑通「说题→听答→硬阻塞追问→复盘报告」完整闭环
- ✅ 真实语音后端接线守卫：缺失模型/库时 `VoskSTT`/`WhisperSTT`/`Pyttsx3TTS`/`EdgeTTSTTS` 构造即抛 `RuntimeError`（懒加载，不污染核心零依赖）
- ✅ 短板聚合：`tests/test_analytics.py` 离线全过；`analyze` 命令跨场聚合（分类/严重度/趋势/反复短板）正确

## 快速使用
```bash
cd research-mock-interview
python src/cli.py run --demo                                  # 离线演示闭环
python src/cli.py run --demo --voice                          # 语音双工离线自检（mock）
python src/cli.py run --profile your_profile.json --scenario 保研   # 导入真实资料
python src/cli.py list / report --id <前缀> / weakness / analyze / purge --yes
```

## 下一步可选
- 接真实本地模型：`config.yaml` 设 `llm.backend=ollama`（如 `qwen2.5:7b`）
- 接云端 BYOK：`backend=cloud` + 环境变量 `RMI_LLM_API_KEY`
- 真实麦克风 STT 实测：`pip install vosk sounddevice numpy` + 下载 `vosk-model-small-cn-0.22`，设 `voice.stt.backend=vosk`
- 云端神经语音实测：`pip install edge-tts playsound`，设 `voice.tts.backend=edge`
- 短板趋势可视化（雷达图 / 时间序列）、评分结构化解析（把复盘报告里的维度分落库便于聚合）、多租户导出
