/**
 * Pure, DOM-free logic for the MogBot web app. No browser APIs on purpose,
 * so this file can be unit tested directly under Node (see
 * tests/run_web_logic_tests.js) and loaded as a plain script in the browser
 * (see index.html) without a build step either way.
 */
(function (global) {
  "use strict";

  function validateSetupInputs(jobDescription, resumeText) {
    const job = (jobDescription || "").trim();
    const resume = (resumeText || "").trim();

    if (!job) return { field: "job", message: "Paste a job description before starting." };
    if (!resume) return { field: "resume", message: "Paste resume text before starting." };
    return null;
  }

  function deriveSessionState(previousState, data) {
    return {
      sessionId: data.session_id || previousState.sessionId,
      roleFocus: data.role_focus || [],
      currentQuestion: data.current_question || null,
      progress: data.progress || previousState.progress,
      feedback: data.feedback || null,
      summary: data.summary || null,
      completed: data.status === "completed"
    };
  }

  function deriveQuestionView(state) {
    const current = state.currentQuestion;
    const currentNumber = current ? current.number || state.progress.current : state.progress.current;
    const total = current ? current.total || state.progress.total : state.progress.total;

    return {
      pillText: `Question ${currentNumber} of ${total}`,
      roleFocusText: state.roleFocus && state.roleFocus.length
        ? `Focus: ${state.roleFocus.join(", ")}`
        : "Focus: role fit, experience, and communication",
      questionText: current ? current.text : "No active question.",
      submitLabel: currentNumber === total ? "Finish" : "Submit answer"
    };
  }

  function deriveFeedbackView(feedback) {
    if (!feedback || !feedback.evaluation) return null;

    const evaluation = feedback.evaluation;
    return {
      score: evaluation.overall_score ?? 0,
      comment: evaluation.evaluator_comment || "Answer evaluated.",
      challenge: feedback.challenge && feedback.challenge.challenge_question
        ? feedback.challenge.challenge_question
        : ""
    };
  }

  const STEP_ORDER = ["setup", "interview", "report"];

  function stepIndexForView(viewName) {
    const normalized = viewName === "summary" ? "report" : viewName;
    return STEP_ORDER.indexOf(normalized);
  }

  function deriveSummaryView(report) {
    const safeReport = report || {};
    const steps = Array.isArray(safeReport.recommended_next_steps) && safeReport.recommended_next_steps.length
      ? safeReport.recommended_next_steps
      : ["Review your answers and add clearer examples with measurable outcomes."];

    return {
      title: safeReport.summary || "Interview complete.",
      trend: safeReport.score_trends && safeReport.score_trends.trend
        ? `Score trend: ${safeReport.score_trends.trend}.`
        : "Score trend: not enough data yet.",
      steps
    };
  }

  function resolveApiBase(configuredMeta, hostname) {
    const configured = (configuredMeta || "").trim();
    if (configured) return configured.replace(/\/$/, "");
    if (["localhost", "127.0.0.1"].includes(hostname)) return "http://127.0.0.1:5000";
    return "";
  }

  const MogBotLogic = {
    validateSetupInputs,
    deriveSessionState,
    deriveQuestionView,
    deriveFeedbackView,
    stepIndexForView,
    deriveSummaryView,
    resolveApiBase
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = MogBotLogic;
  }
  global.MogBotLogic = MogBotLogic;
})(typeof window !== "undefined" ? window : globalThis);
