# 架构

本文描述 v0.1 的实现结构。设计取舍与验收标准见
[设计文档](specs/2026-11-18-feishu-minutes-kit-design.md)。

## 1. 定位与边界

`fmk` 是一个本地命令行工具：把你自己飞书账号下的妙记录音，整理成可检索、
可版本管理的 Markdown 档案。

- 本地优先：没有托管服务、没有遥测，数据只发给你配置的服务商。
- 单用户：不做多租户、权限、协作编辑。
- 线性流水线：一次运行按固定顺序执行九个步骤。
- v0.1 不包含实时录制、GUI、官方逐字稿校对。

## 2. 分层

```
┌──────────────────────────────────────────────────────┐
│ CLI  fmk init / doctor / discover / run / status ... │
├──────────────────────────────────────────────────────┤
│ Kernel                                               │
│  config     默认值 < TOML < 环境变量                  │
│  registry   发现内置与第三方插件，做版本与重名检查     │
│  pipeline   校验依赖、环、未知步骤，生成执行计划       │
│  context    步骤间数据传递，写入所有权检查             │
│  state      state.json，schema 版本 + 原子写           │
│  doctor     依赖、凭证、目录权限诊断                   │
├──────────────────────────────────────────────────────┤
│ Steps（九步）                                        │
│  discover download preflight transcribe compose      │
│  organize reconcile index publish                    │
├──────────────────────────────────────────────────────┤
│ Providers                                            │
│  MinutesProvider  lark-cli                           │
│  AsrProvider      stepfun                            │
│  Publisher        git（可选）                         │
└──────────────────────────────────────────────────────┘
```

上层只依赖下层协议，不依赖具体实现。替换 ASR 服务不需要改任何步骤代码。

## 3. 内核组件

| 模块 | 职责 | 关键约束 |
|---|---|---|
| [cli.py](../src/fmk/cli.py) | 命令解析、参数到配置/上下文的映射 | 命令只做编排，不含业务规则 |
| [config.py](../src/fmk/config.py) | 读取 TOML、环境变量、解析路径 | 缺键或类型错误直接抛 `ConfigError` |
| [registry.py](../src/fmk/registry.py) | 注册内置组件、加载 entry points | 版本不匹配/重名/导入失败只警告并跳过 |
| [pipeline.py](../src/fmk/pipeline.py) | 静态校验与执行计划 | 运行前拒绝未知步骤、缺失依赖、循环依赖 |
| [context.py](../src/fmk/context.py) | 步骤间共享数据 | 步骤只能写自己 `provides` 的键 |
| [state.py](../src/fmk/state.py) | 运行状态持久化 | 原子替换；损坏文件先备份再重建 |
| [doctor.py](../src/fmk/doctor.py) | 环境诊断 | 凭证只显示“已设置/未设置”，必要时只留前 4 位 |
| [logging.py](../src/fmk/logging.py) | 日志与脱敏 | `Authorization`、`*_API_KEY`、token 统一打码 |

## 4. 一次 `fmk run` 的时序

1. 读取配置：`--config` → `FMK_CONFIG` → 当前目录 `config.toml` → 内置默认值。
2. 创建 `work/`、`minutes/`、`state/`、`archive/` 目录。
3. `Registry.discover()` 注册九个内置步骤、三个内置 Provider，再加载
   `fmk.steps` 与 `fmk.providers` 两个 entry point 组。
4. `StateStore.load()` 读取 `state.json`；文件损坏时改名为
   `state.json.corrupt-<时间戳>`，从空状态继续。
5. `Pipeline.plan()` 按 `pipeline.steps` 校验并生成计划；`--only` 截断到指定步骤。
6. 构造 `Context`，依次执行步骤。每完成一步就写入 `completed_steps`。
7. 全流程成功且未使用 `--only` 时，清空 `completed_steps`，把
   `last_search` 记为当天日期。

