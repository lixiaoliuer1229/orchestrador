const state = {graphs: [], controller: null, timer: null, runOffset: 0, runPageSize: 20, currentRunId: null, signalOffset: 0, signalPageSize: 20, currentSignalRunId: null, instrumentOffset: 0, instrumentPageSize: 100, selectedInstrument: null, ingestionOffset: 0, ingestionPageSize: 20};

const graphProfiles = {
  chatbot: {label: "通用研究助手", description: "用于研究讨论、信息梳理和问题分析；结论不构成交易指令。", placeholder: "例如：梳理这项研究假设需要哪些证据，并列出主要风险"},
  data_agent: {label: "只读数据分析", description: "仅执行单条只读 MySQL 查询，用于数据检索与结果总结。", placeholder: "例如：查询最近一周的数据并总结主要变化"},
  research_agent: {label: "联网深度研究", description: "规划检索、并发搜索并生成带来源 ID 的结构化研究报告。", placeholder: "例如：研究生成式 AI 对软件行业商业模式的影响，并说明主要证据与局限"},
  signal_agent: {label: "投资信号转换", description: "将指定研究运行中的合格 Claim 转换为带完整证据血缘的候选信号。", placeholder: "请输入 Research Run ID，例如：11111111-1111-1111-1111-111111111111"},
};

const byId = (id) => document.getElementById(id);
const elements = {
  status: byId("service-status"), modelName: byId("model-name"), modelEndpoint: byId("model-endpoint"),
  graphCount: byId("graph-count"), graphNames: byId("graph-names"), requestTimeout: byId("request-timeout"),
  form: byId("invoke-form"), graphSelect: byId("graph-select"), graphDescription: byId("graph-description"),
  modelSelect: byId("model-select"), threadId: byId("thread-id"), prompt: byId("prompt"), promptLabel: byId("prompt-label"),
  submit: byId("submit-button"), cancel: byId("cancel-button"), retryRuntime: byId("retry-runtime"),
  newThread: byId("new-thread"), error: byId("form-error"), empty: byId("empty-state"),
  content: byId("result-content"), answer: byId("answer-text"), raw: byId("raw-json"), elapsed: byId("elapsed-time"),
  imageSection: byId("image-section"), gallery: byId("image-gallery"), copyAnswer: byId("copy-answer"),
  resultGraph: byId("result-graph"), resultModel: byId("result-model"), resultThread: byId("result-thread"),
  resultFinished: byId("result-finished"), currentUser: byId("current-user"), adminLink: byId("admin-link"), logout: byId("logout"),
  openCurrentRun: byId("open-current-run"), refreshRuns: byId("refresh-runs"), loadMoreRuns: byId("load-more-runs"),
  runList: byId("run-list"), runDetail: byId("run-detail"), archiveError: byId("archive-error"),
  openCurrentSignalRun: byId("open-current-signal-run"), refreshSignals: byId("refresh-signals"),
  signalFilters: byId("signal-filters"), instrumentFilter: byId("instrument-filter"), researchRunFilter: byId("research-run-filter"),
  clearSignalFilters: byId("clear-signal-filters"), signalError: byId("signal-error"), signalList: byId("signal-list"),
  signalDetail: byId("signal-detail"), loadMoreSignals: byId("load-more-signals"),
  refreshInstruments: byId("refresh-instruments"), marketFilter: byId("market-filter"), marketStart: byId("market-start"),
  marketEnd: byId("market-end"), financialAsOf: byId("financial-as-of"), marketError: byId("market-error"),
  instrumentList: byId("instrument-list"), loadMoreInstruments: byId("load-more-instruments"), instrumentDetail: byId("instrument-detail"),
  refreshIngestions: byId("refresh-ingestions"), ingestionList: byId("ingestion-list"), loadMoreIngestions: byId("load-more-ingestions"), qualityDetail: byId("quality-detail"),
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
  const isSignal = elements.graphSelect.value === "signal_agent";
  elements.promptLabel.textContent = isSignal ? "Research Run ID" : "问题或分析要求";
  elements.prompt.rows = isSignal ? 2 : 8;
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
  if (run.status === "completed") {
    const generate = document.createElement("button");
    generate.type = "button";
    generate.className = "primary generate-signal";
    generate.textContent = "从本次研究生成候选信号";
    generate.addEventListener("click", () => prepareSignalGeneration(run.run_id));
    header.append(generate);
  }
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

function prepareSignalGeneration(runId) {
  elements.graphSelect.value = "signal_agent";
  updateGraphGuidance();
  elements.prompt.value = runId;
  elements.form.scrollIntoView({behavior: "smooth", block: "start"});
  elements.submit.focus({preventScroll: true});
}

function directionLabel(direction) {
  return {positive: "正向", negative: "负向", neutral: "中性"}[direction] || direction;
}

function makeSignalItem(signal) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "run-item";
  button.dataset.signalId = signal.signal_id;
  const title = document.createElement("span");
  title.className = "run-item-title";
  title.textContent = `${signal.instrument.name || signal.instrument.symbol} · ${signal.category}`;
  const meta = document.createElement("span");
  meta.className = "run-item-meta";
  const direction = document.createElement("span");
  direction.className = `signal-card-direction direction-${signal.direction}`;
  direction.textContent = directionLabel(signal.direction);
  meta.append(direction, document.createTextNode(signal.instrument.instrument_id), document.createTextNode(`置信度 ${Math.round(signal.confidence * 100)}%`));
  button.append(title, meta);
  button.addEventListener("click", () => loadSignalDetail(signal.signal_id));
  return button;
}

