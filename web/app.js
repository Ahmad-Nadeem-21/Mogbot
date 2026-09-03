const storageKey = "mogbot_web_state";

function resolveApiBase() {
  const meta = document.querySelector('meta[name="mogbot-api-base"]');
  const configured = meta && meta.content ? meta.content.trim() : "";
  if (configured) return configured.replace(/\/$/, "");

  const isLocal = ["localhost", "127.0.0.1"].includes(window.location.hostname);
  if (isLocal) return "http://127.0.0.1:5000";

  // No explicit backend configured for this deployment. Requests will be
  // same-origin; set <meta name="mogbot-api-base" content="https://..."> at
  // deploy time if the API is hosted on a different origin.
  return "";
}

const apiBase = resolveApiBase();

const elements = {
  setupView: document.getElementById("setupView"),
  interviewView: document.getElementById("interviewView"),
  summaryView: document.getElementById("summaryView"),
  setupForm: document.getElementById("setupForm"),
  answerForm: document.getElementById("answerForm"),
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
  summaryPanel: document.getElementById("summaryPanel"),
  stepper: document.getElementById("stepper")
};

const state = {
  sessionId: "",
  jobDescription: "",
  resumeText: "",
  roleFocus: [],
  currentQuestion: null,
  progress: { current: 1, total: 1 },
  feedback: null,
  summary: null,
  completed: false
};

function saveState() {
  const snapshot = {
    ...state,
    jobDescription: elements.jobDescription.value,
    resumeText: elements.resumeText.value
  };
  try {
    localStorage.setItem(storageKey, JSON.stringify(snapshot));
  } catch (err) {
    // Storage can be unavailable (private mode, quota). Non-fatal.
  }
}

function loadState() {
  let raw = null;
  try {
    raw = localStorage.getItem(storageKey);
  } catch (err) {
    return;
  }
  if (!raw) return;

  let saved;
  try {
    saved = JSON.parse(raw);
  } catch (err) {
    return;
  }

  Object.assign(state, {
    sessionId: saved.sessionId || "",
    jobDescription: saved.jobDescription || "",
    resumeText: saved.resumeText || "",
    roleFocus: saved.roleFocus || [],
    currentQuestion: saved.currentQuestion || null,
    progress: saved.progress || { current: 1, total: 1 },
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
    feedback: null,
    summary: null,
    completed: false
  });

  elements.jobDescription.value = "";
  elements.resumeText.value = "";
  elements.answerText.value = "";
  hideAlert(elements.setupError);
  hideAlert(elements.feedbackPanel);

  try {
    localStorage.removeItem(storageKey);
  } catch (err) {
    // ignore
  }
}

function setView(viewName) {
  elements.setupView.classList.toggle("is-active", viewName === "setup");
  elements.interviewView.classList.toggle("is-active", viewName === "interview");
  elements.summaryView.classList.toggle("is-active", viewName === "summary");

  const stepOrder = ["setup", "interview", "report"];
  const activeIndex = stepOrder.indexOf(viewName === "summary" ? "report" : viewName);
  elements.stepper.querySelectorAll("li").forEach((li, index) => {
    li.classList.toggle("is-current", index === activeIndex);
    li.classList.toggle("is-done", index < activeIndex);
  });

  if (viewName !== "setup") {
    document.getElementById("app").scrollIntoView({ block: "start", behavior: "smooth" });
  }
}

function setButtonLoading(button, isLoading) {
  button.disabled = isLoading;
  button.querySelector(".button-label").hidden = isLoading;
  button.querySelector(".spinner").hidden = !isLoading;
  button.setAttribute("aria-busy", String(isLoading));
}

function showAlert(element, message) {
  element.textContent = message;
  element.hidden = false;
}

function hideAlert(element) {
  element.textContent = "";
  element.hidden = true;
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
  } catch (err) {
    throw new Error(
      apiBase
        ? `Could not reach the MogBot API at ${apiBase}. Confirm the backend is running and reachable.`
        : "Could not reach the MogBot API. Set the mogbot-api-base meta tag to the backend URL for this deployment."
    );
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data);
    throw new Error(detail || `MogBot backend returned an error (${response.status}).`);
  }
  return data;
}

