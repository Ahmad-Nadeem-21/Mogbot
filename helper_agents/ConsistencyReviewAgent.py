"""Consistency review helper agent."""

from typing import Any, Dict, List

from core.schemas import AgentMessage, ToolRequest


def run(request: ToolRequest) -> AgentMessage:
    """Check whether a new output conflicts with session history."""
    payload = request.get("payload", {})
    session_context = request.get("session_context", {})
    session_state: Dict[str, Any] = session_context.get("session_state", {})

    proposed_output = payload.get("proposed_output", payload.get("agent_output", {}))
    conversation_history = session_context.get(
        "conversation_history",
        session_state.get("conversation_history", []),
    )
    job_research = session_context.get("job_research", session_state.get("job_research", {}))
    candidate_profile = session_context.get(
        "candidate_profile",
        session_state.get("candidate_profile", {}),
    )
    raw_scores = session_context.get("evaluation_scores", session_state.get("evaluation_scores", []))
    evaluation_scores: List[float] = []
    for score in raw_scores:
        if isinstance(score, (int, float)):
            evaluation_scores.append(float(score))
        elif isinstance(score, dict):
            value = score.get("overall_score", score.get("score"))
            if isinstance(value, (int, float)):
                evaluation_scores.append(float(value))

    contradictions: List[str] = []
    missing_evidence: List[str] = []

    proposed_score = proposed_output.get("decision", {}).get("confidence") or \
        proposed_output.get("payload", {}).get("score")
    if proposed_score is not None and evaluation_scores:
        prior_avg = sum(evaluation_scores) / len(evaluation_scores)
        delta = abs(proposed_score - prior_avg)
        if delta > 0.3:
            contradictions.append(
                f"Proposed score {proposed_score:.2f} deviates from prior average "
                f"{prior_avg:.2f} by {delta:.2f} ; verify scoring criteria."
            )

    source_agent = proposed_output.get("source_agent", "")
    role_sensitive = {"evaluator", "question_generator", "devils_advocate", "career_coach"}
    if any(name in source_agent for name in role_sensitive):
        if not job_research:
            missing_evidence.append(
                "Output is from a role-sensitive agent but job_research is absent in session context."
            )
        if not candidate_profile:
            missing_evidence.append(
                "Output is from a role-sensitive agent but candidate_profile is absent in session context."
            )

    if "evaluator" in source_agent and not conversation_history:
        missing_evidence.append(
            "Evaluator output present but conversation_history is empty ; no answered questions to evaluate."
        )
    #additional checks
    if contradictions or missing_evidence:
        recommendation = "revise"
        confidence = 0.4 if (contradictions and missing_evidence) else 0.6
        reasoning_summary = (
            f"Found {len(contradictions)} contradiction(s) and "
            f"{len(missing_evidence)} missing evidence item(s). Recommend revision."
        )
        next_tool = "helper_expert_review"
    else:
        recommendation = "accept"
        confidence = 0.85
        reasoning_summary = (
            "No contradictions or missing evidence detected. "
            "Output is consistent with session history."
        )
        next_tool = "none"

    return {
        "schema_version": "1.0",
        "request_id": request.get("request_id", ""),
        "session_id": request.get("session_id", ""),
        "source_agent": "helper_consistency_review",
        "target": "main",
        "message_type": "consistency_review",
        "status": "ok",
        "payload": {
            "contradictions": contradictions,
            "missing_evidence": missing_evidence,
            "recommendation": recommendation,
        },
        "decision": {
            "action": "check_consistency",
            "reasoning_summary": reasoning_summary,
            "tools_considered": ["global_vector_memory", "session_context"],
            "tools_used": ["session_context"],
            "confidence": confidence,
            "next_recommended_tool": next_tool,
        },
    }
