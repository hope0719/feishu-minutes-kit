# 插件 API

v0.1 的扩展点只有两类：流水线步骤（`fmk.steps`）与 Provider
（`fmk.providers`）。插件是普通 Python 包，与内核同进程运行，没有沙箱。

完整的可运行示例在 [`examples/plugin-example/`](../examples/plugin-example/)。

## 1. 步骤契约

```python
from pathlib import Path

from fmk.context import Context
from fmk.steps.base import API_VERSION, StepResult


class WordCountStep:
    api_version = API_VERSION          # 必须等于 1
    name = "wordcount"                 # 全局唯一
    requires = frozenset({"doc.path"})
    provides = frozenset({"doc.words"})

    def run(self, ctx: Context) -> StepResult:
        docs: dict[str, Path] = dict(ctx.require("doc.path"))
        counts = {
            token: len(path.read_text(encoding="utf-8", errors="ignore"))
            for token, path in docs.items()
            if path.is_file()
        }
        ctx.set("doc.words", counts, step=self.name, provides=self.provides)
        return StepResult(status="ok", outputs={"doc.words": counts})
```

要求：

1. `api_version` 必须等于 `fmk.steps.base.API_VERSION`（当前为 `1`）。
2. `name` 必须全局唯一；与内置步骤重名时，内置实现优先，插件被跳过。
3. `requires` 中的每个键都必须由 `pipeline.steps` 中更早的步骤提供，
   否则流水线在启动前报 `ConfigError`。
4. 只能通过 `ctx.set(..., step=..., provides=...)` 写入自己声明的键。
5. 下游要用的数据必须写入 `Context`；`StepResult.outputs` 只是本次运行的
   附加返回值，不会被自动合并进上下文。
6. 使用 `ctx.logger`，不要 `print`；日志会自动脱敏。
7. 检查 `ctx.dry_run`：预览模式下不要写文件、不要发起付费请求。

### 1.1 StepResult

```python
@dataclass(frozen=True)
class StepResult:
    status: Literal["ok", "skip", "retry", "fail"]
    outputs: Mapping[str, Any] = field(default_factory=dict)
    reason: str | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)
```

| 状态 | 使用场景 |
|---|---|
| `ok` | 步骤完成，产物可用 |
| `skip` | 配置关闭、没有输入或无事可做；不算失败 |
| `retry` | 当前批次可重试；CLI 以退出码 3 结束，重跑即可 |
| `fail` | 不可恢复的失败；CLI 抛 `StepError` |

`evidence` 用来放验收证据（数量、路径、音量、字数等），不要依赖日志文本。
内置步骤的 `evidence` 都是可 JSON 序列化的基本类型。

### 1.2 可用的上下文方法

| 方法 | 说明 |
|---|---|
| `ctx.require(key)` | 读取上游产物；缺失时抛 `StepError` |
| `ctx.get(key, default)` | 读取可选产物 |
| `ctx.set(key, value, *, step, provides)` | 写入并登记所有权 |
| `ctx.owner(key)` | 查看某个键由哪个步骤写入 |
| `ctx.snapshot()` | 当前上下文的浅拷贝，便于调试 |
| `ctx.provider(name)` | 按名称取 Provider；缺失时抛 `ConfigError` |
| `ctx.option(name, default)` | 运行期选项/测试替身，例如 `ffmpeg`、`since` |
| `ctx.config` | 只读的 `Config` 对象 |
| `ctx.state` | `StateStore` 或 `None` |
| `ctx.dry_run` | 是否为预览模式 |
| `ctx.logger` | 带脱敏过滤器的 logger |

上下文键建议使用 `领域.对象` 形式（如 `doc.path`、`archive.path`），避免命名冲突。

### 1.3 内置上下文键

| 键 | 类型 | 提供者 |
|---|---|---|
| `minutes.list` | `list[MinuteRef]` | `discover` |
| `audio.path` | `dict[str, Path]` | `download` |
| `preflight.verdict` | `dict[str, PreflightVerdict]` | `preflight` |
| `transcript.segments` | `dict[str, list[TranscriptSegment]]` | `transcribe` |
| `doc.path` | `dict[str, Path]` | `compose` |
| `archive.path` | `dict[str, Path]` | `organize` |
| `queue.status` | `dict[str, Any]` | `reconcile` |
| `index.files` | `dict[str, Path]` | `index` |
| `publish.result` | `dict[str, Any]` | `publish` |

### 1.4 异常

抛出以下异常会被 CLI 转成可读错误与稳定退出码：

| 异常 | 退出码 | 用途 |
|---|---|---|
| `ConfigError` | 2 | 配置缺失、类型错误、未知 provider |
| `ProviderError` | 3 | 外部命令、HTTP、git 调用失败 |
| `StepError` | 3 | 步骤无法完成 |
| `VerificationError` | 4 | 产物不满足验收规则 |

