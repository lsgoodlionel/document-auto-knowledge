# 前后端分离架构

## 目标形态

当前工程升级为本地 Web 应用：

- `frontend/`：静态前端页面，负责上传、目录预览、知识网络编辑交互
- `backend/`：Python 标准库 HTTP API，负责 Word 解析、SQLite 持久化、Word 导出
- `data/`：本地 SQLite 数据库目录
- `run.py`：统一启动入口

## 数据模型

`projects`

- `id`：项目 ID
- `name`：项目名称，通常来自 Word 文件名
- `created_at`：创建时间
- `updated_at`：更新时间

`nodes`

- `id`：节点 ID
- `project_id`：所属项目
- `parent_id`：父节点，根节点为空
- `title`：节点标题
- `note`：节点关联文本
- `position`：同级排序
- `created_at`：创建时间
- `updated_at`：更新时间

## API 草案

- `GET /api/projects`：项目列表
- `POST /api/projects/import-docx`：上传 Word，解析目录并创建项目
- `GET /api/projects/{id}`：读取项目和节点树
- `POST /api/projects/{id}/nodes`：新增节点
- `PUT /api/nodes/{id}`：更新节点标题和文本
- `DELETE /api/nodes/{id}`：删除节点及其子节点
- `GET /api/projects/{id}/export`：按当前节点树导出新的 Word

## 当前迁移状态

- 后端 API 与 SQLite 表结构已建立
- HTTP 模式下，`frontend/app.js` 会优先调用后端导入接口
- 直接打开 HTML 时，仍保留前端离线解析能力
- 知识网络编辑器目前仍以浏览器状态为主，后续需要接入节点 CRUD API
