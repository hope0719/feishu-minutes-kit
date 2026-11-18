# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-18

### Added

- Nine-step pipeline: `discover`, `download`, `preflight`, `transcribe`,
  `compose`, `organize`, `reconcile`, `index`, `publish`.
- CLI commands: `init`, `doctor`, `discover`, `run`, `status`, `plugins list`,
  `version`, with global `--config`.
- Provider interfaces and built-in implementations: `lark-cli` for Feishu
  Minutes, StepFun SSE ASR, and git publishing.
- Plugin API v1 with `fmk.steps` and `fmk.providers` entry point groups,
  version checks, duplicate-name rejection and warning-only import failures.
- Resumable-by-idempotency execution: cached 120-second ASR slices, audio reuse,
  archived-token exclusion, atomic state and archive renames.
- Archive layout with monthly numbering, `_overview.md`, per-month `_index.md`,
  `_queue.md`, `_queue-history.md` and optional quote/number/people indexes.
- Evidence-carrying step results, `--dry-run`, stable exit codes and redacted
  logging.
- Documentation: architecture, plugin API, configuration and workflow guides,
  plus bilingual READMEs and an installable example plugin.
- CI for Linux and macOS on Python 3.10–3.13 with lint, format, type check,
  coverage gate, example-plugin discovery and gitleaks.
- Pre-commit hooks for ruff, ruff-format, mypy and gitleaks.

### Fixed

- A `retry` step result is no longer recorded as completed.
- `--dry-run` no longer sends ASR requests or writes slice caches; it only reuses
  existing slices.
- `.env` is explicitly documented as not auto-loaded.

### Security

- Credentials come only from `FMK_STEPFUN_API_KEY`; logs redact
  `Authorization`, API keys and minute tokens.
- Repository contains placeholder configuration only; `.env`, `config.toml`,
  `work/`, `archive/` and `minutes/` are ignored.
- Tests use synthetic audio, fake `lark-cli`/ffmpeg executables and a local SSE
  server; no real recordings or keys are committed.

[Unreleased]: https://github.com/OWNER/feishu-minutes-kit/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/OWNER/feishu-minutes-kit/releases/tag/v0.1.0
