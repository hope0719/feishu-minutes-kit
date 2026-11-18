# 工作流

本文按“第一次使用 → 每天运行 → 出问题”的顺序说明完整流程。配置项细节见
[配置](configuration.md)，内部结构见 [架构](architecture.md)。

## 1. 前置条件

- Python 3.10 及以上
- `ffmpeg` 在 `PATH` 中
- `lark-cli` 已安装，并以你自己的飞书用户身份完成授权
- 所选 ASR 服务的凭证（内置实现为 `FMK_STEPFUN_API_KEY`）

`fmk doctor` 会逐项检查这些依赖、凭证和目录权限。

## 2. 一次性初始化

从源码安装：

```bash
git clone https://github.com/OWNER/feishu-minutes-kit.git
cd feishu-minutes-kit
uv venv
source .venv/bin/activate
uv pip install -e .
```

或者用 `pipx` 安装到你自己的环境：

```bash
pipx install "feishu-minutes-kit @ git+https://github.com/OWNER/feishu-minutes-kit.git"
```

选择一个保存归档的目录并生成配置：

```bash
mkdir -p ~/minutes
cd ~/minutes
fmk init
```

`fmk init` 会写入 `config.toml`、`.env.example`，并创建配置中的四个目录。然后：

```bash
$EDITOR config.toml          # 至少确认 archive_dir 与 ASR 配置
export FMK_STEPFUN_API_KEY="你的密钥"
fmk doctor
```

`fmk doctor` 全部为 `ok` 后再继续。凭证只从环境变量读取；`.env` 不会被自动
加载，可用 `set -a; source .env; set +a` 临时注入。

## 3. 每天运行

```bash
fmk run
```

终端会逐步打印：

```
▶ discover
  ok
▶ download
  ok
...
完成。
```

查看结果：

```bash
fmk status                   # 条目数量、各状态计数、上次运行时间
fmk status --json            # 机器可读
```

首次运行搜索最近 7 天；之后从 `last_search` 往前 2 天开始，避免漏掉跨天上传的
录音。也可以用 `--since` 指定起点：

```bash
fmk run --since 2026-01-01
fmk discover --since 2026-01-01          # 只列出新录音，不下载
fmk discover --since 2026-01-01 --json   # 供脚本消费
```

## 4. 九个步骤分别做什么

| 步骤 | 做什么 | 跳过/失败条件 | 产物 |
|---|---|---|---|
| `discover` | 调用数据源搜索时间窗内的妙记，排除已归档、已下载、队列中或处于终态的 token | 数据源报错则整步失败 | 内存中的新录音列表 |
| `download` | 按 token 下载音频；已有音频直接复用 | 无音频记 `no-audio`，下载异常记 `failed`，批次继续 | `work/minutes/<token>/` |
| `preflight` | 先看标题是否含“重复录像/碎片/录音/录制”，再用 ffmpeg 测平均音量 | 重复记 `duplicate`，低于 `silent_db` 记 `silent`，无音频记 `no-audio` | 每条录音的判定 |
| `transcribe` | 每 120 秒切一段 PCM，交给 ASR；失败按指数退避重试；结果按 1500 秒合并成段落 | 切片全部失败记 `failed`，字数低于 `min_words` 记 `empty` | `_segs/*.txt` 缓存 + 段落 |
| `compose` | 每条录音生成一篇 Markdown，含录制时间、时长、妙记链接、来源、字数等头部字段 | 缺元数据或录制时间则验收失败 | `work/docs/<token>.md` |
| `organize` | 按月份建 `NN-YYYY-MM` 目录，按时间倒序重新编号，写导航文件 | 目标重名、同一 token 多篇成稿时拒绝覆盖并报错 | 归档 Markdown + `_overview.md` + 月索引 |
| `reconcile` | 四方核对：队列、音频、成稿、历史；统计待转、缺音频、孤儿音频、重复 token | 只读状态与文件 | `_queue.md`、`_queue-history.md` |
| `index` | 机械抽取金句、金额、称呼线索 | `index.enabled = false` 时 `skip` | `_quotes.md`、`_numbers.md`、`_people.md` |
| `publish` | 提交归档目录并推送到配置的 git 远端 | 未启用时 `skip`；无变更时不提交；不在 git 仓库内报错 | 远端提交 |

单条录音的失败不会中断整批，批次结束后 CLI 以退出码 3 结束。产物验收失败
（编号断裂、字段不可解析、文件冲突）使用退出码 4，需要人工处理。

## 5. 成稿长什么样

每篇成稿固定包含：

```markdown
# 1月1日 · 原标题

> 录制时间：2026-01-01 09:30 ｜ 时长：1 小时 2 分 3 秒
> 妙记：https://example.feishu.cn/minutes/<token>

- 正文来源：stepfun stepaudio-2.5-asr 重转
- 正文字数：12345
- 原妙记标题：原标题
- 妙记官方逐字稿：未获取，正文未使用

---

## 第 1 段 ｜ 录音 00:00:00 – 00:25:00

正文……
```

正文来自下载的原音频重新转写，不使用妙记官方逐字稿；官方逐字稿只作为可选的
核对信息，v0.1 不获取。

## 6. `--dry-run` 的边界

```bash
fmk run --dry-run
```

预览模式：

- 不写 `state.json`，不移动或改名归档文件，不提交、不推送。
- `download` 只列出缺失的音频，不下载。
- `preflight` 仍会读取音频测量音量（只读）。
- `transcribe` 不请求 ASR，只复用已有切片缓存；没有缓存的录音按空正文估算。
- `compose`、`organize`、`index` 只计算将要写入的路径。
- `publish` 只统计将变更的文件数，不 commit。

