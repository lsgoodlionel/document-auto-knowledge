const state = {
  result: null,
};

const NS = {
  w: "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
};

const docxInput = document.querySelector("#docx-input");
const parseBtn = document.querySelector("#parse-btn");
const sampleBtn = document.querySelector("#sample-btn");
const statusNode = document.querySelector("#status");
const countBadge = document.querySelector("#count-badge");
const treeView = document.querySelector("#tree-view");
const headingList = document.querySelector("#heading-list");
const bashScript = document.querySelector("#bash-script");
const pwshScript = document.querySelector("#pwsh-script");
const downloadBash = document.querySelector("#download-bash");
const downloadPwsh = document.querySelector("#download-pwsh");
const downloadZip = document.querySelector("#download-zip");
const openNetwork = document.querySelector("#open-network");

docxInput.addEventListener("change", () => {
  const file = docxInput.files?.[0];
  statusNode.textContent = file ? `已选择：${file.name}` : "等待上传文档。";
});

parseBtn.addEventListener("click", async () => {
  const file = docxInput.files?.[0];
  if (!file) {
    statusNode.textContent = "请先选择一个 .docx 文件。";
    return;
  }

  statusNode.textContent = "正在本地解析文档，请稍候...";
  parseBtn.disabled = true;

  try {
    const data = await parseDocxFile(file);
    state.result = {
      ...data,
      exportName: file.name.replace(/\.docx$/i, "") || "folder-system",
    };
    renderResult(state.result);
    statusNode.textContent = `解析完成，识别到 ${data.headings.length} 个标题。`;
  } catch (error) {
    statusNode.textContent = error.message || "解析失败，请检查文件格式。";
  } finally {
    parseBtn.disabled = false;
  }
});

sampleBtn.addEventListener("click", () => {
  const data = {
    headings: [
      { title: "01 项目总览", folderName: "01 项目总览", level: 1, source: "style" },
      { title: "项目背景", folderName: "项目背景", level: 2, source: "outline" },
      { title: "参与角色", folderName: "参与角色", level: 2, source: "outline" },
      { title: "02 需求分析", folderName: "02 需求分析", level: 1, source: "style" },
      { title: "业务需求", folderName: "业务需求", level: 2, source: "outline" },
      { title: "功能清单", folderName: "功能清单", level: 2, source: "outline" },
      { title: "前端", folderName: "前端", level: 3, source: "outline" },
      { title: "后端", folderName: "后端", level: 3, source: "outline" },
      { title: "03 交付物", folderName: "03 交付物", level: 1, source: "style" },
    ],
    tree: [
      {
        name: "01 项目总览",
        level: 1,
        children: [
          { name: "项目背景", level: 2, children: [] },
          { name: "参与角色", level: 2, children: [] },
        ],
      },
      {
        name: "02 需求分析",
        level: 1,
        children: [
          { name: "业务需求", level: 2, children: [] },
          {
            name: "功能清单",
            level: 2,
            children: [
              { name: "前端", level: 3, children: [] },
              { name: "后端", level: 3, children: [] },
            ],
          },
        ],
      },
      {
        name: "03 交付物",
        level: 1,
        children: [],
      },
    ],
  };

  data.bashScript = buildBashScript(data.tree);
  data.powershellScript = buildPowerShellScript(data.tree);
  state.result = {
    ...data,
    exportName: "word-folder-system-demo",
  };
  renderResult(state.result);
  statusNode.textContent = "已载入演示数据。";
});

downloadBash.addEventListener("click", () => {
  if (state.result?.bashScript) {
    downloadText("create-folders.sh", state.result.bashScript);
  }
});

downloadPwsh.addEventListener("click", () => {
  if (state.result?.powershellScript) {
    downloadText("create-folders.ps1", state.result.powershellScript);
  }
});

downloadZip.addEventListener("click", () => {
  if (!state.result?.tree?.length) {
    statusNode.textContent = "当前没有可导出的目录结构。";
    return;
  }

  try {
    statusNode.textContent = "正在生成 zip 压缩包...";
    const zipBytes = buildDirectoryZip(state.result.tree);
    downloadBlob(`${state.result.exportName || "folder-system"}.zip`, new Blob([zipBytes], { type: "application/zip" }));
    statusNode.textContent = "zip 压缩包已生成并开始下载。";
  } catch (error) {
    statusNode.textContent = error.message || "zip 生成失败。";
  }
});

