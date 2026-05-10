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
const assistantState = document.querySelector("#assistantState");
const toast = document.querySelector("#toast");

const componentLabels = {
  orchestrator: "Orchestrator",
  stt: "STT",
  rag: "RAG",
  tts: "TTS",
  vision: "Vision",
};

function setBusy(button, busy, label) {
  if (button !== voiceButton) {
    button.disabled = busy;
  }
  if (label) {
    const labelTarget = button.querySelector(".button-text");
    const currentLabel = labelTarget ? labelTarget.textContent : button.textContent;
    button.dataset.defaultLabel = button.dataset.defaultLabel || currentLabel;
    if (labelTarget) {
      labelTarget.textContent = busy ? label : button.dataset.defaultLabel;
    } else {
      button.textContent = busy ? label : button.dataset.defaultLabel;
    }
  }
}

function setInteractionState(state, message) {
  document.body.classList.toggle("is-listening", state === "listening");
  document.body.classList.toggle("is-thinking", state === "thinking");
  document.body.classList.toggle("is-speaking", state === "speaking");
  if (message) {
    assistantState.textContent = message;
  }
}

function isAudioPlaying() {
  return !answerAudio.paused && !answerAudio.ended;
}

function isUsableTranscript(text) {
  const cleaned = text.trim().toLowerCase();
  return cleaned.length >= 3 && cleaned !== "el";
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
  setInteractionState(data.answer ? "speaking" : "idle", data.answer ? "Here is what I found." : "Ready to help.");

  if (data.audio_url) {
    stopRecording(false);
    voiceButton.disabled = true;
    answerAudio.src = data.audio_url;
    answerAudio.hidden = false;
    answerAudio.play().catch(() => {
      voiceButton.disabled = false;
      setInteractionState("idle", "Answer ready.");
    });
  } else {
    answerAudio.removeAttribute("src");
    answerAudio.hidden = true;
    window.setTimeout(() => setInteractionState("idle", "Ready to help."), 1200);
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
    if (!document.body.classList.contains("is-listening") && !document.body.classList.contains("is-thinking")) {
      setInteractionState("idle", "Ready to help.");
    }
  } catch (error) {
    statusText.textContent = "Cannot reach orchestrator.";
    statusGrid.innerHTML = "";
    setInteractionState("idle", "Reception service is offline.");
    showToast(error.message);
  }
}

async function ingestDocuments() {
  setBusy(ingestButton, true, "Ingesting...");
  setInteractionState("thinking", "Updating reception knowledge.");
  try {
    const result = await api("/documents/ingest", { method: "POST" });
    showToast(`Indexed ${result.chunks_processed} chunks from ${result.documents_processed} documents.`);
    await refreshStatus();
  } catch (error) {
    showToast(error.message, 6000);
    setInteractionState("idle", "Ready to help.");
  } finally {
    setBusy(ingestButton, false);
  }
}

async function askTypedQuestion(preserveTranscript = false) {
  const question = questionInput.value.trim();
  if (!question) {
    showToast("Enter a question first.");
    questionInput.focus();
    return;
  }

  setBusy(askButton, true, "Asking...");
  setInteractionState("thinking", "Checking reception information.");
  questionText.textContent = question;
  if (!preserveTranscript) {
    transcriptionText.textContent = "Typed question";
  }
  try {
    const data = await api("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    renderAskResult(data);
  } catch (error) {
    setInteractionState("idle", "I could not answer that yet.");
    showToast(error.message, 7000);
  } finally {
    setBusy(askButton, false);
  }
}

let voiceWebSocket = null;

function clearRecordingState() {
  voiceWebSocket = null;
  setBusy(voiceButton, false);
  voiceButton.disabled = isAudioPlaying();
  if (document.body.classList.contains("is-listening")) {
    setInteractionState("idle", "Ready to help.");
  }
}

function stopRecording(sendStop = true) {
  if (voiceWebSocket) {
    const socket = voiceWebSocket;
    voiceWebSocket = null;
    if (socket.readyState === WebSocket.OPEN) {
      if (sendStop) {
        socket.send("stop");
      }
      socket.close();
    } else if (socket.readyState === WebSocket.CONNECTING) {
      socket.onopen = () => socket.close();
    }
  }
  setBusy(voiceButton, false);
  voiceButton.disabled = isAudioPlaying();
}

async function askByVoice() {
  if (isAudioPlaying()) {
    stopRecording(false);
    showToast("Please wait until the answer finishes speaking.");
    return;
  }

  if (voiceWebSocket) {
    // If already recording, stop it
    stopRecording();
    return;
  }

  setBusy(voiceButton, true, "Stop Listening...");
  setInteractionState("listening", "I am listening.");
  transcriptionText.textContent = "Server is recording...";
  questionText.textContent = "-";
  answerText.textContent = "-";

  try {
    const wsUrl = new URL("/voice/stream", window.location.href);
    wsUrl.protocol = wsUrl.protocol === "https:" ? "wss:" : "ws:";
    voiceWebSocket = new WebSocket(wsUrl);

    voiceWebSocket.onopen = () => {
      setInteractionState("listening", "Please speak now.");
    };

    voiceWebSocket.onmessage = async (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "partial") {
        setInteractionState("listening", "I am listening.");
        transcriptionText.textContent = data.text;
      } else if (data.type === "final") {
        transcriptionText.textContent = data.text;
        stopRecording();
        if (isUsableTranscript(data.text)) {
          questionInput.value = data.text;
          setInteractionState("thinking", "Let me check that.");
          await askTypedQuestion(true);
        } else {
          setInteractionState("idle", "Ready to help.");
          showToast("No clear speech detected.");
        }
      } else if (data.type === "error") {
        setInteractionState("idle", "Voice input needs attention.");
        showToast(data.error);
        stopRecording();
      }
    };

    voiceWebSocket.onclose = () => {
      clearRecordingState();
    };

    voiceWebSocket.onerror = () => {
      setInteractionState("idle", "Voice connection failed.");
      showToast("WebSocket error.");
      stopRecording(false);
    };
  } catch (error) {
    setInteractionState("idle", "Voice input needs attention.");
    showToast(error.message, 8000);
    stopRecording();
  }
}

answerAudio.addEventListener("play", () => {
  stopRecording(false);
  voiceButton.disabled = true;
  setInteractionState("speaking", "Speaking now.");
});

answerAudio.addEventListener("ended", () => {
  voiceButton.disabled = false;
  setInteractionState("idle", "Ready to help.");
});

answerAudio.addEventListener("pause", () => {
  if (!answerAudio.ended) {
    voiceButton.disabled = false;
    setInteractionState("idle", "Answer paused.");
  }
});

refreshStatusButton.addEventListener("click", refreshStatus);
ingestButton.addEventListener("click", ingestDocuments);
askButton.addEventListener("click", () => askTypedQuestion());
voiceButton.addEventListener("click", askByVoice);
questionInput.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
    askTypedQuestion();
  }
});

refreshStatus();
