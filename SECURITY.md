# Security Policy

## Reporting a vulnerability / 漏洞报告

If you discover a security issue, please report it privately rather than opening a public issue.

- **security contact:** open an issue tagged `security`, or contact the maintainers through the repository's issue tracker.
- Please include: a description of the issue, steps to reproduce, and the potential impact.
- We will acknowledge receipt and work with you on a fix and coordinated disclosure.

中文对照：若发现安全漏洞，请通过标记为 `security` 的 Issue 私下报告，并说明问题、复现步骤与影响。我们会及时响应并协调修复与披露。

## Our privacy & security posture / 隐私与安全立场

This tool is designed to be safe by default:

- **No telemetry.** This tool **does not collect or report any telemetry** — no usage statistics, no crash reports, no network calls unless you explicitly choose a cloud backend.
- **Cloud keys come only from the environment.** When using the `cloud` LLM backend, the API key is read **only** from the environment variable `RMI_LLM_API_KEY`. It is **never written to disk**, never logged, and never embedded in any file.
- **Local data.** All interview data (intake, persona, materials, sessions, reports) is stored in a **local SQLite** database on your machine. Nothing is uploaded.
- **Right to delete.** Run `python src/cli.py purge --yes` to remove all stored data.
- **No hardcoded credentials.** The repository contains **no hardcoded secrets or API keys**.

## User responsibilities / 用户须知

- When using the `cloud` backend, **you are responsible for safeguarding your own API key**. Set it via the environment (`export RMI_LLM_API_KEY=...`) and **do not commit it to the repository** (use `.gitignore`, never paste keys into code or issues).
- Review the `mock` backend for fully offline use if you want zero network exposure.
- Report any suspected data-leak behavior via the `security` channel above.
