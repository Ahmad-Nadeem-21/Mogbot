

import uuid
from typing import Any, Dict, List, Optional

from core import llm_client
from core.prompt_manager import PromptManager
from core.vector_memory import GlobalVectorMemory

_PROMPT_MANAGER = PromptManager()

_LLM_TOOL_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "should_challenge": {"type": "boolean"},
        "challenge_question": {"type": "string"},
        "reason": {"type": "string"},
        "severity": {"type": "string", "enum": ["low", "medium", "high"]},
        "reasoning_summary": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["should_challenge", "reason", "reasoning_summary", "confidence"],
}


def _message(message_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"message_type": message_type, "payload": payload}


def _build_challenge(
    evaluation: Dict[str, Any],
    vector_memory: Optional[GlobalVectorMemory] = None,
) -> Dict[str, Any]:
    qid = evaluation.get("original_question_id") or evaluation.get("question_id")
    weakness = evaluation.get("weakness") or evaluation.get("referenced_weakness")
    score = evaluation.get("score")
    severity = "low"
    if isinstance(score, (int, float)):
        if score < 40:
            severity = "high"
        elif score < 70:
            severity = "medium"

    base = evaluation.get("answer_excerpt") or evaluation.get("answer_text") or "the provided answer"
    challenge_question = (
        f'You claimed: "{base}" - please provide concrete evidence or a step-by-step justification,'
        " and address any assumptions made."
    )

    payload = {
        "original_question_id": qid,
        "challenge_question": challenge_question,
        "reason_for_challenge": evaluation.get("evaluator_comment")
        or evaluation.get("reason")
        or "low score / needs follow-up",
        "referenced_weakness": weakness,
        "severity": severity,
    }

    if vector_memory is not None:
        vector_memory.add_record({
            "record_id": str(uuid.uuid4()),
            "session_id": str(evaluation.get("session_id", "")),
            "namespace": "challenge_cases",
            "text": f"{base}\n{challenge_question}",
            "metadata": payload,
        })

    return _message("challenge_prompt", payload)


def _no_challenge(evaluation: Dict[str, Any]) -> Dict[str, Any]:
    reason = evaluation.get("reason") or evaluation.get("evaluator_comment") or "Answer acceptable"
    return _message("no_challenge", {"reason": reason})


def run(
    evaluation_message: Dict[str, Any],
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    vector_memory: Optional[GlobalVectorMemory] = None,
) -> Dict[str, Any]:
    """Decide whether to issue a challenge based on `evaluation_message`.

    Expected keys in evaluation_message (examples):
      - needs_followup: bool
      - contradiction_detected: bool
      - score: int|float (0-100)
      - acceptable: bool
      - original_question_id / question_id
      - weakness / referenced_weakness
      - evaluator_comment / reason
      - answer_text / answer_excerpt

    Returns a plain dict with message_type and payload. Uses a real
    Anthropic call when ANTHROPIC_API_KEY is configured; falls back to the
    deterministic threshold logic below otherwise or on any API failure.
    See ACTION_PLAN.md Milestone 7.
    """
    if evaluation_message is None:
        return _no_challenge({"reason": "no evaluation provided"})

    if llm_client.is_configured():
        try:
            return _run_llm(evaluation_message, conversation_history, vector_memory)
        except Exception as exc:
            print(f"[DevilsAdvocate] LLM path failed ({exc}); falling back to heuristic.")
    return _run_heuristic(evaluation_message, conversation_history, vector_memory)


def _run_llm(
    evaluation_message: Dict[str, Any],
    conversation_history: Optional[List[Dict[str, Any]]],
    vector_memory: Optional[GlobalVectorMemory],
) -> Dict[str, Any]:
    answer_context = {
        "answer_text": llm_client.wrap_untrusted_content(
            "answer_text", str(evaluation_message.get("answer_text") or evaluation_message.get("answer_excerpt") or "")
        ),
        "score": evaluation_message.get("score"),
        "needs_followup": evaluation_message.get("needs_followup"),
        "evaluator_comment": evaluation_message.get("evaluator_comment") or evaluation_message.get("reason"),
        "weakness": evaluation_message.get("weakness") or evaluation_message.get("referenced_weakness"),
    }
    system_prompt = _PROMPT_MANAGER.render("devils_advocate", "system", {})
    task_prompt = _PROMPT_MANAGER.render("devils_advocate", "task", {"answer_context": str(answer_context)})

    llm_output = llm_client.call_structured(
        system_prompt=system_prompt,
        user_prompt=task_prompt,
        tool_name="record_challenge_decision",
        tool_description="Decide whether to issue an interview challenge and, if so, what to ask.",
        input_schema=_LLM_TOOL_SCHEMA,
    )

    if not llm_output["should_challenge"]:
        return _no_challenge({"reason": llm_output["reason"]})

    payload = {
        "original_question_id": evaluation_message.get("original_question_id") or evaluation_message.get("question_id"),
        "challenge_question": llm_output.get("challenge_question", ""),
        "reason_for_challenge": llm_output["reason"],
        "referenced_weakness": evaluation_message.get("weakness") or evaluation_message.get("referenced_weakness"),
        "severity": llm_output.get("severity", "medium"),
    }

    if vector_memory is not None:
        vector_memory.add_record({
            "record_id": str(uuid.uuid4()),
            "session_id": str(evaluation_message.get("session_id", "")),
            "namespace": "challenge_cases",
            "text": f"{answer_context['answer_text']}\n{payload['challenge_question']}",
            "metadata": payload,
        })

    return _message("challenge_prompt", payload)


def _run_heuristic(
    evaluation_message: Dict[str, Any],
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    vector_memory: Optional[GlobalVectorMemory] = None,
) -> Dict[str, Any]:
    """Deterministic threshold-based fallback - see `run()` for when this is used."""
    needs_followup = bool(evaluation_message.get("needs_followup"))
    contradiction = bool(evaluation_message.get("contradiction_detected"))
    score = evaluation_message.get("score")

    threshold = 75

    if evaluation_message.get("acceptable") is True:
        return _no_challenge(evaluation_message)

    if needs_followup or contradiction:
        return _build_challenge(evaluation_message, vector_memory)

    if isinstance(score, (int, float)):
        if score < threshold:
            return _build_challenge(evaluation_message, vector_memory)
        return _no_challenge(evaluation_message)

    if evaluation_message.get("weakness") or evaluation_message.get("referenced_weakness"):
        return _build_challenge(evaluation_message, vector_memory)

    return _no_challenge(evaluation_message)
