# 文档自动知识库系统

Document Auto Knowledge System

把文档的大纲、标题、正文和章节结构转换成可编辑的知识网络，并支持统一导入、历史项目沉淀、多格式导出和后续知识编辑。

## 当前能力

- 上传 `.docx`、`.pdf`、`.epub`、`.azw3`、`.png`、`.jpg`、`.jpeg`、`.xlsx`、`.xls`、`.csv`、`.mm`、`.xmind` 文档
- 通过统一导入入口分发不同格式解析器，并把结果落库到 SQLite
- Word `.docx` 支持识别标题样式、段落大纲级别，并把标题后的正文归入对应节点 `note`
- EPUB 会按 NCX / EPUB3 nav 目录导入章节；没有目录时按 spine 顺序兜底，并把章节 HTML 文本写入 `note`
- PDF 会尽量提取可选中文本，并按标题线索生成层级
- CSV 会按文件名生成表节点，按每行第一列生成子节点，并把列标题和值写入 `note`
- FreeMind `.mm` 会保留思维导图层级和节点说明
- 图片可作为带来源信息的单节点项目导入；OCR 入口已预留，未配置时会返回明确提示
- `.azw3` 已接入格式识别，当前返回需要先转换为 EPUB 或安装 Calibre `ebook-convert` 的能力提示
- `.xmind` 已接入格式识别，当前返回明确的未支持提示
- 导入后生成目录树、历史项目列表和知识网络编辑入口
- 首页引入统一导航壳层，并为登录入口、用户菜单、知识网络入口预留位置
- 知识网络左侧结构树支持显示级别切换：`1-2 级 / 1-3 级 / 全部`
- 左侧结构树支持展开同级、收起同级，并在大项目中自动保护首屏渲染
- 目录总览与关系视图共享同一选中状态，点击任意节点会同步更新右侧节点编辑区
- 节点可维护标题、正文 `note`、上下级关系和同级顺序
- 支持跨项目挂接：把一个项目的根节点或整棵根级树挂到另一个项目节点下
- 导出面板支持导出 `Word / PDF / MM / 图片`
- 导出 Word 支持中文文件名、标题样式、大纲级别、中文字体和基础段落样式
- 导入失败时显示后端返回的错误码和说明
- 支持前后端分离目录结构，本地一键启动

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

首页会显示统一品牌名“文档自动知识库系统”和 V3 导航栏。当前导航已经预留“登录入口”“用户菜单”“知识网络”等位置，后续窗口会继续接入真实登录与用户状态。

首页可以直接选择支持格式中的任意文件，上传区会列出当前前端接受的扩展名。Word `.docx` 支持离线浏览器解析；PDF、电子书、图片、Excel、思维导图等格式需要通过本地服务导入，暂未支持或缺少依赖时会在页面上显示后端返回的结构化错误。

推荐验证主流程：

1. 在首页上传文档并等待项目创建成功
2. 点击“进入知识网络”或在“历史项目”里直接打开项目
3. 在编辑器中查看左侧目录、关系视图和右侧节点正文
4. 按需要修改节点、挂接其他项目，再从顶部导出文件

说明：

- 首页“打开知识网络”现在统一跳转到独立的 `editor.html` 页面，不再使用旧的页面内注入方式
- 如果是数据库项目，会优先通过 `editor.html?projectId=...` 加载
- 如果是离线临时树，会通过 `sessionStorage` 把当前树传入编辑器页

如果多个窗口并行开发导致端口冲突，可以指定不同端口：

```bash
PORT=8001 python3 run.py
```

也可以使用脚本：

- mac：`scripts/start-mac.command`
- Ubuntu：`scripts/start-ubuntu.sh`
- Windows：`scripts/start-windows.bat`

启动脚本会检查 Python 版本、默认端口 `8000` 是否可用，并在启动时显示访问地址。项目需要 Python 3.10 或更高版本。

## 构建安装包

生成 mac / Windows / Ubuntu 三端 zip：

```bash
python3 build_release.py
```

产物会输出到 `dist/`：

- `knowledge-network-local-mac.zip`
- `knowledge-network-local-windows.zip`
- `knowledge-network-local-ubuntu.zip`

每个安装包都包含 `backend/`、`frontend/`、`docs/`、`scripts/`、`data/`、`run.py` 和 `README.md`。解压后使用根目录的启动文件：

