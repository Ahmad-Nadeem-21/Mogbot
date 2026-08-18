import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agents.DevilsAdvocate import run


def test_challenge_on_needs_followup():
    msg = {"needs_followup": True, "question_id": "q1", "answer_text": "I think so."}
    result = run(msg)
    assert result["message_type"] == "challenge_prompt"
    assert "challenge_question" in result["payload"]


def test_challenge_on_contradiction():
    msg = {"contradiction_detected": True, "answer_text": "Always true.", "score": 80}
    result = run(msg)
    assert result["message_type"] == "challenge_prompt"


def test_challenge_on_low_score():
    msg = {"score": 55, "answer_text": "Somewhat.", "evaluator_comment": "Too vague."}
    result = run(msg)
    assert result["message_type"] == "challenge_prompt"
    assert result["payload"]["severity"] == "medium"


def test_challenge_on_very_low_score_severity_high():
    msg = {"score": 30, "answer_text": "Maybe.", "weakness": "No evidence provided."}
    result = run(msg)
    assert result["message_type"] == "challenge_prompt"
    assert result["payload"]["severity"] == "high"


def test_challenge_on_weakness_flag_no_score():
    msg = {"weakness": "Missing quantitative data."}
    result = run(msg)
    assert result["message_type"] == "challenge_prompt"


def test_challenge_on_referenced_weakness():
    msg = {"referenced_weakness": "Assumption not backed up."}
    result = run(msg)
    assert result["message_type"] == "challenge_prompt"



def test_no_challenge_on_acceptable_true():
    msg = {"acceptable": True, "score": 40}  # score is low but acceptable overrides
    result = run(msg)
    assert result["message_type"] == "no_challenge"


def test_no_challenge_on_high_score():
    msg = {"score": 90, "answer_text": "Detailed answer with evidence."}
    result = run(msg)
    assert result["message_type"] == "no_challenge"


def test_no_challenge_on_score_at_threshold():
    msg = {"score": 75, "answer_text": "Good answer."}
    result = run(msg)
    assert result["message_type"] == "no_challenge"


def test_no_challenge_on_none_input():
    result = run(None)
    assert result["message_type"] == "no_challenge"
    assert "reason" in result["payload"]


def test_no_challenge_on_empty_dict():
    result = run({})
    assert result["message_type"] == "no_challenge"


# Payload content

def test_challenge_payload_includes_question_id():
    msg = {"needs_followup": True, "original_question_id": "q42", "answer_text": "Not sure."}
    result = run(msg)
    assert result["payload"]["original_question_id"] == "q42"


def test_challenge_question_includes_answer_excerpt():
    msg = {"score": 20, "answer_excerpt": "I always succeed."}
    result = run(msg)
    assert "I always succeed." in result["payload"]["challenge_question"]


def test_no_challenge_reason_populated():
    msg = {"score": 85, "evaluator_comment": "Well reasoned."}
    result = run(msg)
    assert result["payload"]["reason"] == "Well reasoned."


def test_challenge_reason_falls_back_to_default():
    msg = {"score": 10}
    result = run(msg)
    assert result["payload"]["reason_for_challenge"]  # non-empty



def test_run_accepts_conversation_history():
    history = [{"role": "user", "content": "Tell me about yourself."}]
    msg = {"score": 50}
    result = run(msg, conversation_history=history)
    assert result["message_type"] == "challenge_prompt"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
