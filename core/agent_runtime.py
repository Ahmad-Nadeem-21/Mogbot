"""Threaded agent runtime for MogBot."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timezone
from queue import Empty, Queue
from threading import Event, Thread
from typing import Callable, Tuple

from core.schemas import AgentMessage, ToolRequest, build_agent_decision


AgentRunFunction = Callable[[ToolRequest], AgentMessage]


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def failure_agent_message(
    *,
    source_agent: str,
    request: ToolRequest,
    message_type: str,
    status: str,
    summary: str,
    payload: dict,
) -> AgentMessage:
    return {
        "schema_version": request.get("schema_version", "1.0"),
        "message_id": str(uuid.uuid4()),
        "request_id": request.get("request_id", ""),
        "session_id": request.get("session_id", ""),
        "source_agent": source_agent,
        "target": "main",
        "message_type": message_type,
        "timestamp": _utc_timestamp(),
        "status": status,
        "payload": payload,
        "metadata": {},
        "decision": build_agent_decision(
            status,
            summary,
            tools_considered=[source_agent],
            tools_used=[],
            confidence=0.0,
            next_recommended_tool="none",
        ),
    }


class AgentWorker(Thread):
    """Worker thread that lets main.py treat each agent as a tool."""

    def __init__(
        self,
        name: str,
        run_function: AgentRunFunction,
        input_queue: Queue,
        output_queue: Queue,
        stop_event: Event,
        run_timeout_seconds: float = 120.0,
        retry_limit: int = 1,
    ) -> None:
        super().__init__(name=name, daemon=True)
        self.run_function = run_function
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.stop_event = stop_event
        self.run_timeout_seconds = run_timeout_seconds
        self.retry_limit = retry_limit

    def run(self) -> None:
        """Process ToolRequest objects until main.py stops the worker."""
        while not self.stop_event.is_set():
            try:
                request = self.input_queue.get(timeout=0.5)
            except Empty:
                continue
            if request is None:
                self.input_queue.task_done()
                break
            attempt = 0
            result: AgentMessage
            while True:
                # Deliberately not `with ThreadPoolExecutor(...) as pool:` -
                # exiting that block calls shutdown(wait=True), which blocks
                # until the submitted call actually finishes even after
                # future.result(timeout=...) has already raised. That made
                # this timeout cosmetic: a genuinely hung call (e.g. a slow
                # network path to Anthropic) would still block this thread
                # for however long the real call took, not run_timeout_seconds.
                # shutdown(wait=False) lets a fresh pool per attempt clean up
                # in the background whenever the hung thread eventually ends,
                # instead of blocking - and a fresh pool (not a shared one)
                # keeps one hung call from also blocking every later request.
                pool = ThreadPoolExecutor(max_workers=1)
                try:
                    future = pool.submit(self.run_function, request)
                    result = future.result(timeout=self.run_timeout_seconds)
                    break
                except FuturesTimeout:
                    result = failure_agent_message(
                        source_agent=self.name,
                        request=request,
                        message_type="runtime_timeout",
                        status="error",
                        summary=f"Agent timed out after {self.run_timeout_seconds}s",
                        payload={"timeout_seconds": self.run_timeout_seconds, "retries_attempted": attempt},
                    )
                    break
                except Exception as exc:
                    if attempt >= self.retry_limit:
                        result = failure_agent_message(
                            source_agent=self.name,
                            request=request,
                            message_type="runtime_error",
                            status="error",
                            summary=f"{type(exc).__name__}: {exc}",
                            payload={
                                "error_type": type(exc).__name__,
                                "error_message": str(exc),
                                "retries_attempted": attempt,
                            },
                        )
                        break
                    attempt += 1
                finally:
                    pool.shutdown(wait=False)
            self.output_queue.put(result)
            self.input_queue.task_done()


def spawn_agent_worker(
    name: str,
    run_function: AgentRunFunction,
) -> Tuple[Queue, Queue, Event, AgentWorker]:
    """Create queues, stop flag, and a worker thread for one agent (not started)."""
    input_queue: Queue = Queue()
    output_queue: Queue = Queue()
    stop_event = Event()
    worker = AgentWorker(name, run_function, input_queue, output_queue, stop_event)
    return input_queue, output_queue, stop_event, worker