`--dry-run` 不写状态、不移动归档文件、不推送；详见
[工作流](workflow.md#dry-run-的边界)。

## 5. 步骤契约

每个步骤声明四个属性和一个方法：

```python
class Step(Protocol):
    api_version: int
    name: str
    requires: frozenset[str]
    provides: frozenset[str]

    def run(self, ctx: Context) -> StepResult: ...
```

`StepResult.status` 的语义：

| 状态 | 含义 | 流水线行为 |
|---|---|---|
| `ok` | 步骤完成，产物可验证 | 继续 |
| `skip` | 配置关闭或没有可做的事 | 继续，不算失败 |
| `retry` | 当前批次可重试 | 由调用方决定；CLI 视为未完成 |
| `fail` | 步骤失败 | CLI 抛 `StepError`，退出码 3 |

内置步骤的依赖与产出：

| 步骤 | `requires` | `provides` | 主要副作用 |
|---|---|---|---|
| `discover` | — | `minutes.list` | 无 |
| `download` | `minutes.list` | `audio.path` | 写 `work/minutes/<token>/` |
| `preflight` | `audio.path` | `preflight.verdict` | 无（会调用 ffmpeg 读取音量） |
| `transcribe` | `preflight.verdict` | `transcript.segments` | 写 `_segs/` 切片缓存 |
| `compose` | `transcript.segments` | `doc.path` | 写 `work/docs/<token>.md` |
| `organize` | `doc.path` | `archive.path` | 移动、改名、重写导航 |
| `reconcile` | `archive.path` | `queue.status` | 写 `_queue.md`、`_queue-history.md` |
| `index` | `archive.path` | `index.files` | 写 `_quotes.md` 等（可选） |
| `publish` | `archive.path` | `publish.result` | git 提交与推送（可选） |

插件接口、上下文键和 Provider 协议见 [插件 API](plugin-api.md)。

## 6. 数据传递与所有权

`Context` 是一个带所有权的命名空间：

- `ctx.set(key, value, step=..., provides=...)` 只能写 `provides` 中的键。
- 同一个键一旦被某个步骤写入，其他步骤不能覆盖。
- 步骤通过 `ctx.require(key)` 读取上游产物；缺失时抛 `StepError`。
- `ctx.providers` 按名称注入 Provider；`ctx.options` 用于运行期选项与测试替身
  （例如 `ffmpeg`、`since`）。

这条规则把“步骤之间靠隐式全局变量耦合”的问题挡在运行前。

## 7. Provider 层

| 协议 | 内置实现 | 说明 |
|---|---|---|
| `MinutesProvider` | `LarkCliProvider` | 调用外部 `lark-cli minutes`，处理分页并在本地按时间重排 |
| `AsrProvider` | `StepFunAsr` | SSE 增量拼接，输入 16 kHz 单声道 16 位 PCM |
| `Publisher` | `GitPublisher` | 提交归档目录并推送，未配置时步骤跳过 |

Provider 实例由注册表无参构造。需要凭证或模型参数的实现，应在调用时从环境变量
或自身配置读取；内置 `StepFunAsr` 由转写步骤通过 `with_config()` 注入。

## 8. 状态机与持久化

```
discovered → downloaded → transcribed → composed
           → organized → published

跳过终态：silent | duplicate | no-audio | empty
失败：failed（切片级重试耗尽）
```

当前实现实际写入的状态为：`downloaded`、`duplicate`、`silent`、`no-audio`、
`transcribed`、`empty`、`failed`、`composed`、`organized`、`published`。
`reconciled`、`indexed`、`abandoned` 为保留状态，v0.1 不写入。

`state.json` 结构：

```json
{
  "schema_version": 1,
  "last_run": "2026-01-01T00:00:00+08:00",
  "last_search": "2026-01-01",
  "completed_steps": ["discover", "download"],
  "items": {
    "<token>": {
      "status": "composed",
      "attempts": 0,
      "words": 12345,
      "mean_db": -21.3,
      "files": ["01-2026-01/01-2026-01-01 · 标题.md"],
      "reason": null,
      "updated_at": "2026-01-01T00:10:00+08:00"
    }
  }
}
```

- 写入顺序：同目录临时文件 → `flush` → `fsync` → `os.replace`。
- `schema_version` 不匹配时拒绝启动，不做静默兼容。
- `items` 的键是妙记 token，不写标题、作者或正文。

## 9. 幂等与失败处理

| 场景 | 处理 |
|---|---|
| 音频已存在 | 直接复用，不重复下载 |
| 120 秒切片已有缓存 | 读缓存，不重复请求 ASR |
| 已归档 token | `discover` 阶段排除 |
| 月份目录或文件名变化 | 先改到临时名，再原子改名；冲突时拒绝覆盖 |
| 同一 token 多篇成稿 | `organize` 前直接失败，要求人工处理 |
| 发布无变更 | 跳过 commit 与 push |
| 单条录音失败 | 记入状态，批次继续；CLI 汇总后以退出码 3 结束 |

## 10. 归档结构

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
├── _quotes.md        # index.enabled = true 时生成
├── _numbers.md
└── _people.md
```

- 月份目录与文件都是“编号越小越新”，每次 `organize` 重新计算。
- 所有导航链接都是归档内相对路径，不写本机绝对路径。
- 导航文件内容由固定模板生成，重复运行结果一致。
- `_queue.md` 只替换 `<!-- fmk:status:start -->` 与
  `<!-- fmk:status:end -->` 之间的内容。

## 11. 插件发现与版本

- 两个 entry point 组：`fmk.steps`、`fmk.providers`。
- `api_version` 必须等于 `1`，否则注册表记录警告并跳过。
- 同名插件保留先注册者（内置优先），后来者跳过。
- 第三方插件导入异常不会终止进程，只记录警告。
- 没有沙箱、进程隔离或热加载：插件与内核同进程运行，安装前需自行审查。

## 12. 安全与隐私

- 仓库只提供占位配置与 `.env.example`，不包含真实凭证、路径、姓名或转录。
- 凭证只从 `FMK_STEPFUN_API_KEY` 读取；日志过滤器会打码。
- `publish.remote` 允许写 URL，但 `config.toml` 已被 `.gitignore` 忽略；
  不要把带 token 的 URL 写进示例文件。
- 测试只使用合成音频、假 `lark-cli`、假 ffmpeg 与本地 SSE 服务。

## 13. 测试结构

| 层 | 位置 | 内容 |
|---|---|---|
| 单元 | `tests/unit/` | 配置优先级、状态原子写、命名、Markdown、队列、索引、脱敏 |
| 集成 | `tests/integration/` | 假 `lark-cli` 跑发现/下载；本地 SSE 跑转写；九步串联与发布 |
| 生成物 | `tests/fixtures/golden/` | 成稿逐字节比对 |
| 示例插件 | `tests/unit/test_example_plugin.py` | 通过注册表加载并执行第三方步骤 |

全部测试离线运行，断言不依赖真实网络、真实录音或真实密钥。

## 14. 关键取舍

- **微内核而不是框架**：内核只负责发现、校验、传递与持久化，业务都在步骤里。
- **不做事件总线**：线性顺序可静态推理，排障成本低。
- **dataclasses 而不是 pydantic**：配置项少，显式校验足够，依赖更轻。
- **JSON 状态而不是数据库**：单用户单机，便于查看、备份和手工修复。
- **外部工具走 Provider**：`lark-cli`、`ffmpeg`、`git` 都可替换，测试可注入替身。