async function loadSignals({reset = false} = {}) {
  if (reset) {
    state.signalOffset = 0;
    elements.signalList.replaceChildren();
  }
  elements.signalError.textContent = "";
  elements.refreshSignals.disabled = true;
  elements.loadMoreSignals.disabled = true;
  const params = new URLSearchParams({limit: state.signalPageSize, offset: state.signalOffset});
  if (elements.instrumentFilter.value.trim()) params.set("instrument_id", elements.instrumentFilter.value.trim());
  if (elements.researchRunFilter.value.trim()) params.set("research_run_id", elements.researchRunFilter.value.trim());
  try {
    const response = await fetch(`/signals?${params}`);
    const signals = await response.json();
    if (!response.ok) throw new Error(signals.detail || "候选信号读取失败");
    signals.forEach((signal) => elements.signalList.append(makeSignalItem(signal)));
    state.signalOffset += signals.length;
    elements.loadMoreSignals.hidden = signals.length < state.signalPageSize;
    if (!elements.signalList.children.length) {
      const empty = document.createElement("p");
      empty.className = "field-help";
      empty.textContent = "当前筛选条件下暂无候选信号。";
      elements.signalList.append(empty);
    }
  } catch (error) {
    elements.signalError.textContent = `${error.message}；研究功能仍可正常使用。`;
    elements.loadMoreSignals.hidden = true;
  } finally {
    elements.refreshSignals.disabled = false;
    elements.loadMoreSignals.disabled = false;
  }
}

function signalSummary(signal) {
  const wrapper = document.createElement("div");
  const heading = document.createElement("div");
  heading.className = "record-heading";
  const name = document.createElement("strong");
  name.textContent = `${signal.instrument.name || signal.instrument.symbol}（${signal.instrument.instrument_id}）`;
  const direction = document.createElement("span");
  direction.className = `signal-card-direction direction-${signal.direction}`;
  direction.textContent = directionLabel(signal.direction);
  heading.append(name, direction);
  const meter = document.createElement("div");
  meter.className = "signal-meter";
  const fill = document.createElement("span");
  fill.style.width = `${Math.round(signal.strength * 100)}%`;
  meter.append(fill);
  const meta = document.createElement("p");
  meta.className = "record-meta";
  meta.textContent = `${signal.category} · 强度 ${Math.round(signal.strength * 100)}% · 置信度 ${Math.round(signal.confidence * 100)}% · ${formatDate(signal.effective_at)} 至 ${formatDate(signal.expires_at)}`;
  const rationale = document.createElement("p");
  rationale.textContent = signal.rationale;
  wrapper.append(heading, meter, meta, rationale);
  return wrapper;
}

