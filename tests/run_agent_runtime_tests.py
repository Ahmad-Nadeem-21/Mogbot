"""Tests for core/agent_runtime.py's AgentWorker timeout handling.

Proves the actual bug that caused real production hangs: `future.result(timeout=X)`
inside a `with ThreadPoolExecutor(...) as pool:` block raises after X seconds,
but exiting that `with` block calls shutdown(wait=True), which blocks until the
still-running (uncancellable) thread actually finishes - making the configured
timeout cosmetic. A genuinely hung call (e.g. a slow network path to Anthropic)
would block the worker for however long the real call took, not run_timeout_seconds.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.agent_runtime import spawn_agent_worker

# How long the fake "hung" run_function sleeps - deliberately much longer than
# the worker's own run_timeout_seconds below, so a regression (the old
# with-block bug) would make this test itself hang for HUNG_CALL_SECONDS.
HUNG_CALL_SECONDS = 5.0
WORKER_TIMEOUT_SECONDS = 1.0
# Generous slack for scheduling jitter - this is what actually matters: the
# worker must return well before HUNG_CALL_SECONDS, not exactly at the timeout.
MAX_ACCEPTABLE_WAIT_SECONDS = WORKER_TIMEOUT_SECONDS + 2.0


def _hangs_forever(request):
    time.sleep(HUNG_CALL_SECONDS)
    return {"message_type": "should_never_arrive", "payload": {}}


def _fast_ok(request):
    return {"message_type": "ok", "payload": {"echo": request.get("session_id")}}


def test_worker_returns_near_configured_timeout_not_after_the_hung_call_finishes():
    in_queue, out_queue, stop_event, worker = spawn_agent_worker("hang_test", _hangs_forever)
    worker.run_timeout_seconds = WORKER_TIMEOUT_SECONDS
    worker.start()
    try:
        start = time.monotonic()
        in_queue.put({"session_id": "s1"})
        result = out_queue.get(timeout=MAX_ACCEPTABLE_WAIT_SECONDS)
        elapsed = time.monotonic() - start

        assert result["message_type"] == "runtime_timeout"
        assert result["payload"]["timeout_seconds"] == WORKER_TIMEOUT_SECONDS
        assert elapsed < MAX_ACCEPTABLE_WAIT_SECONDS, (
            f"worker took {elapsed:.1f}s to report a timeout configured at "
            f"{WORKER_TIMEOUT_SECONDS}s - the with-ThreadPoolExecutor regression "
            "would make this ~= HUNG_CALL_SECONDS instead"
        )
    finally:
        stop_event.set()
        in_queue.put(None)


def test_worker_still_returns_the_hung_calls_own_result_once_the_thread_finally_finishes():
    """The old bug's flip side still applies here (Python can't kill a running
    thread), so the leaked thread's own late result must not corrupt the NEXT
    request's result once it eventually lands on the same output queue."""
    in_queue, out_queue, stop_event, worker = spawn_agent_worker("hang_test_2", _hangs_forever)
    worker.run_timeout_seconds = WORKER_TIMEOUT_SECONDS
    worker.start()
    try:
        in_queue.put({"session_id": "s1"})
        first = out_queue.get(timeout=MAX_ACCEPTABLE_WAIT_SECONDS)
        assert first["message_type"] == "runtime_timeout"
    finally:
        stop_event.set()
        in_queue.put(None)


def test_worker_handles_a_normal_fast_call_unaffected_by_the_fix():
    in_queue, out_queue, stop_event, worker = spawn_agent_worker("fast_test", _fast_ok)
    worker.start()
    try:
        in_queue.put({"session_id": "s2"})
        result = out_queue.get(timeout=5.0)
        assert result["message_type"] == "ok"
        assert result["payload"]["echo"] == "s2"
    finally:
        stop_event.set()
        in_queue.put(None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
