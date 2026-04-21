# V2.0 并行开发子任务

V2.0 目标是在 V1.0 的 Word 目录和知识网络基础上，升级为多格式文档导入、目录节点内容管理、知识网络分级浏览和可持续扩展的文档知识系统。

旧窗口只负责协调和最终集成。具体开发请在新 Codex 窗口中按下面子任务分别创建分支。

## 总体需求

1. 在原有 Word `.docx` 识别基础上，增加 PDF、EPUB、AZW3、图片、Excel、FreeMind `.mm`、XMind 导入。
2. 原来只生成目录，V2.0 要在每条目录节点下导入和维护对应正文内容。
3. 打开知识网络后，左侧结构树支持同级展开、按指定级别显示目录。
4. 子任务之间必须保持 API、数据结构和测试用例可集成。

## 统一开发规则

- 每个窗口只修改自己负责的文件范围，避免互相覆盖。
- 所有分支都从最新 `origin/main` 创建。
- 完成后提交到各自分支，不要直接合并 `main`。
- 完成消息必须写清楚提交号、修改文件、验证命令和已知限制。
- `dist/` 和 `data/` 不提交。
- 如果需要新增第三方依赖，先写入文档说明原因；V2.0 优先保持 Python 标准库可运行，确需依赖再统一评估。

## 窗口 V2-A：导入框架和统一数据模型

建议分支：`v2/A-import-foundation`

负责范围：

- `backend/server.py`
- `backend/services/projects.py`
- `backend/services/importers.py`
- `backend/services/docx_parser.py`
- `backend/db.py`
- `tests/`

任务：

- 设计统一导入结果结构，至少包含 `title`、`level`、`note`、`children`、`source_type`、`metadata`。
- 将现有 Word 导入适配到统一结构。
- 后端上传接口支持根据文件扩展名选择 importer。
- 数据库节点增加或兼容保存正文内容、来源格式和扩展元信息。
- 为后续 PDF、EPUB、Excel、思维导图导入预留注册机制。
- 增加 smoke test，验证 `.docx` 仍能导入、保存 note、生成项目树。

验收：

- 原有 Word 导入功能不退化。
- 新增 importer 注册机制后，其他窗口可以独立补具体格式。
- `python3 -m unittest tests.smoke_api` 通过。

## 窗口 V2-B：PDF、图片和 OCR 入口

建议分支：`v2/B-pdf-image-import`

负责范围：

- `backend/services/importers.py`
- `backend/services/pdf_parser.py`
- `backend/services/image_parser.py`
- `tests/`
- `README.md` 中对应格式说明

任务：

- 增加 PDF 导入，优先提取文本并按标题线索生成层级。
- 增加图片导入入口，至少支持把图片作为单节点项目保存。
- 如果本地没有 OCR 依赖，不强制实现 OCR，但要给出可插拔接口和清晰提示。
- PDF 解析失败时返回结构化错误，不影响 Word 导入。
- 增加最小 PDF 或 mock importer 测试。

验收：

- 上传 `.pdf` 可以生成项目。
- 上传图片不会崩溃，可以形成带来源信息的节点。
- 无 OCR 依赖时用户能看到明确提示。

## 窗口 V2-C：EPUB、AZW3 和电子书导入

建议分支：`v2/C-ebook-import`

负责范围：

- `backend/services/importers.py`
- `backend/services/ebook_parser.py`
- `tests/`
- `README.md` 中对应格式说明

任务：

- 增加 EPUB 导入，基于目录文件或章节 HTML 生成节点。
- 增加 AZW3 导入入口；如果无法无依赖解析，提供明确的待安装转换工具提示。
- 将章节正文写入节点 note。
- 保留章节顺序。
- 增加 EPUB 最小样例或 mock 测试。

验收：

- 上传 `.epub` 可以生成章节目录和正文 note。
- 上传 `.azw3` 不会崩溃，并返回可理解的能力说明。

## 窗口 V2-D：Excel、FreeMind MM、XMind 导入

建议分支：`v2/D-structured-import`

负责范围：

- `backend/services/importers.py`
- `backend/services/excel_parser.py`
- `backend/services/mindmap_parser.py`
- `tests/`
- `README.md` 中对应格式说明

任务：

- 增加 Excel 导入，支持 `.xlsx`、`.xls`、`.csv` 中至少一种可用路径。
- Excel 可按工作表、行、列标题生成目录节点，并把行内容写入 note。
- 增加 FreeMind `.mm` XML 解析，保留层级和节点文本。
- 增加 XMind 导入入口；如果当前不实现完整解析，也要返回明确提示。
- 增加 `.mm` 最小样例测试。

验收：

- `.mm` 可以稳定生成树。
- Excel 至少一种格式可导入并形成目录和 note。
- `.xmind` 不支持完整解析时有结构化错误提示。

