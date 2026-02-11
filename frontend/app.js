const el = {
  systemPill: document.getElementById("system-pill"),
  status: document.getElementById("status"),
  menuItems: Array.from(document.querySelectorAll(".menu-item")),
  viewChat: document.getElementById("view-chat"),
  viewNotebook: document.getElementById("view-notebook"),
  viewInsights: document.getElementById("view-insights"),

  chatMessages: document.getElementById("chat-messages"),
  unifiedInput: document.getElementById("unified-input"),
  sendBtn: document.getElementById("send-btn"),
  clearChatBtn: document.getElementById("clear-chat-btn"),
  debugToggle: document.getElementById("debug-toggle"),
  debugPanel: document.getElementById("debug-panel"),
  debugOutput: document.getElementById("debug-output"),

  historyList: document.getElementById("history-list"),
  refreshHistoryBtn: document.getElementById("refresh-history-btn"),
  readerDate: document.getElementById("reader-date"),
  readerContent: document.getElementById("reader-content"),

  refreshInsightsBtn: document.getElementById("refresh-insights-btn"),
  sDiaries: document.getElementById("s-diaries"),
  sEntries: document.getElementById("s-entries"),
  sAnalysis: document.getElementById("s-analysis"),
  sPending: document.getElementById("s-pending"),
  signalsLine: document.getElementById("signals-line"),
  traitList: document.getElementById("trait-list"),
  strengthList: document.getElementById("strength-list"),
  weaknessList: document.getElementById("weakness-list"),
  topicList: document.getElementById("topic-list"),
};

const state = {
  selectedDate: null,
  currentView: "chat",
};

function setStatus(text) {
  if (el.status) {
    el.status.textContent = text || "";
  }
}

async function fetchJson(url, options = {}) {
  const resp = await fetch(url, options);
  const text = await resp.text();
  let data = {};

  try {
    data = text ? JSON.parse(text) : {};
  } catch (_err) {
    data = {};
  }

  if (!resp.ok) {
    const detail = data?.detail;
    const msg = typeof detail === "string"
      ? detail
      : detail?.message || JSON.stringify(detail || data);
    throw new Error(msg || `Request failed: ${resp.status}`);
  }

  return data;
}