function renderSignalInvocation(payload) {
  elements.answer.replaceChildren();
  const signals = Array.isArray(payload.signals) ? payload.signals : [];
  const summary = document.createElement("p");
  summary.textContent = signals.length
    ? `已从研究档案生成 ${signals.length} 个候选信号。`
    : "本次研究没有形成满足证据要求的候选信号。";
  elements.answer.append(summary);
  signals.forEach((signal) => {
    const card = document.createElement("article");
    card.className = "record-card";
    card.append(signalSummary(signal));
    elements.answer.append(card);
  });
  const note = document.createElement("p");
  note.className = "boundary-note";
  note.textContent = "候选信号不能直接触发下单，仍需经过量化验证、组合和独立风控。";
  elements.answer.append(note);
}

async function openResearchReference(runId, reference) {
  await loadRunDetail(runId);
  focusReference(reference);
}

function renderSignalDetail(detail) {
  const {signal, evidence_ids: evidenceIds = [], source_ids: sourceIds = []} = detail;
  elements.signalList.querySelectorAll(".run-item").forEach((item) => item.classList.toggle("is-active", item.dataset.signalId === signal.signal_id));
  elements.signalDetail.replaceChildren();
  const header = document.createElement("header");
  header.className = "detail-header";
  const title = document.createElement("h3");
  title.textContent = `${signal.instrument.name || signal.instrument.symbol}候选信号`;
  header.append(title, signalSummary(signal));
  const marketButton = document.createElement("button");
  marketButton.type = "button";
  marketButton.className = "secondary";
  marketButton.textContent = "查看证券市场数据";
  marketButton.addEventListener("click", () => openMarketInstrument(signal.instrument.instrument_id));
  header.append(marketButton);
  const note = document.createElement("p");
  note.className = "boundary-note";
  note.textContent = "候选信号不是订单，也不代表仓位建议；必须经过后续量化验证、组合计算、独立风控和人工审批。";
  header.append(note);
  elements.signalDetail.append(header);

  const lineage = detailSection("证据血缘");
  [["Research Run", signal.research_run_id, null], ...signal.claim_ids.map((id) => ["Claim", id, id]), ...evidenceIds.map((id) => ["Evidence", id, id]), ...sourceIds.map((id) => ["Source", id, id])].forEach(([type, id, reference]) => {
    const card = recordCard(`lineage-${id}`, id, type);
    const open = document.createElement("button");
    open.type = "button";
    open.className = "text-button";
    open.textContent = reference ? "在研究档案中定位" : "打开研究档案";
    open.addEventListener("click", () => openResearchReference(signal.research_run_id, reference));
    card.append(open);
    lineage.list.append(card);
  });
  elements.signalDetail.append(lineage.section);
}

async function openMarketInstrument(instrumentId) {
  elements.marketError.textContent = "";
  try {
    const instruments = await apiJson("/market/instruments?limit=1000&offset=0");
    const instrument = instruments.find((item) => item.instrument_id === instrumentId);
    if (!instrument) throw new Error(`市场主数据中未找到 ${instrumentId}`);
    renderInstrumentDetail(instrument);
    document.querySelector(".market-workbench").scrollIntoView({behavior: "smooth", block: "start"});
  } catch (error) { elements.marketError.textContent = error.message; }
}

async function loadSignalDetail(signalId) {
  elements.signalError.textContent = "";
  elements.signalDetail.setAttribute("aria-busy", "true");
  try {
    const response = await fetch(`/signals/${encodeURIComponent(signalId)}`);
    const detail = await response.json();
    if (!response.ok) throw new Error(detail.detail || "信号详情读取失败");
    renderSignalDetail(detail);
    elements.signalDetail.scrollIntoView({behavior: "smooth", block: "start"});
  } catch (error) {
    elements.signalError.textContent = error.message;
  } finally {
    elements.signalDetail.removeAttribute("aria-busy");
  }
}