openNetwork.addEventListener("click", () => {
  if (!state.result?.tree?.length) {
    statusNode.textContent = "请先生成目录结构，再打开知识网络。";
    return;
  }

  const payload = {
    name: state.result.exportName || "folder-system",
    tree: prepareEditorTree(state.result.tree),
  };
  sessionStorage.setItem("knowledge-network-state", JSON.stringify(payload));
  openEditorPage();
});

function renderResult(data) {
  renderTree(data.tree || []);
  renderHeadings(data.headings || []);
  bashScript.textContent = data.bashScript || "暂无内容";
  pwshScript.textContent = data.powershellScript || "暂无内容";
  bashScript.classList.toggle("empty", !data.bashScript);
  pwshScript.classList.toggle("empty", !data.powershellScript);

  const folderCount = countFolders(data.tree || []);
  countBadge.textContent = `${folderCount} 个目录`;
  downloadBash.disabled = !data.bashScript;
  downloadPwsh.disabled = !data.powershellScript;
  downloadZip.disabled = !data.tree?.length;
  openNetwork.disabled = !data.tree?.length;
}

function renderTree(tree) {
  if (!tree.length) {
    treeView.textContent = "没有从文档中识别到目录层级，请确认 Word 使用了“标题样式”或设置了“段落大纲级别”。";
    treeView.classList.add("empty");
    return;
  }

  treeView.classList.remove("empty");
  treeView.innerHTML = "";
  treeView.appendChild(createTreeList(tree));
}

function createTreeList(nodes) {
  const list = document.createElement("ul");
  list.className = "tree-list";

  nodes.forEach((node) => {
    const item = document.createElement("li");
    const content = document.createElement("div");
    content.className = "tree-item";
    content.innerHTML = `<span class="folder-icon">📁</span><span>${escapeHtml(node.name)}</span>`;
    item.appendChild(content);

    if (node.children?.length) {
      item.appendChild(createTreeList(node.children));
    }

    list.appendChild(item);
  });

  return list;
}

function renderHeadings(headings) {
  if (!headings.length) {
    headingList.textContent = "还没有识别到任何标题。";
    headingList.classList.add("empty");
    return;
  }

  headingList.classList.remove("empty");
  headingList.innerHTML = "";

  headings.forEach((heading, index) => {
    const row = document.createElement("div");
    row.className = "heading-pill";
    const sourceLabel = heading.source === "outline" ? "大纲" : "样式";
    row.innerHTML = `
      <div>
        <strong>${String(index + 1).padStart(2, "0")} · ${escapeHtml(heading.title)}</strong>
        <span>${escapeHtml(heading.folderName)}</span>
      </div>
      <span>H${heading.level} · ${sourceLabel}</span>
    `;
    headingList.appendChild(row);
  });
}

async function parseDocxFile(file) {
  const arrayBuffer = await file.arrayBuffer();
  const zipEntries = await unzipDocx(arrayBuffer);

  const documentXml = zipEntries.get("word/document.xml");
  if (!documentXml) {
    throw new Error("文档缺少 word/document.xml，无法解析。");
  }

  const stylesXml = zipEntries.get("word/styles.xml") || "";
  const documentRoot = parseXml(documentXml);
  const stylesRoot = stylesXml ? parseXml(stylesXml) : null;
  const styleMap = stylesRoot ? buildStyleMap(stylesRoot) : new Map();
  const headings = extractHeadings(documentRoot, styleMap);
  const tree = buildTree(headings);

  return {
    headings,
    tree,
    bashScript: buildBashScript(tree),
    powershellScript: buildPowerShellScript(tree),
  };
}

function parseXml(xmlText) {
  const doc = new DOMParser().parseFromString(xmlText, "application/xml");
  if (doc.querySelector("parsererror")) {
    throw new Error("Word XML 内容损坏，无法解析。");
  }
  return doc;
}

