(() => {
const STORAGE_KEY = "knowledge-network-state";
const DEFAULT_OUTLINE_LEVEL = "2";
const MAX_OUTLINE_RENDERED_NODES = 700;

const state = {
  projectId: null,
  name: "folder-system",
  tree: [],
  selectedId: null,
  displayDepth: DEFAULT_OUTLINE_LEVEL,
  expandedIds: new Set(),
  collapsedIds: new Set(),
  apiMode: false,
  busy: false,
};

const outlineTree = document.querySelector("#outline-tree");
const nodeCount = document.querySelector("#node-count");
const outlineLevelFilter = document.querySelector("#outline-level-filter");
const expandSiblings = document.querySelector("#expand-siblings");
const collapseSiblings = document.querySelector("#collapse-siblings");
const networkCanvas = document.querySelector("#network-canvas");
const networkMeta = document.querySelector("#network-meta");
const focusLabel = document.querySelector("#focus-label");
const selectionPath = document.querySelector("#selection-path");
const nodeTitle = document.querySelector("#node-title");
const nodeNote = document.querySelector("#node-note");
const saveNode = document.querySelector("#save-node");
const addChild = document.querySelector("#add-child");
const addSibling = document.querySelector("#add-sibling");
const deleteNode = document.querySelector("#delete-node");
const exportDocx = document.querySelector("#export-docx");
const editorSubtitle = document.querySelector("#editor-subtitle");
const returnHome = document.querySelector("#return-home");

boot();

returnHome.addEventListener("click", (event) => {
  event.preventDefault();
  window.location.assign(window.location.protocol === "file:" ? "./index.html" : "./");
});

async function boot() {
  const projectId = getProjectId();
  if (projectId) {
    state.projectId = projectId;
    state.apiMode = true;
    try {
      await loadProject();
    } catch (error) {
      renderEmptyState(error.message || "无法从数据库读取知识网络。");
    }
    return;
  }

  const raw = sessionStorage.getItem(STORAGE_KEY);
  if (!raw) {
    renderEmptyState();
    return;
  }

  try {
    const payload = JSON.parse(raw);
    state.projectId = payload.projectId || null;
    state.name = payload.name || "folder-system";
    state.tree = normalizeTree(payload.tree || []);
    state.selectedId = payload.selectedId || state.tree[0]?.id || null;
    state.displayDepth = normalizeDisplayDepth(payload.displayDepth);
    state.expandedIds = new Set(payload.expandedIds || []);
    state.collapsedIds = new Set(payload.collapsedIds || []);
    if (!state.projectId) {
      state.projectId = await findProjectIdByName(state.name);
    }
    state.apiMode = Boolean(state.projectId);
    if (state.apiMode) {
      await loadProject();
      return;
    }
    protectLargeOutline();
    revealNodeInOutline(state.selectedId, false);
    render();
  } catch (error) {
    renderEmptyState("知识网络数据损坏，无法打开编辑器。");
  }
}

saveNode.addEventListener("click", async () => {
  const selected = findNode(state.selectedId);
  if (!selected) {
    return;
  }

  const title = sanitizeName(nodeTitle.value) || "untitled";
  const note = nodeNote.value.trim();

  if (state.apiMode) {
    await runEditorAction(async () => {
      const data = await apiRequest(`/api/nodes/${selected.id}`, {
        method: "PUT",
        body: {
          title,
          note,
        },
      });
      applyNodePatch(selected, data.node);
      editorSubtitle.textContent = "当前节点已保存到数据库。";
    });
    return;
  }

  selected.name = title;
  selected.title = title;
  selected.note = note;
  render();
});

addChild.addEventListener("click", async () => {
  const selected = findNode(state.selectedId);
  if (!selected) {
    return;
  }

  if (state.apiMode) {
    await runEditorAction(async () => {
      const data = await apiRequest(`/api/projects/${state.projectId}/nodes`, {
        method: "POST",
        body: {
          parentId: selected.id,
          title: "新子节点",
          note: "",
        },
      });
      const child = normalizeNode(data.node);
      selected.children.push(child);
      state.selectedId = child.id;
      revealNodeInOutline(child.id, true);
      editorSubtitle.textContent = "新子节点已保存到数据库。";
    });
    return;
  }

  const child = {
    id: createId(),
    name: "新子节点",
    title: "新子节点",
    note: "",
    children: [],
  };
  selected.children.push(child);
  state.selectedId = child.id;
  revealNodeInOutline(child.id, true);
  render();
});

addSibling.addEventListener("click", async () => {
  const selectedId = state.selectedId;
  if (!selectedId) {
    return;
  }

  if (state.apiMode) {
    const info = findParentInfo(selectedId);
    if (!info) {
      return;
    }

    await runEditorAction(async () => {
      const data = await apiRequest(`/api/projects/${state.projectId}/nodes`, {
        method: "POST",
        body: {
          parentId: info.parent?.id || null,
          title: "新同级节点",
          note: "",
        },
      });
      const moved = await apiRequest(`/api/nodes/${data.node.id}/move`, {
        method: "PUT",
        body: {
          parentId: info.parent?.id || null,
          position: info.index + 1,
        },
      });
      const sibling = normalizeNode(moved.node);
      info.siblings.splice(info.index + 1, 0, sibling);
      state.selectedId = sibling.id;
      revealNodeInOutline(sibling.id, true);
      editorSubtitle.textContent = "新同级节点已保存到数据库。";
    });
    return;
  }

  const target = insertSibling(selectedId);
  if (!target) {
    return;
  }

  state.selectedId = target.id;
  revealNodeInOutline(target.id, true);
  render();
});

deleteNode.addEventListener("click", async () => {
  if (!state.selectedId) {
    return;
  }

  const deletedId = state.selectedId;
  if (state.apiMode) {
    const nextSelectedId = getFallbackSelectedId(state.selectedId);
    await runEditorAction(async () => {
      await apiRequest(`/api/nodes/${deletedId}`, {
        method: "DELETE",
      });
      await loadProject(nextSelectedId);
      editorSubtitle.textContent = "节点已从数据库删除。";
    }, false);
    return;
  }

  const nextSelectedId = removeNode(state.selectedId);
  state.selectedId = nextSelectedId;
  render();
});

outlineLevelFilter.addEventListener("change", () => {
  state.displayDepth = outlineLevelFilter.value;
  state.collapsedIds.clear();
  state.expandedIds.clear();
  protectLargeOutline();
  revealNodeInOutline(state.selectedId, false);
  render();
});

expandSiblings.addEventListener("click", () => {
  setSiblingExpansion(true);
});

collapseSiblings.addEventListener("click", () => {
  setSiblingExpansion(false);
});

exportDocx.addEventListener("click", () => {
  if (!state.tree.length) {
    editorSubtitle.textContent = "没有可导出的知识网络。";
    return;
  }

  if (state.apiMode) {
    window.location.assign(`/api/projects/${state.projectId}/export`);
    editorSubtitle.textContent = "正在按数据库中的最新结构导出 Word。";
    return;
  }

  const docxBytes = buildKnowledgeDocx(state.tree, state.name);
  downloadBlob(`${state.name || "knowledge-network"}.docx`, new Blob([docxBytes], { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" }));
  editorSubtitle.textContent = "新的 Word 文档已生成并开始下载。";
});

function render() {
  renderOutline();
  renderInspector();
  renderNetwork();
  persistState();
}

function renderEmptyState(message = "当前没有可编辑的知识网络，请先从解析页打开。") {
  outlineTree.textContent = message;
  outlineTree.classList.add("empty");
  networkCanvas.textContent = message;
  networkCanvas.classList.add("empty");
  networkMeta.textContent = "请返回解析页生成目录后再进入。";
  networkMeta.classList.add("empty");
  nodeCount.textContent = "0 个节点";
  focusLabel.textContent = "未选择节点";
  selectionPath.textContent = "暂无路径";
  toggleEditor(false);
}

function toggleEditor(enabled) {
  const disabled = !enabled || state.busy;
  nodeTitle.disabled = disabled;
  nodeNote.disabled = disabled;
  saveNode.disabled = disabled;
  addChild.disabled = disabled;
  addSibling.disabled = disabled;
  deleteNode.disabled = disabled;
  exportDocx.disabled = disabled;
  outlineLevelFilter.disabled = !enabled;
  expandSiblings.disabled = disabled;
  collapseSiblings.disabled = disabled;
}

function renderOutline() {
  if (!state.tree.length) {
    renderEmptyState();
    return;
  }

  toggleEditor(true);
  outlineTree.classList.remove("empty");
  outlineTree.innerHTML = "";
  outlineLevelFilter.value = state.displayDepth;
  const renderContext = { rendered: 0, truncated: false };
  outlineTree.appendChild(createOutlineList(state.tree, 1, renderContext));
  if (renderContext.truncated) {
    const note = document.createElement("p");
    note.className = "tree-limit-note";
    note.textContent = `目录较大，左侧已先显示 ${MAX_OUTLINE_RENDERED_NODES} 个节点。请收起同级或切换显示级别后继续查看。`;
    outlineTree.appendChild(note);
  }
  const totalNodes = countNodes(state.tree);
  const visibleLabel = renderContext.truncated ? `，已显示 ${MAX_OUTLINE_RENDERED_NODES} 个` : "";
  nodeCount.textContent = `${totalNodes} 个节点${visibleLabel}`;
}

function createOutlineList(nodes, depth = 1, renderContext = { rendered: 0, truncated: false }) {
  const list = document.createElement("ul");
  list.className = "tree-list";

  nodes.forEach((node) => {
    if (renderContext.rendered >= MAX_OUTLINE_RENDERED_NODES) {
      renderContext.truncated = true;
      return;
    }

    renderContext.rendered += 1;
    const item = document.createElement("li");
    item.className = "tree-item";
    item.dataset.depth = String(depth);

    const row = document.createElement("div");
    row.className = `outline-row ${node.id === state.selectedId ? "selected" : ""}`;

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "outline-toggle";
    toggle.setAttribute("aria-label", `${isOutlineExpanded(node, depth) ? "收起" : "展开"} ${node.name}`);
    toggle.disabled = !canShowChildren(node, depth);
    toggle.textContent = getToggleLabel(node, depth);
    toggle.addEventListener("click", () => {
      toggleNodeExpansion(node, depth);
      render();
    });

    const button = document.createElement("button");
    button.type = "button";
    button.className = `outline-node ${node.id === state.selectedId ? "active" : ""}`;
    button.textContent = node.name;
    button.addEventListener("click", () => {
      state.selectedId = node.id;
      revealNodeInOutline(node.id, false);
      render();
    });
    row.append(toggle, button);
    item.appendChild(row);

    if (isOutlineExpanded(node, depth)) {
      item.appendChild(createOutlineList(node.children, depth + 1, renderContext));
    }

    list.appendChild(item);
  });

  return list;
}

function renderInspector() {
  const selected = findNode(state.selectedId);
  if (!selected) {
    nodeTitle.value = "";
    nodeNote.value = "";
    focusLabel.textContent = "未选择节点";
    selectionPath.textContent = "暂无路径";
    return;
  }

  nodeTitle.value = selected.name;
  nodeNote.value = selected.note || "";
  focusLabel.textContent = selected.name;
  selectionPath.textContent = buildPath(selected.id).join(" / ");
}

function renderNetwork() {
  const selected = findNode(state.selectedId);
  if (!selected) {
    networkCanvas.textContent = "请先从左侧目录中选择一个节点。";
    networkCanvas.classList.add("empty");
    return;
  }

  const parentChain = getAncestors(selected.id);
  const children = selected.children;
  networkCanvas.classList.remove("empty");
  networkCanvas.innerHTML = "";

  const canvas = document.createElement("div");
  canvas.className = "network-stage";

  if (parentChain.length) {
    const parentRow = document.createElement("div");
    parentRow.className = "network-row network-row-top";
    parentChain.forEach((node) => parentRow.appendChild(createGraphNode(node, "ancestor")));
    canvas.appendChild(parentRow);
  }

  const centerRow = document.createElement("div");
  centerRow.className = "network-row network-row-center";
  centerRow.appendChild(createGraphNode(selected, "selected"));
  canvas.appendChild(centerRow);

  if (children.length) {
    const childRow = document.createElement("div");
    childRow.className = "network-row network-row-bottom";
    children.forEach((node) => childRow.appendChild(createGraphNode(node, "child")));
    canvas.appendChild(childRow);
  }

  networkCanvas.appendChild(canvas);

  const parentName = parentChain[parentChain.length - 1]?.name || "无";
  const childNames = children.length ? children.map((node) => node.name).join("、") : "无";
  networkMeta.textContent = `上级节点：${parentName}；下级节点：${childNames}`;
  networkMeta.classList.remove("empty");
}

function createGraphNode(node, type) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `graph-node ${type}`;
  button.innerHTML = `
    <strong>${escapeHtml(node.name)}</strong>
    <span>${node.children.length} 个下级</span>
  `;
  button.addEventListener("click", () => {
    state.selectedId = node.id;
    revealNodeInOutline(node.id, true);
    render();
  });
  return button;
}

function getDisplayDepthLimit() {
  return state.displayDepth === "all" ? Number.POSITIVE_INFINITY : Number(state.displayDepth);
}

function normalizeDisplayDepth(value) {
  return ["2", "3", "all"].includes(value) ? value : DEFAULT_OUTLINE_LEVEL;
}

function canShowChildren(node, depth) {
  return node.children.length > 0 && depth < getDisplayDepthLimit();
}

function isOutlineExpanded(node, depth) {
  if (!canShowChildren(node, depth) || state.collapsedIds.has(node.id)) {
    return false;
  }

  return state.expandedIds.has(node.id) || depth < getDisplayDepthLimit();
}

function getToggleLabel(node, depth) {
  if (!node.children.length) {
    return "·";
  }

  if (!canShowChildren(node, depth)) {
    return "+";
  }

  return isOutlineExpanded(node, depth) ? "−" : "+";
}

function toggleNodeExpansion(node, depth) {
  if (!canShowChildren(node, depth)) {
    return;
  }

  if (isOutlineExpanded(node, depth)) {
    state.collapsedIds.add(node.id);
    state.expandedIds.delete(node.id);
    return;
  }

  state.expandedIds.add(node.id);
  state.collapsedIds.delete(node.id);
}

function setSiblingExpansion(expanded) {
  const info = findParentInfo(state.selectedId);
  if (!info) {
    return;
  }

  const depth = getNodeDepth(state.selectedId);
  info.siblings.forEach((node) => {
    if (!canShowChildren(node, depth)) {
      return;
    }

    if (expanded) {
      state.expandedIds.add(node.id);
      state.collapsedIds.delete(node.id);
    } else {
      state.collapsedIds.add(node.id);
      state.expandedIds.delete(node.id);
    }
  });
  render();
}

function revealNodeInOutline(id, allowDepthChange) {
  if (!id) {
    return;
  }

  const depth = getNodeDepth(id);
  const limit = getDisplayDepthLimit();
  if (allowDepthChange && depth > limit) {
    state.displayDepth = depth <= 3 ? "3" : "all";
  }

  getAncestors(id).forEach((node) => {
    state.expandedIds.add(node.id);
    state.collapsedIds.delete(node.id);
  });
}

function protectLargeOutline() {
  if (state.displayDepth !== "all" || countNodes(state.tree) <= MAX_OUTLINE_RENDERED_NODES) {
    return;
  }

  collectExpandableIds(state.tree).forEach((id) => state.collapsedIds.add(id));
  editorSubtitle.textContent = "目录节点较多，已先收起全部层级，可从左侧逐级展开。";
}

function collectExpandableIds(nodes, ids = []) {
  nodes.forEach((node) => {
    if (node.children.length) {
      ids.push(node.id);
      collectExpandableIds(node.children, ids);
    }
  });
  return ids;
}

function normalizeTree(nodes) {
  return nodes.map((node) => normalizeNode(node));
}

function normalizeNode(node) {
  const name = sanitizeName(node.name || node.title || "untitled");
  return {
    id: node.id || createId(),
    projectId: node.projectId || node.project_id || state.projectId || null,
    parentId: node.parentId ?? node.parent_id ?? null,
    name,
    title: name,
    note: node.note || "",
    position: Number.isInteger(node.position) ? node.position : 0,
    children: normalizeTree(node.children || []),
  };
}

function findNode(id, nodes = state.tree) {
  for (const node of nodes) {
    if (node.id === id) {
      return node;
    }
    const childMatch = findNode(id, node.children);
    if (childMatch) {
      return childMatch;
    }
  }
  return null;
}

function findParentInfo(id, nodes = state.tree, parent = null) {
  for (let index = 0; index < nodes.length; index += 1) {
    const node = nodes[index];
    if (node.id === id) {
      return { parent, siblings: nodes, index, node };
    }
    const childResult = findParentInfo(id, node.children, node);
    if (childResult) {
      return childResult;
    }
  }
  return null;
}

function getAncestors(id) {
  const chain = [];
  let currentInfo = findParentInfo(id);
  while (currentInfo?.parent) {
    chain.unshift(currentInfo.parent);
    currentInfo = findParentInfo(currentInfo.parent.id);
  }
  return chain;
}

function buildPath(id) {
  return [...getAncestors(id).map((node) => node.name), findNode(id)?.name || ""].filter(Boolean);
}

function getNodeDepth(id) {
  return buildPath(id).length || 1;
}

function insertSibling(id) {
  const info = findParentInfo(id);
  if (!info) {
    return null;
  }

  const sibling = {
    id: createId(),
    name: "新同级节点",
    title: "新同级节点",
    note: "",
    children: [],
  };
  info.siblings.splice(info.index + 1, 0, sibling);
  return sibling;
}

function removeNode(id) {
  const info = findParentInfo(id);
  if (!info) {
    return state.tree[0]?.id || null;
  }

  if (!info.parent && info.siblings.length === 1) {
    info.siblings.splice(info.index, 1);
    return null;
  }

  info.siblings.splice(info.index, 1);
  const fallback = info.siblings[info.index] || info.siblings[info.index - 1] || info.parent;
  return fallback?.id || state.tree[0]?.id || null;
}

function getFallbackSelectedId(id) {
  const info = findParentInfo(id);
  if (!info) {
    return state.tree[0]?.id || null;
  }

  if (!info.parent && info.siblings.length === 1) {
    return null;
  }

  const fallback = info.siblings[info.index + 1] || info.siblings[info.index - 1] || info.parent;
  return fallback?.id || state.tree[0]?.id || null;
}

function persistState() {
  sessionStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      projectId: state.projectId,
      name: state.name,
      tree: state.tree,
      selectedId: state.selectedId,
      displayDepth: state.displayDepth,
      expandedIds: Array.from(state.expandedIds),
      collapsedIds: Array.from(state.collapsedIds),
    }),
  );
}

function getProjectId() {
  const queryProjectId = new URLSearchParams(window.location.search).get("projectId");
  if (queryProjectId) {
    return Number(queryProjectId);
  }

  const raw = sessionStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return null;
  }

  try {
    const payload = JSON.parse(raw);
    return payload.projectId ? Number(payload.projectId) : null;
  } catch (error) {
    return null;
  }
}