async function loadSignalRun(signalRunId) {
  elements.signalError.textContent = "";
  try {
    const response = await fetch(`/signals/runs/${encodeURIComponent(signalRunId)}`);
    const detail = await response.json();
    if (!response.ok) throw new Error(detail.detail || "信号转换运行读取失败");
    state.currentSignalRunId = signalRunId;
    elements.signalDetail.replaceChildren();
    const header = document.createElement("header");
    header.className = "detail-header";
    const title = document.createElement("h3");
    title.textContent = "信号转换运行";
    const meta = document.createElement("div");
    meta.className = "run-item-meta";
    meta.append(badge(detail.run.status), document.createTextNode(`${detail.run.model} · ${detail.run.graph_version}`), document.createTextNode(formatDate(detail.run.started_at)));
    header.append(title, meta);
    if (detail.run.error) header.append(recordCard("signal-run-error", detail.run.error, "运行错误", "failed"));
    elements.signalDetail.append(header);
    const section = detailSection(`生成信号（${detail.signals.length}）`);
    detail.signals.forEach((signal) => {
      const card = recordCard(signal.signal_id, signal.rationale, `${signal.instrument.instrument_id} · ${directionLabel(signal.direction)} · 置信度 ${Math.round(signal.confidence * 100)}%`);
      const open = document.createElement("button");
      open.type = "button"; open.className = "text-button"; open.textContent = "查看完整血缘";
      open.addEventListener("click", () => loadSignalDetail(signal.signal_id));
      card.append(open); section.list.append(card);
    });
    elements.signalDetail.append(section.section);
    document.querySelector(".signal-workbench").scrollIntoView({behavior: "smooth", block: "start"});
  } catch (error) {
    elements.signalError.textContent = error.message;
  }
}

function localDateValue(date) {
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

function initializeMarketDates() {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 30);
  elements.marketStart.value = localDateValue(start);
  elements.marketEnd.value = localDateValue(end);
  elements.financialAsOf.value = new Date(end.getTime() - end.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

async function apiJson(url) {
  const response = await fetch(url);
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : `请求失败：${response.status}`);
  return body;
}

function makeInstrumentItem(instrument) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "run-item";
  button.dataset.instrumentId = instrument.instrument_id;
  const title = document.createElement("span");
  title.className = "run-item-title";
  title.textContent = `${instrument.name || instrument.symbol} · ${instrument.symbol}`;
  const meta = document.createElement("span");
  meta.className = "run-item-meta";
  meta.append(document.createTextNode(`${instrument.market} · ${instrument.exchange} · ${instrument.asset_type}`), badge(instrument.state));
  if (instrument.metadata?.synthetic) {
    const synthetic = document.createElement("span");
    synthetic.className = "badge synthetic-badge";
    synthetic.textContent = "模拟数据";
    meta.append(synthetic);
  }
  button.append(title, meta);
  button.addEventListener("click", () => renderInstrumentDetail(instrument));
  return button;
}

async function loadInstruments({reset = false} = {}) {
  if (reset) { state.instrumentOffset = 0; elements.instrumentList.replaceChildren(); }
  elements.marketError.textContent = "";
  const params = new URLSearchParams({limit: state.instrumentPageSize, offset: state.instrumentOffset});
  if (elements.marketFilter.value) params.set("market", elements.marketFilter.value);
  try {
    const instruments = await apiJson(`/market/instruments?${params}`);
    instruments.forEach((item) => elements.instrumentList.append(makeInstrumentItem(item)));
    state.instrumentOffset += instruments.length;
    elements.loadMoreInstruments.hidden = instruments.length < state.instrumentPageSize;
    if (!elements.instrumentList.children.length) {
      const empty = document.createElement("p"); empty.className = "field-help"; empty.textContent = "当前市场暂无证券数据。";
      elements.instrumentList.append(empty);
    }
  } catch (error) {
    elements.marketError.textContent = `${error.message}；其他工作台仍可正常使用。`;
  }
}

