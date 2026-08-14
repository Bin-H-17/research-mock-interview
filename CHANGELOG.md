# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.1]

### Fixed

- **评分逻辑不自洽 bug**：`_overall()` 直接 `100 - sum(全部扣分)` 导致多维度×多题时总分被重复扣减（维度分 85-97 但总分 12/100）。修复为各维度分加权平均，与 `_dimension_scores()` 对齐。
- **'英语/海外适配' 维度丢失**：`_dimension_scores()` 原先遍历全部 rubric 项初始化维度，但该维度在非海外场景下不产生扣分记录，导致显示为 100 分但被质疑"丢失"。现改为按场景过滤维度列表，并新增 `answer_items_for_scenario()` 函数。
- **'英语/海外适配' 误 judge**：非海外场景（保研/申博/求职等）下该维度也被逐题 judge，产生不必要的扣分。修复为仅在 `海外phd` 场景下才 judge 该维度。
- **MockBackend 维度名不一致**：`task == "evaluate"` 返回 `科研深度/项目熟悉度`，与 rubric 的 `项目深度/技术细节` 等不匹配。已对齐为全部 8 个 rubric 维度名。
- **`config.example.yaml` API key 环境变量名不一致**：使用 `HERMES_LLM_API_KEY` 但代码默认 `RMI_LLM_API_KEY`，已统一为 `RMI_LLM_API_KEY`。
- **个人标识泄露**：文档中 `tenant_id=henry-local` 已改为 `tenant_id=local`。
- **SKILL.md / OVERVIEW.md 路径错误**：`cd 科研模拟面试-skill` 已改为 `cd research-mock-interview`。

### Added

- **评分修复单元测试**：`tests/test_scoring_fix.py` 验证维度分与总分自洽、场景过滤、英语维度存在性。
- **`.gitignore`**：排除 `__pycache__`、`data_store/`、`config.yaml` 等。

## [2.0.0]

This release is a major upgrade that makes the skill **agent-agnostic** and dramatically more like a real interview.

### Added

- **Pre-interview intake file (`intake`)** — generate a tailored intake survey so interviews match the candidate's background, target program, and scenario (保研 / 申博 / industry research).
- **Interviewer / company persona customization (`persona`)** — build a custom **interviewer persona** from the intake and optional research notes, so questions come from a realistic point of view.
- **Material collection with gap follow-up + deduction** — candidates submit materials; the agent **proactively follows up** on missing items and applies explicit deductions for unprovided essentials.
- **Pre-defined rubric / catalog of deduction points (`rubric`)** — the agent knows the pass criteria in advance and scores against a published rubric of deduction points.
- **Report with error analysis + improvement suggestions** — each session ends with a report containing concrete **error analysis** and **improvement tips** (面试复盘).
- **Agent-agnostic packaging** — removed single-agent branding; the skill can now be invoked directly by mainstream AI agents as a standalone `research-mock-interview` skill.

### Retained

- **Hard-block follow-up** — core questions answered too vaguely trigger a hard-block follow-up that won't let the interview move on.
- **Cross-session weakness analytics** — answers from multiple sessions aggregate into a weakness library (短板库).
- **Pluggable LLM backends** — `mock` / `ollama` / `cloud` (BYOK), lazy-loaded and optional.
- **Pluggable voice duplex** — `mock` offline voice plus real STT/TTS lazy-loaded backends.
- **Local-first privacy** — local SQLite, tenant isolation, BYOK, no telemetry, `purge` right-to-delete.

## [1.1.0]

- Voice duplex (STT/TTS) and cross-session weakness aggregation added on top of the core engine.

## [1.0.0]

- Initial runnable prototype: intake-free conversational mock interview with rubric-style scoring and a basic report.
