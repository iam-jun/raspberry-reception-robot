const statusText = document.querySelector("#statusText");
const statusGrid = document.querySelector("#statusGrid");
const refreshStatusButton = document.querySelector("#refreshStatusButton");
const ingestButton = document.querySelector("#ingestButton");
const voiceButton = document.querySelector("#voiceButton");
const askButton = document.querySelector("#askButton");
const questionInput = document.querySelector("#questionInput");
const transcriptionText = document.querySelector("#transcriptionText");
const questionText = document.querySelector("#questionText");
const answerText = document.querySelector("#answerText");
const sourcesList = document.querySelector("#sourcesList");
const emotionText = document.querySelector("#emotionText");
const emotionDetail = document.querySelector("#emotionDetail");
const answerAudio = document.querySelector("#answerAudio");
const toast = document.querySelector("#toast");

const componentLabels = {
  orchestrator: "Orchestrator",
  stt: "STT",
  rag: "RAG",
  tts: "TTS",
  vision: "Vision",
};

function setBusy(button, busy, label) {
  button.disabled = busy;
  if (label) {
    button.dataset.defaultLabel = button.dataset.defaultLabel || button.textContent;
    button.textContent = busy ? label : button.dataset.defaultLabel;
  }
}

function showToast(message, timeout = 3600) {
  toast.textContent = message;
  toast.hidden = false;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toast.hidden = true;
  }, timeout);
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  let data = null;
  const text = await response.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
  }
  if (!response.ok) {
    const detail = data?.detail || response.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function renderStatus(data) {
  statusGrid.innerHTML = "";
  const entries = Object.entries(componentLabels);
  for (const [key, label] of entries) {
    const component = data[key] || {};
    const status = component.status || "unknown";
    const pill = document.createElement("div");
    pill.className = `status-pill status-${status}`;
    pill.innerHTML = `<strong>${label}</strong><span>${status}</span>`;
    statusGrid.appendChild(pill);
  }
  const degraded = entries.some(([key]) => {
    const status = data[key]?.status;
    return status && !["ok"].includes(status);
  });
  statusText.textContent = degraded ? "Some modules need configuration." : "All reachable modules are ready.";
}

function renderAskResult(data) {
  transcriptionText.textContent = data.transcription || "-";
  questionText.textContent = data.question || "-";
  answerText.textContent = data.answer || "-";

  if (data.audio_url) {
    answerAudio.src = data.audio_url;
    answerAudio.hidden = false;
  } else {
    answerAudio.removeAttribute("src");
    answerAudio.hidden = true;
  }

  renderSources(data.sources || []);
  renderEmotion(data.emotion);

  if (data.tts_skipped_reason) {
    showToast(data.tts_skipped_reason);
  } else if (data.tts_error) {
    showToast(`TTS error: ${data.tts_error}`);
  }
}

function renderSources(sources) {
  sourcesList.innerHTML = "";
  if (!sources.length) {
    sourcesList.textContent = "No sources returned.";
    return;
  }
  for (const source of sources) {
    const item = document.createElement("div");
    item.className = "source-item";
    const snippet = source.text.length > 420 ? `${source.text.slice(0, 420)}...` : source.text;
    const title = document.createElement("strong");
    const body = document.createElement("p");
    title.textContent = `${source.filename} #${source.chunk_index}`;
    body.textContent = snippet;
    item.append(title, body);
    sourcesList.appendChild(item);
  }
}

function renderEmotion(emotion) {
  if (!emotion) {
    emotionText.textContent = "unknown";
    emotionDetail.textContent = "No camera sample yet.";
    return;
  }
  emotionText.textContent = emotion.emotion || "unknown";
  const confidence = Number(emotion.confidence || 0).toFixed(2);
  const face = emotion.face_detected ? "face detected" : "no face detected";
  emotionDetail.textContent = `${face}, confidence ${confidence}`;
}

async function refreshStatus() {
  try {
    const data = await api("/health");
    renderStatus(data);
  } catch (error) {
    statusText.textContent = "Cannot reach orchestrator.";
    statusGrid.innerHTML = "";
    showToast(error.message);
  }
}

async function ingestDocuments() {
  setBusy(ingestButton, true, "Ingesting...");
  try {
    const result = await api("/documents/ingest", { method: "POST" });
    showToast(`Indexed ${result.chunks_processed} chunks from ${result.documents_processed} documents.`);
    await refreshStatus();
  } catch (error) {
    showToast(error.message, 6000);
  } finally {
    setBusy(ingestButton, false);
  }
}

async function askTypedQuestion() {
  const question = questionInput.value.trim();
  if (!question) {
    showToast("Enter a question first.");
    questionInput.focus();
    return;
  }

  setBusy(askButton, true, "Asking...");
  try {
    const data = await api("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    renderAskResult(data);
  } catch (error) {
    showToast(error.message, 7000);
  } finally {
    setBusy(askButton, false);
  }
}

async function askByVoice() {
  setBusy(voiceButton, true, "Listening...");
  transcriptionText.textContent = "Recording and transcribing...";
  try {
    const data = await api("/voice/ask?duration_seconds=5", { method: "POST" });
    renderAskResult(data);
  } catch (error) {
    transcriptionText.textContent = "-";
    showToast(error.message, 8000);
  } finally {
    setBusy(voiceButton, false);
  }
}

refreshStatusButton.addEventListener("click", refreshStatus);
ingestButton.addEventListener("click", ingestDocuments);
askButton.addEventListener("click", askTypedQuestion);
voiceButton.addEventListener("click", askByVoice);
questionInput.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
    askTypedQuestion();
  }
});

refreshStatus();
