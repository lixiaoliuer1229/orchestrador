const state = {
  graphs: [],
};

const elements = {
  status: document.getElementById("service-status"),
  modelName: document.getElementById("model-name"),
  modelEndpoint: document.getElementById("model-endpoint"),
  graphCount: document.getElementById("graph-count"),
  graphNames: document.getElementById("graph-names"),
  requestTimeout: document.getElementById("request-timeout"),
  form: document.getElementById("invoke-form"),
  graphSelect: document.getElementById("graph-select"),
  modelSelect: document.getElementById("model-select"),
  threadId: document.getElementById("thread-id"),
  prompt: document.getElementById("prompt"),
  submit: document.getElementById("submit-button"),
  newThread: document.getElementById("new-thread"),
  error: document.getElementById("form-error"),
  empty: document.getElementById("empty-state"),
  content: document.getElementById("result-content"),
  answer: document.getElementById("answer-text"),
  raw: document.getElementById("raw-json"),
  elapsed: document.getElementById("elapsed-time"),
  imageSection: document.getElementById("image-section"),
  gallery: document.getElementById("image-gallery"),
  currentUser: document.getElementById("current-user"),
  adminLink: document.getElementById("admin-link"),
  logout: document.getElementById("logout"),
};

async function loadIdentity() {
  const response = await fetch("/auth/me");
  if (response.status === 401) return window.location.replace("/login");
  const user = await response.json();
  elements.currentUser.textContent = user.username;
  elements.adminLink.hidden = user.role !== "admin";
}

function createThreadId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `thread-${Date.now()}`;
}

function setStatus(ok, message) {
  elements.status.className = `status ${ok ? "status-ok" : "status-error"}`;
  elements.status.lastElementChild.textContent = message;
}

function extractText(value) {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    return value.map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object") return item.text || item.content || JSON.stringify(item);
      return String(item ?? "");
    }).join("\n");
  }
  return value == null ? "" : JSON.stringify(value, null, 2);
}

function latestAnswer(result) {
  const messages = Array.isArray(result?.messages) ? result.messages : [];
  const preferred = [...messages].reverse().find((message) => {
    const type = message?.type || message?.role;
    return type === "ai" || type === "assistant";
  });
  const fallback = messages.at(-1);
  return extractText(preferred?.content ?? fallback?.content ?? result);
}

function imagePaths(result) {
  const serialized = JSON.stringify(result);
  const matches = serialized.match(/\/images\/[A-Za-z0-9._/-]+\.(?:png|jpg|jpeg|webp|gif)/gi) || [];
  return [...new Set(matches)];
}

function renderImages(paths) {
  elements.gallery.replaceChildren();
  elements.imageSection.hidden = paths.length === 0;
  paths.forEach((path) => {
    const figure = document.createElement("figure");
    const image = document.createElement("img");
    const caption = document.createElement("figcaption");
    image.src = path;
    image.alt = "数据分析生成图表";
    image.loading = "lazy";
    caption.textContent = path;
    figure.append(image, caption);
    elements.gallery.append(figure);
  });
}

async function loadRuntime() {
  try {
    const [healthResponse, runtimeResponse] = await Promise.all([
      fetch("/health"),
      fetch("/runtime"),
    ]);
    if (!healthResponse.ok || !runtimeResponse.ok) throw new Error("服务状态读取失败");
    const health = await healthResponse.json();
    const runtime = await runtimeResponse.json();
    state.graphs = health.graphs || runtime.graphs || [];

    elements.modelName.textContent = runtime.model;
    elements.modelEndpoint.textContent = runtime.model_endpoint === "custom" ? "自定义兼容端点" : "Anthropic 官方端点";
    elements.graphCount.textContent = String(state.graphs.length);
    elements.graphNames.textContent = state.graphs.join(" · ") || "暂无";
    elements.requestTimeout.textContent = `${runtime.request_timeout_seconds} 秒`;

    elements.graphSelect.replaceChildren();
    state.graphs.forEach((name) => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      elements.graphSelect.append(option);
    });
    elements.modelSelect.replaceChildren();
    runtime.models.forEach((name) => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      option.selected = name === runtime.model;
      elements.modelSelect.append(option);
    });
    setStatus(true, "服务运行正常");
  } catch (error) {
    setStatus(false, "服务不可用");
    elements.error.textContent = error.message;
  }
}

async function invoke(event) {
  event.preventDefault();
  elements.error.textContent = "";
  elements.submit.disabled = true;
  elements.submit.textContent = "运行中…";
  elements.elapsed.textContent = "正在执行";
  const startedAt = performance.now();

  try {
    const response = await fetch(`/graphs/${encodeURIComponent(elements.graphSelect.value)}/invoke`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        input: {messages: [{role: "user", content: elements.prompt.value.trim()}]},
        config: {configurable: {thread_id: elements.threadId.value.trim()}},
        model: elements.modelSelect.value,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `请求失败：${response.status}`);

    elements.empty.hidden = true;
    elements.content.hidden = false;
    elements.answer.textContent = latestAnswer(payload);
    elements.raw.textContent = JSON.stringify(payload, null, 2);
    renderImages(imagePaths(payload));
    elements.elapsed.textContent = `${((performance.now() - startedAt) / 1000).toFixed(1)} 秒`;
  } catch (error) {
    elements.error.textContent = error.message;
    elements.elapsed.textContent = "运行失败";
  } finally {
    elements.submit.disabled = false;
    elements.submit.textContent = "开始运行";
  }
}

elements.threadId.value = createThreadId();
elements.newThread.addEventListener("click", () => {
  elements.threadId.value = createThreadId();
});
elements.form.addEventListener("submit", invoke);
elements.logout.addEventListener("click", async () => {
  await fetch("/auth/logout", {method: "POST"});
  window.location.replace("/login");
});
loadIdentity();
loadRuntime();
