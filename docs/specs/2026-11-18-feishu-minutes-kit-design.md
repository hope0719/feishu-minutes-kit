# feishu-minutes-kit 设计文档

| 项目 | 内容 |
|---|---|
| 版本 | 0.1（设计稿） |
| 日期 | 2026-11-18 |
| 状态 | 已确认，待实现 |
| 命令名 | `fmk` |
| 协议 | MIT |
| 风险级 | routine（只读抓取、本地写入、可选远端推送） |

## 1. 背景

把飞书妙记录音整理成可检索的本地 Markdown 档案，已有四条私有脚本验证过完整链路。现在要把它做成一个可开源、可安装、可扩展的工具，而不是继续维护一组互相调用的脚本。

目标用户是**有飞书妙记、愿意自己配环境的内容工作者**。他们要的不是一个演示，而是装完能稳定跑、出问题能定位、想换组件能替换的工具。

## 2. 目标与非目标

**目标**

- 一条命令完成：发现新妙记 → 下载原音频 → 判重判无声 → 转写 → 生成成稿 → 按月编号 → 队列核对 → 横向索引 → 可选推送。
- 每个步骤可独立运行、可单独替换、失败可重试。
- 默认实现开箱可用，第三方组件通过插件接入。
- 仓库本身不含任何真实凭证、个人信息或录音内容。

**非目标（v0.1 明确不做）**

- Web 界面、桌面应用。
- 通知机器人、常驻守护进程、远程控制。
- 多用户服务或云端部署。
- 直连飞书 OpenAPI 的实现（接口预留，v0.2 再评估）。
- 本地离线 ASR（接口预留）。
- 语义摘要、内容改写、自动发布到社交平台。

## 3. 架构：微内核 + 内置插件

```
┌────────────────────────────────────────────────┐
│ CLI  fmk init / doctor / run / check / index …  │
├────────────────────────────────────────────────┤
│ Kernel                                          │
│  Registry    发现内置与第三方插件                │
│  Pipeline    校验依赖、按序执行、聚合结果        │
│  Context     配置 / 日志 / 状态 / Provider       │
│  StateStore  JSON + schema_version + 原子写      │
├────────────────────────────────────────────────┤
│ Step 协议     name / requires / provides         │
│               run(ctx) -> StepResult             │
├────────────────────────────────────────────────┤
│ 内置 Steps    discover  download  preflight      │
│               transcribe  compose  organize      │
│               reconcile  index  publish          │
├────────────────────────────────────────────────┤
│ Providers     MinutesProvider  (lark-cli)        │
│               AsrProvider      (stepfun)         │
│               Publisher        (git, 可选)       │
└────────────────────────────────────────────────┘
```

### 3.1 扩展点

只有两个 entry point 组：

- `fmk.steps`：新增或替换流水线步骤。
- `fmk.providers`：新增数据源、ASR、发布端。

插件必须声明 `api_version = 1`。内核只做版本匹配与名称冲突检查，不做进程隔离、沙箱或热加载。第三方插件导入失败时记录警告并跳过，不影响内置步骤运行。

### 3.2 为什么不做事件总线

步骤之间只有“上下文传递”一种关系。引入事件会让执行顺序不可静态推理，测试和排障成本都会上升。v0.1 保持线性执行，扩展靠替换步骤实现。

### 3.3 插件契约

```python
class Step(Protocol):
    api_version: int          # 固定为 1
    name: str                 # 全局唯一
    requires: frozenset[str]  # 依赖的上下文键
    provides: frozenset[str]  # 产出的上下文键

    def run(self, ctx: Context) -> StepResult: ...
```

```python
@dataclass(frozen=True)
class StepResult:
    status: Literal["ok", "skip", "retry", "fail"]
    outputs: Mapping[str, Any] = field(default_factory=dict)
    reason: str | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)
```

- `Context` 按命名空间存放数据，步骤只写自己的 `provides` 键，禁止改写其他步骤的输出。
- `StepResult.evidence` 用于验收，例如音量值、字数、文件路径、编号连续性；验收不依赖日志文本。
- Pipeline 启动前做三项静态校验：`requires` 是否都能被前序 `provides` 满足、是否存在环、是否存在重名步骤。校验失败在 `--dry-run` 阶段就退出。

## 4. 内置步骤规范