function buildStyleMap(stylesRoot) {
  const mapping = new Map();
  const styles = stylesRoot.getElementsByTagNameNS(NS.w, "style");

  for (const style of styles) {
    const styleId = style.getAttributeNS(NS.w, "styleId");
    if (!styleId) {
      continue;
    }

    const outlineNode = style.getElementsByTagNameNS(NS.w, "outlineLvl")[0];
    if (outlineNode) {
      const rawValue = outlineNode.getAttributeNS(NS.w, "val");
      const level = Number.parseInt(rawValue ?? "", 10);
      if (Number.isInteger(level)) {
        mapping.set(styleId, level + 1);
        continue;
      }
    }

    const idMatch = styleId.match(/Heading(\d+)$/i);
    if (idMatch) {
      mapping.set(styleId, Number.parseInt(idMatch[1], 10));
      continue;
    }

    const nameNode = style.getElementsByTagNameNS(NS.w, "name")[0];
    const styleName = nameNode?.getAttributeNS(NS.w, "val") || "";
    const nameMatch = styleName.match(/heading\s*(\d+)/i);
    if (nameMatch) {
      mapping.set(styleId, Number.parseInt(nameMatch[1], 10));
    }
  }

  return mapping;
}

function extractHeadings(documentRoot, styleMap) {
  const headings = [];
  const paragraphs = documentRoot.getElementsByTagNameNS(NS.w, "p");

  for (const paragraph of paragraphs) {
    const text = Array.from(paragraph.getElementsByTagNameNS(NS.w, "t"))
      .map((node) => node.textContent || "")
      .join("")
      .trim();

    if (!text) {
      continue;
    }

    const styleId = getParagraphStyleId(paragraph);
    const { level, source } = resolveLevel(paragraph, styleId, styleMap);
    if (!level) {
      continue;
    }

    headings.push({
      title: text,
      folderName: sanitizeName(text),
      level,
      source,
    });
  }

  return headings;
}

function resolveLevel(paragraph, styleId, styleMap) {
  const directOutlineLevel = getParagraphOutlineLevel(paragraph);
  if (directOutlineLevel !== null) {
    return { level: directOutlineLevel, source: "outline" };
  }

  if (styleId && styleMap.has(styleId)) {
    return { level: styleMap.get(styleId), source: "style" };
  }

  const fallbackLevel = getFallbackHeadingLevel(styleId);
  if (fallbackLevel !== null) {
    return { level: fallbackLevel, source: "style" };
  }

  return { level: null, source: null };
}

function getParagraphStyleId(paragraph) {
  const styleNode = paragraph.getElementsByTagNameNS(NS.w, "pStyle")[0];
  return styleNode?.getAttributeNS(NS.w, "val") || null;
}

function getParagraphOutlineLevel(paragraph) {
  const paragraphProperties = paragraph.getElementsByTagNameNS(NS.w, "pPr")[0];
  if (!paragraphProperties) {
    return null;
  }

  const outlineNode = paragraphProperties.getElementsByTagNameNS(NS.w, "outlineLvl")[0];
  if (!outlineNode) {
    return null;
  }

  const rawValue = outlineNode.getAttributeNS(NS.w, "val");
  const level = Number.parseInt(rawValue ?? "", 10);
  return Number.isInteger(level) ? level + 1 : null;
}

function getFallbackHeadingLevel(styleId) {
  if (!styleId) {
    return null;
  }

  const match = styleId.match(/heading\s*(\d+)/i);
  return match ? Number.parseInt(match[1], 10) : null;
}

function buildTree(headings) {
  const root = { name: "root", level: 0, children: [] };
  let stack = [root];

  headings.forEach((heading) => {
    const node = {
      name: heading.folderName,
      level: Math.max(1, Number(heading.level) || 1),
      children: [],
    };

    while (stack.length && stack[stack.length - 1].level >= node.level) {
      stack.pop();
    }

    if (!stack.length) {
      stack = [root];
    }

    stack[stack.length - 1].children.push(node);
    stack.push(node);
  });

  return root.children;
}

function buildBashScript(tree) {
  const lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""];
  iteratePaths(tree).forEach((path) => {
    lines.push(`mkdir -p "${path.replaceAll('"', '\\"')}"`);
  });
  return `${lines.join("\n")}\n`;
}

function buildPowerShellScript(tree) {
  const lines = ["$ErrorActionPreference = 'Stop'", ""];
  iteratePaths(tree).forEach((path) => {
    lines.push(`New-Item -ItemType Directory -Force -Path '${path.replaceAll("'", "''")}' | Out-Null`);
  });
  return `${lines.join("\n")}\n`;
}

