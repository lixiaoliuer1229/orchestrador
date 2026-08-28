const state = {graphs: [], controller: null, timer: null, runOffset: 0, runPageSize: 20, currentRunId: null};

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
  openCurrentRun: byId("open-current-run"), refreshRuns: byId("refresh-runs"), loadMoreRuns: byId("load-more-runs"),
  runList: byId("run-list"), runDetail: byId("run-detail"), archiveError: byId("archive-error"),
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

function formatDate(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {dateStyle: "medium", timeStyle: "medium"}).format(new Date(value));
}

function statusLabel(status) {
  return {running: "运行中", completed: "已完成", failed: "失败", supported: "已支持", partially_supported: "部分支持", conflicting: "证据冲突", unsupported: "不支持", unverified: "未验证", stale: "已过期"}[status] || status || "未知";
}

function appendInline(parent, text) {
  const pattern = /\[([^\]]+)\]/g;
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    parent.append(document.createTextNode(text.slice(cursor, match.index)));
    const button = document.createElement("button");
    button.type = "button";
    button.className = "reference-link";
    button.dataset.reference = match[1];
    button.textContent = match[0];
    parent.append(button);
    cursor = match.index + match[0].length;
  }
  parent.append(document.createTextNode(text.slice(cursor)));
}

function renderMarkdown(container, markdown) {
  container.replaceChildren();
  let list = null;
  String(markdown || "").split(/\r?\n/).forEach((line) => {
    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    const item = line.match(/^[-*]\s+(.+)$/);
    if (heading) {
      list = null;
      const node = document.createElement(`h${heading[1].length}`);
      appendInline(node, heading[2]);
      container.append(node);
    } else if (item) {
      if (!list) { list = document.createElement("ul"); container.append(list); }
      const node = document.createElement("li");
      appendInline(node, item[1]);
      list.append(node);
    } else if (line.trim()) {
      list = null;
      const node = document.createElement("p");
      appendInline(node, line);
      container.append(node);
    } else {
      list = null;
    }
  });
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

function badge(status) {
  const node = document.createElement("span");
  node.className = `badge badge-${status}`;
  node.textContent = statusLabel(status);
  return node;
}

function makeRunItem(run) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "run-item";
  button.dataset.runId = run.run_id;
  const title = document.createElement("span");
  title.className = "run-item-title";
  title.textContent = run.query;
  const meta = document.createElement("span");
  meta.className = "run-item-meta";
  meta.append(badge(run.status), document.createTextNode(run.model), document.createTextNode(formatDate(run.started_at)));
  button.append(title, meta);
  button.addEventListener("click", () => loadRunDetail(run.run_id));
  return button;
}

async function loadResearchRuns({reset = false} = {}) {
  if (reset) {
    state.runOffset = 0;
    elements.runList.replaceChildren();
  }
  elements.archiveError.textContent = "";
  elements.refreshRuns.disabled = true;
  elements.loadMoreRuns.disabled = true;
  try {
    const response = await fetch(`/research/runs?limit=${state.runPageSize}&offset=${state.runOffset}`);
    const runs = await response.json();
    if (!response.ok) throw new Error(runs.detail || "研究历史读取失败");
    runs.forEach((run) => elements.runList.append(makeRunItem(run)));
    state.runOffset += runs.length;
    elements.loadMoreRuns.hidden = runs.length < state.runPageSize;
    if (!elements.runList.children.length) {
      const empty = document.createElement("p");
      empty.className = "field-help";
      empty.textContent = "暂无持久化研究记录。";
      elements.runList.append(empty);
    }
  } catch (error) {
    elements.archiveError.textContent = `${error.message}；Graph 调用功能仍可正常使用。`;
    elements.loadMoreRuns.hidden = true;
  } finally {
    elements.refreshRuns.disabled = false;
    elements.loadMoreRuns.disabled = false;
  }
}

function detailSection(title) {
  const section = document.createElement("section");
  section.className = "detail-section";
  const heading = document.createElement("h4");
  heading.textContent = title;
  const list = document.createElement("div");
  list.className = "record-list";
  section.append(heading, list);
  return {section, list};
}

function recordCard(id, text, meta, status) {
  const card = document.createElement("article");
  card.className = "record-card";
  card.id = `record-${id}`;
  const heading = document.createElement("div");
  heading.className = "record-heading";
  const code = document.createElement("span");
  code.className = "record-id";
  code.textContent = id;
  heading.append(code);
  if (status) heading.append(badge(status));
  const content = document.createElement("div");
  content.textContent = text;
  card.append(heading, content);
  if (meta) {
    const small = document.createElement("div");
    small.className = "record-meta";
    appendInline(small, meta);
    card.append(small);
  }
  return card;
}

