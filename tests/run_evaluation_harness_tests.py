"""Milestone 6 evaluation harness.

Compares Evaluator + DevilsAdvocate decisions against
data/evaluation_examples/labeled_answers.json, checks that scoring is
consistent across repeated runs, and traces tool usage across a full
floor-manager session to confirm memory retrieval, cache reuse, and
feedback loops are actually engaged (not just present in code).
"""

import json
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents import DevilsAdvocate, Evaluator
import main as m

EXAMPLES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "evaluation_examples", "labeled_answers.json"
)

# Minimum fraction of labeled examples the heuristic agents must agree with.
# The current agents are keyword/regex heuristics (see ACTION_PLAN Milestone 7),
# not an LLM, so this baseline is intentionally modest — e.g. Evaluator's
# technical_accuracy category is a hardcoded 65 regardless of answer content,
# which regularly drags well-reasoned answers below the follow-up threshold.
# This is a regression gate against the *current* baseline, and a target to
# clearly beat once Milestone 7 swaps in real LLM calls.
MIN_LABEL_AGREEMENT = 0.5


@pytest.fixture(autouse=True)
def _force_heuristic_path(monkeypatch):
    """This harness measures the deterministic heuristic baseline against
    human labels (see MIN_LABEL_AGREEMENT above), so it must not silently
    pick up a real ANTHROPIC_API_KEY from the environment/.env - that would
    turn a fast, free, deterministic regression gate into a slow, costly,
    non-deterministic one. The real LLM path is covered separately by
    run_llm_agent_integration_tests.py.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def _load_examples():
    with open(EXAMPLES_PATH, encoding="utf-8") as fh:
        return json.load(fh)


EXAMPLES = _load_examples()


def _run_pipeline(example):
    """Run the real Evaluator -> DevilsAdvocate pipeline for one example."""
    eval_result = Evaluator.run({
        "answer_text": example["answer_text"],
        "question": example["question"],
        "question_id": example["id"],
    })
    evaluation = eval_result["payload"]
    da_result = DevilsAdvocate.run(evaluation)
    return evaluation, da_result


@pytest.mark.parametrize("example", EXAMPLES, ids=[e["id"] for e in EXAMPLES])
def test_score_consistency_across_repeated_runs(example):
    """Same question/answer scored twice must produce the same score.

    Today's heuristic scorer is deterministic; this test is the tripwire
    for when Milestone 7 introduces an LLM and reuse/caching stops being
    exact-match safe.
    """
    first, _ = _run_pipeline(example)
    second, _ = _run_pipeline(example)
    assert first["overall_score"] == second["overall_score"]


def test_labeled_example_agreement():
    """Report + gate on agreement between agent decisions and human labels."""
    label_matches = 0
    devils_advocate_matches = 0

    for example in EXAMPLES:
        evaluation, da_result = _run_pipeline(example)
        predicted_label = "needs_followup" if evaluation["needs_followup"] else "acceptable"
        if predicted_label == example["label"]:
            label_matches += 1
        else:
            print(
                f"[label mismatch] {example['id']}: expected {example['label']}, "
                f"got {predicted_label} (score={evaluation['overall_score']})"
            )

        if da_result["message_type"] == example["expect_devils_advocate"]:
            devils_advocate_matches += 1
        else:
            print(
                f"[devils_advocate mismatch] {example['id']}: expected "
                f"{example['expect_devils_advocate']}, got {da_result['message_type']}"
            )

    total = len(EXAMPLES)
    label_accuracy = label_matches / total
    da_accuracy = devils_advocate_matches / total
    print(f"Evaluator label agreement: {label_matches}/{total} ({label_accuracy:.0%})")
    print(f"Devil's Advocate label agreement: {devils_advocate_matches}/{total} ({da_accuracy:.0%})")

    assert label_accuracy >= MIN_LABEL_AGREEMENT
    assert da_accuracy >= MIN_LABEL_AGREEMENT


def test_tool_trace_confirms_memory_and_feedback_loops():
    """Dispatch real ToolRequests and confirm the returned `decision` trace
    shows memory retrieval and cache reuse, not just that the code paths
    exist. `MogBotFloorManager`'s HTTP-facing session response deliberately
    strips `decision` metadata (session_context.md: keep it internal), so
    this drives `main.dispatch_tool_request` directly to inspect it.
    """
    # GlobalVectorMemory's 64-dim hashed bag-of-words embedding has a small
    # enough bucket space that, once many records accumulate across repeated
    # test runs, unrelated documents can occasionally collide above the
    # similarity threshold by chance alone. Reset the shared store first so
    # this test's "no prior hit" assertion is deterministic rather than
    # dependent on how much leftover state prior runs left behind.
    with m.GLOBAL_MEMORY_LOCK:
        m.GLOBAL_VECTOR_MEMORY._records.clear()
        m.GLOBAL_VECTOR_MEMORY._persist_to_disk()

    run_token = uuid.uuid4().hex[:8]
    job_description = f"harness probe job description {run_token}"
    session_id = f"harness-trace-session-{run_token}"

    first_request = m._build_tool_request(
        session_id=session_id,
        target_agent="job_search",
        task_type="research_job",
        payload={"user_inputs": {"job_description": job_description, "session_id": session_id}},
    )
    first_msg = m.dispatch_tool_request(first_request)
    assert first_msg["status"] == "ok"
    assert "global_vector_memory" not in first_msg["decision"]["tools_used"], (
        "first run for a new job_description should not already have a memory hit"
    )

    second_request = m._build_tool_request(
        session_id=session_id,
        target_agent="job_search",
        task_type="research_job",
        payload={"user_inputs": {"job_description": job_description, "session_id": session_id}},
    )
    second_msg = m.dispatch_tool_request(second_request)
    print(f"Second job_search call metadata: {second_msg.get('metadata')}")
    print(f"Second job_search call decision: {second_msg['decision']}")
    assert second_msg["metadata"].get("cache_hit") is True, (
        "identical job_description should be served from the semantic cache on the second call"
    )

    eval_msg = m.dispatch_tool_request(
        m._build_tool_request(
            session_id=session_id,
            target_agent="evaluator",
            task_type="evaluate_answer",
            payload={
                "current_question": {"text": "Describe a scaling challenge you solved."},
                "latest_turn": {"answer_text": "I don't know."},
            },
        )
    )
    print(f"Evaluator decision: {eval_msg['decision']}")
    assert eval_msg["decision"]["next_recommended_tool"] == "devils_advocate", (
        "a low-scoring answer should route the evaluator -> devils_advocate feedback loop"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