## 窗口 V2-E：前端上传、多格式提示和内容预览

建议分支：`v2/E-frontend-import-ui`

负责范围：

- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`
- `README.md` 中用户操作说明

任务：

- 上传控件允许 `.docx,.pdf,.epub,.azw3,.png,.jpg,.jpeg,.xlsx,.xls,.csv,.mm,.xmind`。
- 首页展示支持格式说明。
- 导入成功后，目录预览中显示每个节点是否有正文内容。
- 导入失败时展示后端返回的结构化错误。
- 保持历史项目列表和进入知识网络流程不退化。

验收：

- Word 原流程可用。
- 不同格式上传时前端提示清晰。
- 后端暂未支持的格式不会表现成页面无响应。

## 窗口 V2-F：知识网络左侧结构树和级别控制

建议分支：`v2/F-editor-tree-levels`

负责范围：

- `frontend/editor.html`
- `frontend/editor.js`
- `frontend/styles.css`

任务：

- 左侧结构树支持同级节点展开和收起。
- 增加显示级别控制，例如只显示 1-2 级、1-3 级或全部。
- 当前选中节点高亮。
- 点击节点时右侧仍显示上下级关系和正文 note。
- 大树场景下避免一次性展开导致页面卡顿。

验收：

- 打开知识网络能按级别查看目录。
- 展开同级节点不影响现有节点编辑、添加、删除、导出。
- 刷新后项目仍从数据库加载。

## 窗口 V2-G：节点正文内容编辑和导出回写

建议分支：`v2/G-node-content-export`

负责范围：

- `frontend/editor.js`
- `frontend/editor.html`
- `frontend/styles.css`
- `backend/services/docx_exporter.py`
- `backend/services/projects.py`
- `tests/`

任务：

- 编辑器中明确展示和编辑每个目录节点的正文内容。
- 保存节点时正文内容持久化。
- Word 导出时把每个节点标题和 note 正文按层级写回。
- 为未来富文本、图片、表格保留扩展位置。
- 增加导出 smoke test，验证 note 没有丢失。

验收：

- 导入有正文的文档后，节点正文可见。
- 修改节点正文后刷新仍保留。
- 导出 Word 后正文跟随对应标题出现。

## 集成窗口操作说明

所有子任务完成后，回到协调窗口或新建集成窗口执行：

```bash
cd /Users/lionel/Documents/Codex/2026-04-20-word
git switch main
git pull --ff-only origin main
git switch -c v2/integration
```

按依赖顺序合并：

```bash
git merge --no-ff v2/A-import-foundation
git merge --no-ff v2/B-pdf-image-import
git merge --no-ff v2/C-ebook-import
git merge --no-ff v2/D-structured-import
git merge --no-ff v2/E-frontend-import-ui
git merge --no-ff v2/F-editor-tree-levels
git merge --no-ff v2/G-node-content-export
```

每合并一个分支后都运行：

```bash
python3 scripts/context_snapshot.py
PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile run.py backend/server.py backend/db.py backend/config.py backend/services/docx_parser.py backend/services/docx_exporter.py backend/services/projects.py tests/smoke_api.py build_release.py scripts/context_snapshot.py
python3 -m unittest tests.smoke_api
node --check frontend/app.js
node --check frontend/editor.js
git diff --check
```

如果全部通过，再进行浏览器验证：

```bash
PORT=8001 python3 run.py
```

浏览器打开：

```text
http://127.0.0.1:8001
```

最终合入主线：

```bash
git switch main
git pull --ff-only origin main
git merge --no-ff v2/integration
git push origin main
```

## V2.1 并行开发子任务

下面这一组任务用于处理新一轮需求：

1. 点击关系视图时，节点信息不能消失，目录总览和关系视图要统一显示同一份节点详情。
2. 对没有层级定义的导入结果，允许在目录总览中重新定义、修改层级。
3. 已导入的目录知识网络之间，允许手动建立新的上下级关系，例如把第二次导入的项目挂到第一次导入项目的某个子节点下。
4. 打开知识网络后，导出升级为“导出文件”，格式可选：Word、PDF、FreeMind `.mm`、图片。

### V2.1 统一规则

- 本轮开发统一从 `v2-main` 或最新集成基线创建新分支。
- 每个窗口只修改自己负责的文件范围。
- 如果两个子任务都需要改 `frontend/editor.js`，必须控制在不同代码区域，并在提交说明里写明改动入口函数。
- 所有新增导出格式都要有清晰的失败提示；如果当前只实现占位，也必须通过结构化错误返回。
- 新增“跨项目挂接”功能前，不允许破坏现有单项目树的导入、编辑、导出流程。

### 窗口 V2.1-A：编辑器视图状态统一

建议分支：`v2.1/A-editor-view-sync`

负责范围：

- `frontend/editor.js`
- `frontend/editor.html`
- `frontend/styles.css`

任务：

- 修复点击“关系视图”时节点详情消失的问题。
- 统一目录总览与关系视图的选中节点状态。
- 无论从左侧目录树还是关系图点击节点，右侧详情区都显示同一节点信息。
- 补充最小前端 smoke 验证思路或注释说明，确保后续不再回归。

验收：

- 从目录总览点击节点，详情区正常显示。
- 切换到关系视图后，详情区仍显示当前节点。
- 在关系视图中切换节点，详情区同步更新。

### 窗口 V2.1-B：目录层级重定义

建议分支：`v2.1/B-outline-relevel`

负责范围：

- `frontend/editor.js`
- `frontend/editor.html`
- `frontend/styles.css`
- `backend/services/projects.py`
- `backend/server.py`
- `tests/`

任务：

- 在目录总览中允许对节点重新定义层级或修改层级。
- 优先实现安全的“升级/降级/移到上级/移到下级”交互，而不是自由输入一个可能非法的 level。
- 后端提供必要的节点重挂接或排序接口复用。
- 修改后项目树刷新仍稳定，位置不乱。
- 增加 smoke test，验证层级修改后导出和重新加载都正确。

验收：

- 没有预设级别的导入树可以手工整理成想要的层级。
- 调整层级后，刷新项目仍保持结果。
- 不会出现循环父子关系。

### 窗口 V2.1-C：跨项目手动关联上下级

建议分支：`v2.1/C-cross-project-linking`

负责范围：

- `backend/db.py`
- `backend/services/projects.py`
- `backend/server.py`
- `frontend/editor.js`
- `frontend/editor.html`
- `tests/`

任务：

- 允许把一个项目树或某个项目根节点挂接到另一个项目节点下，形成组合型知识网络。
- 先设计清楚数据模型：是直接移动节点跨项目，还是建立“引用/挂接关系”。
- 默认要求保留来源项目标识，避免用户分不清节点来自哪个导入文件。
- 提供选择目标父节点的交互入口。
- 至少支持用户示例：把“囚徒的困境”挂到“中图法/社会科学/某子节点”下。

验收：

- 能在两个已导入项目之间建立新的上下级关系。
- 原节点内容不丢失。
- 刷新、重新打开、导出时结构仍存在。

### 窗口 V2.1-D：多格式导出框架

建议分支：`v2.1/D-multi-export`

负责范围：

- `backend/services/docx_exporter.py`
- `backend/services/exporters.py`
- `backend/services/projects.py`
- `backend/server.py`
- `tests/`

任务：

- 将原来的 Word 导出升级为统一导出框架。
- 导出格式至少支持：Word、PDF、FreeMind `.mm`、图片。
- 如果 PDF/图片当前只能实现基础版本，也要先提供稳定可下载结果。
- 服务端导出接口支持格式参数，例如 `format=docx/pdf/mm/png`。
- 为每种格式补最小 smoke test。

验收：

- 旧的 Word 导出仍可用。
- 新接口可按格式返回对应文件。
- 不支持时返回结构化错误而不是 500。

### 窗口 V2.1-E：编辑器导出面板和格式选择

建议分支：`v2.1/E-export-ui`

负责范围：

- `frontend/editor.js`
- `frontend/editor.html`
- `frontend/styles.css`

任务：

- 把“导出新 Word”升级为“导出文件”面板。
- 用户可选择导出格式：Word、PDF、MM、图片。
- 点击导出时调用新的后端导出接口。
- 错误提示、加载状态和文件名展示清晰。
- 不要破坏现有节点编辑与关系图交互。

验收：

- 用户可以在编辑器里切换导出格式。
- 至少 Word 路径保持稳定可用。
- 新增格式失败时能看到明确提示。

### V2.1 集成窗口操作说明

所有子任务完成后，在本窗口或新建集成窗口执行：

```bash
cd /Users/lionel/Documents/Codex/2026-04-20-word
git fetch origin
git switch v2-main
git pull --ff-only origin v2-main
git switch -c v2.1/integration
```

按依赖顺序合并：

```bash
git merge --no-ff v2.1/A-editor-view-sync
git merge --no-ff v2.1/B-outline-relevel
git merge --no-ff v2.1/C-cross-project-linking
git merge --no-ff v2.1/D-multi-export
git merge --no-ff v2.1/E-export-ui
```

每次合并后运行：

```bash
PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile run.py backend/server.py backend/db.py backend/config.py backend/services/docx_parser.py backend/services/docx_exporter.py backend/services/projects.py tests/smoke_api.py build_release.py scripts/context_snapshot.py
python3 -m unittest tests.smoke_api
node --check frontend/app.js
node --check frontend/editor.js
git diff --check
```

最后做浏览器验收：

```bash
PORT=8001 python3 run.py
```

浏览器打开：

```text
http://127.0.0.1:8001
```
