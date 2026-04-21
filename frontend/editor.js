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
  availableProjects: [],
  sourceProjectTree: [],
  exporting: false,
};

const EXPORT_FORMATS = {
  docx: {
    label: "Word",
    extension: "docx",
    mime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  },
  pdf: {
    label: "PDF",
    extension: "pdf",
    mime: "application/pdf",
  },
  mm: {
    label: "MM",
    extension: "mm",
    mime: "application/xml",
  },
  png: {
    label: "图片",
    extension: "png",
    mime: "image/png",
  },
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
const selectionSummary = document.querySelector("#selection-summary");
const nodeTitle = document.querySelector("#node-title");
const nodeNote = document.querySelector("#node-note");
const noteStatus = document.querySelector("#note-status");
const saveNode = document.querySelector("#save-node");
const addChild = document.querySelector("#add-child");
const addSibling = document.querySelector("#add-sibling");
const deleteNode = document.querySelector("#delete-node");
const exportFormat = document.querySelector("#export-format");
const exportFile = document.querySelector("#export-file");
const exportFilename = document.querySelector("#export-filename");
const exportStatus = document.querySelector("#export-status");
const editorSubtitle = document.querySelector("#editor-subtitle");
const returnHome = document.querySelector("#return-home");
const linkTargetLabel = document.querySelector("#link-target-label");
const linkSourceProject = document.querySelector("#link-source-project");
const linkSourceRoot = document.querySelector("#link-source-root");
const attachProjectLink = document.querySelector("#attach-project-link");
const linkingHint = document.querySelector("#linking-hint");

boot();

nodeNote.addEventListener("input", () => {
  updateNoteStatus({ note: nodeNote.value });
});

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
  const note = normalizeNoteInput(nodeNote.value);

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

linkSourceProject.addEventListener("change", async () => {
  await runEditorAction(async () => {
    await loadSourceProjectTree(linkSourceProject.value);
  });
});

attachProjectLink.addEventListener("click", async () => {
  if (!state.apiMode || !state.projectId) {
    return;
  }

  const sourceProjectId = Number(linkSourceProject.value);
  if (!sourceProjectId) {
    editorSubtitle.textContent = "请先选择来源项目。";
    return;
  }

  const sourceRootValue = linkSourceRoot.value;
  const targetParentId = state.selectedId || null;
  const sourceRootNodeId = sourceRootValue ? Number(sourceRootValue) : null;

  await runEditorAction(async () => {
    const data = await apiRequest(`/api/projects/${state.projectId}/attachments`, {
      method: "POST",
      body: {
        targetParentId,
        sourceProjectId,
        sourceRootNodeId,
      },
    });
    state.name = data.project.name || state.name;
    state.tree = normalizeTree(data.project.tree || []);
    state.selectedId = targetParentId || state.tree[0]?.id || null;
    editorSubtitle.textContent = "跨项目挂接已保存。";
    await loadAvailableProjects();
    await loadSourceProjectTree(linkSourceProject.value);
  });
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

exportFormat.addEventListener("change", () => {
  updateExportPanel();
});

exportFile.addEventListener("click", async () => {
  if (!state.tree.length) {
    setExportStatus("没有可导出的知识网络。", "error");
    return;
  }

  const formatKey = exportFormat.value;
  const format = EXPORT_FORMATS[formatKey] || EXPORT_FORMATS.docx;
  const filename = buildExportFilename(formatKey);

  if (!state.apiMode) {
    if (formatKey !== "docx") {
      setExportStatus("离线打开编辑器时目前只支持导出 Word。请选择 Word，或通过本地服务打开后导出其他格式。", "error");
      return;
    }

    const docxBytes = buildKnowledgeDocx(state.tree, state.name);
    downloadBlob(filename, new Blob([docxBytes], { type: format.mime }));
    setExportStatus("新的 Word 文档已生成并开始下载。", "success");
    return;
  }

  await runExportAction(async () => {
    setExportStatus(`正在导出 ${format.label}...`);
    const result = await requestExport(formatKey);
    validateExportResponse(formatKey, result);
    downloadBlob(result.filename || filename, result.blob);
    setExportStatus(`${format.label} 文件已生成并开始下载。`, "success");
  });
});

function render() {
  ensureSelectedNode();
  updateExportPanel();
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
  selectionSummary.textContent = "当前未选择节点。";
  selectionSummary.classList.add("empty");
  updateExportPanel();
  toggleEditor(false);
  linkTargetLabel.textContent = "挂接到当前节点";
  linkingHint.textContent = "把另一个已导入项目的根节点复制挂接到当前选中节点下，并保留来源项目标识。";
}

function toggleEditor(enabled) {
  const disabled = !enabled || state.busy || state.exporting;
  nodeTitle.disabled = disabled;
  nodeNote.disabled = disabled;
  saveNode.disabled = disabled;
  addChild.disabled = disabled;
  addSibling.disabled = disabled;
  deleteNode.disabled = disabled;
  outlineLevelFilter.disabled = !enabled;
  expandSiblings.disabled = disabled;
  collapseSiblings.disabled = disabled;
  linkSourceProject.disabled = disabled || !state.apiMode;
  linkSourceRoot.disabled = disabled || !state.apiMode;
  attachProjectLink.disabled = disabled || !state.apiMode;
  exportFormat.disabled = disabled;
  exportFile.disabled = disabled;
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
    const title = document.createElement("span");
    title.className = "tree-title";
    title.textContent = formatNodeLabel(node);
    const badge = document.createElement("span");
    const hasNote = Boolean((node.note || "").trim());
    badge.className = `content-badge ${hasNote ? "has-content" : "no-content"}`;
    badge.textContent = hasNote ? "有正文" : "无正文";
    button.append(title, badge);
    button.addEventListener("click", () => {
      selectNode(node.id);
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
  const selected = getSelectedNode();
  if (!selected) {
    nodeTitle.value = "";
    nodeNote.value = "";
    updateNoteStatus(null);
    renderSelectedNodeDetails(null);
    linkTargetLabel.textContent = "挂接到项目根级";
    linkingHint.textContent = "当前未选择节点，挂接时会追加到项目根级。";
    return;
  }

  nodeTitle.value = selected.name;
  nodeNote.value = selected.note || "";
  updateNoteStatus(selected);
  renderSelectedNodeDetails(selected);
  linkTargetLabel.textContent = `挂接到：${selected.name}`;
  linkingHint.textContent = selected.linkedCopy && selected.sourceProjectName
    ? `当前节点来自 ${selected.sourceProjectName}，仍可继续作为挂接目标。`
    : "把另一个已导入项目的根节点复制挂接到当前选中节点下，并保留来源项目标识。";
}

function renderNetwork() {
  const selected = getSelectedNode();
  if (!selected) {
    networkCanvas.textContent = "请先从左侧目录中选择一个节点。";
    networkCanvas.classList.add("empty");
    networkMeta.textContent = "当前会显示所选节点的上级与下级关系。";
    networkMeta.classList.add("empty");
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
  button.setAttribute("aria-pressed", node.id === state.selectedId ? "true" : "false");
  button.innerHTML = `
    <strong>${escapeHtml(formatNodeLabel(node))}</strong>
    <span>${node.children.length} 个下级</span>
  `;
  button.addEventListener("click", () => {
    selectNode(node.id);
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

// Smoke note:
// Outline clicks and graph clicks must both flow through this single selection path,
// so the inspector, badges, and relation view always point at the same node.
function selectNode(nodeId) {
  if (!nodeId) {
    return;
  }
  if (!findNode(nodeId)) {
    return;
  }
  state.selectedId = nodeId;
  revealNodeInOutline(nodeId, true);
  render();
}

function getSelectedNode() {
  ensureSelectedNode();
  return findNode(state.selectedId);
}

function ensureSelectedNode() {
  if (state.selectedId && findNode(state.selectedId)) {
    return;
  }
  state.selectedId = state.tree[0]?.id || null;
}

function renderSelectedNodeDetails(selected) {
  if (!selected) {
    focusLabel.textContent = "未选择节点";
    selectionPath.textContent = "暂无路径";
    selectionSummary.textContent = "当前未选择节点。";
    selectionSummary.classList.add("empty");
    return;
  }

  const path = buildPath(selected.id).join(" / ");
  const parent = getAncestors(selected.id).at(-1);
  const childCount = selected.children.length;
  focusLabel.textContent = selected.name;
  selectionPath.textContent = path;
  selectionSummary.textContent = `当前节点：${selected.name}；上级：${parent?.name || "无"}；下级：${childCount} 个。`;
  selectionSummary.classList.remove("empty");
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
    sourceType: node.sourceType || node.source_type || "",
    metadata: node.metadata || {},
    sourceProjectId: node.sourceProjectId ?? node.source_project_id ?? null,
    sourceProjectName: node.sourceProjectName || null,
    sourceNodeId: node.sourceNodeId ?? node.source_node_id ?? null,
    linkedCopy: Boolean(node.linkedCopy),
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
  state.selectedId = preferredSelectedId;
  ensureSelectedNode();
  protectLargeOutline();
  revealNodeInOutline(state.selectedId, false);
  await loadAvailableProjects();
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

async function runExportAction(action) {
  if (state.busy || state.exporting) {
    return;
  }

  state.exporting = true;
  const originalLabel = exportFile.textContent;
  exportFile.textContent = "导出中...";
  toggleEditor(Boolean(state.tree.length));
  try {
    await action();
  } catch (error) {
    setExportStatus(error.message || "导出失败，请稍后重试。", "error");
  } finally {
    state.exporting = false;
    exportFile.textContent = originalLabel;
    toggleEditor(Boolean(state.tree.length));
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

async function loadAvailableProjects() {
  if (!state.apiMode) {
    state.availableProjects = [];
    renderLinkSourceProjectOptions();
    return;
  }

  try {
    const data = await apiRequest("/api/projects");
    state.availableProjects = (data.projects || []).filter((project) => project.id !== state.projectId);
  } catch (error) {
    state.availableProjects = [];
  }
  renderLinkSourceProjectOptions();
}

async function loadSourceProjectTree(projectId) {
  const parsedId = Number(projectId);
  if (!parsedId) {
    state.sourceProjectTree = [];
    renderLinkSourceRootOptions();
    return;
  }

  const data = await apiRequest(`/api/projects/${parsedId}`);
  state.sourceProjectTree = normalizeTree(data.project.tree || []);
  renderLinkSourceRootOptions();
}

function renderLinkSourceProjectOptions() {
  const currentValue = linkSourceProject.value;
  linkSourceProject.innerHTML = '<option value="">请选择来源项目</option>';
  state.availableProjects.forEach((project) => {
    const option = document.createElement("option");
    option.value = String(project.id);
    option.textContent = project.name;
    linkSourceProject.appendChild(option);
  });
  if (state.availableProjects.some((project) => String(project.id) === currentValue)) {
    linkSourceProject.value = currentValue;
  } else {
    linkSourceProject.value = "";
  }
  if (!linkSourceProject.value) {
    state.sourceProjectTree = [];
  }
  renderLinkSourceRootOptions();
}

function renderLinkSourceRootOptions() {
  const currentValue = linkSourceRoot.value;
  linkSourceRoot.innerHTML = '<option value="">整个来源项目</option>';
  state.sourceProjectTree.forEach((node) => {
    const option = document.createElement("option");
    option.value = String(node.id);
    option.textContent = node.name;
    linkSourceRoot.appendChild(option);
  });
  if (state.sourceProjectTree.some((node) => String(node.id) === currentValue)) {
    linkSourceRoot.value = currentValue;
  } else {
    linkSourceRoot.value = "";
  }
}

function formatNodeLabel(node) {
  if (node.linkedCopy && node.sourceProjectName) {
    return `${node.name} [来自 ${node.sourceProjectName}]`;
  }
  return node.name;
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
  target.sourceType = node.sourceType;
  target.metadata = node.metadata;
  target.parentId = node.parentId;
  target.position = node.position;
}

function countNodes(nodes) {
  return nodes.reduce((total, node) => total + 1 + countNodes(node.children), 0);
}

function updateExportPanel() {
  exportFilename.textContent = buildExportFilename(exportFormat.value);
  if (!state.tree.length) {
    setExportStatus("加载项目后即可导出当前知识网络。");
    return;
  }
  if (!state.apiMode && exportFormat.value !== "docx") {
    setExportStatus("当前是离线编辑状态，其他格式需要通过本地服务导出。");
    return;
  }
  if (!state.exporting && !exportStatus.dataset.tone) {
    const label = EXPORT_FORMATS[exportFormat.value]?.label || "文件";
    setExportStatus(`将导出当前知识网络为 ${label} 文件。`);
  }
}

function buildExportFilename(formatKey) {
  const format = EXPORT_FORMATS[formatKey] || EXPORT_FORMATS.docx;
  return `${sanitizeName(state.name || "knowledge-network")}.${format.extension}`;
}

function setExportStatus(message, tone = "neutral") {
  exportStatus.textContent = message;
  exportStatus.dataset.tone = tone === "neutral" ? "" : tone;
}

async function requestExport(formatKey) {
  const url = `/api/projects/${state.projectId}/export?format=${encodeURIComponent(formatKey)}`;
  const response = await fetch(url);
  const contentType = response.headers.get("Content-Type") || "";
  if (!response.ok) {
    const data = contentType.includes("application/json") ? await response.json() : {};
    const message = data.error?.message || data.error || "导出失败。";
    throw new Error(message);
  }

  const blob = await response.blob();
  return {
    blob,
    filename: parseDownloadFilename(response.headers.get("Content-Disposition")) || buildExportFilename(formatKey),
    contentType: response.headers.get("Content-Type") || "",
  };
}

function validateExportResponse(formatKey, result) {
  if (formatKey === "docx") {
    return;
  }

  const requested = EXPORT_FORMATS[formatKey];
  const returnedExt = getFilenameExtension(result.filename);
  const returnedType = result.contentType.toLowerCase();
  if (returnedExt === requested.extension) {
    return;
  }
  if (returnedType.startsWith(requested.mime)) {
    return;
  }
  if (returnedExt === "docx" || returnedType.includes("wordprocessingml")) {
    throw new Error(`当前服务返回的仍是 Word 文件，说明 ${requested.label} 导出接口还未接入。`);
  }
}

function parseDownloadFilename(contentDisposition) {
  if (!contentDisposition) {
    return "";
  }

  const encodedMatch = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (encodedMatch) {
    try {
      return decodeURIComponent(encodedMatch[1]);
    } catch (error) {
      return encodedMatch[1];
    }
  }

  const plainMatch = contentDisposition.match(/filename="([^"]+)"/i);
  return plainMatch ? plainMatch[1] : "";
}

function getFilenameExtension(filename) {
  const match = String(filename || "").toLowerCase().match(/\.([^.]+)$/);
  return match ? match[1] : "";
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

function normalizeNoteInput(note) {
  return String(note).replace(/\r\n?/g, "\n");
}

function updateNoteStatus(node) {
  if (!noteStatus) {
    return;
  }

  if (!node) {
    noteStatus.textContent = "未选择节点";
    return;
  }

  const note = node.note || "";
  const lines = note ? note.split("\n").length : 0;
  noteStatus.textContent = note ? `${note.length} 字，${lines} 行正文` : "当前节点还没有正文";
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
        .split(/\r?\n/)
        .filter((line) => line.trim())
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
