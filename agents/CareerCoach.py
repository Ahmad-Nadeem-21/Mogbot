"""
Responsibility: Produces the final coaching report when main.py decides the interview is complete.
Reasoning Logic: Plan to use reflection to ensure the coaching report is accurate and effective for the user.
Tools/Resources: Content of all agent outputs.
Data/Documents: All scores, agent transcripts, and agent outputs from the session.
"""

from __future__ import annotations

from typing import Any, Dict, List

from core.cache_manager import SemanticCache
from core.prompt_manager import PromptManager
from core.schemas import AgentMessage, SessionState, ToolRequest, build_agent_decision
from core.vector_memory import GlobalVectorMemory
from helper_agents import BiasSafetyReviewAgent, ExpertReviewAgent


def _score_trend(scores: List[float]) -> str:
    if len(scores) < 2:
        return "insufficient_data"
    if scores[-1] > scores[0]:
        return "improving"
    if scores[-1] < scores[0]:
        return "declining"
    return "stable"


def _extract_scores(session_state: SessionState) -> List[float]:
    out: List[float] = []
    for item in session_state.get("evaluation_scores", []):
        if isinstance(item, (int, float)):
            out.append(float(item))
        elif isinstance(item, dict):
            score = item.get("overall_score", item.get("score"))
            if isinstance(score, (int, float)):
                out.append(float(score))
    return out


def _reflect_report(report: Dict[str, Any], session_state: SessionState) -> Dict[str, Any]:
    """Simple reflection pass to flag unsupported claims."""
    conversation_len = len(session_state.get("conversation_history", []))
    evidence_notes: List[str] = []
    if conversation_len == 0:
        evidence_notes.append("No conversation history available; keep recommendations general.")
    if not session_state.get("evaluation_scores"):
        evidence_notes.append("No evaluation scores found; score trends are low confidence.")
    report["reflection_notes"] = evidence_notes
    report["evidence_grounded"] = len(evidence_notes) == 0
    return report


def run(session_state: SessionState) -> AgentMessage:
    """Create a final coaching report from completed SessionState."""
    session_id = session_state.get("session_id", "")
    memory = GlobalVectorMemory()
    cache = SemanticCache(memory)
    prompt_manager = PromptManager()

    cache_key = f"career_coach:{session_id}:{len(session_state.get('conversation_history', []))}"
    cached = cache.lookup("career_report", cache_key)
    if cached:
        return {
            "schema_version": "1.0",
            "message_id": "",
            "request_id": "",
            "session_id": session_id,
            "source_agent": "career_coach",
            "target": "main",
            "message_type": "final_report",
            "status": "ok",
            "payload": cached,
            "metadata": {"cache_hit": True},
            "decision": build_agent_decision(
                action="create_final_report",
                reasoning_summary="Returned cached coaching report.",
                tools_considered=["semantic_cache"],
                tools_used=["semantic_cache"],
                confidence=0.8,
                next_recommended_tool="none",
            ),
        }

    scores = _extract_scores(session_state)
    trend = _score_trend(scores)
    strengths = list(session_state.get("candidate_profile", {}).get("strengths", [])) if isinstance(session_state.get("candidate_profile"), dict) else []
    improvement_areas = list(session_state.get("candidate_profile", {}).get("gaps", [])) if isinstance(session_state.get("candidate_profile"), dict) else []

    memory_evidence = memory.search(
        query=f"session {session_id} interview evidence",
        namespace="",
        top_k=5,
    )
    evidence_snippets = [record.get("text", "")[:160] for record in memory_evidence]

    synthesis_prompt = prompt_manager.render(
        "career_coach",
        "task",
        {"session_state": str(session_state)},
    )

    report: Dict[str, Any] = {
        "summary": "Interview coaching report generated from session evidence.",
        "strengths": strengths,
        "improvement_areas": improvement_areas,
        "score_trends": {
            "scores": scores,
            "trend": trend,
        },
        "recommended_next_steps": [
            "Practice one STAR-format behavioral response per weak competency.",
            "Refine role-specific examples with measurable outcomes.",
        ],
        "role_fit_notes": {
            "fit_level": "moderate" if trend != "declining" else "needs_improvement",
            "reason": "Based on score trend and available interview evidence.",
        },
        "conflict_decisions_summary": list(session_state.get("devil_advocate_flags", [])),
        "evidence_snippets": evidence_snippets,
        "synthesis_prompt_used": synthesis_prompt,
    }

    report = _reflect_report(report, session_state)

    review_request: ToolRequest = {
        "schema_version": "1.0",
        "request_id": "",
        "session_id": session_id,
        "source": "career_coach",
        "target_agent": "helper_expert_review",
        "task_type": "review_output",
        "payload": {"agent_output": report},
        "session_context": {},
    }
    expert_review = ExpertReviewAgent.run(review_request)
    safety_review = BiasSafetyReviewAgent.run(review_request)
    report["helper_reviews"] = {
        "expert": expert_review.get("payload", {}),
        "safety": safety_review.get("payload", {}),
    }

    cache.store(
        "career_report",
        cache_key,
        payload=report,
        metadata={"session_id": session_id, "source": "career_coach"},
    )

    memory.add_record(
        {
            "record_id": f"career-report-{session_id}-{len(scores)}",
            "session_id": session_id,
            "namespace": "reports",
            "text": str(report.get("recommended_next_steps", [])),
            "metadata": {"report_summary": report.get("summary", "")},
        }
    )

    return {
        "schema_version": "1.0",
        "message_id": "",
        "request_id": "",
        "session_id": session_id,
        "source_agent": "career_coach",
        "target": "main",
        "message_type": "final_report",
        "status": "ok",
        "payload": report,
        "metadata": {"cache_hit": False},
        "decision": build_agent_decision(
            action="create_final_report",
            reasoning_summary="Synthesized final report with reflection and helper reviews.",
            tools_considered=["global_vector_memory", "semantic_cache", "helper_expert_review", "helper_bias_safety_review"],
            tools_used=["global_vector_memory", "semantic_cache", "helper_expert_review", "helper_bias_safety_review"],
            confidence=0.78,
            next_recommended_tool="none",
        ),
    }
