"""End-to-end tests for the Flask-facing session flow.

Drives the same HTTP contract the Chrome extension / web frontend use
(POST /sessions, GET /sessions/<id>, POST /sessions/<id>/answers) through
Flask's test client, so this exercises the real backend.app + main.py
floor-manager wiring rather than calling MogBotFloorManager in-process.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import main as m
from backend.app import create_app
from main import MogBotFloorManager

JOB_DESCRIPTION = (
    "We are hiring a Senior Python Engineer. Required: python, sql, aws, docker. "
    "Responsibilities: build APIs and lead the team."
)
RESUME_TEXT = (
    "Senior Software Engineer with 8 years experience. Skills: python, sql, docker. "
    "Led a team of 4 engineers building REST APIs."
)


@pytest.fixture(autouse=True)
def _force_heuristic_path(monkeypatch):
    """Force the deterministic agent fallback so this stays a fast, free,
    deterministic HTTP-contract test regardless of a real ANTHROPIC_API_KEY
    in the environment/.env. The real LLM path is covered separately by
    run_llm_agent_integration_tests.py.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture
def client():
    app = create_app(MogBotFloorManager())
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def low_limit_client():
    """A client with a deliberately low rate limit, for testing enforcement
    without needing to fire dozens of requests against the real default."""
    app = create_app(MogBotFloorManager(), session_rate_limit="2 per hour", answer_rate_limit="2 per hour")
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_usage_endpoint(client):
    resp = client.get("/usage")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "by_model" in body
    assert "totals" in body
    assert set(body["totals"].keys()) == {"calls", "input_tokens", "output_tokens"}


def test_session_not_found(client):
    resp = client.get("/sessions/does-not-exist")
    assert resp.status_code == 404


def test_start_session_requires_job_and_resume(client):
    resp = client.post("/sessions", json={"job_description": "", "resume_text": ""})
    assert resp.status_code == 400


def test_full_interview_flow(client):
    start_resp = client.post(
        "/sessions",
        json={
            "job_description": JOB_DESCRIPTION,
            "resume_text": RESUME_TEXT,
            "delivery_mode": "extension",
            "max_questions": 2,
        },
    )
    assert start_resp.status_code == 200
    session = start_resp.get_json()
    session_id = session["session_id"]
    assert session["status"] == "running"
    assert session["current_question"] is not None
    assert session["progress"]["total"] == 2

    get_resp = client.get(f"/sessions/{session_id}")
    assert get_resp.status_code == 200
    assert get_resp.get_json()["session_id"] == session_id

    inputs_resp = client.get(f"/sessions/{session_id}/inputs")
    assert inputs_resp.status_code == 200
    assert inputs_resp.get_json()["job_description"] == JOB_DESCRIPTION

    final_state = None
    for _ in range(2):
        answer_resp = client.post(
            f"/sessions/{session_id}/answers",
            json={"answer_text": "I led a caching project that improved API latency by 40%."},
        )
        assert answer_resp.status_code == 200
        final_state = answer_resp.get_json()
        assert "evaluation" in final_state["feedback"]

    assert final_state["status"] == "completed"
    assert final_state["summary"]
    assert "recommended_next_steps" in final_state["summary"]

    past_end_resp = client.post(
        f"/sessions/{session_id}/answers",
        json={"answer_text": "one more"},
    )
    assert past_end_resp.status_code == 409


def test_oversized_job_description_rejected(client):
    resp = client.post(
        "/sessions",
        json={"job_description": "x" * (m.MAX_INPUT_CHARS + 1), "resume_text": RESUME_TEXT},
    )
    assert resp.status_code == 400


def test_oversized_resume_text_rejected(client):
    resp = client.post(
        "/sessions",
        json={"job_description": JOB_DESCRIPTION, "resume_text": "x" * (m.MAX_INPUT_CHARS + 1)},
    )
    assert resp.status_code == 400


def test_oversized_answer_text_rejected(client):
    start_resp = client.post(
        "/sessions",
        json={"job_description": JOB_DESCRIPTION, "resume_text": RESUME_TEXT, "max_questions": 1},
    )
    session_id = start_resp.get_json()["session_id"]

    resp = client.post(
        f"/sessions/{session_id}/answers",
        json={"answer_text": "x" * (m.MAX_ANSWER_CHARS + 1)},
    )
    assert resp.status_code == 400


def test_session_rate_limit_enforced(low_limit_client):
    for _ in range(2):
        resp = low_limit_client.post(
            "/sessions",
            json={"job_description": JOB_DESCRIPTION, "resume_text": RESUME_TEXT, "max_questions": 1},
        )
        assert resp.status_code == 200

    third_resp = low_limit_client.post(
        "/sessions",
        json={"job_description": JOB_DESCRIPTION, "resume_text": RESUME_TEXT, "max_questions": 1},
    )
    assert third_resp.status_code == 429


def test_answer_rate_limit_enforced(low_limit_client):
    start_resp = low_limit_client.post(
        "/sessions",
        json={"job_description": JOB_DESCRIPTION, "resume_text": RESUME_TEXT, "max_questions": 5},
    )
    session_id = start_resp.get_json()["session_id"]

    for _ in range(2):
        resp = low_limit_client.post(
            f"/sessions/{session_id}/answers",
            json={"answer_text": "A reasonably detailed answer to stay under the answer cap."},
        )
        assert resp.status_code == 200

    third_resp = low_limit_client.post(
        f"/sessions/{session_id}/answers",
        json={"answer_text": "one more"},
    )
    assert third_resp.status_code == 429


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
