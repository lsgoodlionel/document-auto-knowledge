# 可并行开发子任务

这些任务可以拆给多个窗口同时做。建议每个窗口只负责自己的文件范围，减少冲突。

## 窗口 A：后端 API 完整化

负责文件：

- `backend/server.py`
- `backend/services/projects.py`
- `backend/db.py`

任务：

- 补充节点移动和排序接口
- 增加项目重命名、删除项目接口
- 统一 API 错误格式
- 增加基础单元测试或接口 smoke test

验收：

- 能用 API 完成项目创建、节点增删改查、导出 Word
- 数据库重启后数据仍存在

## 窗口 B：知识网络编辑器接入数据库

负责文件：

- `frontend/editor.js`
- `frontend/editor.html`

任务：

- 编辑器打开时根据 `projectId` 调用 `GET /api/projects/{id}`
- 保存节点时调用 `PUT /api/nodes/{id}`
- 新增子节点和同级节点时调用 `POST /api/projects/{id}/nodes`
- 删除节点时调用 `DELETE /api/nodes/{id}`

验收：

- 刷新页面后，节点修改仍保留
- 多次打开同一个项目时显示数据库中的最新结构

## 窗口 C：前端项目列表与入口页

负责文件：

- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`

任务：

- 首页展示历史项目列表
- 点击历史项目直接打开知识网络
- 上传 Word 后创建新项目并自动进入编辑器
- 增加加载、错误、空状态提示

验收：

- 用户可以不重新上传 Word，直接继续编辑历史项目

## 窗口 D：Word 导入导出质量

负责文件：

- `backend/services/docx_parser.py`
- `backend/services/docx_exporter.py`

任务：

- 导入时保留标题下正文为节点 note
- 支持更多 Word 标题样式名称
- 导出时优化标题字号、段落间距、中文字体
- 增加导出目录或大纲级别

验收：

- 导入原 Word 后再导出，目录层级和正文信息尽量完整

## 窗口 E：本地部署与安装包

负责文件：

- `build_release.py`
- `scripts/`
- `.github/workflows/release.yml`
- `README.md`

任务：

- 更新安装包，让 mac/windows/ubuntu 启动后运行 `python3 run.py`
- 检查 Python 版本和端口占用提示
- GitHub Actions 构建三端 zip
- 产物中包含数据库目录和启动说明

验收：

- 三个系统解压后能一键启动 Web 应用

## 推荐开发顺序

1. 窗口 A 先补齐后端节点 CRUD。
2. 窗口 B 接入 CRUD，让编辑器真正持久化。
3. 窗口 C 做项目列表和用户入口。
4. 窗口 D 提升 Word 导入导出质量。
5. 窗口 E 最后收安装包和发布。
