# Contributing

## Development setup

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
pre-commit install
```

## Checks before opening a pull request

```bash
ruff check .
mypy src
pytest -q
```

All three must pass. Keep the coverage of changed modules at or above the
project threshold.

## Code rules

- Each module has one responsibility; if a file needs two paragraphs to explain,
  split it.
- Pipeline steps implement the `Step` protocol and declare `requires` and
  `provides`. A step never writes outside its declared outputs.
- External processes and HTTP calls go behind a provider interface so tests can
  replace them.
- Destructive operations accept `--dry-run` and must be idempotent.
- Public functions and modules have type annotations.

## Test rules

- Tests run offline. Use the fake `lark-cli` executable and the local fake SSE
  server in `tests/fixtures/`.
- Never use real recordings, transcripts, names, or API keys.
- Write only inside `tmp_path`; tests must not touch a real archive.
- Golden files are reviewed like code: a diff means behavior changed.

## Commit messages

Use Conventional Commits, for example:

```
feat(kernel): validate step dependencies before running
fix(transcribe): retry failed slices without re-requesting cached ones
docs(readme): clarify the lark-cli requirement
```

## Pull requests

- Describe the problem, the change, and how you verified it.
- Include the commands you ran and their result.
- Do not mix refactoring with behavior changes.
- Never commit `.env`, `config.toml`, credentials, or recorded content.

## Reporting security issues

Follow [SECURITY.md](SECURITY.md) instead of opening a public issue.
