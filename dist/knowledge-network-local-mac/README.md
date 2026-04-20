# Word 文档目录生成器

一个零依赖的本地网页工具：

- 上传 `.docx` 文档
- 识别 Word 中的标题样式或大纲级别
- 生成对应的文件夹树
- 打开图形化知识网络编辑页
- 在节点上维护说明文本，并增删上下级节点
- 按编辑后的知识网络反向导出新的 Word
- 一键下载目录结构 zip 压缩包
- 导出 Bash / PowerShell 目录创建脚本

## 一键本地部署安装包

项目根目录提供了 [build_release.py](/Users/lionel/Documents/Codex/2026-04-20-word/build_release.py:1)。

执行：

```bash
python3 build_release.py
```

会在 `dist/` 目录下生成三套可分发安装包：

- `knowledge-network-local-mac.zip`
- `knowledge-network-local-windows.zip`
- `knowledge-network-local-ubuntu.zip`

每个安装包都包含：

- `web/` 前端应用
- 对应系统的一键启动脚本
- `INSTALL.txt` 使用说明

说明：

- mac：双击 `start.command`
- Windows：双击 `start.bat`
- Ubuntu：执行 `chmod +x start.sh` 后运行 `./start.sh`
- 当前版本是“离线本地网页应用”交付方式，不依赖 Python/Node 运行环境

## 运行

直接打开 [web/index.html](/Users/lionel/Documents/Codex/2026-04-20-word/web/index.html:1) 也可以使用。

或者运行本地服务：

```bash
python3 app.py
```

然后打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

## 规则

- `标题 1` -> 一级目录
- `标题 2` -> 二级目录
- `标题 3` -> 三级目录
- 段落设置了 `大纲级别 1/2/3...` 时，也会按对应层级生成目录
- 如果同一段同时存在标题样式和直接设置的大纲级别，会优先使用段落上的大纲级别
- 会自动清理文件夹名中的非法字符

## 知识网络编辑

- 在解析页点击“打开知识网络”会进入新的编辑页面
- 点击任意节点会显示它的上级链路和直接下级
- 支持新增子节点、新增同级节点、删除当前节点
- 每个节点都可以填写说明文本
- 导出的 Word 会按当前节点层级生成标题，并把说明文本写在对应标题下方

## GitHub 发布准备

项目已包含 GitHub Actions 工作流：

- [.github/workflows/release.yml](/Users/lionel/Documents/Codex/2026-04-20-word/.github/workflows/release.yml:1)

推送到 GitHub 仓库后，可以在 Actions 中自动构建并上传安装包产物。

## 适用场景

- 项目资料归档
- 课程章节目录初始化
- 招投标文档拆分
- 知识库结构预生成
