const el = {
  systemPill: document.getElementById("system-pill"),
  chatStatus: document.getElementById("chat-status"),
  diaryStatus: document.getElementById("diary-status"),
  menuItems: Array.from(document.querySelectorAll(".menu-item")),
  viewChat: document.getElementById("view-chat"),
  viewNotebook: document.getElementById("view-notebook"),
  viewInsights: document.getElementById("view-insights"),

  newChatBtn: document.getElementById("new-chat-btn"),
  chatSessionList: document.getElementById("chat-session-list"),
  chatSessionTitle: document.getElementById("chat-session-title"),
  chatSessionSubtitle: document.getElementById("chat-session-subtitle"),
  chatMessages: document.getElementById("chat-messages"),
  unifiedInput: document.getElementById("unified-input"),
  voiceChatBtn: document.getElementById("voice-chat-btn"),
  sendBtn: document.getElementById("send-btn"),
  debugToggle: document.getElementById("debug-toggle"),
  debugPanel: document.getElementById("debug-panel"),
  debugOutput: document.getElementById("debug-output"),

  diaryInput: document.getElementById("diary-input"),
  diaryRecordBtn: document.getElementById("diary-record-btn"),
  saveDiaryBtn: document.getElementById("save-diary-btn"),
  toggleComposeBtn: document.getElementById("toggle-compose-btn"),
  toggleHistoryBtn: document.getElementById("toggle-history-btn"),
  notebookComposeWrap: document.getElementById("notebook-compose-wrap"),
  notebookLayout: document.getElementById("notebook-layout"),
  historyPane: document.getElementById("history-pane"),
  historyList: document.getElementById("history-list"),
  refreshHistoryBtn: document.getElementById("refresh-history-btn"),
  readerDate: document.getElementById("reader-date"),
  readerState: document.getElementById("reader-state"),
  readerActions: document.getElementById("reader-actions"),
  readerEditBtn: document.getElementById("reader-edit-btn"),
  readerReanalyzeBtn: document.getElementById("reader-reanalyze-btn"),
  readerDeleteBtn: document.getElementById("reader-delete-btn"),
  readerCancelBtn: document.getElementById("reader-cancel-btn"),
  readerSaveBtn: document.getElementById("reader-save-btn"),
  readerEditor: document.getElementById("reader-editor"),
  readerAudio: document.getElementById("reader-audio"),
  readerContent: document.getElementById("reader-content"),

  refreshInsightsBtn: document.getElementById("refresh-insights-btn"),
  overviewEntriesCount: document.getElementById("overview-entries-count"),
  overviewLatestEntry: document.getElementById("overview-latest-entry"),
  overviewAnalysisJobs: document.getElementById("overview-analysis-jobs"),
  focusLines: document.getElementById("focus-lines"),
};

const state = {
  selectedHistoryKey: null,
  currentChatSessionId: null,
  chatSessions: [],
  currentView: "chat",
  recorder: null,
  recordStream: null,
  recordChunks: [],
  isRecording: false,
  recordMode: null,
  currentEntryDetail: null,
  currentAudioItem: null,
  isReaderEditing: false,
  notebookComposeOpen: false,
  notebookHistoryOpen: false,
};

function setStatus(text) {
  const value = text || "";
  if (el.chatStatus) el.chatStatus.textContent = value;
  if (el.diaryStatus) el.diaryStatus.textContent = value;
}

function setReaderState(text) {
  if (el.readerState) {
    el.readerState.textContent = text || "";
  }
}

function setReaderPlainText(text) {
  if (!el.readerContent) return;
  el.readerContent.classList.add("reader-plain");
  el.readerContent.innerHTML = "";
  el.readerContent.textContent = text || "";
}

function setReaderEditing(active) {
  state.isReaderEditing = Boolean(active);
  if (el.readerEditor) {
    el.readerEditor.classList.toggle("hidden", !active);
  }
  if (el.readerContent) {
    el.readerContent.classList.toggle("hidden", active);
  }
  if (el.readerEditBtn) el.readerEditBtn.classList.toggle("hidden", active);
  if (el.readerReanalyzeBtn) el.readerReanalyzeBtn.classList.toggle("hidden", active);
  if (el.readerDeleteBtn) el.readerDeleteBtn.classList.toggle("hidden", active);
  if (el.readerCancelBtn) el.readerCancelBtn.classList.toggle("hidden", !active);
  if (el.readerSaveBtn) el.readerSaveBtn.classList.toggle("hidden", !active);
}

function setReaderActionVisibility(kind = null) {
  const show = kind === "text" && Boolean(state.currentEntryDetail?.entry_id);
  if (el.readerActions) {
    el.readerActions.classList.toggle("hidden", !show);
  }
  if (!show) {
    setReaderEditing(false);
  }
}

function setNotebookComposeOpen(open) {
  state.notebookComposeOpen = Boolean(open);
  if (el.notebookComposeWrap) {
    el.notebookComposeWrap.classList.toggle("hidden", !state.notebookComposeOpen);
  }
  if (el.toggleComposeBtn) {
    el.toggleComposeBtn.textContent = state.notebookComposeOpen ? "收起输入" : "写日记";
  }
}

