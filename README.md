# Document Knowledge Network

把 Word 文档的大纲和标题结构转换成可编辑的知识网络，并支持反向导出新的 Word。

## 当前能力

- 上传 `.docx` 文档
- 识别 Word 标题样式和段落大纲级别
- 生成目录树和知识网络
- 节点可维护标题、上下级关系和说明文本
- 可反向导出新的 Word 文档
- 后端使用 SQLite 持久化项目和节点
- 支持前后端分离目录结构

## 新工程结构

```text
backend/              Python 后端 API、SQLite 数据库访问、Word 解析导出服务
frontend/             独立静态前端页面
data/                 SQLite 数据库文件目录
docs/                 架构说明与并行任务拆分
scripts/              mac / windows / ubuntu 启动脚本
web/                  旧版离线前端，保留兼容
run.py                新版前后端分离应用启动入口
app.py                旧版单文件服务入口，保留兼容
build_release.py      安装包构建脚本
```

## 本地运行

推荐运行新版应用：

```bash
python3 run.py
```

然后打开：

```text
http://127.0.0.1:8000
```

如果多个窗口并行开发导致端口冲突，可以指定不同端口：

```bash
PORT=8001 python3 run.py
```

也可以使用脚本：

- mac：`scripts/start-mac.command`
- Ubuntu：`scripts/start-ubuntu.sh`
- Windows：`scripts/start-windows.bat`

## API 概览

- `GET /api/projects`
- `POST /api/projects/import-docx`
- `GET /api/projects/{id}`
- `POST /api/projects/{id}/nodes`
- `PUT /api/nodes/{id}`
- `DELETE /api/nodes/{id}`
- `GET /api/projects/{id}/export`

更多说明见：

- [docs/ARCHITECTURE.md](/Users/lionel/Documents/Codex/2026-04-20-word/docs/ARCHITECTURE.md:1)
- [docs/PARALLEL_TASKS.md](/Users/lionel/Documents/Codex/2026-04-20-word/docs/PARALLEL_TASKS.md:1)
- [docs/CONTINUITY_PROTOCOL.md](/Users/lionel/Documents/Codex/2026-04-20-word/docs/CONTINUITY_PROTOCOL.md:1)
- [docs/PROJECT_STATE.md](/Users/lionel/Documents/Codex/2026-04-20-word/docs/PROJECT_STATE.md:1)

## 并行开发建议

可以按以下方向拆给多个窗口同步开发：

- 后端 API 完整化
- 知识网络编辑器接入数据库
- 前端项目列表与入口页
- Word 导入导出质量提升
- 本地部署与安装包

详细拆分见 [docs/PARALLEL_TASKS.md](/Users/lionel/Documents/Codex/2026-04-20-word/docs/PARALLEL_TASKS.md:1)。

## 长上下文持续开发

当当前对话窗口 token 使用率接近 90% 时，执行交接流程：

```bash
python3 scripts/context_snapshot.py
```

然后更新 [docs/PROJECT_STATE.md](/Users/lionel/Documents/Codex/2026-04-20-word/docs/PROJECT_STATE.md:1)，并按照 [docs/CONTINUITY_PROTOCOL.md](/Users/lionel/Documents/Codex/2026-04-20-word/docs/CONTINUITY_PROTOCOL.md:1) 输出交接摘要。
