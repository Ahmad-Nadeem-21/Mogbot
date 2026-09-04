"""Milestone 9 tests: sessions survive a process restart.

Proves the actual guarantee - not just that MogBotFloorManager works, but
that a *second*, independently-constructed MogBotFloorManager backed by the
same SQLite file (simulating a fresh server process after a restart) can
read and continue a session started by the first instance.
"""

import os
import shutil
import sys
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.session_store import SQLiteSessionStore
from main import MogBotFloorManager

# Uses a repo-local scratch dir rather than pytest's default tmp_path
# (system temp), which this environment's sandbox can restrict access to.
_SCRATCH_ROOT = os.path.join(os.path.dirname(__file__), "..", "data", "test_tmp")

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
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture
def db_path():
    scratch_dir = os.path.join(_SCRATCH_ROOT, uuid.uuid4().hex)
    os.makedirs(scratch_dir, exist_ok=True)
    try:
        yield os.path.join(scratch_dir, "sessions.db")
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)


def test_session_survives_new_manager_instance_same_db(db_path):
    """Simulates a restart: a fresh MogBotFloorManager, same SQLite file."""
    manager_a = MogBotFloorManager(SQLiteSessionStore(db_path))
    start_resp, start_code = manager_a.start_session({
        "job_description": JOB_DESCRIPTION,
        "resume_text": RESUME_TEXT,
        "max_questions": 3,
    })
    assert start_code == 200
    session_id = start_resp["session_id"]

    # "Restart": a brand new manager, no shared Python state with manager_a,
    # only the same underlying SQLite file.
    manager_b = MogBotFloorManager(SQLiteSessionStore(db_path))
    get_resp, get_code = manager_b.get_session(session_id)
    assert get_code == 200
    assert get_resp["session_id"] == session_id
    assert get_resp["current_question"] == start_resp["current_question"]


def test_interview_can_continue_on_new_manager_instance_same_db(db_path):
    manager_a = MogBotFloorManager(SQLiteSessionStore(db_path))
    start_resp, _ = manager_a.start_session({
        "job_description": JOB_DESCRIPTION,
        "resume_text": RESUME_TEXT,
        "max_questions": 2,
    })
    session_id = start_resp["session_id"]

    manager_b = MogBotFloorManager(SQLiteSessionStore(db_path))
    answer_resp, answer_code = manager_b.submit_answer(
        session_id, {"answer_text": "I led a caching project that cut latency by 40%."}
    )
    assert answer_code == 200
    assert answer_resp["progress"]["current"] == 2


def test_unknown_session_returns_404_not_a_crash(db_path):
    manager = MogBotFloorManager(SQLiteSessionStore(db_path))
    resp, code = manager.get_session("does-not-exist")
    assert code == 404


def test_default_floor_manager_uses_sqlite_store_by_default():
    """MogBotFloorManager() with no args still gets a real, non-in-memory
    session store - the persistence fix isn't opt-in."""
    manager = MogBotFloorManager()
    assert isinstance(manager._sessions, SQLiteSessionStore)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
