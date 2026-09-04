"""Integration tests for each agent's Milestone 7 LLM path.

Mocks the Anthropic client so these run with no real API key or network
access, but exercise each agent's `_run_llm` path end-to-end - proving the
wiring (prompt rendering, tool schema, response mapping) is correct before
a real ANTHROPIC_API_KEY is ever configured.
"""

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents import CareerCoach, DevilsAdvocate, Evaluator, Interviewer, JobSearchAgent, QuestionGenerator, ResumeAndRoleAnalyzer


def _tool_use_response(input_payload):
    block = SimpleNamespace(type="tool_use", input=input_payload)
    return SimpleNamespace(content=[block])


def _mock_anthropic(tool_input):
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _tool_use_response(tool_input)
    return patch("anthropic.Anthropic", return_value=mock_client), mock_client


@pytest.fixture(autouse=True)
def _configured_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")


def test_job_search_agent_llm_path():
    patcher, mock_client = _mock_anthropic({
        "role_title": "Senior Backend Engineer",
        "company_context": "Acme Corp",
        "required_skills": ["python", "sql"],
        "responsibilities": ["Build APIs"],
        "seniority_level": "senior",
        "interview_focus_areas": ["system design"],
        "reflection_passed": True,
        "confidence": 0.9,
        "reasoning_summary": "Extracted role details from the job description.",
    })
    with patcher:
        result = JobSearchAgent.run({"job_description": "We need a senior backend engineer at Acme."})

    assert result["status"] == "success"
    assert result["payload"]["role_title"] == "Senior Backend Engineer"
    assert "anthropic_llm" in result["decision"]["tools_used"]
    mock_client.messages.create.assert_called_once()


def test_resume_analyzer_llm_path():
    patcher, _ = _mock_anthropic({
        "skills": ["python", "docker"],
        "experience_highlights": ["Led a team of 4 engineers."],
        "seniority_level": "senior",
        "reflection_passed": True,
        "confidence": 0.85,
        "reasoning_summary": "Extracted skills and experience from resume.",
    })
    with patcher:
        result = ResumeAndRoleAnalyzer.run({"resume_text": "Senior engineer with 8 years experience."})

    assert result["status"] == "success"
    assert result["payload"]["skills"] == ["python", "docker"]
    assert "anthropic_llm" in result["decision"]["tools_used"]


def test_question_generator_llm_path():
    question_item = {"text": "Tell me about a challenge you solved.", "difficulty": "medium", "skill_tags": ["general"]}
    patcher, _ = _mock_anthropic({
        "phone_screen": [question_item],
        "behavioral": [question_item],
        "technical": [question_item],
        "difficulty_level": "medium",
        "reflection_passed": True,
        "confidence": 0.8,
        "reasoning_summary": "Generated a staged question plan.",
    })
    with patcher:
        result = QuestionGenerator.run({"role_title": "Backend Engineer", "keywords": ["python"]})

    assert result["status"] == "success"
    assert len(result["payload"]["phone_screen"]) == 1
    assert result["payload"]["phone_screen"][0]["question_id"]  # a real uuid was assigned
    assert "anthropic_llm" in result["decision"]["tools_used"]


def test_evaluator_llm_path():
    patcher, _ = _mock_anthropic({
        "overall_score": 88,
        "rubric_scores": [{"category": "relevance", "score": 88, "rationale": "Directly answers the question."}],
        "confidence": 0.9,
        "needs_followup": False,
        "evaluator_comment": "Strong, specific answer.",
        "reasoning_summary": "Scored against the rubric.",
    })
    with patcher:
        result = Evaluator.run({"answer_text": "I led a caching project that cut latency by 40%.", "question": "Describe a challenge."})

    assert result["message_type"] == "evaluation_result"
    assert result["payload"]["overall_score"] == 88
    assert result["payload"]["acceptable"] is True


def test_devils_advocate_llm_path_challenges():
    patcher, _ = _mock_anthropic({
        "should_challenge": True,
        "challenge_question": "Can you quantify the impact with a specific metric?",
        "reason": "Answer lacked concrete evidence.",
        "severity": "medium",
        "reasoning_summary": "Answer needed more specificity.",
        "confidence": 0.75,
    })
    with patcher:
        result = DevilsAdvocate.run({"needs_followup": True, "answer_text": "It went well."})

    assert result["message_type"] == "challenge_prompt"
    assert result["payload"]["challenge_question"]


def test_devils_advocate_llm_path_no_challenge():
    patcher, _ = _mock_anthropic({
        "should_challenge": False,
        "reason": "Answer was specific and well-supported.",
        "reasoning_summary": "No weakness found.",
        "confidence": 0.9,
    })
    with patcher:
        result = DevilsAdvocate.run({"acceptable": False, "score": 60, "answer_text": "Detailed, evidenced answer."})

    assert result["message_type"] == "no_challenge"


def test_interviewer_llm_path():
    patcher, _ = _mock_anthropic({
        "recommended_action": "continue",
        "suggested_prompt": "Thanks, let's move on.",
        "reason": "Answer was sufficiently detailed.",
        "tone": "neutral",
        "should_continue": True,
        "confidence": 0.8,
    })
    with patcher:
        result = Interviewer.run({"answer_text": "A detailed, well-structured answer."})

    assert result["payload"]["recommended_action"] == "continue"


def test_career_coach_llm_path():
    patcher, _ = _mock_anthropic({
        "summary": "Candidate showed strong technical depth.",
        "strengths": ["Clear communication"],
        "improvement_areas": ["More quantified outcomes"],
        "recommended_next_steps": ["Practice STAR-format answers"],
        "role_fit_level": "strong",
        "role_fit_reason": "Consistent high scores across technical questions.",
        "reasoning_summary": "Synthesized report from transcript and scores.",
        "confidence": 0.85,
    })
    session_state = {
        "session_id": "test-session",
        "conversation_history": [{"question": "Q1", "answer_text": "A1"}],
        "evaluation_scores": [{"overall_score": 85}],
    }
    with patcher:
        result = CareerCoach.run(session_state)

    assert result["payload"]["summary"] == "Candidate showed strong technical depth."
    assert result["payload"]["generated_by"] == "anthropic_llm"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
