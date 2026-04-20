# 项目状态快照

最后更新：2026-04-20

## 当前阶段

V1.0 基本功能开发完成，当前窗口进入归档交接状态。后续原则上不再使用本旧窗口继续开发，V2.0 开发应从新 Codex 窗口接手。

## V1.0 已完成能力

- 上传 `.docx` 文档
- 识别 Word 标题样式、中文标题样式和段落大纲级别
- 将标题结构转换为目录树和知识网络
- 将标题下正文归入对应节点 note
- 首页显示历史项目列表
- 点击历史项目进入知识网络
- 知识网络编辑器接入数据库 CRUD
- 节点新增、编辑、删除、移动和排序
- SQLite 本地持久化
- 反向导出新的 Word
- 导出 Word 支持中文文件名
- 导出 Word 包含标题样式、大纲级别、中文字体和基础段落样式
- mac / Windows / Ubuntu 三端本地安装包构建
- GitHub Actions 自动构建三端 zip
- GitHub Release `v0.1.0` 已发布

## 当前架构

- `backend/`：Python 标准库 HTTP API，SQLite 数据库，Word 导入导出服务
- `frontend/`：前端静态页面，HTTP 模式优先调用后端 API
- `data/`：本地 SQLite 数据目录，已加入忽略规则
- `docs/`：架构说明、并行任务拆分、上下文交接机制
- `scripts/`：三端启动脚本
- `run.py`：新版应用入口
- `web/` 和 `app.py`：旧版兼容入口，暂时保留
- `dist/`：本地构建产物目录，已从 Git 跟踪中移除，只由 `build_release.py` 或 GitHub Actions 生成

## 当前 Git / GitHub 状态

当前 `main` 基线提交：

```text
0c4fdd1 Stop tracking generated dist files
```

远端状态：

```text
main == origin/main
```

重要发布信息：

- GitHub 仓库：`https://github.com/lsgoodlionel/document-auto-knowledge`
- GitHub Actions 最新成功运行：`https://github.com/lsgoodlionel/document-auto-knowledge/actions/runs/24654050605`
- GitHub Release：`https://github.com/lsgoodlionel/document-auto-knowledge/releases/tag/v0.1.0`
- Release 产物：
  - `knowledge-network-local-mac.zip`
  - `knowledge-network-local-ubuntu.zip`
  - `knowledge-network-local-windows.zip`

## 历史并行任务分支

V1.0 并行任务已完成并合入主线：

- `窗口A：后端API完整化`：`0b3be3a Complete backend API endpoints`
- `窗口B：知识网络编辑器接入数据库`：`62891da Connect editor to project API`
- `窗口C：前端项目列表与入口页`：`110c7b7 Add project list entry page`
- `窗口D：Word导入导出质量提升`：`b150eaa Improve Word import export fidelity`
- `窗口E：本地部署与安装包`：`b463da7 Fix non-ASCII export filenames`

这些分支只作为 V1.0 历史记录保留。V2.0 建议新建 `v2-main` 或 `v2/*` 系列分支。

## 已验证内容

- Python 后端模块编译通过
- `frontend/app.js` 语法检查通过
- `frontend/editor.js` 语法检查通过
- `tests.smoke_api` 通过，当前 5 个 smoke tests
- SQLite 初始化通过
- Word 导入到项目通过
- 标题下正文归入 note 通过
- 项目树读取通过
- 节点新增、更新、删除、移动排序通过
- Word 导出 smoke test 通过
- 中文文件名导出 header 修复通过
- 三端安装包构建通过
- `dist/` 已确认不再被 Git 跟踪
- GitHub Actions 在不提交 `dist/` 的情况下成功构建安装包

## 当前注意事项

- `gh auth status` 曾显示本机 GitHub CLI token 失效，但 `git push` 和 `gh release create` 在本机凭据下成功过；新窗口如需操作 GitHub，先检查认证。
- `dist/` 本地可能仍存在，但应保持 ignored，不要提交。
- `data/` 本地数据库目录为运行数据，应保持 ignored，不要提交。
- 旧版 `web/` 和 `app.py` 仍保留，V2.0 可评估是否删除或迁移为兼容模式。
- 当前窗口 token 已接近上限，后续开发请迁移到新窗口。

## V2.0 起点

V2.0 请从 [docs/V2_PLAN.md](/Users/lionel/Documents/Codex/2026-04-20-word/docs/V2_PLAN.md:1) 开始。