function makeTable(rows, columns) {
  const wrap = document.createElement("div");
  wrap.className = "data-table";
  if (!rows.length) { wrap.textContent = "所选条件下暂无数据。"; return wrap; }
  const table = document.createElement("table");
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  columns.forEach(([, label]) => { const th = document.createElement("th"); th.textContent = label; headRow.append(th); });
  head.append(headRow);
  const body = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    columns.forEach(([key]) => { const td = document.createElement("td"); const value = row[key]; td.textContent = typeof value === "boolean" ? (value ? "是" : "否") : (value ?? "—"); tr.append(td); });
    body.append(tr);
  });
  table.append(head, body); wrap.append(table); return wrap;
}

function makePriceChart(rows) {
  const values = rows.map((row) => Number(row.close)).filter(Number.isFinite);
  if (values.length < 2) return null;
  const min = Math.min(...values); const max = Math.max(...values); const range = max - min || 1;
  const points = values.map((value, index) => `${(index / (values.length - 1)) * 100},${95 - ((value - min) / range) * 90}`).join(" ");
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 100 100"); svg.setAttribute("preserveAspectRatio", "none"); svg.classList.add("price-chart");
  const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline"); line.setAttribute("points", points); svg.append(line);
  return svg;
}

async function loadInstrumentDataset(kind) {
  const instrument = state.selectedInstrument;
  if (!instrument) return;
  elements.marketError.textContent = "";
  const target = byId("market-data-content");
  target.textContent = "正在读取…";
  const id = encodeURIComponent(instrument.instrument_id);
  const range = `start=${elements.marketStart.value}&end=${elements.marketEnd.value}`;
  try {
    let rows; let columns;
    if (kind === "bars") {
      rows = await apiJson(`/market/bars/${id}?${range}`);
      columns = [["trade_date", "日期"], ["open", "开"], ["high", "高"], ["low", "低"], ["close", "收"], ["volume", "成交量"], ["suspended", "停牌"], ["provider", "来源"]];
    } else if (kind === "actions") {
      rows = await apiJson(`/market/actions/${id}?${range}`);
      columns = [["ex_date", "除权日"], ["action_type", "类型"], ["cash_amount", "现金"], ["ratio", "比例"], ["provider", "来源"]];
    } else if (kind === "status") {
      rows = await apiJson(`/market/status/${id}?${range}`);
      columns = [["trade_date", "日期"], ["suspended", "停牌"], ["is_st", "ST"], ["can_buy", "可买"], ["can_sell", "可卖"], ["reason", "原因"]];
    } else if (kind === "financials") {
      const asOf = new Date(elements.financialAsOf.value);
      if (Number.isNaN(asOf.getTime())) throw new Error("请选择有效的财务数据时点");
      rows = await apiJson(`/market/financials/${id}?as_of=${encodeURIComponent(asOf.toISOString())}`);
      columns = [["report_period", "报告期"], ["metric", "指标"], ["value", "数值"], ["unit", "单位"], ["announced_at", "公告时间"], ["restatement", "重述版本"]];
    } else {
      rows = await apiJson(`/market/calendar?exchange=${instrument.exchange}&${range}`);
      columns = [["trade_date", "日期"], ["is_open", "开市"], ["opens_at", "开盘"], ["closes_at", "收盘"], ["note", "说明"]];
    }
    target.replaceChildren();
    if (kind === "bars") { const chart = makePriceChart(rows); if (chart) target.append(chart); }
    target.append(makeTable(rows, columns));
    byId("market-data-tabs").querySelectorAll("button").forEach((button) => button.classList.toggle("is-active", button.dataset.kind === kind));
  } catch (error) {
    target.textContent = "";
    elements.marketError.textContent = error.message;
  }
}

