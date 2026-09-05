# AI Handoff

## 当前目标

按 README 为本机配置 uv 开发环境。

## 当前状态

已完成。

## 已完成内容

- 安装 uv 0.12.10，并确认新的 zsh 登录会话可从 `~/.local/bin/uv` 调用。
- 根据 `.python-version` 安装 CPython 3.12.14。
- 使用现有 `uv.lock` 执行 `uv sync`，创建 `.venv` 并安装 43 个依赖包。
- 验证锁文件、Python 版本、项目及主要依赖导入。

## 修改文件

- `docs/AI_HANDOFF.md`

## 架构决策

- 未修改项目架构或依赖定义；沿用 README、`.python-version` 和 `uv.lock`。

## 测试结果

- `uv sync --check`：通过，锁文件与环境一致。
- `uv run python -c 'import mybot'`：通过。
- `uv run --with pytest python -m pytest -q`：166 passed，3 skipped，20 subtests passed。

## 已知问题

- 本机尚未安装 Node.js、npm 和 `playwright-cli`，因此浏览器功能暂不可用。
- `config/config.json` 尚未创建；启动前需由用户复制示例并填写自己的 API Key。
- 项目位于外置磁盘，uv 无法 hardlink 缓存文件，已自动回退为复制；只影响首次同步性能。

## 下一步

- 复制 `config/config.example.json` 为 `config/config.json`，填写模型服务配置后运行 `uv run python mybot/main.py`。
- 如需浏览器功能，再安装 Node.js LTS 和 `@playwright/cli`。

## 不要重复进行的工作

- 无需重新创建 `.venv` 或重新下载 Python 3.12；直接使用 `uv sync` 保持环境同步。