function setNotebookHistoryOpen(open) {
  state.notebookHistoryOpen = Boolean(open);
  if (el.historyPane) {
    el.historyPane.classList.toggle("hidden", !state.notebookHistoryOpen);
  }
  if (el.notebookLayout) {
    el.notebookLayout.classList.toggle("history-collapsed", !state.notebookHistoryOpen);
  }
  if (el.toggleHistoryBtn) {
    el.toggleHistoryBtn.textContent = state.notebookHistoryOpen ? "收起历史" : "历史记录";
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

function formatAnalysisStatus(status, ready = false) {
  const key = String(status || (ready ? "done" : "idle")).toLowerCase();
  if (key === "done") return "已完成";
  if (key === "running") return "分析中";
  if (key === "pending") return "待分析";
  if (key === "failed") return "分析失败";
  return ready ? "已完成" : "未开始";
}

function statusChip(status, ready = false) {
  const key = String(status || (ready ? "done" : "idle")).toLowerCase();
  const cls = ["done", "running", "pending", "failed"].includes(key) ? key : "idle";
  return `<span class="status-chip ${cls}">${escapeHtml(formatAnalysisStatus(key, ready))}</span>`;
}

function formatQualityBand(band, score) {
  const key = String(band || "").toLowerCase();
  if (key === "high") return `质量高 ${score}分`;
  if (key === "medium") return `质量中 ${score}分`;
  if (key === "low") return `质量低 ${score}分`;
  if (key === "insufficient") return "内容不足";
  if (key === "reject") return `质量拒收 ${score}分`;
  return `质量未知 ${score ?? "-"}`;
}

function qualityChip(quality = {}) {
  const band = String(quality.band || "").toLowerCase() || "medium";
  const score = Number(quality.score_total ?? 0);
  return `<span class="quality-chip ${escapeHtml(band)}">${escapeHtml(formatQualityBand(band, score))}</span>`;
}

function formatStageName(stage) {
  const key = String(stage || "").toLowerCase();
  if (key === "evidence") return "证据抽取";
  if (key === "deep") return "深度分析";
  if (key === "normalize") return "标准化";
  if (key === "normalize_repair") return "标准化修复";
  if (key === "final") return "最终落盘";
  return key || "未知阶段";
}

function formatRunStatus(status) {
  const key = String(status || "").toLowerCase();
  if (key === "ok") return "成功";
  if (key === "failed") return "失败";
  if (key === "rejected") return "拒收";
  if (key === "missing") return "未跑";
  return key || "未知";
}

function renderPipelineChip(stageItem = {}) {
  const status = String(stageItem.status || "missing").toLowerCase();
  const cls = ["ok", "failed", "rejected", "missing"].includes(status) ? status : "missing";
  const suffix = stageItem.backend ? ` · ${stageItem.backend}` : "";
  return `<span class="pipeline-chip ${cls}" title="${escapeHtml(stageItem.error || "")}">${escapeHtml(`${formatStageName(stageItem.stage)}：${formatRunStatus(status)}${suffix}`)}</span>`;
}

function renderPipelineSummary(pipeline = {}) {
  if (!pipeline || !pipeline.has_staged_runs) return "";
  const blocks = Array.isArray(pipeline.blocks) ? pipeline.blocks : [];
  if (!blocks.length) return "";

  const overview = (pipeline.stage_order || []).map((stageName) => {
    const stats = pipeline.stage_totals?.[stageName] || {};
    const ok = Number(stats.ok || 0);
    const failed = Number(stats.failed || 0);
    const rejected = Number(stats.rejected || 0);
    const missing = Number(stats.missing || 0);
    return `<div class="pipeline-overview-line"><strong>${escapeHtml(formatStageName(stageName))}</strong><span>成功 ${ok} · 失败 ${failed} · 拒收 ${rejected} · 未跑 ${missing}</span></div>`;
  }).join("");

  const blockLines = blocks.map((block) => {
    const preview = String(block.raw_preview || "").trim();
    return `
      <details class="pipeline-block">
        <summary>
          <span>块 ${escapeHtml(String((Number(block.idx || 0) + 1)))}</span>
          <span class="pipeline-block-status">${escapeHtml(formatRunStatus(block.final_status || "missing"))}</span>
        </summary>
        <div class="pipeline-block-chips">${(block.stages || []).map(renderPipelineChip).join("")}</div>
        ${preview ? `<div class="pipeline-block-preview">${escapeHtml(preview)}</div>` : ""}
      </details>
    `;
  }).join("");

  return `
    <section class="analysis-block full">
      <div class="analysis-label">分析流水线</div>
      <div class="pipeline-overview">${overview}</div>
      <div class="pipeline-block-list">${blockLines}</div>
    </section>
  `;
}

function renderChipRow(items = []) {
  const list = (Array.isArray(items) ? items : []).filter(Boolean);
  if (!list.length) return '<div class="chip-row"><span class="mini-chip">暂无</span></div>';
  return `<div class="chip-row">${list.map((item) => `<span class="mini-chip">${escapeHtml(item)}</span>`).join("")}</div>`;
}

function renderListLines(items = []) {
  const list = (Array.isArray(items) ? items : []).filter(Boolean);
  if (!list.length) return "<div>暂无</div>";
  return `<ul class="list-lines">${list.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function createUserMessageNode(text, kind = "chat") {
  const node = document.createElement("div");
  node.className = "chat-msg user";
  const tag = kind === "diary" ? "日记" : "聊天";
  node.innerHTML = `<div class="msg-kind">${tag}</div><div>${escapeHtml(text)}</div>`;
  return node;
}

function createAiMessageNode(text) {
  const node = document.createElement("div");
  node.className = "chat-msg ai";
  const body = document.createElement("div");
  body.className = "msg-text";
  body.textContent = text || "";
  node.appendChild(body);
  return node;
}

function appendUserMessage(text, kind) {
  if (!el.chatMessages) return;
  clearChatEmpty();
  const node = createUserMessageNode(text, kind);
  el.chatMessages.appendChild(node);
  el.chatMessages.scrollTop = el.chatMessages.scrollHeight;
}

function appendAiMessage(text) {
  if (!el.chatMessages) return;
  clearChatEmpty();
  const node = createAiMessageNode(text);
  el.chatMessages.appendChild(node);
  el.chatMessages.scrollTop = el.chatMessages.scrollHeight;
}

function setActiveSessionTitle(title) {
  if (el.chatSessionTitle) {
    el.chatSessionTitle.textContent = title || "新对话";
  }
}

function updateSessionSubtitle(text) {
  if (el.chatSessionSubtitle) {
    el.chatSessionSubtitle.textContent = text || "私人助理模式，可聊你的事，也可聊别的话题。";
  }
}

function formatSessionPreview(text) {
  const raw = String(text || "").trim().replace(/\s+/g, " ");
  if (!raw) return "还没有内容";
  return raw.slice(0, 38) + (raw.length > 38 ? "…" : "");
}

function formatSessionTime(ts) {
  const t = Date.parse(ts || "");
  if (!Number.isFinite(t)) return "";
  const now = Date.now();
  const diffMin = Math.max(0, Math.round((now - t) / 60000));
  if (diffMin < 1) return "刚刚";
  if (diffMin < 60) return `${diffMin} 分钟前`;
  const diffHour = Math.round(diffMin / 60);
  if (diffHour < 24) return `${diffHour} 小时前`;
  const d = new Date(t);
  return `${d.getMonth() + 1}-${d.getDate()}`;
}

function renderChatEmpty(text = "新建一段对话，或从左侧打开历史会话。") {
  if (!el.chatMessages) return;
  el.chatMessages.innerHTML = `<div class="chat-empty">${escapeHtml(text)}</div>`;
}

function renderChatSessionList(items = []) {
  if (!el.chatSessionList) return;
  if (!items.length) {
    el.chatSessionList.innerHTML = '<div class="history-empty">暂无会话</div>';
    return;
  }
  el.chatSessionList.innerHTML = items.map((item) => {
    const active = Number(item.id) === Number(state.currentChatSessionId) ? "active" : "";
    const preview = formatSessionPreview(item.last_user_text || item.summary || "");
    const count = Number(item.message_count || 0);
    return `
      <button class="chat-session-item ${active}" data-session-id="${item.id}" type="button">
        <div class="chat-session-top">
          <span class="chat-session-name">${escapeHtml(item.title || "新对话")}</span>
          <span class="chat-session-time">${escapeHtml(formatSessionTime(item.updated_at || item.created_at || ""))}</span>
        </div>
        <div class="chat-session-preview">${escapeHtml(preview)}</div>
        <div class="chat-session-meta">${count} 条消息</div>
      </button>
    `;
  }).join("");
}

function renderChatTranscript(items = []) {
  if (!el.chatMessages) return;
  if (!items.length) {
    renderChatEmpty();
    return;
  }
  el.chatMessages.innerHTML = "";
  items.forEach((item) => {
    const role = String(item.role || "");
    const text = String(item.text || "");
    const node = role === "assistant"
      ? createAiMessageNode(text)
      : createUserMessageNode(text, "chat");
    el.chatMessages.appendChild(node);
  });
  el.chatMessages.scrollTop = el.chatMessages.scrollHeight;
}

function formatNum(v, digits = 2) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "-";
  return n.toFixed(digits);
}

function canRecordAudio() {
  return Boolean(
    navigator?.mediaDevices?.getUserMedia &&
    typeof window.MediaRecorder !== "undefined"
  );
}

function preferredRecordMimeType() {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
  for (const c of candidates) {
    if (window.MediaRecorder?.isTypeSupported?.(c)) return c;
  }
  return "";
}

function updateDiaryRecordBtn() {
  if (!el.diaryRecordBtn) return;
  const active = state.isRecording && state.recordMode === "diary";
  el.diaryRecordBtn.classList.toggle("recording", active);
  el.diaryRecordBtn.textContent = active ? "停止录音(日记)" : "开始录音(日记)";
  el.diaryRecordBtn.disabled = state.isRecording && state.recordMode !== "diary";
}

function updateVoiceChatBtn() {
  if (!el.voiceChatBtn) return;
  const active = state.isRecording && state.recordMode === "voice_chat";
  el.voiceChatBtn.classList.toggle("recording", active);
  el.voiceChatBtn.textContent = active ? "停止语音对话" : "语音对话";
  el.voiceChatBtn.disabled = state.isRecording && state.recordMode !== "voice_chat";
}

function cleanupRecordStream() {
  if (state.recordStream) {
    state.recordStream.getTracks().forEach((t) => t.stop());
  }
  state.recordStream = null;
}

async function uploadVoiceBlob(blob) {
  const fd = new FormData();
  fd.append("audio", blob, `voice-${Date.now()}.webm`);

  const note = (el.diaryInput?.value || "").trim();
  if (note) {
    fd.append("note", note);
  }

  const data = await fetchJson("/api/diary/audio/save", {
    method: "POST",
    body: fd,
  });

  const a = data.analysis || {};
  const p = data.voice_profile || {};
  const habits = Array.isArray(p.habits) ? p.habits : [];
  const analysisOk = data.analysis_ok !== false && !a.error;
  if (el.diaryInput) {
    el.diaryInput.value = "";
  }
  if (!analysisOk) {
    if (el.readerDate) el.readerDate.textContent = `语音日记 #${data.audio_entry_id ?? "-"}`;
    setReaderActionVisibility("audio");
    setReaderState("语音已保存，但特征分析失败。");
    setReaderPlainText([
      "语音已保存，但特征分析失败。",
      "",
      `- Audio Entry ID: ${data.audio_entry_id ?? "-"}`,
      `- 失败原因: ${data.analysis_error || a.error || "unknown"}`,
    ].join("\n"));
    return;
  }

  if (el.readerDate) el.readerDate.textContent = `语音日记 #${data.audio_entry_id ?? "-"}`;
  setReaderActionVisibility("audio");
  setReaderState("语音已保存，并已提取本地语音特征。");
  setReaderPlainText([
    "已保存语音日记并完成特征分析。",
    "",
    `- Audio Entry ID: ${data.audio_entry_id ?? "-"}`,
    `- 时长: ${formatNum(a.duration_s, 2)}s`,
    `- 发声占比: ${formatNum((Number(a.voiced_ratio || 0) * 100), 1)}%`,
    `- 停顿占比: ${formatNum((Number(a.pause_ratio || 0) * 100), 1)}%`,
    `- 停顿频率: ${formatNum(a.pauses_per_min, 1)} 次/分钟`,
    `- 语速代理: ${formatNum(a.syllable_rate_proxy, 2)} 单位/s`,
    "",
    habits.length ? "语音习惯画像：" : "语音习惯画像：样本不足",
    ...habits.map((h) => `- ${h}`),
  ].join("\n"));
}

async function playAssistantAudio(audioBase64, audioMime) {
  if (!audioBase64) return;
  const src = `data:${audioMime || "audio/mpeg"};base64,${audioBase64}`;
  const player = new Audio(src);
  await player.play();
}

async function loadChatSessions(preferredSessionId = null) {
  const data = await fetchJson("/api/chat/sessions?limit=80");
  const items = Array.isArray(data.items) ? data.items : [];
  state.chatSessions = items;

  if (preferredSessionId) {
    state.currentChatSessionId = Number(preferredSessionId);
  } else if (!state.currentChatSessionId && items.length) {
    state.currentChatSessionId = Number(items[0].id);
  } else if (
    state.currentChatSessionId &&
    !items.some((item) => Number(item.id) === Number(state.currentChatSessionId))
  ) {
    state.currentChatSessionId = items.length ? Number(items[0].id) : null;
  }

  renderChatSessionList(items);
  const active = items.find((item) => Number(item.id) === Number(state.currentChatSessionId));
  if (active) {
    setActiveSessionTitle(active.title);
    updateSessionSubtitle(`最近更新 ${formatSessionTime(active.updated_at || active.created_at || "")} · ${Number(active.message_count || 0)} 条消息`);
  } else {
    setActiveSessionTitle("新对话");
    updateSessionSubtitle();
  }
  return items;
}

async function createNewChatSession() {
  const data = await fetchJson("/api/chat/session/new", { method: "POST" });
  state.currentChatSessionId = Number(data.id);
  renderChatEmpty();
  setActiveSessionTitle(data.title || "新对话");
  updateSessionSubtitle("新会话已创建，开始聊吧。");
  updateDebugPanel(null);
  await loadChatSessions(state.currentChatSessionId);
  el.unifiedInput?.focus();
}

async function openChatSession(sessionId) {
  const sid = Number(sessionId);
  if (!Number.isFinite(sid) || sid <= 0) return;
  const data = await fetchJson(`/api/chat/session?id=${encodeURIComponent(String(sid))}&limit=300`);
  state.currentChatSessionId = sid;
  renderChatTranscript(Array.isArray(data.items) ? data.items : []);
  const session = data.session || {};
  setActiveSessionTitle(session.title || "新对话");
  updateSessionSubtitle(`最近更新 ${formatSessionTime(session.updated_at || session.created_at || "")} · ${Number((data.items || []).length)} 条消息`);
  renderChatSessionList(state.chatSessions);
}

async function uploadVoiceChatBlob(blob) {
  const fd = new FormData();
  fd.append("audio", blob, `voice-chat-${Date.now()}.webm`);
  if (state.currentChatSessionId) {
    fd.append("session_id", String(state.currentChatSessionId));
  }
  fd.append("debug", String(Boolean(el.debugToggle?.checked)));
  fd.append("mimic_voice", "true");

  const data = await fetchJson("/api/voice/chat", {
    method: "POST",
    body: fd,
  });

  appendUserMessage(data.transcript || "[语音消息]", "chat");
  appendAiMessage(data.reply || "未记录");
  if (data.session_id) {
    state.currentChatSessionId = Number(data.session_id);
    await loadChatSessions(state.currentChatSessionId);
  }
  updateDebugPanel(data.debug);
  if (Boolean(el.debugToggle?.checked) && el.debugPanel) {
    el.debugPanel.open = true;
  }

  if (data.warning) {
    setStatus(data.warning);
  }

  if (data.audio_base64) {
    try {
      await playAssistantAudio(data.audio_base64, data.audio_mime);
    } catch (err) {
      appendAiMessage(`语音播放失败: ${err.message}`);
    }
  }
}

async function startRecording(mode = "diary") {
  if (!canRecordAudio()) {
    throw new Error("当前浏览器不支持录音（需要 MediaRecorder）");
  }

  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  state.recordStream = stream;
  state.recordChunks = [];

  const mimeType = preferredRecordMimeType();
  const recorder = mimeType
    ? new MediaRecorder(stream, { mimeType })
    : new MediaRecorder(stream);
  state.recorder = recorder;

  recorder.addEventListener("dataavailable", (e) => {
    if (e.data && e.data.size > 0) {
      state.recordChunks.push(e.data);
    }
  });

  recorder.addEventListener("stop", async () => {
    const chunkType = state.recordChunks[0]?.type || "audio/webm";
    const blob = new Blob(state.recordChunks, { type: chunkType });
    state.recordChunks = [];
    cleanupRecordStream();

    if (blob.size <= 0) {
      setStatus("录音为空，未上传");
      return;
    }

    try {
      if (el.diaryRecordBtn) el.diaryRecordBtn.disabled = true;
      if (el.voiceChatBtn) el.voiceChatBtn.disabled = true;

      if (mode === "voice_chat") {
        setStatus("语音识别与对话中...");
        await uploadVoiceChatBlob(blob);
        setStatus("语音对话完成");
      } else {
        setStatus("语音上传与分析中...");
        await uploadVoiceBlob(blob);
        await Promise.all([loadHistory(), refreshInsights()]);
        setStatus("语音日记已保存");
      }
    } catch (err) {
      appendAiMessage(`语音上传失败: ${err.message}`);
      setStatus("语音上传失败");
    } finally {
      if (el.diaryRecordBtn) el.diaryRecordBtn.disabled = false;
      if (el.voiceChatBtn) el.voiceChatBtn.disabled = false;
    }
  });

  recorder.start(300);
  state.isRecording = true;
  state.recordMode = mode;
  updateDiaryRecordBtn();
  updateVoiceChatBtn();
  setStatus("录音中，点击“停止录音”结束");
}

function stopRecording() {
  if (!state.recorder || state.recorder.state !== "recording") return;
  state.recorder.stop();
  state.recorder = null;
  state.isRecording = false;
  state.recordMode = null;
  updateDiaryRecordBtn();
  updateVoiceChatBtn();
}

async function toggleRecording(mode = "diary") {
  if (!state.isRecording) {
    await startRecording(mode);
    return;
  }
  if (state.recordMode && state.recordMode !== mode) return;
  stopRecording();
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

async function refreshSystemPill() {
  if (!el.systemPill) return;

  try {
    const info = await fetchJson("/api/_bot");
    const healthy = Boolean(info.bot);
    const answerModel = info?.models?.answer_model || "";

    el.systemPill.classList.remove("ok", "bad");
    el.systemPill.classList.add(healthy ? "ok" : "bad");
    el.systemPill.textContent = healthy
      ? `模型已连接: ${info.bot}${answerModel ? ` · ${answerModel}` : ""}`
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
    const itemType = item.kind || "text";
    const itemKey = item.key || "";
    const active = state.selectedHistoryKey === itemKey ? "active" : "";
    const sizeKB = (Number(item.size_bytes || 0) / 1024).toFixed(1);
    const preview = item.preview || "(无摘要)";
    const dateLabel = itemType === "audio"
      ? `${item.date} · 语音`
      : `${item.date || ""}${item.time_label ? ` · ${item.time_label}` : ""}`;
    const analysisMeta = itemType === "text"
      ? ` · ${formatAnalysisStatus(item.analysis_status, item.analysis_ready)}`
      : "";
    const errorLine = itemType === "text" && item.analysis_status === "failed" && item.analysis_error
      ? `<div class="history-meta">${escapeHtml(item.analysis_error)}</div>`
      : "";
    return `
      <button class="history-item ${active}" data-kind="${itemType}" data-key="${escapeHtml(itemKey)}" data-date="${item.date}" data-entry-id="${item.entry_id || ""}" data-audio-id="${item.audio_id || ""}" type="button">
        <div class="history-date">${dateLabel}</div>
        <div class="history-preview">${escapeHtml(preview)}</div>
        <div class="history-meta">${sizeKB} KB${analysisMeta}</div>
        ${errorLine}
      </button>
    `;
  }).join("");

  el.historyList.innerHTML = html;
}

function formatClockLabel(ts) {
  const t = Date.parse(ts || "");
  if (!Number.isFinite(t)) return "";
  const d = new Date(t);
  return d.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function formatEntryDetail(data, locator = null) {
  const analysis = data.analysis || {};
  const quality = analysis.analysis_quality || {};
  const pipeline = data.analysis_pipeline || {};
  const signals = analysis.signals || {};
  const topics = Array.isArray(analysis.topics) ? analysis.topics : [];
  const facts = Array.isArray(analysis.facts) ? analysis.facts : [];
  const todos = Array.isArray(analysis.todos) ? analysis.todos : [];
  const themes = Array.isArray(analysis.psychological_themes) ? analysis.psychological_themes : [];
  const tensions = Array.isArray(analysis.tensions) ? analysis.tensions : [];
  const needs = Array.isArray(analysis.needs) ? analysis.needs : [];
  const patterns = Array.isArray(analysis.patterns) ? analysis.patterns : [];
  const memoryCandidates = Array.isArray(analysis.memory_candidates) ? analysis.memory_candidates : [];
  const evidence = Array.isArray(analysis.evidence_spans) ? analysis.evidence_spans : [];
  const failures = Array.isArray(data.failure_reasons) ? data.failure_reasons : [];
  const meta = data.job_stats || {};

  const raw = String(data.text || "");
  const lineNo = Number(locator?.line_no || 0);
  let rawText = raw;
  if (Number.isFinite(lineNo) && lineNo > 0) {
    const lines = raw.split("\n");
    const idx = Math.max(0, Math.min(lines.length - 1, lineNo - 1));
    lines[idx] = `>> ${lines[idx]}`;
    rawText = lines.join("\n");
  }

  const signalNames = [
    ["mood", "情绪"],
    ["stress", "压力"],
    ["sleep", "睡眠"],
    ["exercise", "运动"],
    ["social", "社交"],
    ["work", "工作"],
  ];
  const signalHtml = signalNames.map(([key, label]) => `
    <div class="signal-pill">
      <div class="signal-pill-name">${label}</div>
      <div class="signal-pill-value">${escapeHtml(signals[key] ?? "-")}</div>
    </div>
  `).join("");

  const failureHtml = failures.length ? `
    <section class="failure-card">
      <div class="entry-card-title">
        <strong>失败原因</strong>
        ${statusChip("failed")}
      </div>
      <ul class="failure-list">
        ${failures.map((item) => `<li>块 ${escapeHtml((Number(item.block_idx || 0) + 1).toString())} · 第 ${escapeHtml(String(item.attempts || 0))} 次尝试：${escapeHtml(item.message || "")}</li>`).join("")}
      </ul>
    </section>
  ` : "";

  return `
    <div class="entry-stack">
      <section class="analysis-card">
        <div class="entry-card-title">
          <strong>分析结果</strong>
          <div class="analysis-meta-row">
            ${qualityChip(quality)}
            ${statusChip(data.analysis_status, data.analysis_ready)}
          </div>
        </div>
        <div class="analysis-summary">${escapeHtml(analysis.summary_1_3 || "暂无摘要")}</div>
        <div class="analysis-open">${escapeHtml(String(analysis.open_insight || "暂无更深入的开放洞察。"))}</div>
        <div class="analysis-open">质量判定：${escapeHtml((quality.reasons || []).join(" · ") || "暂无质量说明。")}</div>
        <div class="analysis-grid">
          <section class="analysis-block">
            <div class="analysis-label">结构化信号</div>
            <div class="signal-grid">${signalHtml}</div>
            <div class="analysis-open">反思深度：${escapeHtml(String(analysis.reflection_depth ?? "-"))}</div>
          </section>
          <section class="analysis-block">
            <div class="analysis-label">主题与模式</div>
            ${renderChipRow(topics)}
            <div class="analysis-label">心理主题</div>
            ${renderChipRow(themes)}
            <div class="analysis-label">模式</div>
            ${renderChipRow(patterns)}
          </section>
          <section class="analysis-block">
            <div class="analysis-label">张力与需求</div>
            <div class="analysis-label">张力 / 矛盾</div>
            ${renderChipRow(tensions)}
            <div class="analysis-label">需求 / 稳定器</div>
            ${renderChipRow(needs)}
          </section>
          <section class="analysis-block">
            <div class="analysis-label">事实与待办</div>
            <div class="analysis-label">事实</div>
            ${renderListLines(facts)}
            <div class="analysis-label">待办</div>
            ${renderListLines(todos)}
          </section>
          <section class="analysis-block full">
            <div class="analysis-label">长期记忆候选</div>
            ${renderChipRow(memoryCandidates)}
            <div class="analysis-label">证据片段</div>
            ${renderListLines(evidence)}
            <div class="analysis-open">队列状态：pending=${escapeHtml(String(meta.pending ?? 0))}，running=${escapeHtml(String(meta.running ?? 0))}，done=${escapeHtml(String(meta.done ?? 0))}，failed_retriable=${escapeHtml(String(meta.failed_retriable ?? 0))}，failed_exhausted=${escapeHtml(String(meta.failed_exhausted ?? 0))}，skipped=${escapeHtml(String(meta.skipped ?? 0))}</div>
          </section>
          ${renderPipelineSummary(pipeline)}
        </div>
      </section>
      ${failureHtml}
      <section class="raw-card">
        <div class="entry-card-title">
          <strong>原始日记</strong>
        </div>
        <div class="raw-text">${escapeHtml(rawText || "(空白)")}</div>
      </section>
    </div>
  `;
}

async function loadHistory() {
  try {
    const [textData, audioData] = await Promise.all([
      fetchJson("/api/diary/list?limit=120"),
      fetchJson("/api/diary/audio/list?limit=120"),
    ]);

    const textItems = (textData.items || []).map((it) => ({
      kind: "text",
      key: `text:${it.entry_id}`,
      entry_id: it.entry_id,
      date: it.date,
      preview: it.preview,
      size_bytes: it.size_bytes,
      created_at: it.created_at,
      time_label: formatClockLabel(it.created_at),
      analysis_ready: Boolean(it.analysis_ready),
      analysis_status: it.analysis_status || "idle",
      analysis_error: it.analysis_error || "",
    }));

    const audioItems = (audioData.items || []).map((it) => {
      const analysis = it.analysis || {};
      const duration = Number(it.duration_s ?? analysis.duration_s);
      const durationLabel = Number.isFinite(duration) ? `${duration.toFixed(1)}s` : "时长未知";
      const note = (it.note || "").trim();
      return {
        kind: "audio",
        key: `audio:${it.id}`,
        date: it.diary_date,
        audio_id: it.id,
        preview: note ? `🎤 ${note}` : `🎤 语音日记（${durationLabel}）`,
        size_bytes: it.file_size_bytes || analysis.file_size_bytes || 0,
        created_at: it.created_at,
        raw: it,
      };
    });

    const allItems = [...textItems, ...audioItems].sort((a, b) => {
      const ta = Date.parse(a.created_at || a.updated_at || "") || 0;
      const tb = Date.parse(b.created_at || b.updated_at || "") || 0;
      return tb - ta;
    });

    state._audioMap = Object.fromEntries(audioItems.map((x) => [String(x.audio_id), x.raw]));
    renderHistory(allItems);
  } catch (err) {
    el.historyList.innerHTML = `<div class="history-empty">加载失败: ${escapeHtml(err.message)}</div>`;
  }
}

async function renderAudioDiaryDetail(audioItem) {
  const it = audioItem || {};
  state.currentAudioItem = it;
  state.currentEntryDetail = null;
  setReaderActionVisibility("audio");
  setReaderState("语音日记支持播放、查看转写与分析概览。");
  const analysis = it.analysis || {};
  let detail = null;
  let detailErr = "";
  try {
    detail = await fetchJson(`/api/diary/audio/detail?id=${encodeURIComponent(String(it.id || ""))}`);
  } catch (err) {
    detail = null;
    detailErr = err?.message || "unknown";
  }
  const contentLink = detail?.content_link || null;
  const transcriptObj = detail?.transcript || {};
  const cloudProfile = detail?.cloud_profile || {};
  const transcriptProfile = detail?.transcript_profile || {};
  const entryAnalysis = cloudProfile.entry_analysis || {};
  const cloudSignals = entryAnalysis.signals || {};
  const cloudTopics = Array.isArray(entryAnalysis.topics) ? entryAnalysis.topics : [];
  const cloudJobStats = cloudProfile.job_stats || {};
  const transcriptTraits = Array.isArray(transcriptProfile.traits) ? transcriptProfile.traits : [];
  const transcriptSignals = transcriptProfile.signals || {};
  const transcriptRaw = String(transcriptObj.text || "").trim();
  const transcript = transcriptRaw || "(转写文本暂无)";
  const summaryLines = [
    `日期: ${it.diary_date || "-"}`,
    `创建时间: ${it.created_at || "-"}`,
    `格式: ${it.source_format || analysis.source_ext || "-"}`,
    `大小: ${((Number(it.file_size_bytes || 0) / 1024) || 0).toFixed(1)} KB`,
    `时长: ${formatNum(it.duration_s ?? analysis.duration_s, 2)} s`,
    "",
    "【1/4】语音播放进度条",
    "上方播放器可直接播放、拖拽定位和查看进度。",
    "",
    "【2/4】我的说话特征（本地）",
    `- 发声占比: ${formatNum((Number(analysis.voiced_ratio || 0) * 100), 1)}%`,
    `- 停顿占比: ${formatNum((Number(analysis.pause_ratio || 0) * 100), 1)}%`,
    `- 停顿频率: ${formatNum(analysis.pauses_per_min, 1)} 次/分钟`,
    `- 语速代理: ${formatNum(analysis.syllable_rate_proxy, 2)} 单位/s`,
    "",
    "【3/4】云API转写后的说话特点（基于转写文本提炼）",
    `- 样本长度: ${transcriptProfile.sample_chars ?? 0} 字；句子数: ${transcriptProfile.sentence_count ?? 0}；平均句长: ${transcriptProfile.avg_sentence_len ?? "-"} 字`,
    ...(transcriptTraits.length ? transcriptTraits.map((x) => `- ${x}`) : ["- 暂无稳定特点（转写文本不足）"]),
    `- 量化信号: 口语词=${transcriptSignals.fillers_count ?? 0}, 自我修正=${transcriptSignals.self_repair_count ?? 0}, 时间锚点=${transcriptSignals.timeline_anchor_count ?? 0}, 情绪词=${transcriptSignals.emotion_word_count ?? 0}, 行动词=${transcriptSignals.action_word_count ?? 0}`,
    "",
    "云任务附注（非说话特点）",
    `- 文字化状态: ${cloudProfile.status || contentLink?.status || "unknown"}${cloudProfile.error ? ` (${cloudProfile.error})` : ""}${detailErr ? ` (detail_err=${detailErr})` : ""}`,
    `- 云服务商: ${cloudProfile.provider || "-"}`,
    `- 关联条目ID: ${transcriptObj.entry_id ?? "-"}`,
    `- 分析队列: pending=${cloudJobStats.pending ?? 0}, running=${cloudJobStats.running ?? 0}, done=${cloudJobStats.done ?? 0}, failed=${cloudJobStats.failed ?? 0}, skipped=${cloudJobStats.skipped ?? 0}`,
    `- 云侧主题(如有): ${cloudTopics.length ? cloudTopics.slice(0, 4).join("、") : "-"}`,
    `- 云侧情绪信号(如有): mood=${cloudSignals.mood ?? "-"}, stress=${cloudSignals.stress ?? "-"}, sleep=${cloudSignals.sleep ?? "-"}, work=${cloudSignals.work ?? "-"}`,
    "",
    "【4/4】语音日记文本转录",
    transcript,
    "",
    "备注",
    (it.note || "(无备注)"),
  ];
  if (el.readerAudio) {
    el.readerAudio.src = `/api/diary/audio/file?id=${encodeURIComponent(String(it.id || ""))}&prefer=mp3`;
    el.readerAudio.classList.remove("hidden");
    el.readerAudio.load();
  }
  if (el.readerDate) el.readerDate.textContent = `语音日记 #${it.id || "-"}`;
  if (el.readerEditor) el.readerEditor.value = "";
  setReaderEditing(false);
  setReaderPlainText(summaryLines.join("\n"));
}

async function openDiary(date, locator = null) {
  try {
    const entryId = Number(locator?.entry_id || 0);
    const hasEntryId = Number.isFinite(entryId) && entryId > 0;
    const data = hasEntryId
      ? await fetchJson(`/api/diary/entry?id=${encodeURIComponent(String(entryId))}`)
      : await fetchJson(`/api/diary/read?date=${encodeURIComponent(date)}`);
    const resolvedDate = String(data.date || date || "");
    state.selectedHistoryKey = hasEntryId ? `text:${entryId}` : `text:${resolvedDate}`;
    if (el.readerAudio) {
      el.readerAudio.pause();
      el.readerAudio.removeAttribute("src");
      el.readerAudio.classList.add("hidden");
    }
    state.currentAudioItem = null;
    if (el.readerDate) {
      const entryHint = hasEntryId ? ` · 条目 ${entryId}` : "";
      const lineHint = locator?.line_no ? ` · 定位行 ${locator.line_no}` : "";
      const paraHint = locator?.paragraph_id ? ` · 段落 ${locator.paragraph_id}` : "";
      el.readerDate.textContent = `日记 ${resolvedDate}${entryHint}${paraHint}${lineHint}`;
    }
    state.currentEntryDetail = hasEntryId ? data : null;
    if (hasEntryId) {
      setNotebookHistoryOpen(false);
    }
    setReaderActionVisibility(hasEntryId ? "text" : null);
    setReaderEditing(false);
    setReaderState(hasEntryId ? `${formatAnalysisStatus(data.analysis_status, data.analysis_ready)} · 原文与分析已分开存储` : "原始文件视图");
    if (el.readerContent) {
      if (hasEntryId) {
        el.readerContent.classList.remove("reader-plain");
        el.readerContent.innerHTML = formatEntryDetail(data, locator);
        if (el.readerEditor) {
          el.readerEditor.value = String(data.text || "");
        }
      } else {
        setReaderPlainText(String(data.text || ""));
      }
    }
    setStatus(hasEntryId ? `已加载条目 #${entryId}` : `已加载 ${resolvedDate}`);
    await loadHistory();
  } catch (err) {
    setStatus(`读取失败: ${err.message}`);
    setReaderState(`读取失败：${err.message}`);
  }
}

async function refreshInsights() {
  try {
    const data = await fetchJson("/api/dashboard/overview?limit=120");
    const focus = Array.isArray(data.focus_lines) ? data.focus_lines : [];
    const jobs = data.analysis_jobs || {};
    const latest = data.latest_entry || {};
    if (el.overviewEntriesCount) {
      el.overviewEntriesCount.textContent = String(data.entries_count ?? 0);
    }
    if (el.overviewLatestEntry) {
      const latestId = latest.entry_id ? `#${latest.entry_id}` : "暂无";
      const latestAt = latest.created_at ? ` · ${latest.created_at}` : "";
      el.overviewLatestEntry.textContent = `${latestId}${latestAt}`;
    }
    if (el.overviewAnalysisJobs) {
      el.overviewAnalysisJobs.textContent = [
        `总计 ${jobs.total ?? 0}`,
        `待分析 ${jobs.pending ?? 0}`,
        `分析中 ${jobs.running ?? 0}`,
        `完成 ${jobs.done ?? 0}`,
        `失败 ${jobs.failed ?? 0}`,
      ].join(" · ");
    }
    if (el.focusLines) {
      el.focusLines.textContent = focus.length ? focus.join(" · ") : "暂无";
    }
  } catch (err) {
    setStatus(`概览刷新失败: ${err.message}`);
  }
}

function showSavedDiary(text, data) {
  if (el.readerAudio) {
    el.readerAudio.pause();
    el.readerAudio.removeAttribute("src");
    el.readerAudio.classList.add("hidden");
  }
  if (el.readerDate) {
    el.readerDate.textContent = `已保存日记 #${data.entry_id || "-"}`;
  }
  state.currentEntryDetail = data.entry_detail || null;
  state.currentAudioItem = null;
  setNotebookComposeOpen(false);
  setNotebookHistoryOpen(false);
  setReaderActionVisibility("text");
  setReaderEditing(false);
  setReaderState(`${formatAnalysisStatus(data.analysis_status, data.analysis_ok)} · ${data.analysis_backend || "local"} 分析`);
  if (el.readerContent) {
    const detail = data.entry_detail || {};
    if (Object.keys(detail).length) {
      el.readerContent.classList.remove("reader-plain");
      el.readerContent.innerHTML = formatEntryDetail(detail);
      if (el.readerEditor) {
        el.readerEditor.value = String(detail.text || text || "");
      }
    } else {
      setReaderPlainText(String(text || "").trim() || "已保存空白日记");
    }
  }
  state.selectedHistoryKey = `text:${data.entry_id || ""}`;
}

async function saveDiary(text) {
  const data = await fetchJson("/api/diary/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });

  await Promise.all([loadHistory(), refreshInsights()]);
  showSavedDiary(text, data);
  return data;
}

async function updateDiaryEntry(entryId, text) {
  const data = await fetchJson("/api/diary/entry", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: entryId, text }),
  });
  await Promise.all([loadHistory(), refreshInsights()]);
  showSavedDiary(text, data);
  return data;
}

