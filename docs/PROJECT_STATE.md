# 项目状态快照

最后更新：2026-04-20

## 项目目标

把 Word 文档的大纲和标题结构转换成可编辑的知识网络，并支持：

- 目录树生成
- 知识网络图形化编辑
- 节点文本信息维护
- SQLite 持久化
- 反向导出新的 Word
- mac / Windows / Ubuntu 本地部署

## 当前架构

- `backend/`：Python 标准库 HTTP API，SQLite 数据库，Word 导入导出服务
- `frontend/`：前端静态页面，HTTP 模式优先调用后端 API
- `data/`：本地 SQLite 数据目录，已加入忽略规则
- `docs/`：架构说明、并行任务拆分、上下文交接机制
- `scripts/`：三端启动脚本
- `run.py`：新版应用入口
- `web/` 和 `app.py`：旧版兼容入口，暂时保留

## 当前 Git 状态

当前基线提交：

```text
62891da Connect editor to project API
```

当前并行分支：

- `main`
- `窗口A：后端API完整化`
- `窗口B：知识网络编辑器接入数据库`
- `窗口C：前端项目列表与入口页`
- `窗口D：Word导入导出质量提升`
- `窗口E：本地部署与安装包`

当前状态：

- `main` 已合并窗口 A 和窗口 B。
- `窗口A：后端API完整化` 停在自身完成提交 `0b3be3a`。
- `窗口B：知识网络编辑器接入数据库` 停在自身完成提交 `62891da`。
- `窗口C/D/E` 已同步到 `62891da`，可继续开发。

## 已验证内容

- Python 后端模块编译通过
- `frontend/app.js` 语法检查通过
- `frontend/editor.js` 语法检查通过
- SQLite 初始化通过
- Word 导入到项目通过
- 项目树读取通过
- 节点新增、更新、删除通过
- Word 导出 smoke test 通过
- 服务支持通过 `PORT=xxxx python3 run.py` 指定端口
- 窗口 A 后端 API smoke test 通过
- 窗口 B 编辑器接入数据库基础验证通过

## 当前限制

- 首页还没有完整历史项目列表。
- Word 导入暂未把标题下正文完整归入节点 note。
- 安装包需要跟随新版后端服务启动方式继续打磨。
- 本地 `main` 比 `origin/main` 超前 4 个提交，需要后续推送。

## 下一步建议

优先顺序：

1. 窗口 C 做首页历史项目列表和项目入口。
2. 窗口 D 提升 Word 正文导入和导出样式。
3. 窗口 E 更新安装包和 GitHub Actions。