function validateSetup() {
  const job = elements.jobDescription.value.trim();
  const resume = elements.resumeText.value.trim();

  if (!job) return { message: "Paste a job description before starting.", field: elements.jobDescription };
  if (!resume) return { message: "Paste resume text before starting.", field: elements.resumeText };
  return null;
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

async function startInterview(event) {
  event.preventDefault();

  const invalid = validateSetup();
  if (invalid) {
    showAlert(elements.setupError, invalid.message);
    invalid.field.focus();
    return;
  }
  hideAlert(elements.setupError);

  state.jobDescription = elements.jobDescription.value.trim();
  state.resumeText = elements.resumeText.value.trim();
  state.feedback = null;
  state.summary = null;
  state.completed = false;

  setButtonLoading(elements.startButton, true);
  try {
    const data = await apiFetch("/sessions", {
      method: "POST",
      body: JSON.stringify({
        job_description: state.jobDescription,
        resume_text: state.resumeText,
        delivery_mode: "web",
        max_questions: 5
      })
    });
    applySessionResponse(data);
    saveState();
    showInterview();
  } catch (err) {
    showAlert(elements.setupError, err.message);
  } finally {
    setButtonLoading(elements.startButton, false);
  }
}

function showInterview() {
  setView("interview");
  renderCurrentQuestion();
  renderFeedback();
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
  elements.submitAnswerButton.querySelector(".button-label").textContent =
    currentNumber === total ? "Finish" : "Submit answer";
}

function renderFeedback() {
  const feedback = state.feedback;
  if (!feedback || !feedback.evaluation) {
    hideAlert(elements.feedbackPanel);
    return;
  }

  const evaluation = feedback.evaluation;
  const score = evaluation.overall_score ?? 0;
  const comment = evaluation.evaluator_comment || "Answer evaluated.";
  const challenge = feedback.challenge && feedback.challenge.challenge_question
    ? ` Challenge: ${feedback.challenge.challenge_question}`
    : "";

  elements.feedbackPanel.innerHTML = `<strong>${score} / 100.</strong> ${escapeHtml(comment)}${challenge ? escapeHtml(challenge) : ""}`;
  elements.feedbackPanel.hidden = false;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

async function submitAnswer(event) {
  event.preventDefault();

  const answer = elements.answerText.value.trim();
  if (!answer) {
    showAlert(elements.feedbackPanel, "Write an answer before submitting.");
    return;
  }
  if (!state.sessionId) {
    showAlert(elements.feedbackPanel, "Start a session before submitting an answer.");
    return;
  }

  setButtonLoading(elements.submitAnswerButton, true);
  try {
    const data = await apiFetch(`/sessions/${state.sessionId}/answers`, {
      method: "POST",
      body: JSON.stringify({ answer_text: answer })
    });
    applySessionResponse(data);
    saveState();

    if (state.completed) {
      showSummary();
      return;
    }
    showInterview();
  } catch (err) {
    showAlert(elements.feedbackPanel, err.message);
  } finally {
    setButtonLoading(elements.submitAnswerButton, false);
  }
}

function showSummary() {
  setView("summary");
  elements.summaryPanel.innerHTML = "";

  const report = state.summary || {};

  const title = document.createElement("h3");
  title.textContent = report.summary || "Interview complete.";
  elements.summaryPanel.appendChild(title);

  const trend = document.createElement("p");
  trend.className = "trend";
  trend.textContent = report.score_trends && report.score_trends.trend
    ? `Score trend: ${report.score_trends.trend}.`
    : "Score trend: not enough data yet.";
  elements.summaryPanel.appendChild(trend);

  const steps = Array.isArray(report.recommended_next_steps) && report.recommended_next_steps.length
    ? report.recommended_next_steps
    : ["Review your answers and add clearer examples with measurable outcomes."];

  const list = document.createElement("ul");
  steps.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    list.appendChild(li);
  });
  elements.summaryPanel.appendChild(list);

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

elements.setupForm.addEventListener("submit", startInterview);
elements.answerForm.addEventListener("submit", submitAnswer);
elements.clearDraftButton.addEventListener("click", clearState);
elements.backButton.addEventListener("click", goBackToSetup);
elements.newSessionButton.addEventListener("click", startNewSession);
elements.jobDescription.addEventListener("input", saveState);
elements.resumeText.addEventListener("input", saveState);

loadState();
