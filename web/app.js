const storageKey = "mogbot_web_state";

const apiBase = MogBotLogic.resolveApiBase(
  document.querySelector('meta[name="mogbot-api-base"]')?.content,
  window.location.hostname
);

const elements = {
  setupView: document.getElementById("setupView"),
  interviewView: document.getElementById("interviewView"),
  summaryView: document.getElementById("summaryView"),
  setupForm: document.getElementById("setupForm"),
  answerForm: document.getElementById("answerForm"),
  jobDescription: document.getElementById("jobDescription"),
  resumeText: document.getElementById("resumeText"),
  setupError: document.getElementById("setupError"),
  setupLoadingNote: document.getElementById("setupLoadingNote"),
  answerLoadingNote: document.getElementById("answerLoadingNote"),
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

  const activeIndex = MogBotLogic.stepIndexForView(viewName);
  elements.stepper.querySelectorAll("li").forEach((li, index) => {
    li.classList.toggle("is-current", index === activeIndex);
    li.classList.toggle("is-done", index < activeIndex);
  });

  if (viewName !== "setup") {
    document.getElementById("app").scrollIntoView({ block: "start", behavior: "smooth" });
  }
}

function setButtonLoading(button, isLoading, loadingNote) {
  button.disabled = isLoading;
  button.querySelector(".button-label").hidden = isLoading;
  button.querySelector(".spinner").hidden = !isLoading;
  button.setAttribute("aria-busy", String(isLoading));
  if (loadingNote) loadingNote.hidden = !isLoading;
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

async function startInterview(event) {
  event.preventDefault();

  const invalid = MogBotLogic.validateSetupInputs(elements.jobDescription.value, elements.resumeText.value);
  if (invalid) {
    showAlert(elements.setupError, invalid.message);
    (invalid.field === "job" ? elements.jobDescription : elements.resumeText).focus();
    return;
  }
  hideAlert(elements.setupError);

  state.jobDescription = elements.jobDescription.value.trim();
  state.resumeText = elements.resumeText.value.trim();
  state.feedback = null;
  state.summary = null;
  state.completed = false;

  setButtonLoading(elements.startButton, true, elements.setupLoadingNote);
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
    Object.assign(state, MogBotLogic.deriveSessionState(state, data));
    saveState();
    showInterview();
  } catch (err) {
    showAlert(elements.setupError, err.message);
  } finally {
    setButtonLoading(elements.startButton, false, elements.setupLoadingNote);
  }
}

function showInterview() {
  setView("interview");
  renderCurrentQuestion();
  renderFeedback();
}

function renderCurrentQuestion() {
  const view = MogBotLogic.deriveQuestionView(state);
  elements.progressPill.textContent = view.pillText;
  elements.roleFocus.textContent = view.roleFocusText;
  elements.questionPanel.textContent = view.questionText;
  elements.answerText.value = "";
  elements.submitAnswerButton.querySelector(".button-label").textContent = view.submitLabel;
}

function renderFeedback() {
  const view = MogBotLogic.deriveFeedbackView(state.feedback);
  if (!view) {
    hideAlert(elements.feedbackPanel);
    return;
  }

  elements.feedbackPanel.textContent = "";

  const scoreLine = document.createElement("strong");
  scoreLine.textContent = `${view.score} / 100.`;
  elements.feedbackPanel.append(scoreLine, ` ${view.comment}`);

  if (view.challenge) {
    elements.feedbackPanel.append(` Challenge: ${view.challenge}`);
  }

  elements.feedbackPanel.hidden = false;
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

  setButtonLoading(elements.submitAnswerButton, true, elements.answerLoadingNote);
  try {
    const data = await apiFetch(`/sessions/${state.sessionId}/answers`, {
      method: "POST",
      body: JSON.stringify({ answer_text: answer })
    });
    Object.assign(state, MogBotLogic.deriveSessionState(state, data));
    saveState();

    if (state.completed) {
      showSummary();
      return;
    }
    showInterview();
  } catch (err) {
    showAlert(elements.feedbackPanel, err.message);
  } finally {
    setButtonLoading(elements.submitAnswerButton, false, elements.answerLoadingNote);
  }
}

function showSummary() {
  setView("summary");
  elements.summaryPanel.textContent = "";

  const view = MogBotLogic.deriveSummaryView(state.summary);

  const title = document.createElement("h3");
  title.textContent = view.title;
  elements.summaryPanel.appendChild(title);

  const trend = document.createElement("p");
  trend.className = "trend";
  trend.textContent = view.trend;
  elements.summaryPanel.appendChild(trend);

  const list = document.createElement("ul");
  view.steps.forEach((item) => {
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
