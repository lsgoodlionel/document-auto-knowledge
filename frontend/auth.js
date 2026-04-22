(() => {
  const mount = document.querySelector("#login-app");

  boot();

  async function boot() {
    if (!window.AuthClient) {
      renderMessage("登录脚本加载失败。", "error");
      return;
    }

    const authState = await window.AuthClient.getCurrentUser();
    if (authState.status === "authenticated" && authState.user) {
      renderLoggedIn(authState.user);
      return;
    }

    renderLoginForm(authState);
  }

  function renderLoginForm(authState) {
    mount.innerHTML = `
      <div class="panel-head">
        <div>
          <h2>账号登录</h2>
          <p class="section-note">${describeAuthState(authState)}</p>
        </div>
        <a class="ghost button-link" href="./">返回首页</a>
      </div>
      <form id="login-form" class="form-stack">
        <label class="field">
          <span>用户名</span>
          <input id="login-username" name="username" type="text" autocomplete="username" placeholder="请输入用户名" />
        </label>
        <label class="field">
          <span>密码</span>
          <input id="login-password" name="password" type="password" autocomplete="current-password" placeholder="请输入密码" />
        </label>
        <div class="actions wrap">
          <button id="login-submit" class="primary" type="submit">登录</button>
          <a class="ghost button-link" href="./">继续浏览首页</a>
        </div>
        <p id="login-status" class="status">请输入账号信息。</p>
      </form>
    `;

    const form = document.querySelector("#login-form");
    const username = document.querySelector("#login-username");
    const password = document.querySelector("#login-password");
    const status = document.querySelector("#login-status");
    const submit = document.querySelector("#login-submit");

    if (authState.status === "unavailable") {
      submit.disabled = true;
      status.textContent = "当前分支还没有登录后端接口，暂时不能真正发起登录。";
      status.classList.add("error");
      return;
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      status.classList.remove("success", "error");
      status.textContent = "正在登录...";
      submit.disabled = true;

      try {
        await window.AuthClient.login(username.value.trim(), password.value);
        status.classList.add("success");
        status.textContent = "登录成功，正在跳转。";
        window.location.assign(window.AuthClient.consumeRedirect("./"));
      } catch (error) {
        status.classList.add("error");
        status.textContent = error.message || "登录失败。";
      } finally {
        submit.disabled = false;
      }
    });
  }

  function renderLoggedIn(user) {
    mount.innerHTML = `
      <div class="panel-head">
        <div>
          <h2>已登录</h2>
          <p class="section-note">当前账号：${escapeHtml(user.displayName || user.username || "本地用户")}</p>
        </div>
        <a class="ghost button-link" href="./">返回首页</a>
      </div>
      <p class="status success">已检测到有效会话，可以继续返回首页或进入之前的跳转目标。</p>
      <div class="actions wrap">
        <button id="login-continue" class="primary" type="button">继续</button>
      </div>
    `;

    document.querySelector("#login-continue").addEventListener("click", () => {
      window.location.assign(window.AuthClient.consumeRedirect("./"));
    });
  }

  function renderMessage(message, tone = "neutral") {
    mount.innerHTML = `<p class="status ${tone === "neutral" ? "" : tone}">${escapeHtml(message)}</p>`;
  }

  function describeAuthState(authState) {
    if (authState.status === "offline") {
      return "当前是离线打开页面，登录页需要通过本地服务访问。";
    }
    if (authState.status === "network-error") {
      return "暂时无法连接本地服务，请确认它正在运行。";
    }
    if (authState.status === "unavailable") {
      return "前端鉴权流已准备好，等待登录后端接口合入。";
    }
    return "未登录时会跳回这里，登录成功后自动返回原页面。";
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
