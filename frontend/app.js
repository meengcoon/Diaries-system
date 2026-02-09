const el = {
  diaryInput: document.getElementById("diary-input"),
  saveBtn: document.getElementById("save-btn"),
  analyzeLatestBtn: document.getElementById("analyze-latest-btn"),
  status: document.getElementById("status"),
  historyList: document.getElementById("history-list"),
  refreshHistoryBtn: document.getElementById("refresh-history-btn"),
  chatMessages: document.getElementById("chat-messages"),
  chatInput: document.getElementById("chat-input"),
  chatSendBtn: document.getElementById("chat-send-btn"),
  clearChatBtn: document.getElementById("clear-chat-btn"),
  debugToggle: document.getElementById("debug-toggle"),
  debugOutput: document.getElementById("debug-output"),
  debugPanel: document.getElementById("debug-panel"),
  systemPill: document.getElementById("system-pill"),
  metricEntryId: document.getElementById("metric-entry-id"),
  metricBlocks: document.getElementById("metric-blocks"),
  metricMemoryUpdated: document.getElementById("metric-memory-updated"),
  metricAnalysisOk: document.getElementById("metric-analysis-ok"),
  saveFilePath: document.getElementById("save-file-path"),
  anPending: document.getElementById("an-pending"),
  anRunning: document.getElementById("an-running"),
  anDone: document.getElementById("an-done"),
  anFailed: document.getElementById("an-failed"),
};

const state = {
  selectedDate: null,
  analyzePollTimer: null,
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
  if (emptyNode) {
    emptyNode.remove();
  }
}

function appendChat(role, text) {
  if (!el.chatMessages) return;

  clearChatEmpty();

  const node = document.createElement("div");
  node.className = `chat-msg ${role === "user" ? "user" : "ai"}`;

  if (role === "ai") {
    try {
      node.innerHTML = marked.parse(text || "");
    } catch (_err) {
      node.textContent = text;
    }
  } else {
    node.textContent = text;
  }

  el.chatMessages.appendChild(node);
  el.chatMessages.scrollTop = el.chatMessages.scrollHeight;
}

function updateSaveMetrics(data = {}) {
  el.metricEntryId.textContent = data.entry_id || "-";
  el.metricBlocks.textContent = String(data.queued_blocks ?? "-");
  el.metricMemoryUpdated.textContent = String(data.memory_updated ?? "-");
  el.metricAnalysisOk.textContent = String(data.analysis_ok ?? "-");
  el.saveFilePath.textContent = `文件: ${data.file || "-"}`;
}

function updateAnalyzeStats(stats = {}) {
  el.anPending.textContent = String(stats.pending ?? 0);
  el.anRunning.textContent = String(stats.running ?? 0);
  el.anDone.textContent = String(stats.done ?? 0);
  el.anFailed.textContent = String(stats.failed ?? 0);
}

async function refreshAnalyzeStatus() {
  try {
    const data = await fetchJson("/api/diary/analyze_status");
    updateAnalyzeStats(data.stats || {});
    return data.stats || {};
  } catch (_err) {
    return null;
  }
}

function startAnalyzePolling() {
  if (state.analyzePollTimer) {
    clearInterval(state.analyzePollTimer);
    state.analyzePollTimer = null;
  }
  state.analyzePollTimer = setInterval(async () => {
    const stats = await refreshAnalyzeStatus();
    if (!stats) return;
    if ((stats.pending || 0) === 0 && (stats.running || 0) === 0) {
      clearInterval(state.analyzePollTimer);
      state.analyzePollTimer = null;
      setStatus(`分析完成：done=${stats.done || 0}, failed=${stats.failed || 0}`);
    }
  }, 2000);
}

