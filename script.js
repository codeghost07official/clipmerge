(function () {
  "use strict";

  const THEME_KEY = "clipmerge-theme";
  const STATUS = {
    ready: "Ready",
    keywords: "Generating keywords...",
    clips: "Downloading clips...",
    merging: "Merging clips...",
    finished: "Finished"
  };

  const elements = {
    html: document.documentElement,
    form: document.querySelector("#clipmerge-form"),
    prompt: document.querySelector("#prompt"),
    duration: document.querySelector("#duration"),
    promptError: document.querySelector("#prompt-error"),
    durationError: document.querySelector("#duration-error"),
    statusMessage: document.querySelector("#status-message"),
    progressBar: document.querySelector("#progress-bar"),
    themeToggle: document.querySelector("[data-theme-toggle]"),
    themeLabel: document.querySelector("[data-theme-label]"),
    actionButtons: document.querySelectorAll("[data-action]")
  };

  function getStoredTheme() {
    const savedTheme = localStorage.getItem(THEME_KEY);

    if (savedTheme === "light" || savedTheme === "dark") {
      return savedTheme;
    }

    return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }

  function applyTheme(theme) {
    elements.html.dataset.theme = theme;
    elements.themeLabel.textContent = theme === "dark" ? "Dark" : "Light";
    elements.themeToggle.setAttribute("aria-label", `Switch to ${theme === "dark" ? "light" : "dark"} theme`);
  }

  function toggleTheme() {
    const nextTheme = elements.html.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem(THEME_KEY, nextTheme);
    applyTheme(nextTheme);
  }

  function setStatus(message) {
    elements.statusMessage.textContent = message;
  }

  function setProgress(value) {
    const safeValue = Math.max(0, Math.min(100, Number(value) || 0));
    elements.progressBar.style.width = `${safeValue}%`;
    elements.progressBar.setAttribute("aria-valuenow", String(safeValue));
  }

  function resetProgress() {
    setProgress(0);
  }

  function getFormData() {
    return {
      prompt: elements.prompt.value.trim(),
      duration: Number(elements.duration.value)
    };
  }

  function validateInputs() {
    const data = getFormData();
    let isValid = true;

    elements.promptError.textContent = "";
    elements.durationError.textContent = "";

    if (data.prompt.length < 8) {
      elements.promptError.textContent = "Describe the video in at least 8 characters.";
      isValid = false;
    }

    if (!Number.isFinite(data.duration) || data.duration < 1 || data.duration > 600) {
      elements.durationError.textContent = "Enter a video length between 1 and 600 seconds.";
      isValid = false;
    }

    return isValid;
  }

  function setButtonLoading(button, isLoading) {
    button.classList.toggle("is-loading", isLoading);
    button.disabled = isLoading;
    button.setAttribute("aria-busy", String(isLoading));
  }

  function setAllButtonsDisabled(isDisabled) {
    elements.actionButtons.forEach((button) => {
      button.disabled = isDisabled;
    });
  }

  function wait(ms) {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
  }

  async function previewVideo(payload) {
    console.info("Preview API placeholder:", payload);
    await runPlaceholderFlow();
    return { ok: true, type: "preview" };
  }

  async function downloadMp4(payload) {
    console.info("Download API placeholder:", payload);
    await runPlaceholderFlow();
    return { ok: true, type: "download" };
  }

  async function runPlaceholderFlow() {
    const steps = [
      [STATUS.keywords, 25],
      [STATUS.clips, 55],
      [STATUS.merging, 82],
      [STATUS.finished, 100]
    ];

    resetProgress();

    for (const [message, progress] of steps) {
      setStatus(message);
      setProgress(progress);
      await wait(420);
    }
  }

  async function handleAction(event) {
    const button = event.currentTarget;
    const action = button.dataset.action;

    if (!validateInputs()) {
      setStatus(STATUS.ready);
      resetProgress();
      return;
    }

    const payload = getFormData();

    setAllButtonsDisabled(true);
    setButtonLoading(button, true);

    try {
      if (action === "preview") {
        await previewVideo(payload);
      }

      if (action === "download") {
        await downloadMp4(payload);
      }
    } catch (error) {
      console.error(error);
      setStatus("Something went wrong. Try again.");
    } finally {
      setButtonLoading(button, false);
      setAllButtonsDisabled(false);
    }
  }

  function initProgressBar() {
    elements.progressBar.setAttribute("role", "progressbar");
    elements.progressBar.setAttribute("aria-label", "Generation progress");
    elements.progressBar.setAttribute("aria-valuemin", "0");
    elements.progressBar.setAttribute("aria-valuemax", "100");
    setProgress(0);
  }

  function bindEvents() {
    elements.themeToggle.addEventListener("click", toggleTheme);
    elements.actionButtons.forEach((button) => button.addEventListener("click", handleAction));
    elements.prompt.addEventListener("input", validateInputs);
    elements.duration.addEventListener("input", validateInputs);
  }

  function init() {
    applyTheme(getStoredTheme());
    initProgressBar();
    setStatus(STATUS.ready);
    bindEvents();
  }

  window.ClipMerge = {
    setStatus,
    setProgress,
    resetProgress,
    previewVideo,
    downloadMp4
  };

  init();
})();
