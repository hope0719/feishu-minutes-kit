# 配置

`fmk` 的配置来自内置默认值与一个 TOML 文件。凭证只从环境变量读取。

## 1. 配置文件的位置

按以下顺序确定配置文件：

1. 命令行 `--config PATH` / `-c PATH`
2. 环境变量 `FMK_CONFIG`
3. 当前目录下的 `config.toml`（存在时）
4. 都没有：使用内置默认值，工作区根目录为当前目录

显式指定的文件不存在时直接报 `ConfigError`。相对路径的基准是**配置文件所在目录**；
没有配置文件时是当前目录。

`config.toml` 已被 `.gitignore` 忽略，不要提交。仓库里的
[`config.example.toml`](../config.example.toml) 只含占位值。

## 2. 优先级

- 配置项：内置默认值 < `config.toml`。
- 凭证：只来自环境变量 `FMK_STEPFUN_API_KEY`。
- 命令行参数用于选择配置文件与运行范围（`--since`、`--only`、`--dry-run`），
  不覆盖单个配置项。

类型或取值范围不合法时会在启动阶段报 `ConfigError`，并指出具体键名。

## 3. 全部配置项

### `[workspace]`

| 键 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `work_dir` | 字符串 | `"./work"` | 中间产物根目录；成稿写入 `<work_dir>/docs/` |
| `minutes_dir` | 字符串 | `"./work/minutes"` | 每条妙记一个子目录，保存音频与 `_segs/` 切片缓存 |
| `state_dir` | 字符串 | `"./work/state"` | 运行状态 `state.json` 所在目录 |
| `archive_dir` | 字符串 | `"./archive"` | 最终归档目录；也是发布时提交的范围 |

路径支持 `~`；相对路径按配置文件所在目录解析，并统一转为绝对路径。四个目录会在
`fmk run`、`fmk init` 时自动创建。

### `[naming]`

| 键 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `dir_format` | 字符串 | `"{index:02d}-{year}-{month:02d}"` | 月份目录名模板，可用 `{index}`、`{year}`、`{month}` |
| `file_format` | 字符串 | `"{index:02d}-{date} · {title}.md"` | 文件名模板，可用 `{index}`、`{date}`、`{title}` |
| `max_title_chars` | 整数 ≥ 1 | `80` | 标题最大字符数，超出截断 |

- `{index}` 每次 `organize` 重新计算，`01` 表示最新。
- `{date}` 为 `YYYY-MM-DD`。
- 标题会替换 `\ / : * ? " < > |`，合并空白；同名追加 `（2）`。
- 模板会在加载时用样例值试格式化，非法模板直接报错。

### `[preflight]`

| 键 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `silent_db` | 浮点数 | `-50.0` | ffmpeg `volumedetect` 的平均音量低于该值时判为无声 |
| `min_words` | 整数 ≥ 0 | `20` | 转写正文非空白字符数低于该值时判为空录音；`0` 关闭 |

判定顺序：标题命中“重复录像/碎片/录音/录制” → 无音频 → 平均音量 → 转写后字数。

### `[transcribe]`

| 键 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `segment_seconds` | 整数 ≥ 1 | `1500` | 成稿中每个 `## 第 N 段` 覆盖的秒数 |
| `request_seconds` | 整数 ≥ 1 | `120` | 每次切给 ASR 的秒数，同时作为单次请求超时 |
| `concurrency` | 整数 ≥ 1 | `3` | 同一录音内并发转写的切片数 |
| `max_retries` | 整数 ≥ 0 | `3` | 单个切片的最大尝试次数；`0` 表示只尝试一次 |

建议 `segment_seconds` 是 `request_seconds` 的整数倍。切片缓存在
`<minutes_dir>/<token>/_segs/<起始秒:06d>.txt`，重跑时命中缓存不再请求。

### `[source]`

| 键 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `provider` | 字符串 | `"lark-cli"` | 妙记数据源；必须已注册并实现 `MinutesProvider` |

### `[asr]`

| 键 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `provider` | 字符串 | `"stepfun"` | 语音识别 Provider 名称 |
| `model` | 字符串 | `"stepaudio-2.5-asr"` | 传给 ASR 的模型名 |

使用内置 `stepfun` 时必须设置 `FMK_STEPFUN_API_KEY`。