async function loadProject(preferredSelectedId = state.selectedId) {
  editorSubtitle.textContent = "正在从数据库读取知识网络...";
  const data = await apiRequest(`/api/projects/${state.projectId}`);
  const project = data.project;
  state.name = project.name || "folder-system";
  state.tree = normalizeTree(project.tree || []);
  state.selectedId = findNode(preferredSelectedId)?.id || state.tree[0]?.id || null;
  protectLargeOutline();
  revealNodeInOutline(state.selectedId, false);
  editorSubtitle.textContent = `正在编辑：${state.name}`;
  render();
}

async function runEditorAction(action, shouldRender = true) {
  if (state.busy) {
    return;
  }

  state.busy = true;
  toggleEditor(Boolean(state.tree.length));
  try {
    await action();
  } catch (error) {
    editorSubtitle.textContent = error.message || "操作失败，请稍后重试。";
  } finally {
    state.busy = false;
    if (shouldRender) {
      render();
    } else {
      toggleEditor(Boolean(state.tree.length));
      persistState();
    }
  }
}

async function apiRequest(path, options = {}) {
  const response = await fetch(path, {
    method: options.method || "GET",
    headers: options.body ? { "Content-Type": "application/json" } : {},
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const contentType = response.headers.get("Content-Type") || "";
  const data = contentType.includes("application/json") ? await response.json() : {};

  if (!response.ok) {
    const message = data.error?.message || data.error || "数据库操作失败。";
    throw new Error(message);
  }

  return data;
}

async function findProjectIdByName(name) {
  if (window.location.protocol !== "http:" && window.location.protocol !== "https:") {
    return null;
  }

  try {
    const data = await apiRequest("/api/projects");
    const project = (data.projects || []).find((item) => item.name === name);
    return project?.id || null;
  } catch (error) {
    return null;
  }
}

function applyNodePatch(target, patch) {
  const node = normalizeNode({
    ...target,
    ...patch,
    children: target.children,
  });
  target.name = node.name;
  target.title = node.title;
  target.note = node.note;
  target.parentId = node.parentId;
  target.position = node.position;
}

function countNodes(nodes) {
  return nodes.reduce((total, node) => total + 1 + countNodes(node.children), 0);
}

function createId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return `node-${crypto.randomUUID()}`;
  }
  return `node-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
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

function flattenToWordParagraphs(nodes, depth = 1, paragraphs = []) {
  nodes.forEach((node) => {
    paragraphs.push({
      type: "heading",
      level: Math.min(depth, 9),
      text: node.name,
    });

    if (node.note) {
      node.note
        .split(/\n+/)
        .map((line) => line.trim())
        .filter(Boolean)
        .forEach((line) => {
          paragraphs.push({
            type: "text",
            text: line,
          });
        });
    }

    flattenToWordParagraphs(node.children, depth + 1, paragraphs);
  });

  return paragraphs;
}

function buildKnowledgeDocx(tree, title) {
  const paragraphs = flattenToWordParagraphs(tree);
  const entries = [
    { name: "[Content_Types].xml", content: buildContentTypesXml() },
    { name: "_rels/.rels", content: buildRootRelsXml() },
    { name: "docProps/app.xml", content: buildAppXml() },
    { name: "docProps/core.xml", content: buildCoreXml(title) },
    { name: "word/document.xml", content: buildDocumentXml(paragraphs) },
    { name: "word/styles.xml", content: buildStylesXml() },
  ];

  return buildStoredZip(entries);
}

function buildContentTypesXml() {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>`;
}

