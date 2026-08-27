const state = {graphs: [], controller: null, timer: null};

const graphProfiles = {
  chatbot: {label: "通用研究助手", description: "用于研究讨论、信息梳理和问题分析；结论不构成交易指令。", placeholder: "例如：梳理这项研究假设需要哪些证据，并列出主要风险"},
  data_agent: {label: "只读数据分析", description: "仅执行单条只读 MySQL 查询，用于数据检索与结果总结。", placeholder: "例如：查询最近一周的数据并总结主要变化"},
  research_agent: {label: "联网深度研究", description: "规划检索、并发搜索并生成带来源 ID 的结构化研究报告。", placeholder: "例如：研究生成式 AI 对软件行业商业模式的影响，并说明主要证据与局限"},
};

const byId = (id) => document.getElementById(id);
const elements = {
  status: byId("service-status"), modelName: byId("model-name"), modelEndpoint: byId("model-endpoint"),
  graphCount: byId("graph-count"), graphNames: byId("graph-names"), requestTimeout: byId("request-timeout"),
  form: byId("invoke-form"), graphSelect: byId("graph-select"), graphDescription: byId("graph-description"),
  modelSelect: byId("model-select"), threadId: byId("thread-id"), prompt: byId("prompt"),
  submit: byId("submit-button"), cancel: byId("cancel-button"), retryRuntime: byId("retry-runtime"),
  newThread: byId("new-thread"), error: byId("form-error"), empty: byId("empty-state"),
  content: byId("result-content"), answer: byId("answer-text"), raw: byId("raw-json"), elapsed: byId("elapsed-time"),
  imageSection: byId("image-section"), gallery: byId("image-gallery"), copyAnswer: byId("copy-answer"),
  resultGraph: byId("result-graph"), resultModel: byId("result-model"), resultThread: byId("result-thread"),
  resultFinished: byId("result-finished"), currentUser: byId("current-user"), adminLink: byId("admin-link"), logout: byId("logout"),
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

function graphProfile(name) {
  return graphProfiles[name] || {label: name, description: "调用已注册的研究 Graph。", placeholder: "请输入问题或分析要求"};
}

function updateGraphGuidance() {
  const profile = graphProfile(elements.graphSelect.value);
  elements.graphDescription.textContent = profile.description;
  elements.prompt.placeholder = profile.placeholder;
}

function setFormAvailable(available) {
  [elements.graphSelect, elements.modelSelect, elements.threadId, elements.prompt, elements.newThread, elements.submit]
    .forEach((element) => { element.disabled = !available; });
}

function extractText(value) {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map((item) => {
    if (typeof item === "string") return item;
    if (item && typeof item === "object") return item.text || item.content || JSON.stringify(item);
    return String(item ?? "");
  }).join("\n");
  return value == null ? "" : JSON.stringify(value, null, 2);
}

function latestAnswer(result) {
  const messages = Array.isArray(result?.messages) ? result.messages : [];
  const preferred = [...messages].reverse().find((message) => ["ai", "assistant"].includes(message?.type || message?.role));
  const fallback = messages.at(-1);
  return extractText(preferred?.content ?? fallback?.content ?? result);
}

function imagePaths(result) {
  const matches = JSON.stringify(result).match(/\/images\/[A-Za-z0-9._/-]+\.(?:png|jpg|jpeg|webp|gif)/gi) || [];
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
    image.alt = "数据分析附件或图表";
    image.loading = "lazy";
    caption.textContent = path;
    figure.append(image, caption);
    elements.gallery.append(figure);
  });
}

