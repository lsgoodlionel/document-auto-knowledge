# V2.0 开发计划

V2.0 目标是在 V1.0 本地知识网络工具基础上，提升产品化、可维护性和复杂知识编辑能力。

## 推荐启动方式

新窗口接手后先创建 V2 分支：

```bash
git switch main
git pull --ff-only origin main
git switch -c v2-main
```

如果继续拆多窗口并行开发，建议使用：

```bash
git branch v2/A-backend-foundation
git branch v2/B-editor-graph
git branch v2/C-frontend-ux
git branch v2/D-docx-fidelity
git branch v2/E-release-desktop
```

## V2.0 候选方向

### A. 后端工程化

- 将标准库 HTTP server 迁移到 FastAPI 或 Flask
- 增加结构化日志
- 增加数据库 migration 机制
- 增加更完整的 API tests
- 增加配置文件和运行环境检测

### B. 知识网络编辑能力

- 图形节点拖拽布局
- 跨层级节点关联边
- 节点标签、颜色、状态
- 搜索、过滤、折叠/展开
- 撤销/重做
- 自动保存和冲突提示

### C. 前端体验

- 项目仪表盘
- 最近打开、收藏、搜索
- 导入进度和错误详情
- 更清晰的空状态和引导
- 移动端适配

### D. Word / 文档能力

- 更完整地保留 Word 正文格式
- 支持图片、表格、列表
- 支持导出目录页
- 支持 `.docx` 模板
- 支持 Markdown 导入导出

### E. 发布与桌面化

- 评估 Tauri / Electron 桌面壳
- 一键安装器而不只是 zip
- 自动更新
- mac 签名、公证
- Windows 安装向导

## V2.0 第一阶段建议

优先做这些低风险高收益任务：

1. 删除或隔离旧版 `web/` 和 `app.py`，减少维护面。
2. 增加项目级导入/导出备份 JSON。
3. 编辑器增加节点搜索和折叠。
4. Word 导出支持模板。
5. GitHub Release 自动化，把 tag 发布和 artifact 上传串起来。

## V2.0 接手检查清单

新窗口开始前运行：

```bash
git status --short
git branch -vv
python3 scripts/context_snapshot.py
PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile run.py backend/server.py backend/db.py backend/config.py backend/services/docx_parser.py backend/services/docx_exporter.py backend/services/projects.py tests/smoke_api.py build_release.py scripts/context_snapshot.py
python3 -m unittest tests.smoke_api
node --check frontend/app.js
node --check frontend/editor.js
```

如果全部通过，再开始 V2.0 代码开发。