- mac：双击 `start.command`
- Windows：双击 `start.bat`
- Ubuntu：运行 `chmod +x start.sh && ./start.sh`

默认访问地址是 `http://127.0.0.1:8000`。如果端口被占用，可以指定其他端口，例如：

```bash
PORT=8001 ./start.sh
```

## API 概览

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

`POST /api/projects/import` 根据文件扩展名分发解析器，请求体与旧 Word 入口一致：

```json
{
  "filename": "example.csv",
  "file": "base64-encoded-content"
}
```

当前结构化导入状态：

- `.epub`：可用。优先读取 NCX / EPUB3 nav 目录，保留章节顺序和层级，章节 HTML 正文会转为纯文本写入 note。
- `.azw3`：入口可识别，但标准库版本暂不直接解析；建议先用 Calibre 转为 EPUB，或后续安装 `ebook-convert` 后接入转换式 importer。
- `.csv`：可用。第一行为列标题，后续行生成节点，行内容写入 note。
- `.mm`：可用。解析 FreeMind XML 中的 `node TEXT` 层级，并读取常见 NOTE 富文本。
- `.xmind`：入口可识别，但暂不完整解析；API 会返回 `unsupported_format` 和迁移建议。
- `.xlsx` / `.xls`：入口可识别，但当前建议另存为 `.csv` 后导入。

当前导出状态：

- `docx`：可用，保留标题层级和节点正文 `note`
- `pdf`：可用，当前为基础结构化导出版本
- `mm`：可用，导出为 FreeMind XML
- `png`：可用，当前为基础结构图像导出版本

`GET /api/projects/{id}/export` 支持格式参数，例如：

```text
/api/projects/11/export?format=docx
/api/projects/11/export?format=pdf
/api/projects/11/export?format=mm
/api/projects/11/export?format=png
```

跨项目挂接接口：

```json
POST /api/projects/{id}/attachments
{
  "targetParentId": 123,
  "sourceProjectId": 456,
  "sourceRootNodeId": 789
}
```

说明：

- `sourceRootNodeId` 省略时，会把来源项目的全部根节点挂到目标节点下
- 目前挂接采用“复制并保留来源标识”的方式，不直接跨项目移动原节点
- 返回树中会保留 `sourceProjectId`、`sourceProjectName`、`sourceNodeId`、`linkedCopy`

更多说明见：

- [docs/ARCHITECTURE.md](/Users/lionel/Documents/Codex/2026-04-20-word/docs/ARCHITECTURE.md:1)
- [docs/PARALLEL_TASKS.md](/Users/lionel/Documents/Codex/2026-04-20-word/docs/PARALLEL_TASKS.md:1)
- [docs/CONTINUITY_PROTOCOL.md](/Users/lionel/Documents/Codex/2026-04-20-word/docs/CONTINUITY_PROTOCOL.md:1)
- [docs/PROJECT_STATE.md](/Users/lionel/Documents/Codex/2026-04-20-word/docs/PROJECT_STATE.md:1)
- [docs/V2_PLAN.md](/Users/lionel/Documents/Codex/2026-04-20-word/docs/V2_PLAN.md:1)
- [docs/V2_PARALLEL_TASKS.md](/Users/lionel/Documents/Codex/2026-04-20-word/docs/V2_PARALLEL_TASKS.md:1)

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

## 当前阶段

V1.0 基础目录解析、知识网络编辑、Word 导出和本地安装包已完成。

V2.0 已完成第一阶段：

- 多格式导入框架
- 节点正文 `note` 入库与编辑
- 左侧目录显示级别控制
- 多格式导出基础框架

V2.1 已完成并合入主线：

- 目录总览与关系视图选中状态统一
- 跨项目手动挂接上下级
- 导出面板升级为 `Word / PDF / MM / 图片`
- 编辑器页统一使用独立页面跳转方式

后续继续开发时，请先阅读 [docs/V2_PLAN.md](/Users/lionel/Documents/Codex/2026-04-20-word/docs/V2_PLAN.md:1) 和 [docs/V2_PARALLEL_TASKS.md](/Users/lionel/Documents/Codex/2026-04-20-word/docs/V2_PARALLEL_TASKS.md:1)。
