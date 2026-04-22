# V3.0 开发计划

## 当前基线

截至 2026-04-22，`v3-main` 仍然以 V2.1 的可用功能为主：

- 统一导入入口已可用
- 编辑器支持节点 `note`、左侧结构树控制、跨项目挂接和多格式导出
- 前端仍然是“导入页 + 关系视图式编辑器”两页结构

尚未默认合入 `v3-main` 的能力：

- 统一导航栏和品牌壳层
- 登录页、会话接口、当前用户状态
- 思维导图专用后端模型
- 拖拽、缩放、画布化的思维导图编辑体验

因此，V3.0 不是在空白基础上新建产品，而是在当前 V2.1 基线上继续升级。

## V3.0 目标

V3.0 目标是在当前工程基础上，完成更接近正式产品形态的一轮升级：

- 增加统一导航栏和全站基础壳层
- 补齐最小可用登录与会话能力
- 统一产品名称与页面文案
- 将当前关系视图式编辑器升级为更完整的思维导图编辑系统
- 补齐文档、测试清单和发布说明

并行拆分见 [docs/V3_PARALLEL_TASKS.md](/Users/lionel/Documents/Codex/2026-04-20-word/docs/V3_PARALLEL_TASKS.md:1)。

## 推荐启动方式

V3 子任务统一从最新 `origin/v3-main` 拉出：

```bash
git fetch origin
git switch v3-main
git pull --ff-only origin v3-main
git switch -c v3/<task-branch>
```

如果本地 `git pull --ff-only origin v3-main` 因分支配置报错，先确认 `git status --short --branch` 显示本地分支已对齐 `origin/v3-main`，再继续创建子分支，并在窗口汇报里注明该异常。

## V3.0 拆分方向

### A. 导航与产品壳层

- 首页、登录页、编辑器页共享导航
- 统一品牌名称和页面标题
- 为用户中心、项目入口、返回逻辑预留结构

### B. 用户系统

- 登录、退出、读取当前用户
- 本地单机可用
- 为项目归属和权限边界预留扩展点

### C. 思维导图后端模型

- 节点附加属性，例如坐标、折叠状态、样式
- 边或关系线模型
- 批量保存、未来快照和撤销扩展点

### D. 思维导图前端编辑器

- 节点创建、删除、拖拽、折叠
- 画布平移、缩放、关系线
- 工具栏、属性面板
- 保持 `note` 编辑与导出能力不退化

### E. 文档、测试与发布

- README、架构文档、V3 说明同步到真实代码状态
- 明确测试清单
- 明确当前安装包包含的内容与不包含的能力

## 第一阶段建议顺序

1. 先统一导航与品牌壳层，避免页面结构继续分叉。
2. 再打通登录后端与登录前端。
3. 并行推进思维导图模型与编辑器升级。
4. 最后统一收口文档、测试与发布说明。

## 当前验收口径

在 V3 各窗口尚未全部合入前，验收分两层：

### 窗口内验收

每个窗口完成后至少汇报：

- 分支名
- 提交号
- 修改文件
- 验证命令
- 已知风险

### 集成验收

在整合窗口至少运行：

```bash
python3 scripts/context_snapshot.py
PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile \
  run.py \
  backend/server.py \
  backend/db.py \
  backend/services/projects.py \
  backend/services/exporters.py \
  tests/smoke_api.py \
  build_release.py
python3 -m unittest tests.smoke_api
node --check frontend/app.js
node --check frontend/editor.js
git diff --check
```

如果修改了发布脚本，还应追加：

```bash
python3 build_release.py
```

## 接手检查清单

新窗口开始前建议运行：

```bash
git status --short
git branch -vv
python3 scripts/context_snapshot.py
node --check frontend/app.js
node --check frontend/editor.js
git diff --check
```

如果当前任务涉及后端或导出，再补 Python 编译和 smoke test。