async function reanalyzeDiaryEntry(entryId) {
  const data = await fetchJson("/api/diary/entry/reanalyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: entryId, force_reanalyze: true }),
  });
  await Promise.all([loadHistory(), refreshInsights()]);
  const detail = data.entry_detail || {};
  state.currentEntryDetail = detail;
  if (el.readerContent) {
    el.readerContent.classList.remove("reader-plain");
    el.readerContent.innerHTML = formatEntryDetail(detail);
  }
  if (el.readerEditor) {
    el.readerEditor.value = String(detail.text || "");
  }
  setReaderState(`${formatAnalysisStatus(data.analysis_status, data.analysis_ok)} · ${data.analysis_backend || "local"} 分析`);
  return data;
}

async function deleteDiaryEntry(entryId) {
  const data = await fetchJson(`/api/diary/entry?id=${encodeURIComponent(String(entryId))}`, {
    method: "DELETE",
  });
  await Promise.all([loadHistory(), refreshInsights()]);
  state.currentEntryDetail = null;
  state.selectedHistoryKey = null;
  setReaderActionVisibility(null);
  setReaderEditing(false);
  if (el.readerAudio) {
    el.readerAudio.pause();
    el.readerAudio.removeAttribute("src");
    el.readerAudio.classList.add("hidden");
  }
  if (el.readerDate) el.readerDate.textContent = "请选择一条日记";
  if (el.readerEditor) el.readerEditor.value = "";
  setReaderState("这篇日记已删除。");
  setReaderPlainText("请选择另一条日记。");
  return data;
}

