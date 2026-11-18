# v0.1.0 验收记录

- 日期：2026-11-18
- 版本：`0.1.0`
- 环境：macOS（darwin）、Python 3.12.11、ruff 0.17.5、mypy 2.4.1

本记录对应[设计文档第 15 节](specs/2026-11-18-feishu-minutes-kit-design.md#15-验收标准)的
六条标准。离线项已在本机执行；需要真实飞书账号或远程 CI 的项单独标注。

## 结果总览

| # | 验收标准 | 结果 | 证据 |
|---|---|---|---|
| 1 | 全新机器按 README 三步安装配置，跑通一条妙记 | 安装/配置通过；真实录音待联调 | 全新 venv 安装、`fmk version`、`fmk init`、`fmk doctor` 成功 |
| 2 | `fmk doctor` 拦住缺失依赖、凭证与目录权限 | 通过 | 无凭证时 `[fail] credential`，退出码 2 |
| 3 | 无真实凭证、个人信息或录音内容 | 通过（本地扫描） | gitleaks v8.21.2：`no leaks found` |
| 4 | 测试矩阵全绿，覆盖率 ≥ 80% | 本地通过；远程矩阵待 CI | 96 项通过，覆盖率 85.84% |
| 5 | 重复执行不产生重复成稿，状态与文件一致 | 通过 | 幂等与缓存测试 |
| 6 | 步骤失败不破坏已完成产物，重跑可继续 | 通过 | 原子写、损坏恢复、切片缓存测试 |

## 1. 全新环境安装与配置

在一个空的临时虚拟环境中执行：

```bash
uv pip install -e .
fmk version
fmk init --dir <临时工作区>
fmk doctor
```

结果：

- 安装成功，共安装 19 个依赖，`fmk version` 输出 `0.1.0`。
- `fmk init` 生成 `config.toml`、`.env.example` 与四个工作目录。
- `fmk doctor` 能正常启动并逐项输出检查结果。

**未执行真实妙记的端到端联调**：这需要已授权的 `lark-cli`、有效的 StepFun
凭证以及一条实际录音。仓库内的端到端路径由离线集成测试覆盖：

- `tests/integration/test_discover_download.py`：假 `lark-cli` 完成发现与下载。
- `tests/integration/test_compose_pipeline.py`：本地假 ffmpeg 与假 ASR 完成
  预检、转写、成稿，并与 golden 文件逐字节比对。
- `tests/integration/test_publish.py`：本地裸仓库完成提交与推送。

## 2. `fmk doctor` 的拦截能力

在未设置 `FMK_STEPFUN_API_KEY` 的临时工作区运行：

```text
[ok] config: <临时工作区>/config.toml
[ok] lark-cli: ...
[ok] ffmpeg: ...
[fail] credential: 未设置 FMK_STEPFUN_API_KEY
[ok] workspace.work_dir: ...
[ok] workspace.minutes_dir: ...
[ok] workspace.state_dir: ...
[ok] workspace.archive_dir: ...
doctor_exit=2
```

`tests/unit/test_doctor.py` 另外覆盖了缺少 `lark-cli`、`ffmpeg`、凭证和目录
不可写的情况；凭证只显示是否设置，不输出明文。

## 3. 凭证、个人信息与录音内容

使用 gitleaks v8.21.2 对排除 `.venv/` 与各类缓存后的仓库副本执行：

```bash
gitleaks detect --source <仓库副本> --no-git --redact --verbose
```

输出：`no leaks found`（退出码 0）。

补充检查：

- 仓库内不存在 `.env`、`config.toml`、`work/`、`archive/`、`minutes/`。
- `.gitignore` 覆盖上述文件与目录。
- 文档与示例只使用 `OWNER/REPO`、`<token>`、`…` 等占位符。
- 测试使用合成音频、假 `lark-cli`、假 ffmpeg 与本地 SSE 服务。

初始化仓库后执行 `git ls-files`：共 85 个受控文件，未包含 `.env`、
`config.toml`、`work/`、`archive/`、`minutes/`、`output/` 或状态备份。
gitleaks 对初始提交执行历史扫描，结果为 `no leaks found`。

## 4. 测试与覆盖率

```text
ruff format --check src tests examples   63 files already formatted
ruff check .                             All checks passed
mypy src                                 Success: no issues found in 35 source files
pytest                                   96 passed
coverage                                 85.84%（门槛 80%）
```

CI 已配置 Ubuntu 与 macOS、Python 3.10–3.13 矩阵，以及示例插件发现与 gitleaks
任务。远程 CI 尚未运行，首次 push 后以 CI 结果为准。

## 5. 重复执行不产生重复成稿

- `tests/integration/test_archive.py::test_reorganize_is_idempotent`：连续两次
  `organize` 后目录与文件命名不变。
- `tests/unit/test_transcribe.py::test_transcribes_slices_and_caches`：第二次
  转写全部命中切片缓存，不再请求 ASR。
- `tests/integration/test_discover_download.py::test_download_records_no_audio_and_reuses_files`：
  已有音频直接复用。
- `discover` 会排除归档文档、已下载音频、队列 token 与终态条目。

## 6. 失败不破坏产物与重跑

- `tests/unit/test_state.py::test_save_is_atomic_and_versioned`：临时文件 +
  `fsync` + `os.replace`。
- `tests/unit/test_state.py::test_corrupt_file_is_backed_up`：损坏状态改名备份，
  不中断运行。
- 切片缓存使失败重跑只请求缺失片段；归档改名与移动都先写临时名再原子替换。
- v0.1 移除了无法在内存上下文之外正确恢复的 `--resume`；重跑 `fmk run` 即可，
  已完成的下载、切片与归档会被复用。

## 剩余发布动作

- [x] 版本号更新为 `0.1.0`
- [x] CHANGELOG 覆盖九步、Provider、插件 API、CLI、文档、CI 与安全
- [x] 离线验收项执行并记录
- [ ] 真实妙记端到端联调（需要授权环境）
- [ ] 远程 CI 首次运行
- [x] `git init`、初始提交与本地 `v0.1.0` 标签（未添加远端、未推送）
