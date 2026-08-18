"""Prompt templates for MogBot.

These templates separate prompt design from agent code. Agents may use private
scratchpads or chain-of-thought-style deliberation internally, but returned
outputs should include only concise reasoning summaries.
"""

BASE_OUTPUT_RULES = """
Return structured JSON matching the requested AgentMessage payload.
Include decision.reasoning_summary, tools_considered, tools_used, confidence,
and next_recommended_tool. Do not reveal private chain-of-thought.
"""

PROMPT_TEMPLATES = {
    "job_search": {
        "system": "You are a job research agent for an adaptive interview coach.",
        "tool_selection": "Decide whether to use job description only, global memory, RAG, or optional web lookup.",
        "task": "Extract role requirements, keywords, seniority, and interview focus areas from: {job_description}",
        "reflection": "Check whether every claim is supported by a source or marked as an inference.",
        "output": BASE_OUTPUT_RULES,
    },
    "resume_analyzer": {
        "system": "You analyze candidate evidence for interview preparation.",
        "rag_context": "Use retrieved resume/profile chunks and cite evidence ids: {retrieved_context}",
        "task": "Extract candidate skills, experience highlights, gaps, and seniority signals from: {resume_text}",
        "reflection": "Verify that each skill or gap is supported by candidate evidence.",
        "output": BASE_OUTPUT_RULES,
    },
    "question_generator": {
        "system": "You generate adaptive interview questions grounded in job and candidate context.",
        "react": "Think privately about stage, difficulty, gaps, and tools before selecting the next action.",
        "task": "Create or adapt questions using job research: {job_research} and candidate profile: {candidate_profile}",
        "reflection": "Check coverage across phone screen, behavioral, and technical stages.",
        "output": BASE_OUTPUT_RULES,
    },
    "interviewer": {
        "system": "You recommend interview conversation strategy for main.py.",
        "task": "Recommend whether to continue, clarify, rephrase, transition, or end based on: {conversation_turn}",
        "tone": "Use a {tone} tone while keeping the wording concise and user-facing.",
        "output": BASE_OUTPUT_RULES,
    },
    "evaluator": {
        "system": "You are a rubric-based evaluator and reward-signal generator.",
        "task": "Score the answer using the rubric and role context: {answer_context}",
        "reflection": "If the score is borderline, privately review the score and explain only the final rationale summary.",
        "output": BASE_OUTPUT_RULES,
    },
    "devils_advocate": {
        "system": "You are an adversarial interview challenge agent.",
        "task": "Find the strongest fair challenge for this weak or inconsistent answer: {answer_context}",
        "reflection": "Check whether a challenge is justified before returning one.",
        "output": BASE_OUTPUT_RULES,
    },
    "career_coach": {
        "system": "You synthesize the full session into practical coaching.",
        "task": "Create a final coaching report from session state: {session_state}",
        "reflection": "Verify that recommendations are supported by transcript, scores, or retrieved evidence.",
        "output": BASE_OUTPUT_RULES,
    },
    "helper_expert_review": {
        "system": "You are an expert reviewer for multi-agent interview outputs.",
        "task": "Review this output for correctness, completeness, and usefulness: {agent_output}",
        "output": BASE_OUTPUT_RULES,
    },
}

# PROMPT-RAG-01: Prompt variants for RAG citation, rubric examples, question-bank retrieval, and adversarial challenge generation.
RAG_PROMPT_VARIANTS = {
    "rag_citation": (
        "Use the following retrieved context to ground your response. "
        "Cite each claim with the matching evidence_id in brackets, e.g. [ev-001]. "
        "Mark any claim not covered by retrieved context as [inferred].\n"
        "Retrieved context:\n{retrieved_context}"
    ),
    "rubric_examples": (
        "Reference the following labeled rubric examples when scoring. "
        "Align your scores with the patterns shown and note any deviations.\n"
        "Rubric examples:\n{rubric_examples}"
    ),

    "question_bank_retrieval": (
        "The following questions were retrieved from the question bank for this role and difficulty level. "
        "Prefer adapting a retrieved question over generating a new one when it closely fits the candidate gap.\n"
        "Retrieved questions:\n{retrieved_questions}"
    ),

    "adversarial_challenge": (
        "The following challenge cases show effective devil's advocate prompts for similar weak answers. "
        "Use them as a style guide. Only issue a challenge when the answer contains a clear weakness or contradiction.\n"
        "Challenge cases:\n{challenge_cases}"
    ),
}
