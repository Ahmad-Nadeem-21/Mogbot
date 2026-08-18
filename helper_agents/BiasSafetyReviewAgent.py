"""Bias and safety review helper agent."""

from __future__ import annotations

from typing import Any, Dict, List

from core.schemas import AgentMessage, ToolRequest, build_agent_decision

_SENSITIVE_TERMS = {"race", "religion", "gender", "ethnicity", "politics", "age"}
_HARSH_TERMS = {"stupid", "dumb", "lazy", "useless"}


def _scan_text(text: str) -> List[str]:
    lower = text.lower()
    flags: List[str] = []
    if any(term in lower for term in _SENSITIVE_TERMS):
        flags.append("Possible unsupported sensitive inference.")
    if any(term in lower for term in _HARSH_TERMS):
        flags.append("Potentially harsh or unprofessional tone.")
    if "ssn" in lower or "social security" in lower:
        flags.append("Potential privacy-risky personal information.")
    return flags


def run(request: ToolRequest) -> AgentMessage:
    """Review outputs for fairness, privacy, and tone risks."""
    payload: Dict[str, Any] = request.get("payload", {})
    agent_output = payload.get("agent_output", {}) if isinstance(payload, dict) else {}
    text_blob = str(agent_output)
    flags = _scan_text(text_blob)
    safe = not flags

    return {
        "schema_version": request.get("schema_version", "1.0"),
        "request_id": request.get("request_id", ""),
        "session_id": request.get("session_id", ""),
        "source_agent": "helper_bias_safety_review",
        "target": "main",
        "message_type": "bias_safety_review",
        "status": "ok",
        "payload": {
            "safe": safe,
            "flags": flags,
            "suggested_revision": "No changes needed." if safe else "Remove sensitive/harsh wording and keep feedback job-relevant.",
        },
        "decision": build_agent_decision(
            action="check_bias_safety",
            reasoning_summary="Bias/safety helper scanned output for sensitive inferences and tone risks.",
            tools_considered=["safety_prompt_template", "global_vector_memory"],
            tools_used=[],
            confidence=0.9 if safe else 0.65,
            next_recommended_tool="none" if safe else "helper_expert_review",
        ),
    }
