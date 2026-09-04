"""
Responsibility: Scores each answer in real time and returns the score to main.py so main.py can decide which tool to call next.
Reasoning Logic: Uses reflection to ensure scoring is accurate. Borderline scores get a second-pass re-check before returning.
Tools/Resources: Rubric definitions, optional vector memory for similar labeled answers, optional helper-agent review.
Data/Documents: User answer from main.py, current question, job research, candidate profile, and role-specific evaluation rubrics.
"""

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core import llm_client
from core.prompt_manager import PromptManager
from core.vector_memory import GlobalVectorMemory

_PROMPT_MANAGER = PromptManager()

_LLM_TOOL_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "overall_score": {"type": "number", "minimum": 0, "maximum": 100},
        "rubric_scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "score": {"type": "number"},
                    "rationale": {"type": "string"},
                },
                "required": ["category", "score", "rationale"],
            },
        },
        "strengths": {"type": "array", "items": {"type": "string"}},
        "weaknesses": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "needs_followup": {"type": "boolean"},
        "evaluator_comment": {"type": "string"},
        "reasoning_summary": {"type": "string"},
    },
    "required": [
        "overall_score", "rubric_scores", "confidence", "needs_followup",
        "evaluator_comment", "reasoning_summary",
    ],
}


@dataclass
class RubricCategory:
    """Weights and descriptions for one scoring dimension."""
    name: str
    weight: float
    description: str


@dataclass
class RubricResult:
    """Score (0-100) and rationale for a single rubric category."""
    category: str
    score: float
    rationale: str


@dataclass
class EvaluationPayload:
    """Full scoring output returned inside an AgentMessage payload."""
    question_id: Optional[str]
    answer_text: str
    overall_score: float
    rubric_scores: List[Dict[str, Any]]
    strengths: List[str]
    weaknesses: List[str]
    evidence: List[str]
    confidence: float
    needs_followup: bool
    evaluator_comment: str
    reward_signal: float
    acceptable: bool


DEFAULT_RUBRIC: List[RubricCategory] = [
    RubricCategory("relevance", 0.25, "Does the answer directly address the question?"),
    RubricCategory("technical_accuracy", 0.25, "Are the facts, concepts, or methods stated correctly?"),
    RubricCategory("specificity", 0.20, "Does the answer include concrete details, numbers, or examples?"),
    RubricCategory("communication", 0.15, "Is the answer clear, well-structured, and easy to follow?"),
    RubricCategory("STAR_structure", 0.15, "For behavioral answers: does it follow Situation-Task-Action-Result?"),
]

FOLLOWUP_THRESHOLD = 75
BORDERLINE_BAND = 8

def _get_rubric(rubric: Optional[List[Dict[str, Any]]]) -> List[RubricCategory]:
    """Return caller-supplied rubric or the default one."""
    if not rubric:
        return DEFAULT_RUBRIC
    result = []
    for item in rubric:
        result.append(RubricCategory(
            name=item.get("name", "unknown"),
            weight=float(item.get("weight", 0.0)),
            description=item.get("description", ""),
        ))
    return result


def _score_answer(answer: str, question: str, rubric: List[RubricCategory]) -> List[RubricResult]:
    """
    Heuristic scorer (no LLM dependency) - returns a RubricResult per category.

    The current implementation is deterministic so it works without an LLM.
    """
    results: List[RubricResult] = []
    answer_lower = answer.lower().strip()
    word_count = len(answer_lower.split())

    for cat in rubric:
        score: float
        rationale: str

        if cat.name == "relevance":
            q_words = set(question.lower().split())
            a_words = set(answer_lower.split())
            overlap = len(q_words & a_words) / max(len(q_words), 1)
            score = min(overlap * 200, 100)
            rationale = f"Keyword overlap with question: {overlap:.0%}"

        elif cat.name == "technical_accuracy":
            score = 65.0
            rationale = "Default technical score; no fact-checking backend is connected yet."

        elif cat.name == "specificity":
            if word_count >= 80:
                score = 90.0
            elif word_count >= 40:
                score = 70.0
            elif word_count >= 15:
                score = 50.0
            else:
                score = 25.0
            rationale = f"Answer length: {word_count} words."

        elif cat.name == "communication":
            has_structure = any(kw in answer_lower for kw in ("first", "then", "finally", "because", "therefore", "however"))
            score = 75.0 if has_structure else 50.0
            rationale = "Structural connectors detected." if has_structure else "No structural connectors found."

        elif cat.name == "STAR_structure":
            star_hits = sum(1 for kw in ("situation", "task", "action", "result") if kw in answer_lower)
            score = star_hits * 25.0
            rationale = f"{star_hits}/4 STAR keywords found."

        else:
            score = 50.0
            rationale = "No heuristic defined for this category."

        results.append(RubricResult(category=cat.name, score=round(score, 1), rationale=rationale))

    return results


