# Contributing to Research Mock Interview Coach

Thank you for considering a contribution! This document explains how to report issues, submit changes, and keep the codebase healthy. Whether you want to add a new scenario question bank, a new LLM/voice backend, or just fix a typo — you're welcome here.

中文对照：欢迎贡献！本文说明如何提 Issue、提交 PR，以及保持代码库健康。无论是新增场景题库、新增 LLM/语音后端，还是修个错别字，都欢迎。

## Reporting issues / 提 Issue

- **Search first.** Check [existing issues](../../issues) to avoid duplicates.
- **Open a clear issue.** Include: what you did, what you expected, what happened, your Python version, and (if relevant) the backend you used (`mock` / `ollama` / `cloud`).
- **Tag appropriately.** Use labels like `bug`, `enhancement`, `scenario`, `backend`, or `security` (see SECURITY.md for vulnerability reports).
- **Don't post secrets.** Never include API keys, real interview content, or personal data in an issue.

## Pull request process / PR 流程

1. **Fork & branch.** Create a feature branch off `main` (e.g. `feat/voice-whisper` or `fix/rubric-export`).
2. **Keep changes focused.** One logical change per PR. Small, reviewable PRs get merged faster.
3. **Add tests.** Any new behavior must ship with an offline test (see Testing below).
4. **Run the suite.** Make sure `python tests/test_*.py` passes under managed Python 3.11 and 3.12.
5. **Update docs.** If you change the CLI, update README.md; if you change behavior, update CHANGELOG.md.
6. **Open the PR** with a clear description of the motivation and what changed. Link any related issue.

## Code style / 代码风格

- **Core stays zero-dependency.** The core engine (`src/core`, CLI, rubric, analytics) must run with the Python standard library only. Dependencies like PyYAML are *optional* and lazy-loaded.
- **New LLM / STT / TTS backends are pluggable.** Any new backend (e.g. a new cloud provider, `whisper`, `vosk`, `edge-tts`) must implement the existing unified abstraction and be **lazy-loaded** — importing it must not pull in heavy packages unless the backend is actually selected.
- **Never break the zero-dependency core.** A missing optional dependency should degrade gracefully (fall back to `mock`), not crash the CLI.
- **Formatting.** Follow PEP 8; keep functions small and typed where reasonable. Prefer readable names over clever ones.
- **No hardcoded secrets.** Keys come only from `RMI_LLM_API_KEY` at runtime; nothing sensitive is committed.

## Testing / 测试要求

- **Offline tests required for new features.** Every new feature must have a test that runs fully offline using the `mock` backend (no network, no API key).
- **Run under managed environments.** Tests must pass under Python 3.11 and 3.12:
  ```bash
  python tests/test_*.py
  ```
- **Cover the contract.** Backend implementations should be tested through the unified abstraction so a regression in one backend doesn't silently break others.

## Commit message convention / 提交信息规范

We use a lightweight Conventional Commits style:

- `feat:` new feature (e.g. `feat: add edge-tts cloud voice backend`)
- `fix:` bug fix (e.g. `fix: persona builder drops empty research notes`)
- `docs:` documentation only
- `test:` adding or updating tests
- `refactor:` internal change, no behavior change
- `chore:` tooling, deps, misc

Keep the subject line under ~72 characters and use the body to explain *why* when it isn't obvious.

## Code of conduct / 行为准则

Be kind and respectful. We want this to be a welcoming project for students and researchers preparing for **research interviews**, **grad school interviews**, and **PhD interviews** around the world.

---

Questions? Open an issue or start a discussion — we're happy to help you get your contribution in.
