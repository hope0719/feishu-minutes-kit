# feishu-minutes-kit

Turn Feishu Minutes recordings into a searchable, versioned Markdown archive.

[简体中文](README.zh-CN.md)

> **Status: v0.1.0.** All nine pipeline steps and the plugin API are usable.
> The command surface and configuration keys may still evolve in later 0.x
> releases.

## What it does

`fmk` runs a fixed, idempotent pipeline over your own Feishu Minutes recordings:

```
discover → download → preflight → transcribe → compose
        → organize → reconcile → index → publish
```

- **discover** lists new recordings and skips anything already archived.
- **download** stores the original audio locally.
- **preflight** skips duplicate, silent, and empty recordings with evidence.
- **transcribe** slices audio and sends it to the configured ASR provider.
- **compose** writes one Markdown document per recording.
- **organize** groups documents by month and renumbers them.
- **reconcile** checks that the queue, audio, documents, and history agree.
- **index** builds optional cross-document indexes.
- **publish** pushes the archive to a git remote you configure.

Every step is a plugin. Data sources, ASR engines, and publishers are separate
provider plugins, so you can replace one without touching the pipeline.

## Design principles

- **Local first.** No telemetry, no hosted service; data leaves your machine only
  for the providers you configure.
- **Idempotent.** Re-running never duplicates documents or re-downloads audio.
- **Evidence over exit codes.** A step succeeds only when its artifacts verify.
- **No secrets in the repository.** Credentials come from environment variables.

## Requirements

- Python 3.10 or newer
- `ffmpeg` on `PATH`
- `lark-cli`, authorized as your Feishu user
- An ASR credential for the provider you choose (`FMK_STEPFUN_API_KEY` by default)

## Install

With `pipx`:

```bash
pipx install "feishu-minutes-kit @ git+https://github.com/OWNER/feishu-minutes-kit.git"
```

From source:

```bash
git clone https://github.com/OWNER/feishu-minutes-kit.git
cd feishu-minutes-kit
uv venv
source .venv/bin/activate
uv pip install -e .
fmk --help
```

For development, install the dev extras and pre-commit hooks:

```bash
uv pip install -e ".[dev]"
pre-commit install
```

## Quick start

```bash
mkdir -p ~/minutes
cd ~/minutes

fmk init                        # write config.toml, .env.example and directories
$EDITOR config.toml             # confirm paths, ASR, optional publish settings
export FMK_STEPFUN_API_KEY="…"  # the tool does not load .env automatically
fmk doctor                      # verify tools, credential and directory permissions
fmk run                         # run the pipeline
fmk status                      # summarize the archive and stored state
```

Preview a run without writing the archive, state, or calling ASR:

```bash
fmk run --dry-run
```

Only list new recordings:

```bash
fmk discover --since 2026-01-01
```

## Commands

| Command | Purpose |
|---|---|
| `fmk init [--dir PATH] [--force]` | Create `config.toml`, `.env.example` and workspace directories |
| `fmk doctor` | Check external commands, credential and directory permissions |
| `fmk discover [--since DATE] [--json]` | List new recordings without downloading |
| `fmk run [--since DATE] [--only STEP] [--dry-run]` | Run the pipeline |
| `fmk status [--json]` | Show configuration, plan and state statistics |
| `fmk plugins list` | List discovered steps and providers |
| `fmk version` | Print the installed version |

Global option: `--config PATH` / `-c PATH`.

## Documentation

- [Architecture](docs/architecture.md)
- [Plugin API](docs/plugin-api.md)
- [Configuration](docs/configuration.md)
- [Workflow](docs/workflow.md)
- [Release acceptance (v0.1.0)](docs/acceptance-0.1.0.md)

The design and implementation plan live in [`docs/specs/`](docs/specs/).

## Security

Please do not open a public issue containing credentials or recorded content.
See [SECURITY.md](SECURITY.md) for the disclosure process and the project's
credential-handling rules.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Tests run offline and must never use
real recordings or real API keys.

## License

[MIT](LICENSE)