function buildRootRelsXml() {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>`;
}

function buildAppXml() {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
  xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Codex</Application>
</Properties>`;
}

function buildCoreXml(title) {
  const safeTitle = xmlEscape(title || "Knowledge Network");
  const now = new Date().toISOString();
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:dcterms="http://purl.org/dc/terms/"
  xmlns:dcmitype="http://purl.org/dc/dcmitype/"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>${safeTitle}</dc:title>
  <dc:creator>Codex</dc:creator>
  <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">${now}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">${now}</dcterms:modified>
</cp:coreProperties>`;
}

function buildStylesXml() {
  const headingStyles = Array.from({ length: 9 }, (_, index) => {
    const level = index + 1;
    return `<w:style w:type="paragraph" w:styleId="Heading${level}">
      <w:name w:val="heading ${level}"/>
      <w:basedOn w:val="Normal"/>
      <w:qFormat/>
      <w:pPr><w:outlineLvl w:val="${level - 1}"/></w:pPr>
    </w:style>`;
  }).join("");

  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:qFormat/>
  </w:style>
  ${headingStyles}
</w:styles>`;
}

function buildDocumentXml(paragraphs) {
  const body = paragraphs
    .map((paragraph) => {
      if (paragraph.type === "heading") {
        return `<w:p>
          <w:pPr><w:pStyle w:val="Heading${paragraph.level}"/></w:pPr>
          <w:r><w:t xml:space="preserve">${xmlEscape(paragraph.text)}</w:t></w:r>
        </w:p>`;
      }

      return `<w:p><w:r><w:t xml:space="preserve">${xmlEscape(paragraph.text)}</w:t></w:r></w:p>`;
    })
    .join("");

  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    ${body}
    <w:sectPr>
      <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>`;
}

function xmlEscape(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function buildStoredZip(entries) {
  const encoder = new TextEncoder();
  const localChunks = [];
  const centralChunks = [];
  let offset = 0;

  entries.forEach((entry) => {
    const nameBytes = encoder.encode(entry.name);
    const contentBytes = encoder.encode(entry.content);
    const crc = crc32(contentBytes);
    const localOffset = offset;
    const localHeader = createLocalFileHeader(nameBytes, crc, contentBytes.length, contentBytes.length);
    localChunks.push(localHeader, contentBytes);
    offset += localHeader.length + contentBytes.length;
    centralChunks.push(createCentralDirectoryHeader(nameBytes, crc, contentBytes.length, contentBytes.length, localOffset));
  });

  const centralDirectoryOffset = offset;
  const centralDirectorySize = centralChunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const endRecord = createEndOfCentralDirectory(entries.length, centralDirectorySize, centralDirectoryOffset);
  return concatenateUint8Arrays([...localChunks, ...centralChunks, endRecord]);
}

function createLocalFileHeader(nameBytes, crc32Value, compressedSize, uncompressedSize) {
  const header = new Uint8Array(30 + nameBytes.length);
  const view = new DataView(header.buffer);
  view.setUint32(0, 0x04034b50, true);
  view.setUint16(4, 20, true);
  view.setUint16(6, 0, true);
  view.setUint16(8, 0, true);
  view.setUint16(10, 0, true);
  view.setUint16(12, 0, true);
  view.setUint32(14, crc32Value >>> 0, true);
  view.setUint32(18, compressedSize, true);
  view.setUint32(22, uncompressedSize, true);
  view.setUint16(26, nameBytes.length, true);
  view.setUint16(28, 0, true);
  header.set(nameBytes, 30);
  return header;
}

function createCentralDirectoryHeader(nameBytes, crc32Value, compressedSize, uncompressedSize, localHeaderOffset) {
  const header = new Uint8Array(46 + nameBytes.length);
  const view = new DataView(header.buffer);
  view.setUint32(0, 0x02014b50, true);
  view.setUint16(4, 20, true);
  view.setUint16(6, 20, true);
  view.setUint16(8, 0, true);
  view.setUint16(10, 0, true);
  view.setUint16(12, 0, true);
  view.setUint16(14, 0, true);
  view.setUint32(16, crc32Value >>> 0, true);
  view.setUint32(20, compressedSize, true);
  view.setUint32(24, uncompressedSize, true);
  view.setUint16(28, nameBytes.length, true);
  view.setUint16(30, 0, true);
  view.setUint16(32, 0, true);
  view.setUint16(34, 0, true);
  view.setUint16(36, 0, true);
  view.setUint32(38, 0, true);
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

function downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function crc32(bytes) {
  let crc = 0xffffffff;
  for (let index = 0; index < bytes.length; index += 1) {
    crc ^= bytes[index];
    for (let bit = 0; bit < 8; bit += 1) {
      const mask = -(crc & 1);
      crc = (crc >>> 1) ^ (0xedb88320 & mask);
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}
})();
