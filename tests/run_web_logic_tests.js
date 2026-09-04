/**
 * Unit tests for web/logic.js - the pure logic behind the MogBot web frontend
 * (validation, state derivation, view models). No DOM, no browser: run with
 *
 *   node tests/run_web_logic_tests.js
 */

const test = require("node:test");
const assert = require("node:assert/strict");
const logic = require("../web/logic.js");

test("validateSetupInputs rejects empty job description", () => {
  const result = logic.validateSetupInputs("   ", "Resume text");
  assert.deepEqual(result, { field: "job", message: "Paste a job description before starting." });
});

test("validateSetupInputs rejects empty resume when job description is present", () => {
  const result = logic.validateSetupInputs("Job text", "  ");
  assert.deepEqual(result, { field: "resume", message: "Paste resume text before starting." });
});

test("validateSetupInputs passes when both fields have content", () => {
  assert.equal(logic.validateSetupInputs("Job text", "Resume text"), null);
});

test("deriveSessionState maps a running session response", () => {
  const previous = { sessionId: "", progress: { current: 1, total: 1 } };
  const data = {
    session_id: "abc-123",
    role_focus: ["communication"],
    current_question: { text: "Tell me about yourself.", number: 1, total: 3 },
    progress: { current: 1, total: 3 },
    feedback: null,
    summary: {},
    status: "running"
  };

  assert.deepEqual(logic.deriveSessionState(previous, data), {
    sessionId: "abc-123",
    roleFocus: ["communication"],
    currentQuestion: { text: "Tell me about yourself.", number: 1, total: 3 },
    progress: { current: 1, total: 3 },
    feedback: null,
    summary: {},
    completed: false
  });
});

test("deriveSessionState keeps the prior session id when the response omits it", () => {
  const previous = { sessionId: "keep-me", progress: { current: 2, total: 3 } };
  const result = logic.deriveSessionState(previous, { status: "running" });
  assert.equal(result.sessionId, "keep-me");
  assert.equal(result.progress, previous.progress);
});

test("deriveSessionState marks completed only when status is completed", () => {
  assert.equal(logic.deriveSessionState({}, { status: "completed" }).completed, true);
  assert.equal(logic.deriveSessionState({}, { status: "running" }).completed, false);
});

test("deriveQuestionView renders progress, focus, and question text", () => {
  const state = {
    currentQuestion: { text: "Describe a challenge.", number: 2, total: 5 },
    progress: { current: 2, total: 5 },
    roleFocus: ["Python", "system design"]
  };
  assert.deepEqual(logic.deriveQuestionView(state), {
    pillText: "Question 2 of 5",
    roleFocusText: "Focus: Python, system design",
    questionText: "Describe a challenge.",
    submitLabel: "Submit answer"
  });
});

test("deriveQuestionView labels the last question as Finish", () => {
  const state = {
    currentQuestion: { text: "Last one.", number: 5, total: 5 },
    progress: { current: 5, total: 5 },
    roleFocus: []
  };
  assert.equal(logic.deriveQuestionView(state).submitLabel, "Finish");
});

test("deriveQuestionView falls back to a default focus line with no role focus", () => {
  const state = {
    currentQuestion: { text: "Q", number: 1, total: 1 },
    progress: { current: 1, total: 1 },
    roleFocus: []
  };
  assert.equal(
    logic.deriveQuestionView(state).roleFocusText,
    "Focus: role fit, experience, and communication"
  );
});

test("deriveFeedbackView returns null when there is no evaluation", () => {
  assert.equal(logic.deriveFeedbackView(null), null);
  assert.equal(logic.deriveFeedbackView({}), null);
});

test("deriveFeedbackView surfaces score, comment, and an optional challenge", () => {
  const feedback = {
    evaluation: { overall_score: 72, evaluator_comment: "Good structure." },
    challenge: { challenge_question: "Name the measurable outcome." }
  };
  assert.deepEqual(logic.deriveFeedbackView(feedback), {
    score: 72,
    comment: "Good structure.",
    challenge: "Name the measurable outcome."
  });
});

test("deriveFeedbackView omits challenge text when there is no challenge", () => {
  const feedback = { evaluation: { overall_score: 90, evaluator_comment: "Solid." } };
  assert.equal(logic.deriveFeedbackView(feedback).challenge, "");
});

test("stepIndexForView orders setup, interview, and report/summary", () => {
  assert.equal(logic.stepIndexForView("setup"), 0);
  assert.equal(logic.stepIndexForView("interview"), 1);
  assert.equal(logic.stepIndexForView("summary"), 2);
  assert.equal(logic.stepIndexForView("report"), 2);
});

test("stepIndexForView returns -1 for an unknown view", () => {
  assert.equal(logic.stepIndexForView("nonsense"), -1);
});

test("deriveSummaryView reads through a full report", () => {
  const report = {
    summary: "Strong on system design, thin on leadership examples.",
    score_trends: { trend: "improving" },
    recommended_next_steps: ["Add a measurable outcome to your STAR answers."]
  };
  assert.deepEqual(logic.deriveSummaryView(report), {
    title: "Strong on system design, thin on leadership examples.",
    trend: "Score trend: improving.",
    steps: ["Add a measurable outcome to your STAR answers."]
  });
});

test("deriveSummaryView falls back sensibly on an empty report", () => {
  assert.deepEqual(logic.deriveSummaryView({}), {
    title: "Interview complete.",
    trend: "Score trend: not enough data yet.",
    steps: ["Review your answers and add clearer examples with measurable outcomes."]
  });
});

test("deriveSummaryView handles a missing report entirely", () => {
  assert.equal(logic.deriveSummaryView(undefined).title, "Interview complete.");
});

test("resolveApiBase prefers an explicitly configured meta tag", () => {
  assert.equal(logic.resolveApiBase("https://api.example.com/", "mogbot.example.com"), "https://api.example.com");
});

test("resolveApiBase defaults to the local Flask port on localhost", () => {
  assert.equal(logic.resolveApiBase("", "localhost"), "http://127.0.0.1:5000");
  assert.equal(logic.resolveApiBase("", "127.0.0.1"), "http://127.0.0.1:5000");
});

test("resolveApiBase falls back to same-origin when nothing is configured off localhost", () => {
  assert.equal(logic.resolveApiBase("", "mogbot.example.com"), "");
});
