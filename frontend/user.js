(() => {
  const mount = document.querySelector("#user-app");

  boot();

  async function boot() {
    if (!window.AuthClient) {
      renderMessage("用户菜单脚本加载失败。", "error");
      return;
    }

    const authState = await window.AuthClient.getCurrentUser();
    if (authState.status === "authenticated" && authState.user) {
      renderUserPanel(authState.user);
      return;
    }

    window.location.assign("./login.html?redirect=%2Fuser.html");
  }

  function renderUserPanel(user) {
    mount.innerHTML = `
      <div class="auth-panel-head">
        <div>
          <p class="eyebrow">PROFILE</p>
          <h2>${escapeHtml(user.displayName || user.username || "本地用户")}</h2>
          <p class="section-note">当前会话已生效，你可以继续进入首页、知识网络，或在这里安全退出。</p>
        </div>
        <span class="auth-chip">已登录</span>
      </div>

      <div class="auth-story-grid auth-menu-grid">
        <div class="auth-story-card">
          <strong>用户名</strong>
          <span>${escapeHtml(user.username || "admin")}</span>
        </div>
        <div class="auth-story-card">
          <strong>显示名称</strong>
          <span>${escapeHtml(user.displayName || user.username || "本地管理员")}</span>
        </div>
        <div class="auth-story-card">
          <strong>会话状态</strong>
          <span>本地单机会话有效，可继续访问受保护页面。</span>
        </div>
      </div>

      <div class="actions wrap auth-menu-actions">
        <a class="primary button-link" href="./index.html">进入首页</a>
        <a class="ghost button-link" href="./editor.html">进入知识网络</a>
        <a class="ghost button-link" href="./login.html">切换登录页</a>
        <button id="logout-button" class="ghost danger" type="button">退出登录</button>
      </div>

      <p id="user-status" class="status">你当前处于已登录状态。</p>
    `;

    document.querySelector("#logout-button")?.addEventListener("click", async () => {
      const status = document.querySelector("#user-status");
      try {
        status.textContent = "正在退出登录...";
        await window.AuthClient.logout();
        status.className = "status success";
        status.textContent = "已退出登录，正在返回登录页。";
        window.location.assign("./login.html");
      } catch (error) {
        status.className = "status error";
        status.textContent = error.message || "退出登录失败。";
      }
    });
  }

  function renderMessage(message, tone = "neutral") {
    mount.innerHTML = `<p class="status ${tone === "neutral" ? "" : tone}">${escapeHtml(message)}</p>`;
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }
})();
