# 当前架构说明

本文描述的是当前 `v3-main` 基线已经落地的结构，而不是 V3 目标态的全部功能。

## 1. 运行形态

当前工程是一个本地 Web 应用，分成三层：

- `frontend/`：静态页面与浏览器交互逻辑
- `backend/`：Python 标准库 HTTP API、导入导出服务、SQLite 访问
- `data/`：本地 SQLite 数据库目录

统一入口是 [run.py](/Users/lionel/Documents/Codex/2026-04-20-word/run.py:1)。服务启动后同时承担 API 和静态资源分发。

## 2. 前端页面

### 首页

[frontend/index.html](/Users/lionel/Documents/Codex/2026-04-20-word/frontend/index.html:1) + [frontend/app.js](/Users/lionel/Documents/Codex/2026-04-20-word/frontend/app.js:1)

当前职责：

- 选择文件并发起导入
- 展示识别后的目录树和标题列表
- 显示历史项目
- 生成 Bash / PowerShell 目录创建脚本
- 跳转到知识网络编辑器

运行模式：

- HTTP 模式下优先调用后端导入接口
- 直接打开 HTML 文件时仅保留 `.docx` 的浏览器本地解析兜底

### 编辑器页

[frontend/editor.html](/Users/lionel/Documents/Codex/2026-04-20-word/frontend/editor.html:1) + [frontend/editor.js](/Users/lionel/Documents/Codex/2026-04-20-word/frontend/editor.js:1)

当前职责：

- 展示目录总览、关系视图和节点编辑区
- 支持节点新增、更新、删除、移动顺序
- 支持左侧结构树级别切换与同级展开/收起
- 支持跨项目挂接
- 支持 `docx / pdf / mm / png` 导出

当前限制：

- 还不是完整思维导图画布
- 没有统一导航栏
- 没有登录态和用户菜单
- 还没有拖拽布局、缩放、连线编辑等 V3 目标能力

## 3. 后端 API

[backend/server.py](/Users/lionel/Documents/Codex/2026-04-20-word/backend/server.py:1) 使用 `ThreadingHTTPServer` 提供本地 API。

### 已实现接口

- `GET /api/projects`
- `POST /api/projects/import`
- `POST /api/projects/import-docx`
- `GET /api/projects/{id}`
- `PUT /api/projects/{id}`
- `DELETE /api/projects/{id}`
- `POST /api/projects/{id}/attachments`
- `POST /api/projects/{id}/nodes`
- `PUT /api/nodes/{id}`
- `PUT /api/nodes/{id}/move`
- `DELETE /api/nodes/{id}`
- `GET /api/projects/{id}/export`

### 错误模型

API 统一返回：

```json
{
  "error": {
    "code": "bad_request",
    "message": "..."
  }
}
```

导入器和导出器通过自定义异常把 `code / message / status` 透传到前端。

## 4. 当前数据模型

SQLite 表定义在 [backend/db.py](/Users/lionel/Documents/Codex/2026-04-20-word/backend/db.py:1)。

### `projects`

- `id`
- `name`
- `created_at`
- `updated_at`

### `nodes`

- `id`
- `project_id`
- `parent_id`
- `title`
- `note`
- `source_type`
- `metadata`
- `position`
- `created_at`
- `updated_at`

说明：

- 当前“跨项目挂接来源信息”主要通过节点 `metadata` 和树组装逻辑暴露给前端
- 当前还没有用户表、会话表，也没有思维导图专用坐标、折叠、边关系等模型

## 5. 服务分层

### 项目与节点服务

[backend/services/projects.py](/Users/lionel/Documents/Codex/2026-04-20-word/backend/services/projects.py:1)

负责：

- 创建项目
- 组装节点树
- 节点 CRUD
- 节点排序与移动
- 跨项目挂接复制

### 导入服务

[backend/services/importers.py](/Users/lionel/Documents/Codex/2026-04-20-word/backend/services/importers.py:1)

当前导入入口根据文件扩展名分发到：

- Word：`docx_parser.py`
- PDF：`pdf_parser.py`
- EPUB / AZW3：`ebook_parser.py`
- Excel / CSV：`excel_parser.py`
- 图片：`image_parser.py`
- FreeMind / XMind：`mindmap_parser.py`

### 导出服务

[backend/services/exporters.py](/Users/lionel/Documents/Codex/2026-04-20-word/backend/services/exporters.py:1)

当前通过注册表选择导出器：

- `docx`
- `pdf`
- `mm`
- `png`

其中：

- Word 导出由 [backend/services/docx_exporter.py](/Users/lionel/Documents/Codex/2026-04-20-word/backend/services/docx_exporter.py:1) 负责
- PNG 导出当前依赖平台可用的图像生成能力，不是完全跨平台纯 Python 方案

## 6. 当前数据流

### 导入

1. 前端读取文件
2. HTTP 模式下调用 `POST /api/projects/import`
3. 后端分发解析器
4. 解析结果写入 SQLite
5. 前端收到 `projectId` 和项目树后进入编辑器

### 编辑

1. 编辑器通过 `GET /api/projects/{id}` 读取完整项目树
2. 左侧结构树、关系视图和编辑区共享同一选中节点
3. 节点变更通过 `/api/nodes/*` 和 `/api/projects/{id}/nodes`
4. 跨项目挂接通过 `/api/projects/{id}/attachments`

### 导出

1. 编辑器选择导出格式
2. HTTP 模式下请求 `/api/projects/{id}/export?format=...`
3. 后端调用导出注册表生成文件
4. 浏览器下载返回的二进制数据

## 7. V3 规划与当前基线的边界

V3 目标中提到的以下能力目前还没有合入当前主线：

- 统一导航与品牌壳层
- 用户登录、退出、当前用户接口
- 项目归属用户和权限边界
- 思维导图画布坐标、折叠状态、边模型
- 节点拖拽、缩放、连线编辑

这些能力的设计与拆分见：

- [docs/V3_PLAN.md](/Users/lionel/Documents/Codex/2026-04-20-word/docs/V3_PLAN.md:1)
- [docs/V3_PARALLEL_TASKS.md](/Users/lionel/Documents/Codex/2026-04-20-word/docs/V3_PARALLEL_TASKS.md:1)

因此，阅读和修改代码时要把“当前已实现架构”和“V3 目标架构”分开理解，避免把规划文档中的字段和 API 当成已经存在的实现。
