# 持续开发与上下文交接机制

这份文档定义本项目长期开发时的固定工作方式。目标是在单个对话窗口上下文接近上限时，能稳定交接到新窗口继续开发，不丢任务、不丢决策、不丢验证状态。

## 触发条件

当当前对话窗口的 258k token 使用量接近 90% 时，必须暂停新增大功能，开始执行“交接收口流程”。

可执行判断：

- 如果系统或界面显示 token 使用率达到 90% 左右，立即执行交接。
- 如果没有精确显示，但对话已经很长、代码变更很多、开始担心上下文丢失，也提前执行交接。
- 不等到 100%，避免最后来不及整理。

## 交接收口流程

1. 停止启动新的大范围改造。
2. 跑基础验证：

```bash
PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile run.py backend/server.py backend/db.py backend/config.py backend/services/docx_parser.py backend/services/docx_exporter.py backend/services/projects.py
node --check frontend/app.js
node --check frontend/editor.js
python3 scripts/context_snapshot.py
```

3. 查看 Git 状态：

```bash
git status --short
git branch -vv
git log --oneline --decorate --all --max-count=12
```

4. 更新 [PROJECT_STATE.md](/Users/lionel/Documents/Codex/2026-04-20-word/docs/PROJECT_STATE.md:1)。
5. 如有代码改动，提交一个清晰的 checkpoint commit。
6. 在最终回复里给新窗口提供：

- 当前目标
- 已完成内容
- 未完成内容
- 当前分支
- 最近提交
- 关键文件
- 验证结果
- 下一步建议

## 新窗口启动流程

新窗口开始时先读这些文件：

1. [README.md](/Users/lionel/Documents/Codex/2026-04-20-word/README.md:1)
2. [docs/PROJECT_STATE.md](/Users/lionel/Documents/Codex/2026-04-20-word/docs/PROJECT_STATE.md:1)
3. [docs/PARALLEL_TASKS.md](/Users/lionel/Documents/Codex/2026-04-20-word/docs/PARALLEL_TASKS.md:1)
4. [docs/ARCHITECTURE.md](/Users/lionel/Documents/Codex/2026-04-20-word/docs/ARCHITECTURE.md:1)

然后运行：

```bash
git status --short
git branch -vv
python3 scripts/context_snapshot.py
```

## 分支策略

当前项目有 5 个并行任务分支：

- `窗口A：后端API完整化`
- `窗口B：知识网络编辑器接入数据库`
- `窗口C：前端项目列表与入口页`
- `窗口D：Word导入导出质量提升`
- `窗口E：本地部署与安装包`

建议：

- 每个窗口只切到自己的分支工作。
- 多窗口同步开发时，优先使用不同工作目录或 `git worktree`，避免一个目录频繁切分支。
- 每个窗口提交前必须跑自己模块相关验证。
- 合并回 `main` 前先记录变更和风险。

## 端口策略

多个窗口同时启动服务时使用不同端口：

```bash
PORT=8001 python3 run.py
PORT=8002 python3 run.py
PORT=8003 python3 run.py
```

## 固定交接输出模板

交接时使用这个结构：

```text
当前状态：
- 分支：
- 最近提交：
- 工作区是否干净：

已完成：
- 

未完成：
- 

验证结果：
- 

风险/注意：
- 

下一窗口建议：
- 
```

