# V3.0 并行开发子任务

V3.0 目标是在现有 V2 主线基础上，升级为带统一导航、用户登录和更完整思维导图交互能力的“文档自动知识库系统”。

## 总体需求

1. 给页面增加统一导航栏。
2. 增加用户登录模块。
3. 网页名称调整为“文档自动知识库系统”。
4. 在当前“打开知识网络”基础上，大幅升级思维导图建立、编辑、删除、拖拽、绘制和节点管理能力。

## 统一开发规则

- 所有 V3 分支都从最新 `origin/v3-main` 创建。
- 每个窗口尽量只修改自己负责的文件范围。
- 完成后提交到各自分支，不直接合并 `v3-main`。
- 完成消息必须包含：分支名、提交号、修改文件、验证命令、已知风险。
- `dist/`、`data/` 不提交。
- 如果需要新增第三方依赖，先在文档中说明原因、用途和平台影响。

## 窗口 V3-A：导航栏与品牌壳层

建议分支：`v3/A-nav-shell-branding`

负责范围：

- `frontend/index.html`
- `frontend/styles.css`
- 新增 `frontend/common-nav.js` 或 `frontend/common-shell.js`
- `README.md`

任务：

- 全站统一名称改为“文档自动知识库系统”。
- 首页引入统一导航栏。
- 为登录入口、用户菜单、知识网络入口预留导航位。
- 抽取共享标题、导航样式、基础页头结构。

验收：

- 首页标题、页头、品牌名一致。
- `node --check frontend/app.js` 通过。

## 窗口 V3-B：登录后端与会话基础

建议分支：`v3/B-auth-backend-session`

负责范围：

- `backend/db.py`
- `backend/server.py`
- 新增 `backend/services/auth.py`
- `tests/`

任务：

- 增加用户与会话基础模型。
- 提供 `login / logout / me` API。
- 兼容本地运行模式，先做单机可用版本。
- 为项目归属用户预留字段或兼容入口。

验收：

- 能完成登录、退出、当前用户读取。
- 新增 smoke test 通过。

## 窗口 V3-C：登录前端与鉴权流

建议分支：`v3/C-auth-frontend-flow`

负责范围：

- 新增 `frontend/login.html`
- 新增 `frontend/auth.js`
- `frontend/app.js`
- 可按需要新增 `frontend/common-auth.js`

任务：

- 增加登录页。
- 首页接入当前用户状态。
- 未登录时显示登录入口，已登录时显示用户菜单。
- 基础处理会话失效、未登录跳转和用户状态展示。

验收：

- 登录后首页状态变化正确。
- 退出后状态恢复未登录。

## 窗口 V3-D：思维导图后端模型与 API

建议分支：`v3/D-mindmap-backend-api`

负责范围：

- `backend/db.py`
- `backend/server.py`
- `backend/services/projects.py`
- 新增 `backend/services/mindmap.py`
- `tests/`

任务：

- 增加思维导图节点附加属性，例如坐标、折叠、样式。
- 增加边、关联关系或主题线模型。
- 支持批量保存和节点/边更新。
- 为未来撤销/重做预留版本或快照结构。

验收：

- API 可以保存和读取增强后的思维导图结构。
- 不破坏现有项目树导入、编辑和导出流程。

## 窗口 V3-E：思维导图编辑器大升级

建议分支：`v3/E-mindmap-editor-upgrade`

负责范围：

- `frontend/editor.html`
- `frontend/editor.js`
- `frontend/styles.css`

任务：

- 将现有编辑器升级为思维导图式交互。
- 支持节点创建、删除、同级/子级新增、拖拽、折叠、选中、属性编辑。
- 支持画布平移、缩放和关系线展示。
- 保持正文 `note`、导出面板和历史项目打开逻辑不退化。

验收：

- 可以像基础思维导图工具一样进行节点管理。
- 打开现有项目不会丢失原树结构。

## 窗口 V3-F：文档、测试与发布收口

建议分支：`v3/F-docs-tests-release`

负责范围：

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/V3_PLAN.md`
- `docs/V3_PARALLEL_TASKS.md`
- 需要时更新 `build_release.py`

任务：

- 更新 V3 功能文档、安装说明和测试说明。
- 为新增登录与导航栏补文档。
- 为思维导图升级补测试清单和发布说明。

验收：

- 文档内容与实际代码状态一致。
- `git diff --check` 通过。

## 集成窗口操作说明

所有子任务完成后，在协调窗口执行：

```bash
cd /Users/lionel/Documents/Codex/2026-04-20-word
git fetch origin
git switch v3-main
git pull --ff-only origin v3-main
git switch -c v3/integration
```

建议按顺序合并：

```bash
git merge --no-ff v3/A-nav-shell-branding
git merge --no-ff v3/B-auth-backend-session
git merge --no-ff v3/C-auth-frontend-flow
git merge --no-ff v3/D-mindmap-backend-api
git merge --no-ff v3/E-mindmap-editor-upgrade
git merge --no-ff v3/F-docs-tests-release
```

每合并一个分支后至少运行：

```bash
PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile run.py backend/server.py backend/db.py backend/services/projects.py tests/smoke_api.py
python3 -m unittest tests.smoke_api
node --check frontend/app.js
node --check frontend/editor.js
git diff --check
```

最终合入主线：

```bash
git switch v3-main
git merge --no-ff v3/integration
git push origin v3-main
```