| 步骤 | 依赖 | 产出 | 主要副作用 | 验收证据 |
|---|---|---|---|---|
| `discover` | — | `minutes.list` | 无 | 列表按开始时间降序，去重后无已知 token |
| `download` | `minutes.list` | `audio.path` | 写 `work/minutes/<token>/` | 音频文件存在且体积大于 0 |
| `preflight` | `audio.path` | `preflight.verdict` | 无 | 重复标题或平均音量低于阈值时有明确判定 |
| `transcribe` | `preflight.verdict` | `transcript.segments` | 写切片缓存 | 总字数不少于阈值，段数与时长匹配 |
| `compose` | `transcript.segments` | `doc.path` | 写 Markdown | 头部六项字段可解析，段落时间连续 |
| `organize` | `doc.path` | `archive.path` | 移动、改名、重写导航 | 编号连续、无重名、导航链接可达 |
| `reconcile` | `archive.path` | `queue.status` | 写状态区与历史文件 | 待转为 0、孤儿音频为 0、无重复发布 |
| `index` | 全部成稿 | `index.files` | 写三类索引 | 每个条目可回溯到文件与段落 |
| `publish` | `archive.path` | `publish.result` | 远端提交 | 远端提交存在或明确无变更 |

`preflight` 的判定顺序：标题重复优先，其次是音量，最后是转写后字数。三类跳过都写入状态，终态不是“已删除”。

## 5. Provider 接口

### 5.1 MinutesProvider

```python
class MinutesProvider(Protocol):
    def search(self, start: date, end: date) -> list[MinuteRef]: ...
    def meta(self, token: str) -> MinuteMeta: ...
    def download(self, token: str, dest: Path) -> Path | None: ...
    def official_transcript(self, token: str) -> str | None: ...
```

默认实现 `LarkCliProvider`，调用外部 `lark-cli`。实现必须处理分页，不能假设单页返回完整结果；必须在本地按开始时间重排，不信任接口顺序。

### 5.2 AsrProvider

```python
class AsrProvider(Protocol):
    def transcribe(self, pcm: bytes) -> str: ...
```

默认实现 `StepFunAsr`：16 kHz、单声道、16 位 PCM，模型 `stepaudio-2.5-asr`，`enable_itn=true`，SSE 增量拼接。凭证只从环境变量读取。

### 5.3 Publisher

```python
class Publisher(Protocol):
    def publish(
        self,
        archive_dir: Path,
        *,
        remote: str,
        branch: str,
        message: str,
        dry_run: bool = False,
    ) -> PublishResult: ...
```

默认实现 `GitPublisher`，目标仓库、分支、提交信息全部来自配置，无内置默认仓库。

## 6. 状态机与持久化

```
downloaded → transcribed → composed → organized → published

跳过终态：silent | duplicate | no-audio | empty
失败：failed（切片级重试耗尽）
```

`reconciled`、`indexed`、`abandoned` 为保留状态，v0.1 不写入。

状态文件 `state.json`：

```json
{
  "schema_version": 1,
  "last_run": "2026-01-01T00:00:00+08:00",
  "last_search": "2026-01-01",
  "items": {
    "<token>": {
      "status": "composed",
      "attempts": 1,
      "words": 12345,
      "mean_db": -21.3,
      "files": ["01-2026-01/01-2026-01-01 · 标题.md"],
      "updated_at": "2026-01-01T00:10:00+08:00"
    }
  }
}
```

- 写入方式：同目录临时文件 → `fsync` → `os.replace`，保证原子性。
- `schema_version` 不匹配时拒绝启动并提示迁移命令，不做静默兼容。
- 中断恢复：重跑 `fmk run`。已下载音频、切片缓存与已归档 token 都会复用，
  不需要单独的续跑参数。
- 单条失败不中断整批；批次结束时汇总。

## 7. 配置

优先级：**内置默认值 < `config.toml`**。凭证只来自环境变量；命令行参数用于
选择配置文件与运行范围（`--since`、`--only`、`--dry-run`），不覆盖单个配置项。

```toml
[workspace]
work_dir = "./work"
minutes_dir = "./work/minutes"
state_dir = "./work/state"
archive_dir = "./archive"

[naming]
dir_format = "{index:02d}-{year}-{month:02d}"
file_format = "{index:02d}-{date} · {title}.md"
max_title_chars = 80

[preflight]
silent_db = -50.0
min_words = 20

[transcribe]
segment_seconds = 1500
request_seconds = 120
concurrency = 3
max_retries = 3

[source]
provider = "lark-cli"

[asr]
provider = "stepfun"
model = "stepaudio-2.5-asr"

[index]
enabled = false

[publish]
enabled = false
provider = "git"
remote = ""
branch = "main"
commit_message = "chore: sync minutes archive"

[pipeline]
steps = [
  "discover", "download", "preflight", "transcribe", "compose",
  "organize", "reconcile", "index", "publish",
]
```

