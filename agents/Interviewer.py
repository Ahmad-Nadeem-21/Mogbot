"""Conversation strategy agent for MogBot."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from core import llm_client
from core.prompt_manager import PromptManager
from core.schemas import AgentMessage, build_agent_decision

_PROMPT_MANAGER = PromptManager()

_LLM_TOOL_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "recommended_action": {
            "type": "string",
            "enum": ["clarify", "continue", "rephrase", "transition", "end"],
        },
        "suggested_prompt": {"type": "string"},
        "reason": {"type": "string"},
        "tone": {"type": "string"},
        "should_continue": {"type": "boolean"},
        "next_recommended_tool": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["recommended_action", "suggested_prompt", "reason", "tone", "should_continue", "confidence"],
}


def run(conversation_turn: Dict[str, Any], session_state: Dict[str, Any] | None = None) -> AgentMessage:
    """Recommend the next interview move without displaying anything to the user.

    Uses a real Anthropic call when ANTHROPIC_API_KEY is configured; falls
    back to the deterministic heuristic below otherwise or on any API
    failure. See ACTION_PLAN.md Milestone 7.
    """
    if llm_client.is_configured():
        try:
            return _run_llm(conversation_turn, session_state)
        except Exception as exc:
            print(f"[Interviewer] LLM path failed ({exc}); falling back to heuristic.")
    return _run_heuristic(conversation_turn, session_state)


def _run_llm(conversation_turn: Dict[str, Any], session_state: Dict[str, Any] | None = None) -> AgentMessage:
    session_state = session_state or {}
    evaluation = conversation_turn.get("evaluation_result", {})
    latest_answer = str(conversation_turn.get("answer_text", conversation_turn.get("answer", "")))

    system_prompt = _PROMPT_MANAGER.render("interviewer", "system", {})
    task_prompt = _PROMPT_MANAGER.render(
        "interviewer",
        "task",
        {"conversation_turn": str({
            "latest_answer": llm_client.wrap_untrusted_content("latest_answer", latest_answer),
            "evaluation_result": evaluation,
        })},
    )

    llm_output = llm_client.call_structured(
        system_prompt=system_prompt,
        user_prompt=task_prompt,
        tool_name="record_interview_strategy",
        tool_description="Recommend the next interview conversation move.",
        input_schema=_LLM_TOOL_SCHEMA,
    )

    session_id = session_state.get("session_id", conversation_turn.get("session_id", ""))
    return {
        "schema_version": "1.0",
        "message_id": str(uuid.uuid4()),
        "request_id": conversation_turn.get("request_id", ""),
        "session_id": session_id,
        "source_agent": "interviewer",
        "target": "main",
        "message_type": "interview_strategy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "payload": {
            "recommended_action": llm_output["recommended_action"],
            "suggested_prompt": llm_output["suggested_prompt"],
            "reason": llm_output["reason"],
            "tone": llm_output["tone"],
            "should_continue": llm_output["should_continue"],
        },
        "metadata": {},
        "decision": build_agent_decision(
            action=llm_output["recommended_action"],
            reasoning_summary=llm_output["reason"],
            tools_considered=["conversation_history", "evaluation_result", "anthropic_llm"],
            tools_used=["conversation_history", "evaluation_result", "anthropic_llm"],
            confidence=float(llm_output["confidence"]),
            next_recommended_tool=llm_output.get("next_recommended_tool", "none"),
        ),
    }


def _run_heuristic(conversation_turn: Dict[str, Any], session_state: Dict[str, Any] | None = None) -> AgentMessage:
    """Deterministic answer-length heuristic fallback - see `run()` for when this is used."""
    session_state = session_state or {}
    evaluation = conversation_turn.get("evaluation_result", {})
    latest_answer = conversation_turn.get("answer_text", conversation_turn.get("answer", ""))
    needs_followup = bool(evaluation.get("needs_followup"))
    answer_is_short = len(str(latest_answer).split()) < 35

    if needs_followup or answer_is_short:
        recommended_action = "clarify"
        suggested_prompt = "Could you add a specific example, your exact role, and the result?"
        tone = "supportive"
        should_continue = True
        next_tool = "evaluator"
        confidence = 0.72
        reason = "The answer needs more detail before moving forward."
    else:
        recommended_action = "continue"
        suggested_prompt = "Thanks. Let's move to the next question."
        tone = "neutral"
        should_continue = True
        next_tool = "question_generator"
        confidence = 0.78
        reason = "The answer appears specific enough to continue."

    session_id = session_state.get("session_id", conversation_turn.get("session_id", ""))
    return {
        "schema_version": "1.0",
        "message_id": str(uuid.uuid4()),
        "request_id": conversation_turn.get("request_id", ""),
        "session_id": session_id,
        "source_agent": "interviewer",
        "target": "main",
        "message_type": "interview_strategy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "payload": {
            "recommended_action": recommended_action,
            "suggested_prompt": suggested_prompt,
            "reason": reason,
            "tone": tone,
            "should_continue": should_continue,
        },
        "metadata": {},
        "decision": build_agent_decision(
            action=recommended_action,
            reasoning_summary=reason,
            tools_considered=["conversation_history", "evaluation_result"],
            tools_used=["conversation_history", "evaluation_result"],
            confidence=confidence,
            next_recommended_tool=next_tool,
        ),
    }