async function loadRuntime() {
  elements.retryRuntime.hidden = true;
  elements.error.textContent = "";
  setFormAvailable(false);
  try {
    const [healthResponse, runtimeResponse] = await Promise.all([fetch("/health"), fetch("/runtime")]);
    if (!healthResponse.ok || !runtimeResponse.ok) throw new Error("服务状态读取失败");
    const health = await healthResponse.json();
    const runtime = await runtimeResponse.json();
    state.graphs = health.graphs || runtime.graphs || [];
    const models = Array.isArray(runtime.models) ? runtime.models : [];

    elements.modelName.textContent = runtime.model;
    elements.modelEndpoint.textContent = runtime.model_endpoint === "custom" ? "自定义兼容端点" : "Anthropic 官方端点";
    elements.graphCount.textContent = String(state.graphs.length);
    elements.graphNames.textContent = state.graphs.map((name) => graphProfile(name).label).join(" · ") || "暂无";
    elements.requestTimeout.textContent = `${runtime.request_timeout_seconds} 秒`;

    elements.graphSelect.replaceChildren();
    state.graphs.forEach((name) => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = `${graphProfile(name).label} · ${name}`;
      elements.graphSelect.append(option);
    });
    elements.modelSelect.replaceChildren();
    models.forEach((name) => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      option.selected = name === runtime.model;
      elements.modelSelect.append(option);
    });
    updateGraphGuidance();
    setFormAvailable(state.graphs.length > 0 && models.length > 0);
    setStatus(true, "服务运行正常");
  } catch (error) {
    setStatus(false, "服务不可用");
    elements.error.textContent = `${error.message}，请检查服务后重试。`;
    elements.retryRuntime.hidden = false;
  }
}

async function invoke(event) {
  event.preventDefault();
  elements.error.textContent = "";
  elements.submit.disabled = true;
  elements.submit.textContent = "运行中…";
  elements.cancel.hidden = false;
  const startedAt = performance.now();
  state.controller = new AbortController();
  const updateElapsed = () => { elements.elapsed.textContent = `已运行 ${((performance.now() - startedAt) / 1000).toFixed(1)} 秒`; };
  updateElapsed();
  state.timer = window.setInterval(updateElapsed, 100);

  try {
    const response = await fetch(`/graphs/${encodeURIComponent(elements.graphSelect.value)}/invoke`, {
      method: "POST", headers: {"Content-Type": "application/json"}, signal: state.controller.signal,
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
    elements.resultGraph.textContent = graphProfile(elements.graphSelect.value).label;
    elements.resultModel.textContent = elements.modelSelect.value;
    elements.resultThread.textContent = elements.threadId.value.trim();
    elements.resultFinished.textContent = new Intl.DateTimeFormat("zh-CN", {dateStyle: "medium", timeStyle: "medium"}).format(new Date());
    renderImages(imagePaths(payload));
    elements.elapsed.textContent = `${((performance.now() - startedAt) / 1000).toFixed(1)} 秒完成`;
  } catch (error) {
    if (error.name === "AbortError") {
      elements.error.textContent = "请求已取消。服务端任务可能仍会继续执行，请稍后检查相关运行状态。";
      elements.elapsed.textContent = "已取消";
    } else {
      elements.error.textContent = error.message;
      elements.elapsed.textContent = "运行失败";
    }
  } finally {
    window.clearInterval(state.timer);
    state.timer = null;
    state.controller = null;
    elements.submit.disabled = false;
    elements.submit.textContent = "开始运行";
    elements.cancel.hidden = true;
  }
}

elements.threadId.value = createThreadId();
elements.newThread.addEventListener("click", () => { elements.threadId.value = createThreadId(); });
elements.form.addEventListener("submit", invoke);
elements.graphSelect.addEventListener("change", updateGraphGuidance);
elements.cancel.addEventListener("click", () => state.controller?.abort());
elements.retryRuntime.addEventListener("click", loadRuntime);
elements.copyAnswer.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(elements.answer.textContent);
    elements.copyAnswer.textContent = "已复制";
    window.setTimeout(() => { elements.copyAnswer.textContent = "复制结果"; }, 1600);
  } catch (error) {
    elements.error.textContent = "复制失败，请手动选择结果文本。";
  }
});
elements.logout.addEventListener("click", async () => {
  await fetch("/auth/logout", {method: "POST"});
  window.location.replace("/login");
});
loadIdentity();
loadRuntime();