function updateDebugPanel(debugData) {
  if (!el.debugOutput) return;
  if (!debugData) {
    el.debugOutput.textContent = "暂无";
    return;
  }
  el.debugOutput.textContent = JSON.stringify(debugData, null, 2);
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
        <div class="history-preview">${preview}</div>
        <div class="history-meta">${sizeKB} KB</div>
      </button>
    `;
  }).join("");

  el.historyList.innerHTML = html;
}

async function loadHistory() {
  try {
    const data = await fetchJson("/api/diary/list?limit=90");
    renderHistory(data.items || []);
  } catch (err) {
    el.historyList.innerHTML = `<div class="history-empty">加载失败: ${err.message}</div>`;
  }
}

async function openDiary(date) {
  try {
    const data = await fetchJson(`/api/diary/read?date=${encodeURIComponent(date)}`);
    el.diaryInput.value = data.text || "";
    state.selectedDate = date;
    setStatus(`已加载 ${date}`);
    await loadHistory();
  } catch (err) {
    setStatus(`读取失败: ${err.message}`);
  }
}

async function saveDiary() {
  const text = el.diaryInput?.value?.trim() || "";
  if (!text) {
    setStatus("内容为空，未保存。");
    return;
  }

  el.saveBtn.disabled = true;
  setStatus("正在保存...");

  try {
    const data = await fetchJson("/api/diary/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });

    updateSaveMetrics(data);
    state.selectedDate = data.file?.match(/(\d{4}-\d{2}-\d{2})\.txt$/)?.[1] || null;
    await loadHistory();
    await refreshAnalyzeStatus();
    setStatus(`保存成功，已入队 ${data.queued_blocks ?? 0} 个分块`);
  } catch (err) {
    setStatus(`保存失败: ${err.message}`);
  } finally {
    el.saveBtn.disabled = false;
  }
}

async function analyzeLatest() {
  el.analyzeLatestBtn.disabled = true;
  setStatus("已提交同步任务，正在分析最新未完成日记...");
  try {
    await fetchJson("/api/diary/analyze_latest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        entry_limit: 60,
        job_limit: 300,
        preferred_provider: "deepseek",
        min_block_chars: 20,
        max_attempts: 12,
        job_timeout_s: 180,
      }),
    });
    await refreshAnalyzeStatus();
    startAnalyzePolling();
  } catch (err) {
    setStatus(`同步任务提交失败: ${err.message}`);
  } finally {
    el.analyzeLatestBtn.disabled = false;
  }
}

async function sendChat() {
  const text = el.chatInput?.value?.trim() || "";
  if (!text) return;

  const debugEnabled = Boolean(el.debugToggle?.checked);

  appendChat("user", text);
  el.chatInput.value = "";
  setStatus("AI 正在回复...");
  el.chatSendBtn.disabled = true;

  try {
    const data = await fetchJson("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, mode: "chat", debug: debugEnabled }),
    });

    appendChat("ai", data.reply || "未记录");
    updateDebugPanel(data.debug);
    if (debugEnabled && el.debugPanel) {
      el.debugPanel.open = true;
    }
    setStatus("");
  } catch (err) {
    appendChat("ai", `请求失败: ${err.message}`);
    setStatus("聊天请求失败");
  } finally {
    el.chatSendBtn.disabled = false;
    el.chatInput?.focus();
  }
}

function clearChat() {
  if (!el.chatMessages) return;
  el.chatMessages.innerHTML = "";
  const empty = document.createElement("div");
  empty.className = "chat-empty";
  empty.textContent = "会话已清空，开始新的提问。";
  el.chatMessages.appendChild(empty);
  updateDebugPanel(null);
}

function bindEvents() {
  el.saveBtn?.addEventListener("click", saveDiary);
  el.analyzeLatestBtn?.addEventListener("click", analyzeLatest);
  el.chatSendBtn?.addEventListener("click", sendChat);
  el.clearChatBtn?.addEventListener("click", clearChat);
  el.refreshHistoryBtn?.addEventListener("click", loadHistory);

  el.diaryInput?.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      saveDiary();
    }
  });

  el.chatInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendChat();
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
  const missing = Object.entries(el)
    .filter(([, node]) => !node)
    .map(([name]) => name);

  if (missing.length > 0) {
    throw new Error(`Missing DOM nodes: ${missing.join(", ")}`);
  }
}

async function bootstrap() {
  ensureDomReady();
  bindEvents();
  await Promise.all([refreshSystemPill(), loadHistory(), refreshAnalyzeStatus()]);
}

bootstrap();