function renderInstrumentDetail(instrument) {
  state.selectedInstrument = instrument;
  elements.instrumentList.querySelectorAll(".run-item").forEach((item) => item.classList.toggle("is-active", item.dataset.instrumentId === instrument.instrument_id));
  elements.instrumentDetail.replaceChildren();
  const header = document.createElement("header"); header.className = "detail-header";
  const title = document.createElement("h3"); title.textContent = `${instrument.name || instrument.symbol}（${instrument.instrument_id}）`;
  const meta = document.createElement("div"); meta.className = "run-item-meta";
  meta.append(badge(instrument.state), document.createTextNode(`${instrument.market} · ${instrument.exchange} · ${instrument.currency} · ${instrument.asset_type}`));
  const flags = document.createElement("div"); flags.className = "instrument-flags";
  [["行业", instrument.industry], ["板块", instrument.sector], ["Qlib", instrument.qlib_code], ["每手", instrument.lot_size], ["交收日", instrument.settlement_days]].forEach(([label, value]) => { if (value !== null && value !== undefined) { const item = document.createElement("span"); item.className = "badge"; item.textContent = `${label}: ${value}`; flags.append(item); } });
  if (instrument.metadata?.synthetic) { const warning = document.createElement("p"); warning.className = "boundary-note"; warning.textContent = "这是 Mock Provider 生成的合成数据，只用于验证数据管线与质量门控。"; header.append(title, meta, flags, warning); }
  else header.append(title, meta, flags);
  const tabs = document.createElement("div"); tabs.id = "market-data-tabs"; tabs.className = "data-tabs";
  [["bars", "日线行情"], ["actions", "公司行为"], ["status", "交易状态"], ["financials", "财务事实"], ["calendar", "交易日历"]].forEach(([kind, label]) => { const button = document.createElement("button"); button.type = "button"; button.className = "secondary"; button.dataset.kind = kind; button.textContent = label; button.addEventListener("click", () => loadInstrumentDataset(kind)); tabs.append(button); });
  const content = document.createElement("div"); content.id = "market-data-content";
  elements.instrumentDetail.append(header, tabs, content);
  loadInstrumentDataset("bars");
}

async function loadQualityIssues(runId) {
  elements.qualityDetail.textContent = "正在读取质量问题…";
  try {
    const issues = await apiJson(`/market/ingestions/${encodeURIComponent(runId)}/issues?limit=100&offset=0`);
    const section = detailSection(`质量问题（${issues.length}）`);
    issues.forEach((issue) => section.list.append(recordCard(issue.issue_id, issue.message, `${issue.code} · ${issue.entity_type} · ${issue.entity_key}${issue.rejected ? " · 已拒绝入库" : ""}`, issue.severity)));
    if (!issues.length) section.list.textContent = "该批次没有记录质量问题。";
    elements.qualityDetail.replaceChildren(section.section);
  } catch (error) { elements.qualityDetail.textContent = ""; elements.marketError.textContent = error.message; }
}

function makeIngestionCard(run) {
  const card = document.createElement("article"); card.className = "ingestion-card";
  const title = document.createElement("h4"); title.textContent = `${run.dataset} · ${run.market}`;
  const meta = document.createElement("div"); meta.className = "run-item-meta"; meta.append(badge(run.status), document.createTextNode(`${run.provider} · ${run.version}`));
  const counts = document.createElement("div"); counts.className = "count-row"; counts.textContent = `接收 ${run.received_count} · 接受 ${run.accepted_count} · 拒绝 ${run.rejected_count}`;
  const button = document.createElement("button"); button.type = "button"; button.className = "text-button"; button.textContent = "查看质量问题"; button.addEventListener("click", () => loadQualityIssues(run.ingestion_run_id));
  card.append(title, meta, counts, button); return card;
}

async function loadIngestions({reset = false} = {}) {
  if (reset) { state.ingestionOffset = 0; elements.ingestionList.replaceChildren(); }
  try {
    const runs = await apiJson(`/market/ingestions?limit=${state.ingestionPageSize}&offset=${state.ingestionOffset}`);
    runs.forEach((run) => elements.ingestionList.append(makeIngestionCard(run)));
    state.ingestionOffset += runs.length;
    elements.loadMoreIngestions.hidden = runs.length < state.ingestionPageSize;
    if (!elements.ingestionList.children.length) elements.ingestionList.textContent = "暂无数据采集批次。";
  } catch (error) { elements.marketError.textContent = error.message; }
}