def _weighted_score(rubric: List[RubricCategory], results: List[RubricResult]) -> float:
    """Compute weighted average overall score (0-100)."""
    total = 0.0
    for cat, res in zip(rubric, results):
        total += cat.weight * res.score
    return round(total, 1)


def _extract_strengths_weaknesses(results: List[RubricResult]) -> tuple[List[str], List[str]]:
    strengths = [f"{r.category}: {r.rationale}" for r in results if r.score >= 70]
    weaknesses = [f"{r.category}: {r.rationale}" for r in results if r.score < 70]
    return strengths, weaknesses


def _reflection_pass(
    answer: str,
    question: str,
    rubric: List[RubricCategory],
    first_results: List[RubricResult],
    first_score: float,
) -> tuple[List[RubricResult], float]:
    """
    EVAL-04: Re-score the answer if the score is in the borderline band.
    Returns the averaged results and score to reduce scoring variance.
    """
    second_results = _score_answer(answer, question, rubric)
    second_score = _weighted_score(rubric, second_results)

    averaged: List[RubricResult] = []
    for r1, r2 in zip(first_results, second_results):
        avg_score = round((r1.score + r2.score) / 2, 1)
        averaged.append(RubricResult(
            category=r1.category,
            score=avg_score,
            rationale=f"[avg of 2 passes] {r1.rationale}",
        ))
    averaged_overall = round((first_score + second_score) / 2, 1)
    return averaged, averaged_overall


def _compute_confidence(rubric_results: List[RubricResult]) -> float:
    """
    Confidence is high when scores are consistent across categories.
    Returns 0.0-1.0.
    """
    if not rubric_results:
        return 0.5
    scores = [r.score for r in rubric_results]
    mean = sum(scores) / len(scores)
    variance = sum((s - mean) ** 2 for s in scores) / len(scores)

    confidence = max(0.0, 1.0 - (variance / 2500))  # max useful variance
    return round(confidence, 2)


def _reward_signal(overall_score: float) -> float:
    """EVAL-07: Normalise the score to a 0-1 reward for the interview loop."""
    return round(max(0.0, min(1.0, overall_score / 100)), 4)

def run(
    user_response_message: Dict[str, Any],
    rubric: Optional[List[Dict[str, Any]]] = None,
    session_context: Optional[Dict[str, Any]] = None,
    vector_memory: Optional[GlobalVectorMemory] = None,
) -> Dict[str, Any]:
    """Score a candidate answer and return an evaluation_result AgentMessage.

    Uses a real Anthropic call when ANTHROPIC_API_KEY is configured; falls
    back to the deterministic rubric scorer below otherwise or on any API
    failure. See ACTION_PLAN.md Milestone 7.
    """
    if llm_client.is_configured():
        try:
            return _run_llm(user_response_message, rubric, session_context, vector_memory)
        except Exception as exc:
            print(f"[Evaluator] LLM path failed ({exc}); falling back to heuristic.")
    return _run_heuristic(user_response_message, rubric, session_context, vector_memory)


def _run_llm(
    user_response_message: Dict[str, Any],
    rubric: Optional[List[Dict[str, Any]]],
    session_context: Optional[Dict[str, Any]],
    vector_memory: Optional[GlobalVectorMemory],
) -> Dict[str, Any]:
    if not user_response_message:
        return {
            "message_type": "evaluation_result",
            "payload": {"error": "No user_response_message provided.", "needs_followup": True},
        }

    answer: str = user_response_message.get("answer_text", "").strip()
    question: str = user_response_message.get("question", "").strip()
    question_id: Optional[str] = user_response_message.get("question_id")

    if not answer:
        return {
            "message_type": "evaluation_result",
            "payload": {
                "question_id": question_id,
                "overall_score": 0,
                "needs_followup": True,
                "evaluator_comment": "Empty answer - no content to evaluate.",
                "acceptable": False,
                "reward_signal": 0.0,
            },
        }

    active_rubric = _get_rubric(rubric)
    answer_context = {
        "question": question,
        "answer_text": answer,
        "rubric": [{"name": c.name, "weight": c.weight, "description": c.description} for c in active_rubric],
    }

    system_prompt = _PROMPT_MANAGER.render("evaluator", "system", {})
    task_prompt = _PROMPT_MANAGER.render(
        "evaluator",
        "task",
        {"answer_context": str({**answer_context, "answer_text": llm_client.wrap_untrusted_content("answer_text", answer)})},
    )

    llm_output = llm_client.call_structured(
        system_prompt=system_prompt,
        user_prompt=task_prompt,
        tool_name="record_evaluation",
        tool_description="Record a structured rubric-based evaluation of a candidate's answer.",
        input_schema=_LLM_TOOL_SCHEMA,
    )

    overall = float(llm_output["overall_score"])
    needs_followup = bool(llm_output["needs_followup"])
    result_payload = {
        "question_id": question_id,
        "answer_text": answer,
        "overall_score": overall,
        "rubric_scores": llm_output["rubric_scores"],
        "strengths": llm_output.get("strengths", []),
        "weaknesses": llm_output.get("weaknesses", []),
        "evidence": llm_output.get("evidence", []),
        "confidence": float(llm_output["confidence"]),
        "needs_followup": needs_followup,
        "evaluator_comment": llm_output["evaluator_comment"],
        "reward_signal": _reward_signal(overall),
        "acceptable": not needs_followup,
    }

    if vector_memory is not None:
        vector_memory.add_record({
            "record_id": str(uuid.uuid4()),
            "session_id": str((session_context or {}).get("session_id", "")),
            "namespace": "rubric_examples",
            "text": f"Q: {question}\nA: {answer}",
            "metadata": result_payload,
        })

    return {"message_type": "evaluation_result", "payload": result_payload}


