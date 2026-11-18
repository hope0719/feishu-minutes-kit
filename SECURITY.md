# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x | Yes (pre-release) |

## Reporting a vulnerability

Report security issues privately through GitHub Security Advisories on this
repository. Do not open a public issue for a vulnerability.

Please include:

- the affected version and operating system;
- a minimal reproduction that does not contain real credentials or recordings;
- the impact you believe the issue has.

We aim to acknowledge reports within 7 days and to publish a fix or mitigation
plan after triage. There is no bug bounty.

## Credential handling rules

These rules apply to code, tests, documentation, issues, and pull requests:

- The repository never contains real API keys, tokens, cookies, or app secrets.
- Configuration examples contain placeholders only.
- `.env`, `config.toml`, `work/`, `archive/`, `minutes/`, and `output/` are
  ignored by git.
- Logs redact `Authorization` headers, `*_API_KEY` values, and minute tokens.
  Request and response bodies are never logged.
- `fmk doctor` reports whether a credential is set, never its value. When a
  partial value must be shown, only the first four characters are kept.
- Tests use synthetic audio and a placeholder key such as `test-key`.
- CI runs a secret scanner and fails on findings.

## If a credential is exposed

1. Revoke and rotate the credential at the provider immediately.
2. Remove it from the working tree and from git history.
3. Open a private advisory describing what was exposed and for how long.
4. Assume anything pushed to a public remote has been copied.
