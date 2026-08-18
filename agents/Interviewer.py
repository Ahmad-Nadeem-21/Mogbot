"""Conversation strategy agent for MogBot."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from core.schemas import AgentMessage, build_agent_decision


def run(conversation_turn: Dict[str, Any], session_state: Dict[str, Any] | None = None) -> AgentMessage:
    """Recommend the next interview move without displaying anything to the user."""
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
