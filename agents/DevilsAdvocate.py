

from typing import Any, Dict, List, Optional


def _message(message_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"message_type": message_type, "payload": payload}


def _build_challenge(evaluation: Dict[str, Any]) -> Dict[str, Any]:
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
    return _message("challenge_prompt", payload)


def _no_challenge(evaluation: Dict[str, Any]) -> Dict[str, Any]:
    reason = evaluation.get("reason") or evaluation.get("evaluator_comment") or "Answer acceptable"
    return _message("no_challenge", {"reason": reason})


def run(evaluation_message: Dict[str, Any], conversation_history: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
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

    Returns a plain dict with message_type and payload.
    """
    if evaluation_message is None:
        return _no_challenge({"reason": "no evaluation provided"})

    needs_followup = bool(evaluation_message.get("needs_followup"))
    contradiction = bool(evaluation_message.get("contradiction_detected"))
    score = evaluation_message.get("score")

    threshold = 75

    if evaluation_message.get("acceptable") is True:
        return _no_challenge(evaluation_message)

    if needs_followup or contradiction:
        return _build_challenge(evaluation_message)

    if isinstance(score, (int, float)):
        if score < threshold:
            return _build_challenge(evaluation_message)
        return _no_challenge(evaluation_message)

    if evaluation_message.get("weakness") or evaluation_message.get("referenced_weakness"):
        return _build_challenge(evaluation_message)

    return _no_challenge(evaluation_message)
