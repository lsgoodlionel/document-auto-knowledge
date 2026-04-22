(() => {
  const page = document.body?.dataset?.appPage || "home";
  if (page === "login" || !window.AuthClient || !window.AuthClient.canUseBackend()) {
    return;
  }

  document.documentElement.classList.add("auth-gating");
  window.AuthClient.requireAuthenticated(`${window.location.pathname}${window.location.search}`).then((authState) => {
    if (authState.status === "authenticated" && authState.user) {
      document.documentElement.classList.remove("auth-gating");
    }
  });
})();