function renderRunDetail(detail) {
  const {run, sources = [], evidence = [], claims = []} = detail;
  state.currentRunId = run.run_id;
  elements.runList.querySelectorAll(".run-item").forEach((item) => item.classList.toggle("is-active", item.dataset.runId === run.run_id));
  elements.runDetail.replaceChildren();

  const header = document.createElement("header");
  header.className = "detail-header";
  const title = document.createElement("h3");
  title.textContent = run.query;
  const meta = document.createElement("div");
  meta.className = "run-item-meta";
  meta.append(badge(run.status), document.createTextNode(`${run.model} · ${run.graph_version}`), document.createTextNode(formatDate(run.started_at)));
  const supported = claims.filter((item) => ["supported", "partially_supported"].includes(item.verification_status)).length;
  const stats = document.createElement("div");
  stats.className = "detail-stats";
  [[sources.length, "来源"], [evidence.length, "证据"], [claims.length, "主张"], [supported, "有支持主张"]].forEach(([value, label]) => {
    const box = document.createElement("div");
    const strong = document.createElement("strong"); strong.textContent = value;
    const span = document.createElement("span"); span.textContent = label;
    box.append(strong, span); stats.append(box);
  });
  header.append(title, meta, stats);
  elements.runDetail.append(header);

  if (run.report) {
    const {section, list} = detailSection("最终报告");
    const report = document.createElement("div");
    report.className = "markdown-body";
    renderMarkdown(report, run.report.markdown_report);
    list.append(report);
    if (run.report.limitations?.length) list.append(recordCard("limitations", run.report.limitations.join("；"), "研究局限"));
    elements.runDetail.append(section);
  }
  if (run.failures?.length || run.error) {
    const {section, list} = detailSection("失败与异常");
    run.failures?.forEach((item, index) => list.append(recordCard(`failure-${index}`, item.query, item.error)));
    if (run.error) list.append(recordCard("run-error", run.error, "运行错误", "failed"));
    elements.runDetail.append(section);
  }
  const claimSection = detailSection(`主张（${claims.length}）`);
  claims.forEach((item) => claimSection.list.append(recordCard(item.claim_id, item.statement, `${item.claim_type} · 置信度 ${Math.round(item.confidence * 100)}% · 证据 ${item.evidence_ids.map((id) => `[${id}]`).join("、") || "无"}`, item.verification_status)));
  elements.runDetail.append(claimSection.section);
  const evidenceSection = detailSection(`证据（${evidence.length}）`);
  evidence.forEach((item) => evidenceSection.list.append(recordCard(item.evidence_id, `“${item.excerpt}”`, `来源 [${item.source_id}] · 置信度 ${Math.round(item.confidence * 100)}%${item.data_period ? ` · ${item.data_period}` : ""}`)));
  elements.runDetail.append(evidenceSection.section);
  const sourceSection = detailSection(`来源（${sources.length}）`);
  sources.forEach((item) => {
    const card = recordCard(item.source_id, item.title, `${item.publisher || "未知发布者"} · 抓取于 ${formatDate(item.retrieved_at)}`);
    const link = document.createElement("a");
    link.className = "source-link";
    link.href = item.canonical_url;
    link.target = "_blank";
    link.rel = "noreferrer noopener";
    link.textContent = item.canonical_url;
    card.append(link);
    sourceSection.list.append(card);
  });
  elements.runDetail.append(sourceSection.section);
}

async function loadRunDetail(runId) {
  elements.archiveError.textContent = "";
  elements.runDetail.setAttribute("aria-busy", "true");
  try {
    const response = await fetch(`/research/runs/${encodeURIComponent(runId)}`);
    const detail = await response.json();
    if (!response.ok) throw new Error(detail.detail || "研究详情读取失败");
    renderRunDetail(detail);
    elements.runDetail.scrollIntoView({behavior: "smooth", block: "start"});
  } catch (error) {
    elements.archiveError.textContent = error.message;
  } finally {
    elements.runDetail.removeAttribute("aria-busy");
  }
}

function focusReference(reference) {
  const target = document.getElementById(`record-${reference}`);
  if (!target) return;
  target.classList.add("is-highlighted");
  target.scrollIntoView({behavior: "smooth", block: "center"});
  window.setTimeout(() => target.classList.remove("is-highlighted"), 1800);
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
    const answer = latestAnswer(payload);
    if (elements.graphSelect.value === "research_agent") renderMarkdown(elements.answer, answer);
    else elements.answer.textContent = answer;
    elements.raw.textContent = JSON.stringify(payload, null, 2);
    elements.resultGraph.textContent = graphProfile(elements.graphSelect.value).label;
    elements.resultModel.textContent = elements.modelSelect.value;
    elements.resultThread.textContent = elements.threadId.value.trim();
    elements.resultFinished.textContent = new Intl.DateTimeFormat("zh-CN", {dateStyle: "medium", timeStyle: "medium"}).format(new Date());
    renderImages(imagePaths(payload));
    elements.openCurrentRun.hidden = !payload.run_id;
    elements.openCurrentRun.dataset.runId = payload.run_id || "";
    if (payload.run_id) await loadResearchRuns({reset: true});
    elements.elapsed.textContent = `${((performance.now() - startedAt) / 1000).toFixed(1)} 秒完成`;
  } catch (error) {
    if (error.name === "AbortError") {
      elements.error.textContent = "已停止等待。后端研究可能仍在执行，可稍后在研究档案中查看状态。";
      elements.elapsed.textContent = "已停止等待";
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
elements.refreshRuns.addEventListener("click", () => loadResearchRuns({reset: true}));
elements.loadMoreRuns.addEventListener("click", () => loadResearchRuns());
elements.openCurrentRun.addEventListener("click", () => loadRunDetail(elements.openCurrentRun.dataset.runId));
document.addEventListener("click", (event) => {
  const reference = event.target.closest("[data-reference]")?.dataset.reference;
  if (reference) focusReference(reference);
});
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
loadResearchRuns({reset: true});
