(() => {
const page = document.body?.dataset?.appPage || "home";
const loginHref = "./login.html";
const menuHref = page === "home" ? "#auth-status-panel" : "./index.html#auth-status-panel";
const root = document.createElement("header");
root.className = "site-nav-shell";
root.innerHTML = `
  <div class="site-nav">
    <a class="brand-mark" href="./index.html" aria-label="文档自动知识库系统首页">
      <span class="brand-badge">V3</span>
      <span class="brand-copy">
        <strong>文档自动知识库系统</strong>
        <small>Document Auto Knowledge System</small>
      </span>
    </a>
    <nav class="site-links" aria-label="主导航">
      <a class="site-link ${page === "home" ? "active" : ""}" href="./index.html">首页</a>
      <a class="site-link ${page === "network" ? "active" : ""}" href="./editor.html">知识网络</a>
      <a class="site-link ${page === "login" ? "active" : ""}" href="${loginHref}">登录入口</a>
      <a class="site-link" href="${menuHref}">用户菜单</a>
    </nav>
  </div>
`;
document.body.prepend(root);
})();
