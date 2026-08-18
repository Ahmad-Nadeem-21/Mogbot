const apiBase = "http://127.0.0.1:5000";
const storageKey = "mogbot_extension_state";

const elements = {
  setupView: document.getElementById("setupView"),
  interviewView: document.getElementById("interviewView"),
  summaryView: document.getElementById("summaryView"),
  jobDescription: document.getElementById("jobDescription"),
  resumeText: document.getElementById("resumeText"),
  setupError: document.getElementById("setupError"),
  startButton: document.getElementById("startButton"),
  clearDraftButton: document.getElementById("clearDraftButton"),
  backButton: document.getElementById("backButton"),
  submitAnswerButton: document.getElementById("submitAnswerButton"),
  newSessionButton: document.getElementById("newSessionButton"),
  progressPill: document.getElementById("progressPill"),
  roleFocus: document.getElementById("roleFocus"),
  questionPanel: document.getElementById("questionPanel"),
  answerText: document.getElementById("answerText"),
  feedbackPanel: document.getElementById("feedbackPanel"),
  summaryPanel: document.getElementById("summaryPanel")
};

const state = {
  sessionId: "",
  jobDescription: "",
  resumeText: "",
  roleFocus: [],
  currentQuestion: null,
  progress: { current: 1, total: 1 },
  answers: [],
  feedback: null,
  summary: null,
  completed: false
};

function useStorage() {
  return typeof chrome !== "undefined" && chrome.storage && chrome.storage.local;
}

function saveState() {
  const snapshot = {
    ...state,
    jobDescription: elements.jobDescription.value,
    resumeText: elements.resumeText.value
  };

  if (useStorage()) {
    chrome.storage.local.set({ [storageKey]: snapshot });
    return;
  }

  localStorage.setItem(storageKey, JSON.stringify(snapshot));
}

function loadState() {
  if (useStorage()) {
    chrome.storage.local.get(storageKey, (result) => {
      restoreState(result[storageKey]);
    });
    return;
  }

  const raw = localStorage.getItem(storageKey);
  restoreState(raw ? JSON.parse(raw) : null);
}

function restoreState(saved) {
  if (!saved) return;

  Object.assign(state, {
    sessionId: saved.sessionId || "",
    jobDescription: saved.jobDescription || "",
    resumeText: saved.resumeText || "",
    roleFocus: saved.roleFocus || [],
    currentQuestion: saved.currentQuestion || null,
    progress: saved.progress || { current: 1, total: 1 },
    answers: saved.answers || [],
    feedback: saved.feedback || null,
    summary: saved.summary || null,
    completed: Boolean(saved.completed)
  });

  elements.jobDescription.value = state.jobDescription;
  elements.resumeText.value = state.resumeText;

  if (state.completed) {
    showSummary();
    return;
  }

  if (state.currentQuestion) {
    showInterview();
  }
}

function clearState() {
  Object.assign(state, {
    sessionId: "",
    jobDescription: "",
    resumeText: "",
    roleFocus: [],
    currentQuestion: null,
    progress: { current: 1, total: 1 },
    answers: [],
    feedback: null,
    summary: null,
    completed: false
  });

  elements.jobDescription.value = "";
  elements.resumeText.value = "";
  elements.answerText.value = "";
  elements.setupError.textContent = "";
  hideFeedback();

  if (useStorage()) {
    chrome.storage.local.remove(storageKey);
  } else {
    localStorage.removeItem(storageKey);
  }
}

function setView(viewName) {
  elements.setupView.classList.toggle("is-active", viewName === "setup");
  elements.interviewView.classList.toggle("is-active", viewName === "interview");
  elements.summaryView.classList.toggle("is-active", viewName === "summary");
}

function setLoading(isLoading) {
  elements.startButton.disabled = isLoading;
  elements.submitAnswerButton.disabled = isLoading;
  elements.clearDraftButton.disabled = isLoading;
  elements.backButton.disabled = isLoading;
}

