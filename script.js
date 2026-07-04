(function () {
  "use strict";

  const THEME_KEY = "clipmerge-theme";
  const POLL_INTERVAL_MS = 1000;
  const STATUS = {
    ready: "Ready",
    finished: "Finished."
  };

  const elements = {
    html: document.documentElement,
    form: document.querySelector("#clipmerge-form"),
    prompt: document.querySelector("#prompt"),
    duration: document.querySelector("#duration"),
    orientation: document.querySelector("#orientation"),
    promptError: document.querySelector("#prompt-error"),
    durationError: document.querySelector("#duration-error"),
    statusMessage: document.querySelector("#status-message"),
    progressBar: document.querySelector("#progress-bar"),
    themeToggle: document.querySelector("[data-theme-toggle]"),
    themeLabel: document.querySelector("[data-theme-label]"),
    actionButtons: document.querySelectorAll("[data-action]"),
    previewPanel: document.querySelector("#preview-panel"),
    videoPreview: document.querySelector("#video-preview"),
    previewDownload: document.querySelector("#preview-download")
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

  function setPreviewOrientation(orientation) {
    elements.previewPanel.dataset.orientation = orientation || elements.orientation.value || "portrait";
  }

  function hidePreview() {
    elements.previewPanel.hidden = true;
    elements.videoPreview.removeAttribute("src");
    elements.videoPreview.load();
    elements.previewDownload.removeAttribute("href");
    setPreviewOrientation(elements.orientation.value);
  }

  function showPreview(videoUrl, downloadUrl, orientation) {
    setPreviewOrientation(orientation);
    elements.videoPreview.src = videoUrl;
    elements.previewDownload.href = downloadUrl;
    elements.previewPanel.hidden = false;
    elements.videoPreview.load();
  }

  function triggerDownload(downloadUrl) {
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = "";
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  function getFormData() {
    return {
      prompt: elements.prompt.value.trim(),
      duration: Number(elements.duration.value),
      orientation: elements.orientation.value
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

  async function requestJson(url, options) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(data.error || "The server could not complete the request.");
    }

    return data;
  }

  async function startGeneration(payload) {
    return requestJson("/api/generate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });
  }

  async function pollJob(jobId) {
    while (true) {
      const job = await requestJson(`/api/status/${jobId}`);
      setStatus(job.status || STATUS.ready);
      setProgress(job.progress || 0);

      if (job.state === "finished") {
        return job;
      }

      if (job.state === "error") {
        throw new Error(job.error || "Video generation failed.");
      }

      await wait(POLL_INTERVAL_MS);
    }
  }

  async function generateVideo(payload) {
    const startedJob = await startGeneration(payload);
    setStatus(startedJob.status || "Generating keywords...");
    setProgress(startedJob.progress || 0);
    return pollJob(startedJob.job_id);
  }

  async function previewVideo(payload) {
    const job = await generateVideo(payload);
    showPreview(job.video_url, job.download_url, job.orientation || payload.orientation);
    return job;
  }

  async function downloadMp4(payload) {
    const job = await generateVideo(payload);
    showPreview(job.video_url, job.download_url, job.orientation || payload.orientation);
    triggerDownload(job.download_url);
    return job;
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

    hidePreview();
    setAllButtonsDisabled(true);
    setButtonLoading(button, true);

    try {
      let job = null;

      if (action === "preview") {
        job = await previewVideo(payload);
      }

      if (action === "download") {
        job = await downloadMp4(payload);
      }

      setStatus((job && job.status) || STATUS.finished);
      setProgress(100);
    } catch (error) {
      console.error(error);
      setStatus(error.message || "Something went wrong. Try again.");
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
    elements.orientation.addEventListener("change", hidePreview);
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