因为预览不写中间成稿，尚未下载/成稿的新条目可能不会出现在最终的归档路径规划
里。预览适合检查配置、依赖与已有归档的变更，不替代真实运行。

## 7. 只运行到某一步

```bash
fmk run --only compose
```

`--only` 表示“执行到该步骤为止（含）”，用于先看成稿、暂不归档。步骤名必须是
`pipeline.steps` 中的一项。v0.1 没有独立的 `fmk organize` / `fmk publish`
子命令；这些动作通过 `fmk run` 执行。

## 8. 失败与重跑

- 直接重新执行 `fmk run`。已下载音频会复用，已有切片缓存不会重复请求 ASR，
  已归档 token 会在 `discover` 阶段排除。
- v0.1 不提供跨进程断点续跑参数；整条流水线是幂等的，重跑即可。
- `state.json` 损坏时会改名为 `state.json.corrupt-<时间戳>`，从空状态继续；
  归档文件不受影响。
- `state.json` 的 `schema_version` 不是 `1` 时工具拒绝启动，需要先迁移或恢复备份。
- 遇到 `VerificationError`（退出码 4）时不要强行删除文件；先按报错指出的路径
  人工核对，再重跑。

## 9. 归档结构与导航

```
archive/
├── 01-2026-01/
│   ├── _index.md
│   └── 01-2026-01-01 · 标题.md
├── 02-2025-12/
│   ├── _index.md
│   └── ...
├── _overview.md
├── _queue.md
├── _queue-history.md
├── _quotes.md
├── _numbers.md
└── _people.md
```

- 月份目录和文件都是编号越小越新，`01` 为最新。
- `_overview.md` 是总目录；每月 `_index.md` 是当月索引。
- `_queue.md` 的状态区由 `<!-- fmk:status:start -->` 与
  `<!-- fmk:status:end -->` 包裹，只替换标记之间的内容；标记外的自定义笔记
  会保留。
- `_queue-history.md` 保存超过 14 天的完成记录。
- 三类索引默认关闭；启用后由规则机械抽取，只是候选，需要人工复核。
- 所有链接都是归档内相对路径，移动整个目录不会失效。

## 10. 发布到 git

先让归档目录处于一个 git 工作树中，并配置远端：

```bash
cd ~/minutes/archive
git init
git add .
git commit -m "chore: init minutes archive"
git remote add origin git@github.com:OWNER/REPO.git
git push -u origin main
```

然后启用发布：

```toml
[publish]
enabled = true
provider = "git"
remote = "origin"
branch = "main"
commit_message = "chore: sync minutes archive"
```

再次执行 `fmk run`。`GitPublisher` 会：

1. 确认 `archive_dir` 在 git 仓库内；
2. 只检查、提交归档目录相对仓库根的子路径；
3. 无变更时跳过；
4. 有变更时 `git add`、`commit`、`push <remote> HEAD:<branch>`。

不会 force push，也不会修改你的 git 用户配置。推送被拒绝时按 git 的提示先
同步远端再重跑。

## 11. 常见问题

| 现象 | 原因与处理 |
|---|---|
| `未找到 lark-cli` | 安装 `lark-cli` 并确认在 `PATH`；运行 `fmk doctor` |
| `lark-cli 无 JSON 输出` | 授权过期或命令失败；重新授权后重试 |
| `未设置 FMK_STEPFUN_API_KEY` | 导出环境变量；`.env` 不会自动加载 |
| 条目状态 `no-audio` | 妙记没有可用音频或下载失败；检查 `work/minutes/<token>/` |
| 条目状态 `silent` | 平均音量低于 `-50 dB`；确认不是空录音后可调低 `silent_db` |
| 条目状态 `empty` | 转写字数低于 `min_words`；检查 `_segs/*.txt` 是否为空 |
| 条目状态 `duplicate` | 标题含“重复录像/碎片”等字样；确认后可手工移除该条目 |
| `目标文件已存在，拒绝覆盖` | 归档里有同名文件；人工核对后移走冲突文件再重跑 |
| `同一妙记出现多篇成稿` | 手工删除多余成稿，保留一篇后重跑 |
| `归档目录不在 git 仓库中` | 在 `archive_dir` 执行 `git init`，或把配置指向已有仓库内的目录 |
| `state.json` schema 不匹配 | 迁移状态文件或从备份恢复；工具不做静默兼容 |
| `插件 ... 导入失败` | 运行 `fmk plugins list` 查看警告；修复依赖或卸载该插件 |

## 12. 隐私提醒

- `work/` 与 `archive/` 含真实录音与转录，已在 `.gitignore` 中忽略。
- 不要把 `config.toml`、`.env`、录音或转录提交到公开仓库。
- 发布归档时优先使用私有仓库；远端 URL 含令牌时只写在本地配置。
- 日志会对 `Authorization`、`*_API_KEY`、token 打码；仍建议不要把完整日志
  贴到公开 Issue。

## 13. 命令速查

| 命令 | 用途 |
|---|---|
| `fmk init [--dir PATH] [--force]` | 生成配置与 `.env.example`，创建目录 |
| `fmk doctor` | 检查外部命令、凭证、目录权限 |
| `fmk discover [--since DATE] [--json]` | 只列出新妙记 |
| `fmk run [--since DATE] [--only STEP] [--dry-run]` | 执行流水线 |
| `fmk status [--json]` | 查看配置、流水线与状态统计 |
| `fmk plugins list` | 列出已发现的步骤与 Provider |
| `fmk version` | 输出版本号 |

全局参数 `--config PATH` / `-c PATH` 可放在子命令前，用于指定配置文件。
