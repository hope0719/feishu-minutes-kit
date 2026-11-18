# feishu-minutes-kit

把飞书妙记录音整理成可检索、可版本管理的本地 Markdown 档案。

[English](README.md)

> **状态：v0.1.0。** 九个流水线步骤与插件 API 已可用；命令与配置项可能在后续
> 0.x 版本继续演进。

## 它做什么

`fmk` 对你自己账号下的飞书妙记执行一条固定、幂等的流水线：

```
发现 → 下载 → 预检 → 转写 → 成稿 → 归档 → 核对 → 索引 → 发布
```

- **发现**：列出新录音，跳过已归档的条目。
- **下载**：把原始音频保存到本地。
- **预检**：带证据地跳过重复、无声和空录音。
- **转写**：切片后交给配置的 ASR 服务。
- **成稿**：每条录音生成一篇 Markdown。
- **归档**：按月分组并重新编号。
- **核对**：检查队列、音频、成稿、历史四方是否一致。
- **索引**：可选地生成金句、数字、人物三类索引。
- **发布**：推送到你配置的 git 远端。

每个步骤都是插件；数据源、ASR、发布端是独立的 Provider 插件，替换其一不影响
流水线。

## 设计原则

- **本地优先**：无遥测、无托管服务；除你配置的服务商外，数据不出本机。
- **幂等**：重复运行不会产生重复成稿，也不会重复下载音频。
- **看产物不看返回码**：步骤成功必须能用生成物验证。
- **仓库不存密钥**：凭证只从环境变量读取。

## 环境要求

- Python 3.10 及以上
- `ffmpeg` 在 `PATH` 中
- 已以你自己的飞书用户身份完成授权的 `lark-cli`
- 所选 ASR 服务的凭证（内置实现使用 `FMK_STEPFUN_API_KEY`）

## 安装

用 `pipx`：

```bash
pipx install "feishu-minutes-kit @ git+https://github.com/OWNER/feishu-minutes-kit.git"
```

从源码安装：

```bash
git clone https://github.com/OWNER/feishu-minutes-kit.git
cd feishu-minutes-kit
uv venv
source .venv/bin/activate
uv pip install -e .
fmk --help
```

参与开发时安装开发依赖与预提交钩子：

```bash
uv pip install -e ".[dev]"
pre-commit install
```

## 快速开始

```bash
mkdir -p ~/minutes
cd ~/minutes

fmk init                        # 生成 config.toml、.env.example 与目录
$EDITOR config.toml             # 确认路径、ASR，按需开启发布
export FMK_STEPFUN_API_KEY="…"  # 工具不会自动读取 .env
fmk doctor                      # 检查工具、凭证与目录权限
fmk run                         # 执行流水线
fmk status                      # 查看归档与状态统计
```

预览一次运行，不写归档、不写状态、不请求 ASR：

```bash
fmk run --dry-run
```

只列出新录音：

```bash
fmk discover --since 2026-01-01
```

## 命令

| 命令 | 用途 |
|---|---|
| `fmk init [--dir PATH] [--force]` | 生成 `config.toml`、`.env.example` 与工作目录 |
| `fmk doctor` | 检查外部命令、凭证与目录权限 |
| `fmk discover [--since DATE] [--json]` | 只列出新录音，不下载 |
| `fmk run [--since DATE] [--only STEP] [--dry-run]` | 执行流水线 |
| `fmk status [--json]` | 查看配置、计划与状态统计 |
| `fmk plugins list` | 列出已发现的步骤与 Provider |
| `fmk version` | 输出版本号 |

全局参数：`--config PATH` / `-c PATH`。

## 文档

- [架构](docs/architecture.md)
- [插件 API](docs/plugin-api.md)
- [配置](docs/configuration.md)
- [工作流](docs/workflow.md)
- [v0.1.0 验收记录](docs/acceptance-0.1.0.md)

设计稿与实现计划位于 [`docs/specs/`](docs/specs/)。

## 安全

请勿在公开 Issue 中粘贴凭证或录音内容。披露流程与凭证处理规则见
[SECURITY.md](SECURITY.md)。

## 贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)。测试必须离线运行，且不得使用真实录音或
真实 API Key。

## 协议

[MIT](LICENSE)
