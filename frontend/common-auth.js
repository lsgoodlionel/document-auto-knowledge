(() => {
  const REDIRECT_KEY = "knowledge-auth-redirect";

  function canUseBackend() {
    return window.location.protocol === "http:" || window.location.protocol === "https:";
  }

  async function request(path, options = {}) {
    const response = await fetch(path, {
      method: options.method || "GET",
      headers: options.body ? { "Content-Type": "application/json" } : {},
      body: options.body ? JSON.stringify(options.body) : undefined,
      credentials: "same-origin",
    });
    const contentType = response.headers.get("Content-Type") || "";
    const data = contentType.includes("application/json") ? await response.json() : {};
    return { response, data };
  }

  async function getCurrentUser() {
    if (!canUseBackend()) {
      return { status: "offline", available: false, user: null };
    }

    try {
      const { response, data } = await request("/api/me");
      if (response.status === 404) {
        return { status: "unavailable", available: false, user: null };
      }
      if (response.status === 401) {
        return { status: "guest", available: true, user: null };
      }
      if (!response.ok) {
        throw new Error(data.error?.message || "读取当前用户失败。");
      }
      return {
        status: "authenticated",
        available: true,
        user: data.user || data.me || null,
      };
    } catch (error) {
      return { status: "network-error", available: false, user: null, error };
    }
  }

  async function login(username, password) {
    const { response, data } = await request("/api/login", {
      method: "POST",
      body: { username, password },
    });
    if (response.status === 404) {
      throw createAuthError("auth_unavailable", "登录后端尚未合入当前分支。");
    }
    if (!response.ok) {
      throw createAuthError(data.error?.code || "login_failed", data.error?.message || "登录失败。");
    }
    return data.user || data.me || null;
  }

  async function logout() {
    const { response, data } = await request("/api/logout", { method: "POST" });
    if (response.status === 404) {
      throw createAuthError("auth_unavailable", "退出接口尚未合入当前分支。");
    }
    if (!response.ok) {
      throw createAuthError(data.error?.code || "logout_failed", data.error?.message || "退出失败。");
    }
    return true;
  }

  function createAuthError(code, message) {
    const error = new Error(message);
    error.code = code;
    return error;
  }

  function setRedirect(path) {
    sessionStorage.setItem(REDIRECT_KEY, normalizeRedirect(path));
  }

  function consumeRedirect(fallback = "./") {
    const stored = sessionStorage.getItem(REDIRECT_KEY);
    if (stored) {
      sessionStorage.removeItem(REDIRECT_KEY);
      return stored;
    }
    const queryRedirect = new URLSearchParams(window.location.search).get("redirect");
    return normalizeRedirect(queryRedirect || fallback);
  }

  function normalizeRedirect(path) {
    if (!path || /^https?:\/\//i.test(path)) {
      return "./";
    }
    return path.startsWith("/") || path.startsWith(".") ? path : `./${path}`;
  }

  function openLoginPage(redirectPath) {
    const redirect = normalizeRedirect(redirectPath || `${window.location.pathname}${window.location.search}`);
    setRedirect(redirect);
    window.location.assign(`./login.html?redirect=${encodeURIComponent(redirect)}`);
  }

  function handleUnauthorized(redirectPath) {
    openLoginPage(redirectPath);
  }

  window.AuthClient = {
    REDIRECT_KEY,
    canUseBackend,
    getCurrentUser,
    login,
    logout,
    setRedirect,
    consumeRedirect,
    openLoginPage,
    handleUnauthorized,
  };
})();