其他异常不会被 CLI 美化，会带堆栈退出。插件应把可预期的外部失败包装成上表
中的类型，并给出 `hint`。

## 2. 注册步骤

在插件包的 `pyproject.toml` 中声明 entry point：

```toml
[project]
name = "fmk-wordcount"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["feishu-minutes-kit"]

[project.entry-points."fmk.steps"]
wordcount = "fmk_wordcount:WordCountStep"

[build-system]
requires = ["hatchling>=1.24"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/fmk_wordcount"]
```

安装到与 `fmk` 相同的环境：

```bash
uv pip install -e path/to/plugin
fmk plugins list
```

注册表的行为：

- 导入失败的插件只记录警告，不影响内置步骤。
- `api_version` 不匹配、缺 `name`、未实现协议、重名，都会被跳过并告警。
- 发现顺序：内置组件先注册，然后是两个 entry point 组。

## 3. 在流水线中启用

步骤必须出现在 `config.toml` 的 `[pipeline] steps` 中才会执行，并且顺序要满足
依赖：

```toml
[pipeline]
steps = [
  "discover", "download", "preflight", "transcribe", "compose",
  "wordcount", "organize", "reconcile", "index", "publish",
]
```

`wordcount` 依赖 `doc.path`，所以必须排在 `compose` 之后；它产出的
`doc.words` 目前没有内置步骤消费，仅作为示例。

## 4. Provider 契约

Provider 由注册表无参构造，因此构造函数不能要求必填参数。需要凭证或模型名的
实现应在调用时从环境变量或自身配置读取。

### 4.1 MinutesProvider

```python
class MinutesProvider(Protocol):
    name: str
    api_version: int

    def search(self, start: date, end: date) -> list[MinuteRef]: ...
    def meta(self, token: str) -> MinuteMeta: ...
    def download(self, token: str, dest: Path) -> Path | None: ...
    def official_transcript(self, token: str) -> str | None: ...
```

- `search` 的日期区间含首尾；实现必须处理分页，不能假设一页返回全部。
- 不要求 `search` 排序；`discover` 会在本地按开始时间降序并去重。
- `download` 应在 `dest` 下写入音频并返回文件路径；没有音频时返回 `None`。
- `official_transcript` 在 v0.1 不被调用，预留给后续版本。

```python
@dataclass(frozen=True)
class MinuteRef:
    token: str
    title: str
    start: datetime | None = None
    duration_seconds: int = 0
    url: str = ""
    keywords: tuple[str, ...] = ()
```

### 4.2 AsrProvider

```python
class AsrProvider(Protocol):
    name: str
    api_version: int

    def transcribe(self, pcm: bytes) -> str: ...
```

输入固定为 16 kHz、单声道、16 位小端 PCM。返回非空文本；失败时抛
`ProviderError`。内置实现 `StepFunAsr` 读取 `FMK_STEPFUN_API_KEY`，模型来自
`[asr] model`。

### 4.3 Publisher

```python
@dataclass(frozen=True)
class PublishResult:
    committed: bool
    commit: str | None = None
    changed_files: int = 0


class Publisher(Protocol):
    name: str
    api_version: int

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

- `dry_run=True` 时只统计将变更的文件，不提交、不推送。
- 没有变更时返回 `PublishResult(committed=False, changed_files=0)`。
- 内置 `GitPublisher` 要求归档目录位于某个 git 工作树内，只提交归档目录相对
  仓库根的子路径。

注册 Provider：

```toml
[project.entry-points."fmk.providers"]
my-asr = "fmk_my_asr:MyAsr"
```

然后在配置里选择：

```toml
[asr]
provider = "my-asr"
```

`source.provider` 与 `publish.provider` 同理。

## 5. 测试插件

测试不需要安装 entry point，可以直接注入：

```python
from fmk.registry import Registry


class FakeEntryPoint:
    name = "wordcount"
    value = "tests.fake:WordCountStep"

    def load(self):
        return WordCountStep()


registry = Registry()
registry.discover(entry_points={"fmk.steps": [FakeEntryPoint()]})
assert registry.get_step("wordcount").name == "wordcount"
```

端到端测试用 `Context` 构造最小环境：

```python
context = Context(config, providers={}, options={})
context.set("doc.path", docs, step="compose", provides=frozenset({"doc.path"}))
result = WordCountStep().run(context)
assert result.status == "ok"
```

测试必须离线，且只写 `tmp_path`。不要使用真实录音、真实姓名或真实密钥。

## 6. 版本演进

- 新增可选上下文键、`StepResult` 字段：保持 `api_version = 1`。
- 修改方法签名、删除字段、改变语义：提升 `API_VERSION`，旧插件会被内核拒绝。
- 内核不会尝试兼容旧版本插件；错误信息会指出不匹配的 `api_version`。

## 7. 安全提示

插件与内核同权限运行，可以读写你的归档与凭证环境变量。只安装你信任的插件，
并在安装前阅读其源码。项目不会对第三方插件做审计或背书。