async function apiFetch(path, options = {}) {
  let response;
  try {
    response = await fetch(`${apiBase}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {})
      }
    });
  } catch (error) {
    throw new Error("MogBot Flask server is not running. Start it with: python main.py");
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data);
    throw new Error(detail || "MogBot backend returned an error.");
  }
  return data;
}

function validateSetup() {
  const job = elements.jobDescription.value.trim();
  const resume = elements.resumeText.value.trim();

  if (!job) {
    return "Paste a job description before starting.";
  }

  if (!resume) {
    return "Paste resume text before starting.";
  }

  return "";
}

function applySessionResponse(data) {
  state.sessionId = data.session_id || state.sessionId;
  state.roleFocus = data.role_focus || [];
  state.currentQuestion = data.current_question || null;
  state.progress = data.progress || state.progress;
  state.feedback = data.feedback || null;
  state.summary = data.summary || null;
  state.completed = data.status === "completed";
}

async function startInterview() {
  const error = validateSetup();
  elements.setupError.textContent = error;
  if (error) return;

  state.jobDescription = elements.jobDescription.value.trim();
  state.resumeText = elements.resumeText.value.trim();
  state.answers = [];
  state.feedback = null;
  state.summary = null;
  state.completed = false;

  setLoading(true);
  elements.setupError.textContent = "";
  try {
    const data = await apiFetch("/sessions", {
      method: "POST",
      body: JSON.stringify({
        job_description: state.jobDescription,
        resume_text: state.resumeText,
        delivery_mode: "extension",
        max_questions: 5
      })
    });
    applySessionResponse(data);
    saveState();
    showInterview();
  } catch (err) {
    elements.setupError.textContent = err.message;
  } finally {
    setLoading(false);
  }
}

function showInterview() {
  setView("interview");
  renderCurrentQuestion();
  renderFeedback();
}

function hideFeedback() {
  elements.feedbackPanel.classList.remove("is-visible");
  elements.feedbackPanel.textContent = "";
}

function renderCurrentQuestion() {
  const current = state.currentQuestion;
  const currentNumber = current ? current.number || state.progress.current : state.progress.current;
  const total = current ? current.total || state.progress.total : state.progress.total;

  elements.progressPill.textContent = `Question ${currentNumber} of ${total}`;
  elements.roleFocus.textContent = state.roleFocus.length
    ? `Focus: ${state.roleFocus.join(", ")}`
    : "Focus: role fit, experience, and communication";
  elements.questionPanel.textContent = current ? current.text : "No active question.";
  elements.answerText.value = "";
  elements.submitAnswerButton.textContent = currentNumber === total ? "Finish" : "Submit";
}

function renderFeedback() {
  const feedback = state.feedback;
  if (!feedback || !feedback.evaluation) {
    hideFeedback();
    return;
  }

  const evaluation = feedback.evaluation;
  const score = evaluation.overall_score ?? 0;
  const comment = evaluation.evaluator_comment || "Answer evaluated.";
  const challenge = feedback.challenge && feedback.challenge.challenge_question
    ? ` Challenge: ${feedback.challenge.challenge_question}`
    : "";
  elements.feedbackPanel.textContent = `Score ${score}/100. ${comment}${challenge}`;
  elements.feedbackPanel.classList.add("is-visible");
}

async function submitAnswer() {
  const answer = elements.answerText.value.trim();

  if (!answer) {
    elements.feedbackPanel.textContent = "Write an answer before submitting.";
    elements.feedbackPanel.classList.add("is-visible");
    return;
  }

  if (!state.sessionId) {
    elements.feedbackPanel.textContent = "Start a session before submitting an answer.";
    elements.feedbackPanel.classList.add("is-visible");
    return;
  }

  const answeredQuestion = state.currentQuestion;
  setLoading(true);
  try {
    const data = await apiFetch(`/sessions/${state.sessionId}/answers`, {
      method: "POST",
      body: JSON.stringify({ answer_text: answer })
    });
    state.answers.push({
      question: answeredQuestion ? answeredQuestion.text : "",
      answer,
      feedback: data.feedback
    });
    applySessionResponse(data);
    saveState();

    if (state.completed) {
      showSummary();
      return;
    }
    showInterview();
  } catch (err) {
    elements.feedbackPanel.textContent = err.message;
    elements.feedbackPanel.classList.add("is-visible");
  } finally {
    setLoading(false);
  }
}

function appendList(parent, items) {
  const list = document.createElement("ul");
  items.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    list.appendChild(li);
  });
  parent.appendChild(list);
}

function showSummary() {
  setView("summary");
  elements.summaryPanel.textContent = "";

  const report = state.summary || {};
  const title = document.createElement("h3");
  title.textContent = report.summary || "Interview complete.";
  elements.summaryPanel.appendChild(title);

  const trend = report.score_trends && report.score_trends.trend
    ? `Score trend: ${report.score_trends.trend}.`
    : "Score trend: not enough data yet.";
  const trendText = document.createElement("p");
  trendText.textContent = trend;
  elements.summaryPanel.appendChild(trendText);

  const steps = Array.isArray(report.recommended_next_steps)
    ? report.recommended_next_steps
    : ["Review your answers and add clearer examples with measurable outcomes."];
  appendList(elements.summaryPanel, steps);

  saveState();
}

function goBackToSetup() {
  saveState();
  setView("setup");
}

function startNewSession() {
  clearState();
  setView("setup");
}

elements.startButton.addEventListener("click", startInterview);
elements.clearDraftButton.addEventListener("click", clearState);
elements.backButton.addEventListener("click", goBackToSetup);
elements.submitAnswerButton.addEventListener("click", submitAnswer);
elements.newSessionButton.addEventListener("click", startNewSession);
elements.jobDescription.addEventListener("input", saveState);
elements.resumeText.addEventListener("input", saveState);

loadState();