def _run_heuristic(
    user_response_message: Dict[str, Any],
    rubric: Optional[List[Dict[str, Any]]] = None,
    session_context: Optional[Dict[str, Any]] = None,
    vector_memory: Optional[GlobalVectorMemory] = None,
) -> Dict[str, Any]:
    """Deterministic rubric-heuristic fallback - see `run()` for when this is used.

    Parameters
    ----------
    user_response_message : dict
        Must contain at least:
          - answer_text  : str   - the candidate's answer
          - question     : str   - the interview question being answered
          - question_id  : str   - optional identifier
    rubric : list[dict], optional
        Each item: {"name": str, "weight": float, "description": str}.
        Defaults to DEFAULT_RUBRIC if omitted.
    session_context : dict, optional
        Carries job_research, candidate_profile, conversation_history, etc.
        Not used by the heuristic scorer today but forwarded in metadata.

    Returns
    -------
    dict
        AgentMessage with message_type="evaluation_result" and a full payload.
        Keys: overall_score, rubric_scores, strengths, weaknesses, evidence,
              confidence, needs_followup, evaluator_comment, reward_signal,
              acceptable.
    """
    if not user_response_message:
        return {
            "message_type": "evaluation_result",
            "payload": {"error": "No user_response_message provided.", "needs_followup": True},
        }

    answer: str = user_response_message.get("answer_text", "").strip()
    question: str = user_response_message.get("question", "").strip()
    question_id: Optional[str] = user_response_message.get("question_id")

    if not answer:
        return {
            "message_type": "evaluation_result",
            "payload": {
                "question_id": question_id,
                "overall_score": 0,
                "needs_followup": True,
                "evaluator_comment": "Empty answer - no content to evaluate.",
                "acceptable": False,
                "reward_signal": 0.0,
            },
        }

    active_rubric = _get_rubric(rubric)

    rubric_results = _score_answer(answer, question, active_rubric)
    overall = _weighted_score(active_rubric, rubric_results)

    if abs(overall - FOLLOWUP_THRESHOLD) <= BORDERLINE_BAND:
        rubric_results, overall = _reflection_pass(answer, question, active_rubric, rubric_results, overall)

    confidence = _compute_confidence(rubric_results)
    strengths, weaknesses = _extract_strengths_weaknesses(rubric_results)
    needs_followup = overall < FOLLOWUP_THRESHOLD
    acceptable = not needs_followup

    evidence = [f"{r.category} ({r.score}/100): {r.rationale}" for r in rubric_results]

    evaluator_comment = (
        "Answer meets the expected standard." if acceptable
        else f"Score {overall}/100 is below threshold {FOLLOWUP_THRESHOLD}. Weaknesses: {'; '.join(weaknesses) or 'none identified'}."
    )

    payload = EvaluationPayload(
        question_id=question_id,
        answer_text=answer,
        overall_score=overall,
        rubric_scores=[{"category": r.category, "score": r.score, "rationale": r.rationale} for r in rubric_results],
        strengths=strengths,
        weaknesses=[w.split(":")[0] for w in weaknesses],
        evidence=evidence,
        confidence=confidence,
        needs_followup=needs_followup,
        evaluator_comment=evaluator_comment,
        reward_signal=_reward_signal(overall),
        acceptable=acceptable,
    )

    result_payload = {
        "question_id": payload.question_id,
        "answer_text": payload.answer_text,
        "overall_score": payload.overall_score,
        "rubric_scores": payload.rubric_scores,
        "strengths": payload.strengths,
        "weaknesses": payload.weaknesses,
        "evidence": payload.evidence,
        "confidence": payload.confidence,
        "needs_followup": payload.needs_followup,
        "evaluator_comment": payload.evaluator_comment,
        "reward_signal": payload.reward_signal,
        "acceptable": payload.acceptable,
    }

    if vector_memory is not None:
        vector_memory.add_record({
            "record_id": str(uuid.uuid4()),
            "session_id": str((session_context or {}).get("session_id", "")),
            "namespace": "rubric_examples",
            "text": f"Q: {question}\nA: {answer}",
            "metadata": result_payload,
        })

    return {
        "message_type": "evaluation_result",
        "payload": result_payload,
    }