async function replyChat(text, debugEnabled) {
  const data = await fetchJson("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text,
      mode: "chat",
      session_id: state.currentChatSessionId,
      debug: debugEnabled,
    }),
  });

  appendAiMessage(data.reply || "未记录");
  if (data.session_id) {
    state.currentChatSessionId = Number(data.session_id);
    await loadChatSessions(state.currentChatSessionId);
  }
  updateDebugPanel(data.debug);
  if (debugEnabled && el.debugPanel) {
    el.debugPanel.open = true;
  }
  return data;
}

async function sendChatInput() {
  const text = el.unifiedInput?.value?.trim() || "";
  if (!text) return;

  const debugEnabled = Boolean(el.debugToggle?.checked);
  appendUserMessage(text, "chat");
  el.unifiedInput.value = "";
  setStatus("对话处理中...");
  if (el.sendBtn) el.sendBtn.disabled = true;

  try {
    await replyChat(text, debugEnabled);
    setStatus("");
  } catch (err) {
    appendAiMessage(`请求失败: ${err.message}`);
    setStatus("处理失败");
  } finally {
    if (el.sendBtn) el.sendBtn.disabled = false;
    el.unifiedInput?.focus();
  }
}

async function sendDiaryInput() {
  const text = el.diaryInput?.value?.trim() || "";
  if (!text) return;

  if (el.saveDiaryBtn) el.saveDiaryBtn.disabled = true;
  const oldLabel = el.saveDiaryBtn?.textContent || "保存日记";
  if (el.saveDiaryBtn) el.saveDiaryBtn.textContent = "保存并排队分析...";
  setStatus("正在保存原文并加入分析队列...");
  setReaderState("正在保存这篇日记，分析会在后台开始。");

  try {
    const data = await saveDiary(text);
    if (el.diaryInput) {
      el.diaryInput.value = "";
    }
    const backend = data.analysis_backend ? `，分析后端 ${data.analysis_backend}` : "";
    const statusText = data.analysis_ok
      ? "，分析结果已可用"
      : `，分析状态 ${formatAnalysisStatus(data.analysis_status, false)}`;
    setStatus(`日记已保存（Entry #${data.entry_id || "-"}${backend}）${statusText}`);
  } catch (err) {
    setStatus(`日记保存失败: ${err.message}`);
    setReaderState("保存或分析失败，请重试。");
  } finally {
    if (el.saveDiaryBtn) {
      el.saveDiaryBtn.disabled = false;
      el.saveDiaryBtn.textContent = oldLabel;
    }
    el.diaryInput?.focus();
  }
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

  el.sendBtn?.addEventListener("click", sendChatInput);
  el.newChatBtn?.addEventListener("click", createNewChatSession);
  el.diaryRecordBtn?.addEventListener("click", async () => {
    try {
      await toggleRecording("diary");
    } catch (err) {
      setStatus(`录音失败: ${err.message}`);
      cleanupRecordStream();
      state.isRecording = false;
      state.recordMode = null;
      updateDiaryRecordBtn();
      updateVoiceChatBtn();
    }
  });
  el.voiceChatBtn?.addEventListener("click", async () => {
    try {
      await toggleRecording("voice_chat");
    } catch (err) {
      setStatus(`语音对话失败: ${err.message}`);
      cleanupRecordStream();
      state.isRecording = false;
      state.recordMode = null;
      updateDiaryRecordBtn();
      updateVoiceChatBtn();
    }
  });
  el.saveDiaryBtn?.addEventListener("click", sendDiaryInput);
  el.toggleComposeBtn?.addEventListener("click", () => setNotebookComposeOpen(!state.notebookComposeOpen));
  el.toggleHistoryBtn?.addEventListener("click", () => setNotebookHistoryOpen(!state.notebookHistoryOpen));
  el.refreshHistoryBtn?.addEventListener("click", loadHistory);
  el.refreshInsightsBtn?.addEventListener("click", refreshInsights);
  el.readerEditBtn?.addEventListener("click", () => {
    if (!state.currentEntryDetail) return;
    if (el.readerEditor) {
      el.readerEditor.value = String(state.currentEntryDetail.text || "");
      el.readerEditor.focus();
    }
    setReaderState("编辑原文后保存，会重新分析这篇日记。");
    setReaderEditing(true);
  });
  el.readerCancelBtn?.addEventListener("click", () => {
    if (el.readerEditor && state.currentEntryDetail) {
      el.readerEditor.value = String(state.currentEntryDetail.text || "");
    }
    setReaderState(`${formatAnalysisStatus(state.currentEntryDetail?.analysis_status, state.currentEntryDetail?.analysis_ready)} · 已取消编辑`);
    setReaderEditing(false);
  });
  el.readerSaveBtn?.addEventListener("click", async () => {
    const entryId = Number(state.currentEntryDetail?.entry_id || 0);
    const text = el.readerEditor?.value?.trim() || "";
    if (!entryId || !text) return;
    const oldLabel = el.readerSaveBtn?.textContent || "保存修改";
    if (el.readerSaveBtn) {
      el.readerSaveBtn.disabled = true;
      el.readerSaveBtn.textContent = "保存并排队分析...";
    }
    setReaderState("正在保存修改并重新排队分析...");
    try {
      const data = await updateDiaryEntry(entryId, text);
      setStatus(`日记 #${entryId} 已更新`);
      setReaderState(`${formatAnalysisStatus(data.analysis_status, data.analysis_ok)} · 修改已写回数据库与当天备份`);
    } catch (err) {
      setStatus(`更新失败: ${err.message}`);
      setReaderState(`更新失败：${err.message}`);
    } finally {
      if (el.readerSaveBtn) {
        el.readerSaveBtn.disabled = false;
        el.readerSaveBtn.textContent = oldLabel;
      }
    }
  });
  el.readerReanalyzeBtn?.addEventListener("click", async () => {
    const entryId = Number(state.currentEntryDetail?.entry_id || 0);
    if (!entryId) return;
    const oldLabel = el.readerReanalyzeBtn?.textContent || "重分析";
    if (el.readerReanalyzeBtn) {
      el.readerReanalyzeBtn.disabled = true;
      el.readerReanalyzeBtn.textContent = "重新排队中...";
    }
    setReaderState("正在重新排队分析这篇日记...");
    try {
      const data = await reanalyzeDiaryEntry(entryId);
      setStatus(`日记 #${entryId} 已加入重分析队列`);
      setReaderState(`${formatAnalysisStatus(data.analysis_status, data.analysis_ok)} · ${data.analysis_backend || "local"} 分析`);
    } catch (err) {
      setStatus(`重分析失败: ${err.message}`);
      setReaderState(`重分析失败：${err.message}`);
    } finally {
      if (el.readerReanalyzeBtn) {
        el.readerReanalyzeBtn.disabled = false;
        el.readerReanalyzeBtn.textContent = oldLabel;
      }
    }
  });
  el.readerDeleteBtn?.addEventListener("click", async () => {
    const entryId = Number(state.currentEntryDetail?.entry_id || 0);
    if (!entryId) return;
    if (!window.confirm(`确定删除日记 #${entryId} 吗？这会删除数据库里的原文、分析和任务记录。`)) {
      return;
    }
    const oldLabel = el.readerDeleteBtn?.textContent || "删除";
    if (el.readerDeleteBtn) {
      el.readerDeleteBtn.disabled = true;
      el.readerDeleteBtn.textContent = "删除中...";
    }
    try {
      await deleteDiaryEntry(entryId);
      setStatus(`日记 #${entryId} 已删除`);
    } catch (err) {
      setStatus(`删除失败: ${err.message}`);
      setReaderState(`删除失败：${err.message}`);
    } finally {
      if (el.readerDeleteBtn) {
        el.readerDeleteBtn.disabled = false;
        el.readerDeleteBtn.textContent = oldLabel;
      }
    }
  });

  el.unifiedInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendChatInput();
    }
  });

  el.diaryInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      sendDiaryInput();
    }
  });

  el.chatSessionList?.addEventListener("click", (e) => {
    const button = e.target.closest(".chat-session-item");
    if (!button) return;
    const sessionId = button.getAttribute("data-session-id") || "";
    openChatSession(sessionId).catch((err) => setStatus(`加载会话失败: ${err.message}`));
  });

  el.historyList?.addEventListener("click", (e) => {
    const button = e.target.closest(".history-item");
    if (!button) return;
    const kind = button.getAttribute("data-kind") || "text";
    const key = button.getAttribute("data-key") || "";
    state.selectedHistoryKey = key;
    if (kind === "audio") {
      const audioId = button.getAttribute("data-audio-id") || "";
      const audioMap = state._audioMap || {};
      const item = audioMap[audioId];
      if (item) {
        renderAudioDiaryDetail(item)
          .then(() => loadHistory())
          .catch((err) => setStatus(`读取语音详情失败: ${err.message}`));
        return;
      }
    }
    const date = button.getAttribute("data-date");
    const entryIdRaw = button.getAttribute("data-entry-id") || "";
    if (date) {
      openDiary(date, {
        date,
        entry_id: Number(entryIdRaw) || null,
      });
    }
  });

}

