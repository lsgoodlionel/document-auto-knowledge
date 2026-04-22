# V3.0 开发计划

V3.0 目标是在当前“文档自动知识库系统”基础上，完成一轮更接近正式产品形态的升级：

- 增加统一导航栏和全站信息架构
- 增加用户登录模块和基础会话能力
- 完成产品名称与页面文案升级
- 将“知识网络”编辑器升级为更完整的思维导图式编辑系统

V3.0 的并行拆分见 [docs/V3_PARALLEL_TASKS.md](/Users/lionel/Documents/Codex/2026-04-20-word/docs/V3_PARALLEL_TASKS.md:1)。

## 推荐启动方式

V3 开发统一从 `v2-main` 拉出 `v3-main`：

```bash
git switch v2-main
git pull --ff-only origin v2-main
git switch -c v3-main
```

后续所有 V3 子任务都从 `v3-main` 创建，不再直接从 `main` 或历史任务分支创建。

## V3.0 目标拆分

### A. 导航与产品壳层

- 首页、登录页、编辑器页统一导航栏
- 统一品牌名称为“文档自动知识库系统”
- 统一页面标题、页眉、基础跳转逻辑
- 为后续仪表盘、用户中心预留导航入口

### B. 用户系统

- 增加最小可用登录模块
- 支持登录、退出、查询当前用户
- 为项目归属用户、权限边界预留字段
- 保持本地运行环境优先，先做单机可用版本

### C. 思维导图后端模型

- 在现有项目/节点模型基础上增加思维导图编辑能力
- 增加节点样式、坐标、折叠状态、连接关系等数据模型
- 支持批量保存、边管理、节点布局更新
- 为撤销/重做和版本快照预留扩展点

### D. 思维导图前端编辑器

- 支持节点创建、编辑、删除、移动、拖拽
- 支持画布平移、缩放、选中、折叠
- 支持节点关系线或主题线绘制
- 支持工具栏、快捷操作和节点属性面板
- 保持现有正文 `note` 编辑与导出能力不退化

### E. 文档与发布

- 更新 README、架构文档、安装说明
- 明确 V3 验证清单
- 如有新增运行依赖，要写清用途和平台兼容性

## V3.0 第一阶段建议

优先顺序建议如下：

1. 先建立统一导航栏和品牌壳层，避免各页面重复分叉。
2. 再做登录后端和前端，先打通基础会话。
3. 并行推进思维导图数据模型和编辑器交互。
4. 最后统一收敛文档、测试和发布说明。

## V3.0 接手检查清单

新窗口开始前运行：

```bash
git status --short
git branch -vv
python3 scripts/context_snapshot.py
PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile run.py backend/server.py backend/db.py backend/services/projects.py backend/services/exporters.py tests/smoke_api.py
python3 -m unittest tests.smoke_api
node --check frontend/app.js
node --check frontend/editor.js
```

如果全部通过，再开始 V3.0 代码开发。
