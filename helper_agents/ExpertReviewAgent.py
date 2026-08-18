"""Expert review helper agent.

This helper critiques important agent outputs before main.py accepts them into SessionState.
"""

from __future__ import annotations

from typing import Any, Dict, List

from core.schemas import AgentMessage, ToolRequest, build_agent_decision


def _collect_issues(agent_output: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    if not agent_output:
        issues.append("Output payload is empty.")
    decision = agent_output.get("decision")
    if not isinstance(decision, dict):
        issues.append("Missing structured decision metadata.")
    elif decision.get("confidence", 0.0) < 0.4:
        issues.append("Low decision confidence; consider review pass.")
    payload = agent_output.get("payload")
    if payload in ({}, None):
        issues.append("Output payload has no substantive content.")
    return issues


def run(request: ToolRequest) -> AgentMessage:
    """Review another agent output for quality and completeness."""
    candidate_output = request.get("payload", {}).get("agent_output", {})
    issues = _collect_issues(candidate_output if isinstance(candidate_output, dict) else {})
    score = max(0.0, 1.0 - 0.25 * len(issues))
    recommendation = "accept" if score >= 0.75 else "revise"
    suggested_fix = "Looks good." if not issues else "Address listed issues and rerun helper review."

    return {
        "schema_version": request.get("schema_version", "1.0"),
        "request_id": request.get("request_id", ""),
        "session_id": request.get("session_id", ""),
        "source_agent": "helper_expert_review",
        "target": "main",
        "message_type": "expert_review",
        "status": "ok",
        "payload": {
            "review_score": round(score, 2),
            "issues_found": issues,
            "suggested_fix": suggested_fix,
            "accept_reject_revise": recommendation,
        },
        "decision": build_agent_decision(
            action="review",
            reasoning_summary="Expert helper rated quality and recommended acceptance or revision.",
            tools_considered=["prompt_template", "global_vector_memory"],
            tools_used=[],
            confidence=round(score, 2),
            next_recommended_tool="none" if recommendation == "accept" else "helper_bias_safety_review",
        ),
    }
