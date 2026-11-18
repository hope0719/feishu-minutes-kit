# feishu-minutes-kit 实现计划

| 项目 | 内容 |
|---|---|
| 对应设计 | `docs/specs/2026-11-18-feishu-minutes-kit-design.md` |
| 目标版本 | 0.1.0 |
| 执行方式 | 按 M0 → M6 顺序推进，每个里程碑独立可验证 |
| 提交策略 | 不自动提交；每个里程碑完成后由你确认是否 commit |

## 0. 执行约定

- 每个里程碑结束时必须跑通该阶段的验证命令，未通过不进入下一阶段。
- 所有新增文件先保证类型可检查、风格可通过 `ruff`，再补测试。
- 测试全程不联网：外部依赖用假可执行文件与本地假 HTTP 服务替代。
- 仓库内任何位置不写入真实凭证、个人路径、仓库名、姓名或录音内容。
- 破坏性操作（`organize`、`publish`）在实现时就内置 `--dry-run`，不做事后补丁。

验证基线：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ruff check .
mypy src
pytest -q
```

## 1. 里程碑总览

| 阶段 | 主题 | 关键产物 | 完成判据 |
|---|---|---|---|
| M0 | 项目骨架 | 可安装的空包、配置样例、许可与忽略规则 | `fmk --help` 可运行 |
| M1 | 内核 | Registry / Pipeline / Config / State / CLI | 单元测试通过，`fmk doctor` 可诊断环境 |
| M2 | 数据源与下载 | LarkCliProvider、discover、download | 假 lark-cli 下能列出并下载音频 |
| M3 | 判定、转写与成稿 | preflight、transcribe、compose | 假 ASR 下生成 golden 成稿 |
| M4 | 归档、核对与索引 | organize、reconcile、index | 重复运行结果一致，队列一致 |
| M5 | 发布与开源配套 | publish、四篇文档、示例插件、CI | 全量检查通过、README 可跑通 |
| M6 | 发布 0.1.0 | CHANGELOG、版本号、验收记录 | 验收清单全过 |

## 2. M0 项目骨架

| ID | 任务 | 文件 | 验证 |
|---|---|---|---|
| M0-1 | 初始化构建配置与入口点 | `pyproject.toml` | `pip install -e .` 成功，`fmk --help` 有输出 |
| M0-2 | 包入口与版本 | `src/fmk/__init__.py`、`__main__.py` | `python -m fmk --help` |
| M0-3 | 仓库卫生 | `.gitignore`、`.env.example`、`config.example.toml` | `git status` 不出现 `.env`、`work/`、`archive/` |
| M0-4 | 开源文件占位 | `LICENSE`、`README.md`、`README.zh-CN.md`、`SECURITY.md`、`CONTRIBUTING.md`、`CHANGELOG.md` | 文件存在且无个人信息 |

M0 完成判据：空包可安装、可执行；样例配置中的凭证全部为占位符。

## 3. M1 内核

| ID | 任务 | 文件 | 测试 |
|---|---|---|---|
| M1-1 | 错误类型 | `errors.py` | 类型与退出码映射 |
| M1-2 | 日志与脱敏 | `logging.py` | `Authorization`、`*_API_KEY`、token 被替换 |
| M1-3 | 配置加载与优先级 | `config.py` | 默认值 < toml < env < CLI；缺键报 `ConfigError` |
| M1-4 | 运行上下文 | `context.py` | 命名空间隔离，步骤不能越权写 |
| M1-5 | 状态存储 | `state.py` | 原子写、schema 版本、损坏文件处理 |
| M1-6 | 插件注册表 | `registry.py` | 版本不匹配跳过、重名拒绝、导入失败不致命 |
| M1-7 | 流水线 | `pipeline.py` | requires/provides 校验、环检测、`--only`、`--resume` |
| M1-8 | CLI 骨架 | `cli.py` | `init`、`doctor`、`plugins list`、`status` |
| M1-9 | 环境诊断 | `doctor.py` | 缺 lark-cli / ffmpeg / 凭证 / 目录权限时报错且打码 |

M1 完成判据：`pytest tests/unit` 全绿；在临时目录执行 `fmk init` 与 `fmk doctor` 行为符合预期。

## 4. M2 数据源与下载

| ID | 任务 | 文件 | 测试 |
|---|---|---|---|
| M2-1 | Provider 协议 | `providers/base.py` | 协议符合性检查 |
| M2-2 | lark-cli 适配 | `providers/lark_cli.py` | 分页、本地降序、失败重试、超时 |
| M2-3 | 假 lark-cli 夹具 | `tests/fixtures/fake_lark_cli` | 可模拟分页、空结果、报错 |
| M2-4 | discover 步骤 | `steps/discover.py` | 四类已知来源差集、去重、日期窗 |
| M2-5 | download 步骤 | `steps/download.py` | 已有音频复用、扩展名识别、失败记 `no-audio` |

M2 完成判据：集成测试用假 lark-cli 跑通「发现 3 条 → 下载 2 条 → 1 条记 no-audio」。

## 5. M3 判定、转写与成稿

| ID | 任务 | 文件 | 测试 |
|---|---|---|---|
| M3-1 | 判重与判无声 | `steps/preflight.py` | 重复标题优先、阈值边界、证据字段 |
| M3-2 | 切片与缓存 | `steps/transcribe.py`、`core/audio.py` | 120 秒切片、缓存命中、失败片重跑 |
| M3-3 | 阶跃星辰适配 | `providers/stepfun.py` | SSE 增量拼接、错误事件、超时 |
| M3-4 | 假 SSE 服务 | `tests/fixtures/sse_server.py` | 正常、截断、错误三种响应 |
| M3-5 | Markdown 合成 | `core/markdown.py`、`steps/compose.py` | 六项头部字段、段落时间连续 |
| M3-6 | golden 文件 | `tests/fixtures/golden/*.md` | 生成结果逐字节一致 |

M3 完成判据：集成测试从假音频生成一篇成稿，与 golden 文件一致；字数低于阈值时记 `empty`。

## 6. M4 归档、核对与索引

| ID | 任务 | 文件 | 测试 |
|---|---|---|---|
| M4-1 | 命名与编号 | `core/naming.py`、`steps/organize.py` | 月份文件夹、编号连续、重名失败 |
| M4-2 | 导航生成 | `core/navigation.py` | 重复运行结果一致、链接可达 |
| M4-3 | 队列核对 | `core/queue.py`、`steps/reconcile.py` | 四向统计、14 天归档、重复发布告警 |
| M4-4 | 横向索引 | `core/indexes.py`、`steps/index.py` | 金句去噪、金额分类、人名排除职业词 |
| M4-5 | 幂等测试 | `tests/integration/test_idempotent.py` | 连跑两次无新增、无改名 |

M4 完成判据：固定夹具上连续运行两次，文件树与状态文件完全一致。

## 7. M5 发布与开源配套

| ID | 任务 | 文件 | 验证 |
|---|---|---|---|
| M5-1 | Git 发布适配 | `providers/git_publisher.py`、`steps/publish.py` | 无变更跳过、dry-run 不写入 |
| M5-2 | 架构与插件文档 | `docs/architecture.md`、`docs/plugin-api.md` | 示例插件按文档可加载 |
| M5-3 | 配置与流程文档 | `docs/configuration.md`、`docs/workflow.md` | 每个配置键有说明与默认值 |
| M5-4 | 示例插件 | `examples/plugin-example/` | 被 `fmk plugins list` 发现 |
| M5-5 | CI 与预提交 | `.github/workflows/ci.yml`、`.pre-commit-config.yaml` | 3.10–3.13 矩阵通过、gitleaks 无告警 |
| M5-6 | README 快速开始 | `README.md`、`README.zh-CN.md` | 三步安装、五条命令说明 |

M5 完成判据：全新虚拟环境按 README 操作可运行；CI 全绿；文档与实现无冲突。

## 8. M6 发布 0.1.0

| ID | 任务 | 验证 |
|---|---|---|
| M6-1 | 版本号与 CHANGELOG | `0.1.0`，条目覆盖九步与插件接口 |
| M6-2 | 验收清单执行 | 设计文档第 15 节六条逐条记录结果 |
| M6-3 | 仓库卫生复查 | gitleaks、`git ls-files` 无敏感文件 |
| M6-4 | 打标签 | `v0.1.0`（需你确认后执行） |

## 9. 测试矩阵

| 层 | 文件 | 覆盖对象 |
|---|---|---|
| 单元 | `tests/unit/` | 配置、状态、命名、Markdown、队列、索引、脱敏 |
| 契约 | `tests/contract/` | 三个 Provider 的接口语义与异常路径 |
| 集成 | `tests/integration/` | 九步串联、断点续跑、幂等 |
| 生成物 | `tests/fixtures/golden/` | 成稿、月份索引、导航、三类索引 |

覆盖率门槛 80%，CI 中低于门槛直接失败。

## 10. 风险控制

- **先做假实现再连真环境**：M2–M3 全部用夹具验证，避免开发期反复消耗真实额度。
- **接口先行**：Provider 协议在 M2 冻结，后续替换实现不改步骤代码。
- **数据不越界**：所有测试在 `tmp_path` 内运行，禁止读写真实 `minutes/` 与 `archive/`。
- **凭证零落盘**：测试用 `test-key`，日志断言中不得出现完整 key。
- **文档跟随代码**：每个里程碑结束时同步更新对应文档段落，避免最后补写失真。

## 11. 验收映射

| 设计文档验收项 | 实现证据 |
|---|---|
| 新机器三步跑通 | M5 README + M6 验收记录 |
| `doctor` 拦截缺失依赖 | M1-9 单元测试 |
| 无真实凭证与个人信息 | M5-5 gitleaks + M6-3 复查 |
| 测试矩阵全绿、覆盖率达标 | CI 结果 |
| 重复执行不产生重复成稿 | M4-5 幂等测试 |
| 失败不破坏已完成产物 | M1-5 原子写 + M3 缓存测试 |