### `[index]`

| 键 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `enabled` | 布尔 | `false` | 是否生成 `_quotes.md`、`_numbers.md`、`_people.md` |

关闭时 `index` 步骤返回 `skip`，不算失败。

### `[publish]`

| 键 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `enabled` | 布尔 | `false` | 是否提交并推送归档 |
| `provider` | 字符串 | `"git"` | 发布 Provider 名称 |
| `remote` | 字符串 | `""` | `git push` 的远端名或 URL；启用时不能为空 |
| `branch` | 字符串 | `"main"` | 推送目标分支 |
| `commit_message` | 字符串 | `"chore: sync minutes archive"` | 提交信息 |

`enabled = true` 且 `remote` 为空会在加载阶段报错。`archive_dir` 必须位于某个
git 工作树内；只提交归档目录相对仓库根的子路径。

> 如果远端 URL 内含访问令牌，请只写在 `config.toml`（已被忽略），不要写入
> 示例文件或提交历史。

### `[pipeline]`

| 键 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `steps` | 非空字符串列表 | 九步默认顺序 | 要执行的步骤及顺序 |

默认值：

```toml
[pipeline]
steps = [
  "discover", "download", "preflight", "transcribe", "compose",
  "organize", "reconcile", "index", "publish",
]
```

约束：

- 不能为空，不能重复。
- 每个名字必须能被注册表发现，否则报 `ConfigError`。
- 每个步骤的 `requires` 必须被更早步骤的 `provides` 满足。
- 可以删除末尾步骤（例如只做到 `compose`），但不能删除中间依赖。

## 4. 环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `FMK_STEPFUN_API_KEY` | 使用 `stepfun` 时必填 | StepFun ASR 凭证；日志与会话中会打码 |
| `FMK_CONFIG` | 否 | 配置文件路径，等价于 `--config`，优先级低于命令行 |

`.env` **不会**被自动读取。可以用下面任一方式注入：

```bash
# 方式一：当前 shell 手动导出
export FMK_STEPFUN_API_KEY="..."
fmk run

# 方式二：临时载入 .env
set -a
source .env
set +a
fmk run

# 方式三：使用 direnv / 1Password CLI 等工具管理环境变量
```

`fmk doctor` 会检查凭证是否设置，但只显示“已设置（前 4 位…）”或“未设置”。

## 5. 常用配置示例

### 最小配置

```toml
[workspace]
work_dir = "./work"
minutes_dir = "./work/minutes"
state_dir = "./work/state"
archive_dir = "./archive"

[source]
provider = "lark-cli"

[asr]
provider = "stepfun"
model = "stepaudio-2.5-asr"
```

其余配置项使用默认值；`index` 与 `publish` 默认关闭。

### 启用索引与发布

```toml
[index]
enabled = true

[publish]
enabled = true
provider = "git"
remote = "origin"
branch = "main"
commit_message = "chore: sync minutes archive"
```

### 只做到成稿，不归档

```toml
[pipeline]
steps = ["discover", "download", "preflight", "transcribe", "compose"]
```

成稿位于 `<work_dir>/docs/<token>.md`，不会移动或改名。

### 自定义编号与标题长度

```toml
[naming]
dir_format = "{index:02d}-{year}-{month:02d}"
file_format = "{index:02d}-{date} · {title}.md"
max_title_chars = 60
```

## 6. 相关文件

| 文件 | 内容 | 是否提交 |
|---|---|---|
| `config.toml` | 你的真实配置 | 否，已忽略 |
| `config.example.toml` | 占位示例 | 是 |
| `.env.example` | 凭证占位 | 是 |
| `.env` | 你的真实凭证 | 否，已忽略 |
| `<state_dir>/state.json` | 运行状态与条目状态 | 否，位于 `work/` |

`state.json` 的 `schema_version` 必须为 `1`；不匹配时工具拒绝启动，不做静默兼容。
文件损坏时会改名为 `state.json.corrupt-<时间戳>` 并从空状态继续。

## 7. 退出码

| 码 | 含义 |
|---|---|
| 0 | 全部成功 |
| 2 | 配置或环境错误 |
| 3 | Provider/步骤失败或部分条目失败 |
| 4 | 产体验收失败（字段不可解析、编号断裂、文件冲突） |