function ensureDomReady() {
  const required = [
    "systemPill", "chatSessionList", "newChatBtn", "chatSessionTitle", "chatMessages", "chatStatus", "unifiedInput", "voiceChatBtn", "sendBtn", "diaryInput", "diaryRecordBtn", "saveDiaryBtn", "diaryStatus", "historyList", "readerContent", "readerDate", "readerAudio", "readerState", "readerActions", "readerEditBtn", "readerReanalyzeBtn", "readerDeleteBtn", "readerCancelBtn", "readerSaveBtn", "readerEditor",
    "overviewEntriesCount", "overviewLatestEntry", "overviewAnalysisJobs", "focusLines",
    "toggleComposeBtn", "toggleHistoryBtn", "notebookComposeWrap", "notebookLayout", "historyPane"
  ];

  const missing = required.filter((name) => !el[name]);
  if (missing.length > 0) {
    throw new Error(`Missing DOM nodes: ${missing.join(", ")}`);
  }
}

async function bootstrap() {
  ensureDomReady();
  setNotebookComposeOpen(false);
  setNotebookHistoryOpen(false);
  setReaderActionVisibility(null);
  setReaderState("读取后会在这里展示内容。");
  if (!canRecordAudio()) {
    if (el.diaryRecordBtn) {
      el.diaryRecordBtn.disabled = true;
      el.diaryRecordBtn.title = "当前浏览器不支持录音";
    }
    if (el.voiceChatBtn) {
      el.voiceChatBtn.disabled = true;
      el.voiceChatBtn.title = "当前浏览器不支持录音";
    }
  }
  updateDiaryRecordBtn();
  updateVoiceChatBtn();
  bindEvents();
  switchView("chat");
  await Promise.all([refreshSystemPill(), loadHistory(), refreshInsights(), loadChatSessions()]);
  if (state.currentChatSessionId) {
    await openChatSession(state.currentChatSessionId);
  } else {
    await createNewChatSession();
  }
}

bootstrap();