环境变量只承载凭证：`FMK_STEPFUN_API_KEY`。任何路径、仓库名都没有个人默认值；缺失即报 `ConfigError`，并指出具体键名。

## 8. CLI

```
fmk init [--dir PATH] [--force]  生成 config.toml 与 .env.example
fmk doctor                       检查依赖、凭证、目录与权限
fmk discover [--since DATE] [--json]  只列新妙记
fmk run [--since|--only|--dry-run]    执行流水线
fmk status [--json]
fmk plugins list
fmk version
```

退出码：

| 码 | 含义 |
|---|---|
| 0 | 全部成功 |
| 2 | 配置或环境错误 |
| 3 | 部分条目失败（批次继续完成） |
| 4 | 产体验收失败（文件缺失、字段不可解析、编号断裂） |

`run` 的默认顺序由 `[pipeline] steps` 决定；未配置时使用内置九步顺序。
`--only` 只执行到指定步骤。归档、核对、索引、发布都通过 `fmk run` 执行，
v0.1 不提供独立子命令。

## 9. 输出结构与技术选型

### 9.1 归档目录

```
archive/
├── 01-2026-01/                    月份文件夹，编号越小越新
│   ├── _index.md                  当月索引
│   └── 01-2026-01-01 · 标题.md    成稿
├── _overview.md                   根目录导航
├── _queue.md                      队列状态区（含 fmk:status 标记）
├── _quotes.md                     金句索引（可选）
├── _numbers.md                    商业数据索引（可选）
└── _people.md                     人脉索引（可选）
```

- 日期优先级：成稿头部录制时间 → 文件名日期 → 文件修改时间。
- 标题清洗：替换 `\ / : * ? " < > |`，合并空白，按 `max_title_chars` 截断；同名追加 `（2）`。
- 导航文件由固定模板生成，重复运行结果一致；状态区用 `<!-- fmk:status:start -->` 与 `<!-- fmk:status:end -->` 包裹，只替换标记之间内容。
- `[index]` 或 `[publish]` 为 `enabled = false` 时，对应步骤在 Pipeline 中记为 `skipped(config)`，不算失败。

### 9.2 技术选型

| 项 | 选择 | 理由 |
|---|---|---|
| Python | 3.10+ | 与现有链路的运行环境一致，类型语法够用 |
| 运行依赖 | `httpx`、`typer`、`rich`；3.10 额外 `tomli` | 只保留 SSE、CLI、终端输出三件事所需 |
| 数据建模 | 标准库 `dataclasses` + 显式校验 | 不引入 pydantic，减少体积与版本冲突 |
| 构建 | `hatchling`，src 布局 | 打包简单，入口点声明清晰 |
| 开发工具 | `pytest`、`ruff`、`mypy`、`pre-commit`、`gitleaks` | 测试、风格、类型、防泄漏各司其职 |

## 10. 安全与隐私（硬约束）

威胁模型：真实凭证被误提交、日志或报错泄露、测试夹具带入真实数据、截图与文档带入个人信息、CI 产物留存敏感内容。

| 风险 | 控制措施 |
|---|---|
| Key 进入仓库 | 只提供 `.env.example` 与占位配置；`.gitignore` 覆盖 `.env`、`config.toml`、`work/`、`archive/` |
| 日志泄露凭证 | 统一日志过滤器，脱敏 `Authorization`、`*_API_KEY`、token；请求体与响应体永不打印 |
| 报错回显 | `doctor` 只报告“已设置 / 未设置”；需要展示时保留前 4 位并打码 |
| 测试数据 | 使用合成音频与 `test-key`；禁止提交真实录音与逐字稿 |
| 提交前扫描 | pre-commit 与 CI 运行 gitleaks |
| 个人信息 | 不内置用户名、仓库名、路径、姓名；示例一律用 `OWNER/REPO`、`YOU` |
| 遥测 | 无任何遥测、无外部回传 |

`SECURITY.md` 说明漏洞披露渠道与响应时限。CI 日志禁止开启调试模式打印完整请求。

## 11. 错误处理与幂等