function clearChatEmpty() {
  const emptyNode = el.chatMessages?.querySelector(".chat-empty");
  if (emptyNode) emptyNode.remove();
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function appendUserMessage(text, kind) {
  if (!el.chatMessages) return;
  clearChatEmpty();

  const node = document.createElement("div");
  node.className = "chat-msg user";
  const tag = kind === "diary" ? "日记" : "聊天";
  node.innerHTML = `<div class="msg-kind">${tag}</div><div>${escapeHtml(text)}</div>`;

  el.chatMessages.appendChild(node);
  el.chatMessages.scrollTop = el.chatMessages.scrollHeight;
}

function appendAiMessage(text) {
  if (!el.chatMessages) return;
  clearChatEmpty();

  const node = document.createElement("div");
  node.className = "chat-msg ai";
  try {
    node.innerHTML = marked.parse(text || "");
  } catch (_err) {
    node.textContent = text || "";
  }

  el.chatMessages.appendChild(node);
  el.chatMessages.scrollTop = el.chatMessages.scrollHeight;
}

function updateDebugPanel(debugData) {
  if (!el.debugOutput) return;
  if (!debugData) {
    el.debugOutput.textContent = "暂无";
    return;
  }
  el.debugOutput.textContent = JSON.stringify(debugData, null, 2);
}

function switchView(view) {
  state.currentView = view;

  el.menuItems.forEach((btn) => {
    const active = btn.getAttribute("data-view") === view;
    btn.classList.toggle("active", active);
  });

  el.viewChat?.classList.toggle("hidden", view !== "chat");
  el.viewNotebook?.classList.toggle("hidden", view !== "notebook");
  el.viewInsights?.classList.toggle("hidden", view !== "insights");
}

function detectInputKind(text) {
  const value = String(text || "").trim();
  const hasQuestion = /[?？]|(为什么|怎么|如何|吗|呢|what|how|why|can|could|should)/i.test(value);
  const diaryHint = /(今天|昨天|刚刚|刚才|记录|日记|心情|反思|经历|早上|中午|晚上|凌晨|我觉得|我在|我想想|总结)/.test(value);
  const lineCount = value.split(/\n+/).filter(Boolean).length;
  const looksLong = value.length >= 80;
  const firstPerson = /(我|\bI\b)/.test(value);

  if (hasQuestion && !looksLong && lineCount <= 2 && !diaryHint) return "chat";
  if (looksLong || lineCount >= 2 || diaryHint) return "diary";
  if (!hasQuestion && firstPerson) return "diary";
  return "chat";
}

async function refreshSystemPill() {
  if (!el.systemPill) return;

  try {
    const info = await fetchJson("/api/_bot");
    const healthy = Boolean(info.bot);

    el.systemPill.classList.remove("ok", "bad");
    el.systemPill.classList.add(healthy ? "ok" : "bad");
    el.systemPill.textContent = healthy
      ? `模型已连接: ${info.bot}`
      : "模型未就绪";
  } catch (_err) {
    el.systemPill.classList.remove("ok");
    el.systemPill.classList.add("bad");
    el.systemPill.textContent = "系统状态获取失败";
  }
}

function renderHistory(items = []) {
  if (!el.historyList) return;

  if (items.length === 0) {
    el.historyList.innerHTML = '<div class="history-empty">暂无历史记录</div>';
    return;
  }

  const html = items.map((item) => {
    const active = state.selectedDate === item.date ? "active" : "";
    const sizeKB = (Number(item.size_bytes || 0) / 1024).toFixed(1);
    const preview = item.preview || "(无摘要)";
    return `
      <button class="history-item ${active}" data-date="${item.date}" type="button">
        <div class="history-date">${item.date}</div>
        <div class="history-preview">${escapeHtml(preview)}</div>
        <div class="history-meta">${sizeKB} KB</div>
      </button>
    `;
  }).join("");

  el.historyList.innerHTML = html;
}

async function loadHistory() {
  try {
    const data = await fetchJson("/api/diary/list?limit=120");
    renderHistory(data.items || []);
  } catch (err) {
    el.historyList.innerHTML = `<div class="history-empty">加载失败: ${escapeHtml(err.message)}</div>`;
  }
}

async function openDiary(date) {
  try {
    const data = await fetchJson(`/api/diary/read?date=${encodeURIComponent(date)}`);
    state.selectedDate = date;
    if (el.readerDate) el.readerDate.textContent = `日记 ${date}`;
    if (el.readerContent) el.readerContent.textContent = data.text || "";
    setStatus(`已加载 ${date}`);
    await loadHistory();
  } catch (err) {
    setStatus(`读取失败: ${err.message}`);
  }
}

function setList(container, items) {
  if (!container) return;
  if (!items || items.length === 0) {
    container.innerHTML = "<li>暂无</li>";
    return;
  }
  container.innerHTML = items.map((x) => `<li>${escapeHtml(String(x))}</li>`).join("");
}

async function refreshInsights() {
  try {
    const data = await fetchJson("/api/dashboard/overview?limit=120");
    const stats = data.stats || {};
    const jobs = stats.jobs || {};

    if (el.sDiaries) el.sDiaries.textContent = String(stats.diaries_count ?? "-");
    if (el.sEntries) el.sEntries.textContent = String(stats.entries_count ?? "-");
    if (el.sAnalysis) el.sAnalysis.textContent = String(stats.analysis_samples ?? "-");
    if (el.sPending) el.sPending.textContent = String((jobs.pending || 0) + (jobs.running || 0));

    const sig = data.signals_avg || {};
    const sigText = [
      `mood ${sig.mood ?? "-"}`,
      `stress ${sig.stress ?? "-"}`,
      `sleep ${sig.sleep ?? "-"}`,
      `exercise ${sig.exercise ?? "-"}`,
      `social ${sig.social ?? "-"}`,
      `work ${sig.work ?? "-"}`,
    ].join(" | ");
    if (el.signalsLine) el.signalsLine.textContent = sigText;

    const persona = data.persona || {};
    setList(el.traitList, persona.traits || []);
    setList(el.strengthList, persona.strengths || []);
    setList(el.weaknessList, persona.weaknesses || []);

    const topics = (data.topics || []).map((x) => `${x.topic} (${x.count})`);
    if (el.topicList) {
      el.topicList.textContent = topics.length ? topics.join(" · ") : "暂无";
    }
  } catch (err) {
    setStatus(`画像刷新失败: ${err.message}`);
  }
}

async function saveDiaryFromChat(text) {
  const data = await fetchJson("/api/diary/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });

  await Promise.all([loadHistory(), refreshInsights()]);

  appendAiMessage(
    `已识别为日记并保存。\n\n- Entry ID: ${data.entry_id || "-"}\n- Queued Blocks: ${data.queued_blocks ?? "-"}\n- Memory Updated: ${data.memory_updated ?? "-"}`
  );
}

async function replyChat(text, debugEnabled) {
  const data = await fetchJson("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, mode: "chat", debug: debugEnabled }),
  });

  appendAiMessage(data.reply || "未记录");
  updateDebugPanel(data.debug);
  if (debugEnabled && el.debugPanel) {
    el.debugPanel.open = true;
  }
}

async function sendUnifiedInput() {
  const text = el.unifiedInput?.value?.trim() || "";
  if (!text) return;

  const debugEnabled = Boolean(el.debugToggle?.checked);
  const kind = detectInputKind(text);

  appendUserMessage(text, kind);
  el.unifiedInput.value = "";
  setStatus(`已识别为${kind === "diary" ? "日记" : "聊天"}，处理中...`);
  if (el.sendBtn) el.sendBtn.disabled = true;

  try {
    if (kind === "diary") {
      await saveDiaryFromChat(text);
    } else {
      await replyChat(text, debugEnabled);
    }
    setStatus("");
  } catch (err) {
    appendAiMessage(`请求失败: ${err.message}`);
    setStatus("处理失败");
  } finally {
    if (el.sendBtn) el.sendBtn.disabled = false;
    el.unifiedInput?.focus();
  }
}

function clearChat() {
  if (!el.chatMessages) return;
  el.chatMessages.innerHTML = "";
  const empty = document.createElement("div");
  empty.className = "chat-empty";
  empty.textContent = "会话已清空，继续输入即可。";
  el.chatMessages.appendChild(empty);
  updateDebugPanel(null);
}

function bindEvents() {
  el.menuItems.forEach((btn) => {
    btn.addEventListener("click", () => {
      const view = btn.getAttribute("data-view") || "chat";
      switchView(view);
      if (view === "notebook") {
        loadHistory();
      }
      if (view === "insights") {
        refreshInsights();
      }
    });
  });

  el.sendBtn?.addEventListener("click", sendUnifiedInput);
  el.clearChatBtn?.addEventListener("click", clearChat);
  el.refreshHistoryBtn?.addEventListener("click", loadHistory);
  el.refreshInsightsBtn?.addEventListener("click", refreshInsights);

  el.unifiedInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendUnifiedInput();
    }
  });

  el.historyList?.addEventListener("click", (e) => {
    const button = e.target.closest(".history-item");
    if (!button) return;
    const date = button.getAttribute("data-date");
    if (date) {
      openDiary(date);
    }
  });
}

function ensureDomReady() {
  const required = [
    "systemPill", "chatMessages", "unifiedInput", "sendBtn", "historyList", "readerContent", "readerDate",
    "sDiaries", "sEntries", "sAnalysis", "sPending", "signalsLine", "traitList", "strengthList", "weaknessList", "topicList"
  ];

  const missing = required.filter((name) => !el[name]);
  if (missing.length > 0) {
    throw new Error(`Missing DOM nodes: ${missing.join(", ")}`);
  }
}

async function bootstrap() {
  ensureDomReady();
  bindEvents();
  switchView("chat");
  await Promise.all([refreshSystemPill(), loadHistory(), refreshInsights()]);
}

bootstrap();