function iteratePaths(nodes, prefix = "") {
  const paths = [];
  nodes.forEach((node) => {
    const current = prefix ? `${prefix}/${node.name}` : node.name;
    paths.push(current);
    paths.push(...iteratePaths(node.children || [], current));
  });
  return paths;
}

function countFolders(nodes) {
  return nodes.reduce((total, node) => total + 1 + countFolders(node.children || []), 0);
}

function downloadText(filename, content) {
  downloadBlob(filename, new Blob([content], { type: "text/plain;charset=utf-8" }));
}

function downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function sanitizeName(name) {
  const cleaned = String(name)
    .replace(/[<>:"/\\|?*\x00-\x1F]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\.+$/g, "");
  return cleaned || "untitled";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function unzipDocx(arrayBuffer) {
  const bytes = new Uint8Array(arrayBuffer);
  const view = new DataView(arrayBuffer);
  const eocdOffset = findEndOfCentralDirectory(view);

  if (eocdOffset < 0) {
    throw new Error("文件不是有效的 .docx 压缩包。");
  }

  const totalEntries = view.getUint16(eocdOffset + 10, true);
  const centralDirectoryOffset = view.getUint32(eocdOffset + 16, true);
  const entries = new Map();
  let offset = centralDirectoryOffset;
  const textDecoder = new TextDecoder("utf-8");

  for (let index = 0; index < totalEntries; index += 1) {
    if (view.getUint32(offset, true) !== 0x02014b50) {
      throw new Error("ZIP 中央目录损坏，无法读取 Word 内容。");
    }

    const compressionMethod = view.getUint16(offset + 10, true);
    const compressedSize = view.getUint32(offset + 20, true);
    const fileNameLength = view.getUint16(offset + 28, true);
    const extraLength = view.getUint16(offset + 30, true);
    const commentLength = view.getUint16(offset + 32, true);
    const localHeaderOffset = view.getUint32(offset + 42, true);
    const fileNameBytes = bytes.slice(offset + 46, offset + 46 + fileNameLength);
    const fileName = textDecoder.decode(fileNameBytes);

    const localNameLength = view.getUint16(localHeaderOffset + 26, true);
    const localExtraLength = view.getUint16(localHeaderOffset + 28, true);
    const dataOffset = localHeaderOffset + 30 + localNameLength + localExtraLength;
    const compressedData = bytes.slice(dataOffset, dataOffset + compressedSize);
    const uncompressed = await inflateEntry(compressionMethod, compressedData);

    entries.set(fileName, textDecoder.decode(uncompressed));
    offset += 46 + fileNameLength + extraLength + commentLength;
  }

  return entries;
}

function findEndOfCentralDirectory(view) {
  const minOffset = Math.max(0, view.byteLength - 65557);
  for (let offset = view.byteLength - 22; offset >= minOffset; offset -= 1) {
    if (view.getUint32(offset, true) === 0x06054b50) {
      return offset;
    }
  }
  return -1;
}

async function inflateEntry(compressionMethod, compressedData) {
  if (compressionMethod === 0) {
    return compressedData;
  }

  if (compressionMethod !== 8) {
    throw new Error(`不支持的 ZIP 压缩方式：${compressionMethod}`);
  }

  if (typeof DecompressionStream === "undefined") {
    throw new Error("当前浏览器不支持解压 .docx，请改用本地服务方式打开。");
  }

  const stream = new Blob([compressedData]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
  const response = new Response(stream);
  return new Uint8Array(await response.arrayBuffer());
}

function buildDirectoryZip(tree) {
  const encoder = new TextEncoder();
  const directoryPaths = iteratePaths(tree).map((path) => `${path}/`);
  const localChunks = [];
  const centralChunks = [];
  let offset = 0;

  directoryPaths.forEach((path) => {
    const nameBytes = encoder.encode(path);
    const crc = 0;
    const size = 0;

    localChunks.push(createLocalFileHeader(nameBytes, crc, size, size));
    offset += 30 + nameBytes.length;

    centralChunks.push(createCentralDirectoryHeader(nameBytes, crc, size, size, offset - (30 + nameBytes.length)));
  });

  const centralDirectoryOffset = offset;
  let centralDirectorySize = 0;
  centralChunks.forEach((chunk) => {
    centralDirectorySize += chunk.length;
  });

  const eocd = createEndOfCentralDirectory(directoryPaths.length, centralDirectorySize, centralDirectoryOffset);
  return concatenateUint8Arrays([...localChunks, ...centralChunks, eocd]);
}

function createLocalFileHeader(nameBytes, crc32, compressedSize, uncompressedSize) {
  const header = new Uint8Array(30 + nameBytes.length);
  const view = new DataView(header.buffer);
  view.setUint32(0, 0x04034b50, true);
  view.setUint16(4, 20, true);
  view.setUint16(6, 0, true);
  view.setUint16(8, 0, true);
  view.setUint16(10, 0, true);
  view.setUint16(12, 0, true);
  view.setUint32(14, crc32, true);
  view.setUint32(18, compressedSize, true);
  view.setUint32(22, uncompressedSize, true);
  view.setUint16(26, nameBytes.length, true);
  view.setUint16(28, 0, true);
  header.set(nameBytes, 30);
  return header;
}

function createCentralDirectoryHeader(nameBytes, crc32, compressedSize, uncompressedSize, localHeaderOffset) {
  const header = new Uint8Array(46 + nameBytes.length);
  const view = new DataView(header.buffer);
  view.setUint32(0, 0x02014b50, true);
  view.setUint16(4, 20, true);
  view.setUint16(6, 20, true);
  view.setUint16(8, 0, true);
  view.setUint16(10, 0, true);
  view.setUint16(12, 0, true);
  view.setUint16(14, 0, true);
  view.setUint32(16, crc32, true);
  view.setUint32(20, compressedSize, true);
  view.setUint32(24, uncompressedSize, true);
  view.setUint16(28, nameBytes.length, true);
  view.setUint16(30, 0, true);
  view.setUint16(32, 0, true);
  view.setUint16(34, 0, true);
  view.setUint16(36, 0, true);
  view.setUint32(38, 0x10, true);
  view.setUint32(42, localHeaderOffset, true);
  header.set(nameBytes, 46);
  return header;
}

function createEndOfCentralDirectory(entryCount, centralDirectorySize, centralDirectoryOffset) {
  const header = new Uint8Array(22);
  const view = new DataView(header.buffer);
  view.setUint32(0, 0x06054b50, true);
  view.setUint16(4, 0, true);
  view.setUint16(6, 0, true);
  view.setUint16(8, entryCount, true);
  view.setUint16(10, entryCount, true);
  view.setUint32(12, centralDirectorySize, true);
  view.setUint32(16, centralDirectoryOffset, true);
  view.setUint16(20, 0, true);
  return header;
}

function concatenateUint8Arrays(chunks) {
  const totalLength = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const merged = new Uint8Array(totalLength);
  let offset = 0;

  chunks.forEach((chunk) => {
    merged.set(chunk, offset);
    offset += chunk.length;
  });

  return merged;
}

function prepareEditorTree(tree) {
  return tree.map((node) => cloneNodeForEditor(node));
}

async function openEditorPage() {
  statusNode.textContent = "正在打开知识网络页面...";

  try {
    const [htmlResponse, scriptResponse] = await Promise.all([
      fetch("./editor.html", { cache: "no-store" }),
      fetch("./editor.js", { cache: "no-store" }),
    ]);
    if (!htmlResponse.ok || !scriptResponse.ok) {
      throw new Error("编辑器页面加载失败。");
    }

    const html = await htmlResponse.text();
    const script = await scriptResponse.text();
    const inlineScript = `<script>${script.replaceAll("</script", "<\\/script")}<\/script>`;
    const htmlWithBase = html
      .replace("<head>", '<head><base href="./">')
      .replace('<script src="./editor.js"></script>', inlineScript);
    document.open();
    document.write(htmlWithBase);
    document.close();
  } catch (error) {
    statusNode.textContent = error.message || "编辑器页面加载失败。";
  }
}

function cloneNodeForEditor(node) {
  return {
    id: `node-${cryptoRandomId()}`,
    name: node.name,
    note: node.note || "",
    children: (node.children || []).map((child) => cloneNodeForEditor(child)),
  };
}

function cryptoRandomId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }

  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