- 错误类型：`ConfigError`、`ProviderError`、`StepError`、`VerificationError`。
- 每个 Provider 调用有超时与重试；重试采用指数退避，次数来自配置。
- 幂等保证：
  - 已下载音频直接复用；
  - 已生成的 120 秒切片读缓存，不重复请求；
  - 已出稿 token 在 `discover` 阶段排除；
  - `organize` 遇到重名直接失败，不覆盖；
  - `publish` 无变更时跳过提交。
- 所有“移动、改名、推送”默认支持 `--dry-run`，输出将发生的变更清单。

## 12. 测试策略

| 层级 | 内容 | 是否联网 |
|---|---|---|
| 单元 | 命名、编号、Markdown 合成、队列判定、索引规则、配置优先级、日志脱敏 | 否 |
| 契约 | 每个 Provider 满足接口语义；分页、异常、超时、空结果 | 否 |
| 集成 | 假 `lark-cli` 可执行文件 + 本地假 SSE 服务，跑完整九步 | 否 |
| 生成物 | 成稿、索引、导航用 golden file 比对 | 否 |

CI 矩阵：Ubuntu 与 macOS，Python 3.10–3.13。覆盖率门槛 80%。集成测试在临时目录运行，结束后清理。

## 13. 仓库结构

```
feishu-minutes-kit/
├── pyproject.toml
├── README.md
├── README.zh-CN.md
├── LICENSE
├── CHANGELOG.md
├── CONTRIBUTING.md
├── SECURITY.md
├── .env.example
├── config.example.toml
├── .gitignore
├── .pre-commit-config.yaml
├── .github/workflows/ci.yml
├── docs/
│   ├── architecture.md
│   ├── plugin-api.md
│   ├── configuration.md
│   └── workflow.md
├── examples/plugin-example/
├── src/fmk/
│   ├── cli.py
│   ├── config.py
│   ├── context.py
│   ├── registry.py
│   ├── pipeline.py
│   ├── state.py
│   ├── logging.py
│   ├── errors.py
│   ├── steps/
│   └── providers/
└── tests/
    ├── unit/
    ├── contract/
    ├── integration/
    └── fixtures/
```

## 14. 里程碑

| 阶段 | 交付 | 完成判据 |
|---|---|---|
| M1 | 内核、注册表、Pipeline、配置、`init`、`doctor`、`plugins list` | 能发现内置步骤并输出执行计划 |
| M2 | `LarkCliProvider`、`StepFunAsr`、`discover`、`download` | 能列出并下载一条真实妙记 |
| M3 | `preflight`、`transcribe`、`compose` | 生成一篇字段完整的成稿 |
| M4 | `organize`、`reconcile`、`index` | 归档后编号连续、队列一致 |
| M5 | `publish`、双语 README、四篇文档、示例插件、CI | 新机器按 README 跑通 |
| M6 | 0.1.0 发布 | 验收清单全过 |

## 15. 验收标准

1. 全新机器按 README 三步完成安装与配置，能跑通一条妙记。
2. `fmk doctor` 能拦住缺失的 lark-cli、ffmpeg、凭证与目录权限。
3. 公开仓库通过 gitleaks 扫描，无任何真实凭证、个人信息或录音内容。
4. 测试矩阵全绿，覆盖率不低于 80%。
5. 重复执行 `fmk run` 不产生重复成稿，状态与文件一致。
6. 任一步骤失败时，已完成产物不被破坏；重跑 `fmk run` 可继续（状态、音频与切片缓存复用）。

## 16. 风险与待验证项

| 风险 | 影响 | 应对 |
|---|---|---|
| `lark-cli` 在非插件环境的获取方式与许可 | 影响“同好落地” | 文档写清安装来源；Provider 接口保留直连 OpenAPI 的替换位 |
| `+search` 单页上限与 `has_more` 不可信 | 可能漏扫 | 分页 + 日期分段 + 条数等于上限时告警 |
| 长音频 SSE 限流或截断 | 成稿缺失 | 固定 120 秒切片、并发可配、失败片可重跑 |
| 不同妙记音频格式差异 | 下载失败 | 支持常见扩展名，失败记 `no-audio` 并可单条重试 |
| 第三方插件质量不可控 | 稳定性 | 版本校验、失败跳过、`plugins list` 标注来源 |

## 17. 后续版本（不在 v0.1）

- 直连飞书 OpenAPI 的 `MinutesProvider`。
- OpenAI 兼容与本地 whisper.cpp 的 `AsrProvider`。
- 待办、踩坑、方案三个索引维度。
- 增量索引与全文检索。
- 可视化报告（只读，本地生成）。
