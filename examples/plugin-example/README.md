# Example plugin

A minimal `fmk.steps` entry point used as a template and as a CI smoke test.

```bash
uv pip install -e examples/plugin-example
fmk plugins list
```

Add it to `config.toml` only if you want it to run:

```toml
[pipeline]
steps = ["discover", "download", "preflight", "transcribe", "compose",
         "wordcount", "organize", "reconcile", "index", "publish"]
```

Steps declare `api_version = 1`, a unique `name`, the context keys they
`require` and `provide`, and a `run(ctx)` method returning `StepResult`.
