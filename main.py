"""
CS 494 Group Project
MogBot

Shazaib Dawood
Zaid Haidry
Ahmad Nadeem
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timezone
from queue import Empty
from threading import RLock, Thread
from typing import Any, Dict, List, Optional, Tuple

from core.agent_runtime import AgentRunFunction, failure_agent_message, spawn_agent_worker
from core.cache_manager import SemanticCache
from core.prompt_manager import PromptManager
from core.vector_memory import GlobalVectorMemory
from core.schemas import (
    AgentDecision,
    AgentMessage,
    SessionState,
    ToolRequest,
    agent_message_decision_issues,
    build_agent_decision,
    decision_is_complete,
)

from helper_agents import BiasSafetyReviewAgent
from helper_agents import ConsistencyReviewAgent
from helper_agents import ExpertReviewAgent
from helper_agents import RewardReviewAgent
from agents import CareerCoach
from agents import DevilsAdvocate
from agents import Evaluator
from agents import Interviewer
from agents import JobSearchAgent
from agents import QuestionGenerator
from agents import ResumeAndRoleAnalyzer


__all__ = [
    "AGENT_RUN_REGISTRY",
    "AGENT_WORKER_CHANNELS",
    "GLOBAL_VECTOR_MEMORY",
    "GLOBAL_MEMORY_LOCK",
    "AgentDecision",
    "AgentMessage",
    "SessionState",
    "ToolRequest",
    "agent_message_decision_issues",
    "build_agent_decision",
    "create_session_state",
    "decision_is_complete",
    "dispatch_tool_request",
    "failure_agent_message",
    "MogBotFloorManager",
    "run_floor_manager_session",
    "start_flask_server",
]

GLOBAL_VECTOR_MEMORY = GlobalVectorMemory()
GLOBAL_MEMORY_LOCK = RLock()
PROMPT_MANAGER = PromptManager()
SEMANTIC_CACHE = SemanticCache(GLOBAL_VECTOR_MEMORY)


def create_session_state(session_id: str) -> SessionState:
    """Create the canonical empty SessionState for a new MogBot session."""
    return {
        "session_id": session_id,
        "user_inputs": {},
        "job_research": {},
        "candidate_profile": {},
        "question_plan": {},
        "current_question": {},
        "conversation_history": [],
        "evaluation_scores": [],
        "reward_signals": [],
        "interview_strategy_notes": [],
        "devil_advocate_flags": [],
        "helper_reviews": [],
        "memory_records": [],
        "cache_hits": [],
        "final_report": {},
        "status": "created",
    }


AGENT_RUN_REGISTRY: Dict[str, AgentRunFunction] = {
    "helper_expert_review": ExpertReviewAgent.run,
    "helper_bias_safety_review": BiasSafetyReviewAgent.run,
    "helper_consistency_review": ConsistencyReviewAgent.run,
    "helper_reward_review": RewardReviewAgent.run,
}
AGENT_WORKER_CHANNELS: Dict[str, Tuple[Any, Any, Any, Any]] = {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def register_agent(target_agent: str, run_fn: AgentRunFunction) -> None:
    """Register one agent in both run map and durable worker map."""
    AGENT_RUN_REGISTRY[target_agent] = run_fn
    if target_agent in AGENT_WORKER_CHANNELS:
        return
    in_queue, out_queue, stop_event, worker = spawn_agent_worker(target_agent, run_fn)
    worker.start()
    AGENT_WORKER_CHANNELS[target_agent] = (in_queue, out_queue, stop_event, worker)


def _normalize_agent_message(
    result: Dict[str, Any],
    request: ToolRequest,
    *,
    source_agent: str,
    message_type: str,
) -> AgentMessage:
    """Adapt branch-specific agent return shapes to the shared AgentMessage contract."""
    result_data = result if isinstance(result, dict) else {}
    payload = result_data.get("payload", {})
    status = result_data.get("status", "ok") if result_data else "error"
    if status == "success":
        status = "ok"
    decision = result_data.get("decision", {})
    if not decision_is_complete(decision):
        decision = build_agent_decision(
            action=str(decision.get("action", message_type)),
            reasoning_summary=str(
                decision.get("reasoning_summary", f"{source_agent} returned {message_type}.")
            ),
            tools_considered=list(decision.get("tools_considered", [])),
            tools_used=list(decision.get("tools_used", [])),
            confidence=float(decision.get("confidence", 0.0)),
            next_recommended_tool=str(decision.get("next_recommended_tool", "none")),
        )
    return {
        "schema_version": request.get("schema_version", result_data.get("schema_version", "1.0")),
        "message_id": result_data.get("message_id", str(uuid.uuid4())),
        "request_id": request.get("request_id", result_data.get("request_id", "")),
        "session_id": request.get("session_id", result_data.get("session_id", "")),
        "source_agent": source_agent,
        "target": "main",
        "message_type": result_data.get("message_type", message_type),
        "timestamp": result_data.get("timestamp", _utc_now()),
        "status": status,
        "payload": payload,
        "metadata": result_data.get("metadata", {}),
        "decision": decision,
    }


def _user_inputs_from_request(request: ToolRequest) -> Dict[str, Any]:
    payload = request.get("payload", {})
    user_inputs = payload.get("user_inputs", payload) if isinstance(payload, dict) else {}
    data = dict(user_inputs)
    data.setdefault("session_id", request.get("session_id", ""))
    return data


def _job_search_runner(request: ToolRequest) -> AgentMessage:
    """Adapter: run Zaid's JobSearchAgent from Ahmad's ToolRequest dispatcher."""
    result = JobSearchAgent.run(_user_inputs_from_request(request), vector_memory=GLOBAL_VECTOR_MEMORY)
    return _normalize_agent_message(
        result,
        request,
        source_agent="job_search",
        message_type="job_research",
    )


def _resume_analyzer_runner(request: ToolRequest) -> AgentMessage:
    """Adapter: run Zaid's ResumeAndRoleAnalyzer from Ahmad's dispatcher."""
    data = _user_inputs_from_request(request)
    payload = request.get("payload", {})
    if isinstance(payload, dict) and "job_research" in payload:
        data["job_research"] = payload["job_research"]
    result = ResumeAndRoleAnalyzer.run(data)
    return _normalize_agent_message(
        result,
        request,
        source_agent="resume_analyzer",
        message_type="candidate_profile",
    )


def _question_generator_runner(request: ToolRequest) -> AgentMessage:
    """Adapter: run Zaid's QuestionGenerator from Ahmad's dispatcher."""
    payload = request.get("payload", {})
    session_context = request.get("session_context", {})
    result = QuestionGenerator.run(
        payload.get("job_research", {}) if isinstance(payload, dict) else {},
        payload.get("candidate_profile", {}) if isinstance(payload, dict) else {},
        session_context.get("session_state", session_context),
    )
    return _normalize_agent_message(
        result,
        request,
        source_agent="question_generator",
        message_type="question_plan",
    )


def _evaluator_runner(request: ToolRequest) -> AgentMessage:
    """Adapter: run Zaid's Evaluator from Ahmad's dispatcher."""
    payload = request.get("payload", {})
    latest_turn = payload.get("latest_turn", {}) if isinstance(payload, dict) else {}
    current_question = payload.get("current_question", {}) if isinstance(payload, dict) else {}
    question_text = current_question.get("text", str(current_question))
    user_response = {
        "answer_text": latest_turn.get("answer_text", latest_turn.get("answer", "")),
        "question": latest_turn.get("question", question_text),
        "question_id": current_question.get("id", latest_turn.get("question_id", "")),
    }
    result = Evaluator.run(user_response, session_context=request.get("session_context", {}))
    message = _normalize_agent_message(
        result,
        request,
        source_agent="evaluator",
        message_type="evaluation_result",
    )
    payload = message.get("payload", {})
    needs_followup = bool(payload.get("needs_followup"))
    message["decision"] = build_agent_decision(
        action="evaluate_answer",
        reasoning_summary=str(payload.get("evaluator_comment", "Evaluated answer against rubric.")),
        tools_considered=["rubric", "session_context"],
        tools_used=["rubric"],
        confidence=float(payload.get("confidence", 0.0)),
        next_recommended_tool="devils_advocate" if needs_followup else "none",
    )
    return message


def _devils_advocate_runner(request: ToolRequest) -> AgentMessage:
    """Adapter: run Zaid's Devil's Advocate challenge tool."""
    payload = request.get("payload", {})
    evaluation_result = payload.get("evaluation_result", payload) if isinstance(payload, dict) else {}
    if "overall_score" in evaluation_result and "score" not in evaluation_result:
        evaluation_result = {**evaluation_result, "score": evaluation_result["overall_score"]}
    session_context = request.get("session_context", {})
    result = DevilsAdvocate.run(
        evaluation_result,
        session_context.get("conversation_history", []),
    )
    return _normalize_agent_message(
        result,
        request,
        source_agent="devils_advocate",
        message_type=result.get("message_type", "challenge_prompt"),
    )


def _interviewer_runner(request: ToolRequest) -> AgentMessage:
    """Adapter: run the interview strategy agent from the dispatcher."""
    payload = request.get("payload", {})
    session_context = request.get("session_context", {})
    turn = payload if isinstance(payload, dict) else {}
    result = Interviewer.run(turn, session_context.get("session_state", session_context))
    return _normalize_agent_message(
        result,
        request,
        source_agent="interviewer",
        message_type="interview_strategy",
    )


def _career_coach_runner(request: ToolRequest) -> AgentMessage:
    """Adapter: run CareerCoach with SessionState payload."""
    payload = request.get("payload", {})
    session_state = payload.get("session_state", {}) if isinstance(payload, dict) else {}
    return CareerCoach.run(session_state)


register_agent("job_search", _job_search_runner)
register_agent("resume_analyzer", _resume_analyzer_runner)
register_agent("question_generator", _question_generator_runner)
register_agent("evaluator", _evaluator_runner)
register_agent("devils_advocate", _devils_advocate_runner)
register_agent("interviewer", _interviewer_runner)
register_agent("career_coach", _career_coach_runner)
for _target_agent, _run_fn in list(AGENT_RUN_REGISTRY.items()):
    register_agent(_target_agent, _run_fn)


def _build_tool_request(
    *,
    session_id: str,
    target_agent: str,
    task_type: str,
    payload: Dict[str, Any],
    session_context: Optional[Dict[str, Any]] = None,
) -> ToolRequest:
    return {
        "schema_version": "1.0",
        "request_id": str(uuid.uuid4()),
        "session_id": session_id,
        "source": "main",
        "target_agent": target_agent,
        "task_type": task_type,
        "timestamp": _utc_now(),
        "payload": payload,
        "session_context": session_context or {},
    }


def _safe_memory_add(record: Dict[str, Any]) -> Optional[str]:
    """MAIN-MEM-02 helper: serialize memory writes under a main-level lock."""
    with GLOBAL_MEMORY_LOCK:
        try:
            return GLOBAL_VECTOR_MEMORY.add_record(record)
        except Exception:
            return None


def _append_reward_signal(state: SessionState, signal: Dict[str, Any]) -> None:
    signals = state.setdefault("reward_signals", [])
    signals.append(signal)


def dispatch_tool_request(
    request: ToolRequest,
    *,
    run_timeout_seconds: Optional[float] = 300.0,
) -> AgentMessage:
    """Call the registered run() for request['target_agent'] (optional wall-clock timeout)."""
    target = request.get("target_agent", "")
    runner = AGENT_RUN_REGISTRY.get(target)
    if runner is None:
        return failure_agent_message(
            source_agent="main",
            request=request,
            message_type="unknown_agent",
            status="error",
            summary=f"No agent registered for target_agent={target!r}",
            payload={"target_agent": target},
        )

    cache_type = request.get("task_type", "generic")
    cache_key = f"{target}:{request.get('payload', {})}"
    cached_payload = SEMANTIC_CACHE.lookup(cache_type, cache_key)
    if cached_payload is not None:
        return {
            "schema_version": request.get("schema_version", "1.0"),
            "message_id": "",
            "request_id": request.get("request_id", ""),
            "session_id": request.get("session_id", ""),
            "source_agent": target,
            "target": "main",
            "message_type": "cached_result",
            "status": "ok",
            "payload": cached_payload,
            "metadata": {"cache_hit": True},
            "decision": build_agent_decision(
                action="cache_hit",
                reasoning_summary="Returned cached payload for matching request.",
                tools_considered=["semantic_cache", target],
                tools_used=["semantic_cache"],
                confidence=0.85,
                next_recommended_tool="none",
            ),
        }

    if target.startswith("helper_"):
        try:
            request.setdefault("session_context", {})
            request["session_context"]["system_prompt"] = PROMPT_MANAGER.render(
                target,
                "system",
                {},
            )
        except ValueError:
            # Some helper templates may not define `system`; safe to continue.
            pass
    worker_channels = AGENT_WORKER_CHANNELS.get(target)
    if worker_channels:
        in_queue, out_queue, _, _ = worker_channels
        in_queue.put(request)
        if run_timeout_seconds is None:
            result = out_queue.get()
        else:
            try:
                result = out_queue.get(timeout=run_timeout_seconds)
            except Empty:
                return failure_agent_message(
                    source_agent=target,
                    request=request,
                    message_type="timeout",
                    status="error",
                    summary=f"Agent exceeded timeout of {run_timeout_seconds}s",
                    payload={"timeout_seconds": run_timeout_seconds},
                )
    else:
        if run_timeout_seconds is None:
            result = runner(request)
        else:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(runner, request)
                try:
                    result = future.result(timeout=run_timeout_seconds)
                except FuturesTimeout:
                    return failure_agent_message(
                        source_agent=target,
                        request=request,
                        message_type="timeout",
                        status="error",
                        summary=f"Agent exceeded timeout of {run_timeout_seconds}s",
                        payload={"timeout_seconds": run_timeout_seconds},
                    )
    if result.get("status") == "ok":
        SEMANTIC_CACHE.store(
            cache_type=cache_type,
            key_text=cache_key,
            payload=result.get("payload", {}),
            metadata={"session_id": request.get("session_id", ""), "target_agent": target},
        )
    return result


def _run_helper_reviews(session_state: SessionState, output: Dict[str, Any]) -> List[AgentMessage]:
    review_messages: List[AgentMessage] = []
    for helper_target in (
        "helper_expert_review",
        "helper_consistency_review",
        "helper_bias_safety_review",
    ):
        request = _build_tool_request(
            session_id=session_state.get("session_id", ""),
            target_agent=helper_target,
            task_type="review_output",
            payload={"agent_output": output},
            session_context={"session_state": session_state},
        )
        review_messages.append(dispatch_tool_request(request))
    return review_messages


def run_floor_manager_session(session_state: SessionState, max_turns: int = 3) -> SessionState:
    """Run main orchestration skeleton with graceful fallbacks for missing agents."""
    session_state["status"] = "running"
    session_id = session_state.get("session_id", "")

    # MAIN-THREAD-01: run startup analysis tasks in parallel.
    startup_requests = [
        _build_tool_request(
            session_id=session_id,
            target_agent="job_search",
            task_type="research_job",
            payload={"user_inputs": session_state.get("user_inputs", {})},
        ),
        _build_tool_request(
            session_id=session_id,
            target_agent="resume_analyzer",
            task_type="analyze_resume",
            payload={"user_inputs": session_state.get("user_inputs", {})},
        ),
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        startup_results = list(pool.map(dispatch_tool_request, startup_requests))
    for msg in startup_results:
        if msg.get("source_agent") == "job_search" and msg.get("status") == "ok":
            session_state["job_research"] = msg.get("payload", {})
        elif msg.get("source_agent") == "resume_analyzer" and msg.get("status") == "ok":
            session_state["candidate_profile"] = msg.get("payload", {})
        _append_reward_signal(
            session_state,
            {"type": "startup_agent_status", "agent": msg.get("source_agent", ""), "status": msg.get("status", "")},
        )

    # MAIN-ORCH-04: call question generator only after startup data is present.
    if session_state.get("job_research") and session_state.get("candidate_profile"):
        q_msg = dispatch_tool_request(
            _build_tool_request(
                session_id=session_id,
                target_agent="question_generator",
                task_type="generate_questions",
                payload={
                    "job_research": session_state.get("job_research", {}),
                    "candidate_profile": session_state.get("candidate_profile", {}),
                },
            )
        )
        if q_msg.get("status") == "ok":
            session_state["question_plan"] = q_msg.get("payload", {})

    # MAIN-ORCH-05/06: evaluator routing loop.
    for _ in range(max_turns):
        current_question = session_state.get("current_question") or {}
        conversation_history = session_state.setdefault("conversation_history", [])
        if not conversation_history:
            break
        latest_turn = conversation_history[-1]
        eval_msg = dispatch_tool_request(
            _build_tool_request(
                session_id=session_id,
                target_agent="evaluator",
                task_type="evaluate_answer",
                payload={
                    "current_question": current_question,
                    "latest_turn": latest_turn,
                    "job_research": session_state.get("job_research", {}),
                    "candidate_profile": session_state.get("candidate_profile", {}),
                },
            )
        )
        if eval_msg.get("status") == "ok":
            session_state.setdefault("evaluation_scores", []).append(eval_msg.get("payload", {}))
        decision = eval_msg.get("decision", {})
        next_tool = decision.get("next_recommended_tool", "")
        if next_tool in {"interviewer", "devils_advocate"}:
            followup_msg = dispatch_tool_request(
                _build_tool_request(
                    session_id=session_id,
                    target_agent=next_tool,
                    task_type="plan_interview_move",
                    payload={"evaluation_result": eval_msg.get("payload", {})},
                )
            )
            if next_tool == "devils_advocate":
                session_state.setdefault("devil_advocate_flags", []).append(followup_msg.get("payload", {}))
            else:
                session_state.setdefault("interview_strategy_notes", []).append(followup_msg.get("payload", {}))
        _append_reward_signal(
            session_state,
            {
                "type": "evaluation_turn",
                "confidence": decision.get("confidence", 0.0),
                "next_tool": next_tool,
            },
        )

    # MAIN-ORCH-07: final coaching report.
    coach_msg = dispatch_tool_request(
        _build_tool_request(
            session_id=session_id,
            target_agent="career_coach",
            task_type="create_final_report",
            payload={"session_state": session_state},
        )
    )
    if coach_msg.get("status") == "ok":
        session_state["final_report"] = coach_msg.get("payload", {})
        stored_id = _safe_memory_add(
            {
                "record_id": f"session-final-{session_id}",
                "session_id": session_id,
                "namespace": "reports",
                "text": str(session_state["final_report"]),
                "metadata": {"source": "main"},
            }
        )
        if stored_id:
            session_state.setdefault("memory_records", []).append(stored_id)

    # MAIN-FEEDBACK-01: helper review loop for important outputs.
    if session_state.get("final_report"):
        reviews = _run_helper_reviews(session_state, session_state["final_report"])
        session_state.setdefault("helper_reviews", []).extend([msg.get("payload", {}) for msg in reviews])
        for msg in reviews:
            _append_reward_signal(
                session_state,
                {"type": "helper_review", "source": msg.get("source_agent", ""), "status": msg.get("status", "")},
            )

    # MAIN-REWARD-01: aggregate signal snapshots.
    eval_scores = session_state.get("evaluation_scores", [])
    _append_reward_signal(
        session_state,
        {
            "type": "session_summary",
            "evaluation_count": len(eval_scores),
            "helper_review_count": len(session_state.get("helper_reviews", [])),
            "final_report_present": bool(session_state.get("final_report")),
        },
    )
    session_state["status"] = "completed"
    return session_state


def _flatten_questions(question_plan: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    ordered = (
        list(question_plan.get("phone_screen", []))
        + list(question_plan.get("behavioral", []))
        + list(question_plan.get("technical", []))
    )
    questions: List[Dict[str, Any]] = []
    for index, question in enumerate(ordered[:limit]):
        item = dict(question)
        item.setdefault("question_id", item.get("id", f"q-{index + 1}"))
        item.setdefault("stage", "interview")
        item.setdefault("text", "")
        questions.append(item)
    return questions


def _public_question(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    current_index = int(record.get("current_index", 0))
    questions = record.get("questions", [])
    if current_index >= len(questions):
        return None
    question = dict(questions[current_index])
    question["number"] = current_index + 1
    question["total"] = len(questions)
    return question


def _role_focus(state: Dict[str, Any]) -> List[str]:
    job_research = state.get("job_research", {})
    if isinstance(job_research, dict):
        focus = job_research.get("interview_focus_areas") or job_research.get("keywords") or []
        return [str(item) for item in focus[:5]]
    return []


def _received_inputs(state: Dict[str, Any]) -> Dict[str, Any]:
    user_inputs = state.get("user_inputs", {})
    job_description = str(user_inputs.get("job_description", ""))
    resume_text = str(user_inputs.get("resume_text", ""))
    return {
        "job_description": job_description,
        "resume_text": resume_text,
        "job_description_length": len(job_description),
        "resume_text_length": len(resume_text),
    }


def _session_response(record: Dict[str, Any], *, feedback: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    state = record["state"]
    questions = record.get("questions", [])
    current_index = int(record.get("current_index", 0))
    return {
        "session_id": state.get("session_id", ""),
        "status": state.get("status", "running"),
        "role_focus": _role_focus(state),
        "current_question": _public_question(record),
        "progress": {
            "current": min(current_index + 1, len(questions)),
            "total": len(questions),
        },
        "feedback": feedback,
        "summary": state.get("final_report", {}),
        "debug_received_inputs": _received_inputs(state),
    }


class MogBotFloorManager:
    """Owns HTTP-facing session state while delegating agent work through main.py."""

    def __init__(self) -> None:
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._sessions_lock = RLock()

    def _get_record(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._sessions_lock:
            return self._sessions.get(session_id)

    def health(self) -> Dict[str, str]:
        return {"status": "ok"}

    def get_session(self, session_id: str) -> Tuple[Dict[str, Any], int]:
        record = self._get_record(session_id)
        if record is None:
            return {"error": "Session not found"}, 404
        return _session_response(record), 200

    def get_session_inputs(self, session_id: str) -> Tuple[Dict[str, Any], int]:
        record = self._get_record(session_id)
        if record is None:
            return {"error": "Session not found"}, 404
        return _received_inputs(record["state"]), 200

    def start_session(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        job_description = str(data.get("job_description", ""))
        resume_text = str(data.get("resume_text", ""))
        max_questions = int(data.get("max_questions", 5) or 5)
        max_questions = max(1, min(max_questions, 20))

        session_id = str(uuid.uuid4())
        state: SessionState = create_session_state(session_id)
        state["status"] = "running"
        state["user_inputs"] = {
            "job_description": job_description,
            "resume_text": resume_text,
            "company_name": str(data.get("company_name", "")),
            "role_title": str(data.get("role_title", "")),
            "job_posting_url": str(data.get("job_posting_url", "")),
            "linkedin_url": str(data.get("linkedin_url", "")),
            "delivery_mode": str(data.get("delivery_mode", "extension")),
        }

        job_msg = dispatch_tool_request(
            _build_tool_request(
                session_id=session_id,
                target_agent="job_search",
                task_type="research_job",
                payload={"user_inputs": state["user_inputs"]},
                session_context={"session_state": state},
            )
        )
        resume_msg = dispatch_tool_request(
            _build_tool_request(
                session_id=session_id,
                target_agent="resume_analyzer",
                task_type="analyze_resume",
                payload={
                    "user_inputs": state["user_inputs"],
                    "job_research": job_msg.get("payload", {}),
                },
                session_context={"session_state": state},
            )
        )
        if job_msg.get("status") != "ok":
            return {"error": "job_search failed", "detail": job_msg.get("payload", {})}, 400
        if resume_msg.get("status") != "ok":
            return {"error": "resume_analyzer failed", "detail": resume_msg.get("payload", {})}, 400

        state["job_research"] = job_msg.get("payload", {})
        state["candidate_profile"] = resume_msg.get("payload", {})

        question_msg = dispatch_tool_request(
            _build_tool_request(
                session_id=session_id,
                target_agent="question_generator",
                task_type="generate_questions",
                payload={
                    "job_research": state["job_research"],
                    "candidate_profile": state["candidate_profile"],
                },
                session_context={"session_state": state},
            )
        )
        if question_msg.get("status") != "ok":
            return {"error": "question_generator failed", "detail": question_msg.get("payload", {})}, 400

        state["question_plan"] = question_msg.get("payload", {})
        questions = _flatten_questions(state["question_plan"], max_questions)
        if not questions:
            return {"error": "Question generation returned no questions"}, 500

        state["current_question"] = questions[0]
        record = {
            "state": dict(state),
            "questions": questions,
            "current_index": 0,
            "max_questions": max_questions,
        }
        with self._sessions_lock:
            self._sessions[session_id] = record
        return _session_response(record), 200

    def submit_answer(self, session_id: str, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        record = self._get_record(session_id)
        if record is None:
            return {"error": "Session not found"}, 404
        questions = record.get("questions", [])
        current_index = int(record.get("current_index", 0))
        if current_index >= len(questions):
            return {"error": "Interview is already complete"}, 409

        answer_text = str(data.get("answer_text", ""))
        state = record["state"]
        current_question = questions[current_index]
        turn = {
            "question_id": current_question.get("question_id", current_question.get("id", "")),
            "question": current_question.get("text", ""),
            "answer_text": answer_text,
            "answered_at": _utc_now(),
        }
        state.setdefault("conversation_history", []).append(turn)

        eval_msg = dispatch_tool_request(
            _build_tool_request(
                session_id=session_id,
                target_agent="evaluator",
                task_type="evaluate_answer",
                payload={
                    "current_question": current_question,
                    "latest_turn": turn,
                    "job_research": state.get("job_research", {}),
                    "candidate_profile": state.get("candidate_profile", {}),
                },
                session_context={"session_state": state},
            )
        )
        evaluation = eval_msg.get("payload", {})
        state.setdefault("evaluation_scores", []).append(evaluation)

        challenge = None
        if evaluation.get("needs_followup"):
            challenge_msg = dispatch_tool_request(
                _build_tool_request(
                    session_id=session_id,
                    target_agent="devils_advocate",
                    task_type="challenge_answer",
                    payload={"evaluation_result": evaluation},
                    session_context={"session_state": state},
                )
            )
            challenge = challenge_msg.get("payload", {})
            state.setdefault("devil_advocate_flags", []).append(challenge)

        feedback = {
            "evaluation": evaluation,
            "challenge": challenge,
        }

        record["current_index"] = current_index + 1
        if record["current_index"] >= len(questions):
            state["status"] = "completed"
            coach_msg = dispatch_tool_request(
                _build_tool_request(
                    session_id=session_id,
                    target_agent="career_coach",
                    task_type="create_final_report",
                    payload={"session_state": state},
                    session_context={"session_state": state},
                )
            )
            if coach_msg.get("status") == "ok":
                state["final_report"] = coach_msg.get("payload", {})
        else:
            state["current_question"] = questions[record["current_index"]]

        with self._sessions_lock:
            self._sessions[session_id] = record
        return _session_response(record, feedback=feedback), 200


def start_flask_server(
    manager: Optional[MogBotFloorManager] = None,
    *,
    host: str = "127.0.0.1",
    port: int = 5000,
) -> Thread:
    """Start the Flask HTTP wrapper on a background thread controlled by main.py."""
    from backend.app import create_app

    floor_manager = manager or MogBotFloorManager()
    flask_app = create_app(floor_manager)
    server_thread = Thread(
        target=lambda: flask_app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True),
        name="mogbot-flask-server",
        daemon=True,
    )
    server_thread.start()
    return server_thread


def main() -> None:
    manager = MogBotFloorManager()
    server_thread = start_flask_server(manager)
    print("MogBot floor manager is running Flask at http://127.0.0.1:5000")
    print("Load chrome_extension in Chrome, then paste a job description and resume.")
    try:
        server_thread.join()
    except KeyboardInterrupt:
        print("\nMogBot shutting down.")


if __name__ == "__main__":
    main()