async function invoke(event) {
  event.preventDefault();
  elements.error.textContent = "";
  elements.submit.disabled = true;
  elements.submit.textContent = "运行中…";
  elements.cancel.hidden = false;
  elements.openCurrentRun.hidden = true;
  elements.openCurrentSignalRun.hidden = true;
  const startedAt = performance.now();
  state.controller = new AbortController();
  const updateElapsed = () => { elements.elapsed.textContent = `已运行 ${((performance.now() - startedAt) / 1000).toFixed(1)} 秒`; };
  updateElapsed();
  state.timer = window.setInterval(updateElapsed, 100);

  try {
    const graphName = elements.graphSelect.value;
    const graphInput = graphName === "signal_agent"
      ? {research_run_id: elements.prompt.value.trim()}
      : {messages: [{role: "user", content: elements.prompt.value.trim()}]};
    const response = await fetch(`/graphs/${encodeURIComponent(graphName)}/invoke`, {
      method: "POST", headers: {"Content-Type": "application/json"}, signal: state.controller.signal,
      body: JSON.stringify({
        input: graphInput,
        config: {configurable: {thread_id: elements.threadId.value.trim()}},
        model: elements.modelSelect.value,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `请求失败：${response.status}`);

    elements.empty.hidden = true;
    elements.content.hidden = false;
    const answer = latestAnswer(payload);
    if (graphName === "research_agent") renderMarkdown(elements.answer, answer);
    else if (graphName === "signal_agent") renderSignalInvocation(payload);
    else elements.answer.textContent = answer;
    elements.raw.textContent = JSON.stringify(payload, null, 2);
    elements.resultGraph.textContent = graphProfile(elements.graphSelect.value).label;
    elements.resultModel.textContent = elements.modelSelect.value;
    elements.resultThread.textContent = graphName === "signal_agent" ? "不适用" : elements.threadId.value.trim();
    elements.resultFinished.textContent = new Intl.DateTimeFormat("zh-CN", {dateStyle: "medium", timeStyle: "medium"}).format(new Date());
    renderImages(imagePaths(payload));
    elements.openCurrentRun.hidden = !payload.run_id;
    elements.openCurrentRun.dataset.runId = payload.run_id || "";
    elements.openCurrentSignalRun.hidden = !payload.signal_run_id;
    elements.openCurrentSignalRun.dataset.signalRunId = payload.signal_run_id || "";
    if (payload.run_id) await loadResearchRuns({reset: true});
    if (payload.signal_run_id) await loadSignals({reset: true});
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
elements.openCurrentSignalRun.addEventListener("click", () => loadSignalRun(elements.openCurrentSignalRun.dataset.signalRunId));
elements.refreshSignals.addEventListener("click", () => loadSignals({reset: true}));
elements.loadMoreSignals.addEventListener("click", () => loadSignals());
elements.signalFilters.addEventListener("submit", (event) => { event.preventDefault(); loadSignals({reset: true}); });
elements.clearSignalFilters.addEventListener("click", () => {
  elements.instrumentFilter.value = "";
  elements.researchRunFilter.value = "";
  loadSignals({reset: true});
});
elements.refreshInstruments.addEventListener("click", () => loadInstruments({reset: true}));
elements.loadMoreInstruments.addEventListener("click", () => loadInstruments());
elements.marketFilter.addEventListener("change", () => loadInstruments({reset: true}));
elements.refreshIngestions.addEventListener("click", () => loadIngestions({reset: true}));
elements.loadMoreIngestions.addEventListener("click", () => loadIngestions());
elements.marketStart.addEventListener("change", () => { if (state.selectedInstrument) loadInstrumentDataset("bars"); });
elements.marketEnd.addEventListener("change", () => { if (state.selectedInstrument) loadInstrumentDataset("bars"); });
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
loadSignals({reset: true});
initializeMarketDates();
loadInstruments({reset: true});
loadIngestions({reset: true});
