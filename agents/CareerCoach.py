"""
Responsibility: Produces the final coaching report when main.py decides the interview is complete.
Reasoning Logic: Plan to use reflection to ensure the coaching report is accurate and effective for the user.
Tools/Resources: Content of all agent outputs.
Data/Documents: All scores, agent transcripts, and agent outputs from the session.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from core import llm_client
from core.cache_manager import SemanticCache
from core.prompt_manager import PromptManager
from core.schemas import AgentMessage, SessionState, ToolRequest, build_agent_decision
from core.vector_memory import GlobalVectorMemory
from helper_agents import BiasSafetyReviewAgent, ExpertReviewAgent

_LLM_TOOL_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "improvement_areas": {"type": "array", "items": {"type": "string"}},
        "recommended_next_steps": {"type": "array", "items": {"type": "string"}},
        "role_fit_level": {"type": "string", "enum": ["strong", "moderate", "needs_improvement"]},
        "role_fit_reason": {"type": "string"},
        "reasoning_summary": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": [
        "summary", "strengths", "improvement_areas", "recommended_next_steps",
        "role_fit_level", "role_fit_reason", "reasoning_summary", "confidence",
    ],
}


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


def _build_report_content(
    session_state: SessionState,
    scores: List[float],
    trend: str,
    evidence_snippets: List[str],
    prompt_manager: PromptManager,
) -> Tuple[Dict[str, Any], str, float, bool]:
    """Return (report core fields, reasoning_summary, confidence, used_llm).

    Uses a real Anthropic call when ANTHROPIC_API_KEY is configured; falls
    back to the deterministic synthesis below otherwise or on any API
    failure. See ACTION_PLAN.md Milestone 7.
    """
    if llm_client.is_configured():
        try:
            return _synthesize_via_llm(session_state, scores, trend, evidence_snippets, prompt_manager) + (True,)
        except Exception as exc:
            print(f"[CareerCoach] LLM path failed ({exc}); falling back to heuristic synthesis.")
    return _synthesize_heuristic(session_state, scores, trend) + (False,)


def _synthesize_via_llm(
    session_state: SessionState,
    scores: List[float],
    trend: str,
    evidence_snippets: List[str],
    prompt_manager: PromptManager,
) -> Tuple[Dict[str, Any], str, float]:
    transcript = [
        {"question": turn.get("question", ""), "answer": turn.get("answer_text", "")}
        for turn in session_state.get("conversation_history", [])
    ]
    synthesis_context = {
        "score_trend": trend,
        "scores": scores,
        "transcript": llm_client.wrap_untrusted_content("transcript", str(transcript)),
        "evidence_snippets": evidence_snippets,
        "devil_advocate_flags": session_state.get("devil_advocate_flags", []),
    }
    system_prompt = prompt_manager.render("career_coach", "system", {})
    task_prompt = prompt_manager.render("career_coach", "task", {"session_state": str(synthesis_context)})

    llm_output = llm_client.call_structured(
        system_prompt=system_prompt,
        user_prompt=task_prompt,
        tool_name="record_coaching_report",
        tool_description="Record a structured final interview coaching report.",
        input_schema=_LLM_TOOL_SCHEMA,
    )

    content = {
        "summary": llm_output["summary"],
        "strengths": llm_output["strengths"],
        "improvement_areas": llm_output["improvement_areas"],
        "recommended_next_steps": llm_output["recommended_next_steps"],
        "role_fit_level": llm_output["role_fit_level"],
        "role_fit_reason": llm_output["role_fit_reason"],
    }
    return content, llm_output["reasoning_summary"], float(llm_output["confidence"])


def _synthesize_heuristic(
    session_state: SessionState,
    scores: List[float],
    trend: str,
) -> Tuple[Dict[str, Any], str, float]:
    candidate_profile = session_state.get("candidate_profile", {})
    strengths = list(candidate_profile.get("strengths", [])) if isinstance(candidate_profile, dict) else []
    improvement_areas = list(candidate_profile.get("gaps", [])) if isinstance(candidate_profile, dict) else []

    content = {
        "summary": "Interview coaching report generated from session evidence.",
        "strengths": strengths,
        "improvement_areas": improvement_areas,
        "recommended_next_steps": [
            "Practice one STAR-format behavioral response per weak competency.",
            "Refine role-specific examples with measurable outcomes.",
        ],
        "role_fit_level": "moderate" if trend != "declining" else "needs_improvement",
        "role_fit_reason": "Based on score trend and available interview evidence.",
    }
    return content, "Synthesized final report with reflection and helper reviews.", 0.78


def run(
    session_state: SessionState,
    vector_memory: GlobalVectorMemory | None = None,
    cache: SemanticCache | None = None,
    prompt_manager: PromptManager | None = None,
) -> AgentMessage:
    """Create a final coaching report from completed SessionState.

    Callers should pass the shared `vector_memory`/`cache`/`prompt_manager`
    instances owned by main.py; falling back to fresh instances here would
    bypass the global memory lock and risk clobbering concurrent writes.
    """
    session_id = session_state.get("session_id", "")
    memory = vector_memory if vector_memory is not None else GlobalVectorMemory()
    cache = cache if cache is not None else SemanticCache(memory)
    prompt_manager = prompt_manager if prompt_manager is not None else PromptManager()

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

    memory_evidence = memory.search(
        query=f"session {session_id} interview evidence",
        namespace="",
        top_k=5,
    )
    evidence_snippets = [record.get("text", "")[:160] for record in memory_evidence]

    content, reasoning_summary, confidence, used_llm = _build_report_content(
        session_state, scores, trend, evidence_snippets, prompt_manager
    )

    report: Dict[str, Any] = {
        "summary": content["summary"],
        "strengths": content["strengths"],
        "improvement_areas": content["improvement_areas"],
        "score_trends": {
            "scores": scores,
            "trend": trend,
        },
        "recommended_next_steps": content["recommended_next_steps"],
        "role_fit_notes": {
            "fit_level": content["role_fit_level"],
            "reason": content["role_fit_reason"],
        },
        "conflict_decisions_summary": list(session_state.get("devil_advocate_flags", [])),
        "evidence_snippets": evidence_snippets,
        "generated_by": "anthropic_llm" if used_llm else "heuristic_synthesis",
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
            reasoning_summary=reasoning_summary,
            tools_considered=["global_vector_memory", "semantic_cache", "helper_expert_review", "helper_bias_safety_review", "anthropic_llm"],
            tools_used=[
                "global_vector_memory", "semantic_cache", "helper_expert_review", "helper_bias_safety_review",
                *(["anthropic_llm"] if used_llm else []),
            ],
            confidence=confidence,
            next_recommended_tool="none",
        ),
    }
