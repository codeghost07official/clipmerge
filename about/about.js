(function () {
  "use strict";

  const THEME_KEY = "clipmerge-theme";
  const html = document.documentElement;
  const themeToggle = document.querySelector("[data-theme-toggle]");
  const themeLabel = document.querySelector("[data-theme-label]");

  function getStoredTheme() {
    const savedTheme = localStorage.getItem(THEME_KEY);

    if (savedTheme === "light" || savedTheme === "dark") {
      return savedTheme;
    }

    return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }

  function applyTheme(theme) {
    html.dataset.theme = theme;
    themeLabel.textContent = theme === "dark" ? "Dark" : "Light";
    themeToggle.setAttribute("aria-label", `Switch to ${theme === "dark" ? "light" : "dark"} theme`);
  }

  function toggleTheme() {
    const nextTheme = html.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem(THEME_KEY, nextTheme);
    applyTheme(nextTheme);
  }

  applyTheme(getStoredTheme());
  themeToggle.addEventListener("click", toggleTheme);
})();
