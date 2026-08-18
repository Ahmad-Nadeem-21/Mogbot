"""
Responsibility: Uses job research and the candidate profile to dynamically generate a multiple-question bank: a phone screen stage, a behavioral stage (STAR-format questions targeting weak resume areas), and a technical stage (role-specific problems). Adapts question difficulty based on responses.
Reasoning Logic: Plan to use ReAct to generate well-thought-out questions that are based on previous answers.
Tools / Resources: Plan to use RAG for industry-related questions from different data sets. Difficulty can be adjusted based on the live score.
Data / Documents: Job research from JobSearchAgent, candidate profile from ResumeAndRoleAnalyzer, and role-related question banks.
"""

import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple




DIFFICULTY_LEVELS = ["easy", "medium", "hard"]

# avg_score >= HARD_THRESHOLD , then bump difficulty up
# avg_score <= EASY_THRESHOLD , thenbump difficulty down
HARD_THRESHOLD = 80.0
EASY_THRESHOLD = 50.0



# Each question is a dict:
#   id          - stable identifier
#   stage       - phone_screen | behavioral | technical
#   difficulty  - easy | medium | hard
#   skill_tags  - list of skill keywords this question targets
#   text        - the question text ({role}, {skill}, {gap} are substitution slots)


_PHONE_SCREEN_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "ps-001",
        "stage": "phone_screen",
        "difficulty": "easy",
        "skill_tags": ["general"],
        "text": "Can you walk me through your background and why you're interested in the {role} role?",
    },
    {
        "id": "ps-002",
        "stage": "phone_screen",
        "difficulty": "easy",
        "skill_tags": ["general"],
        "text": "What attracted you to {company} and this position specifically?",
    },
    {
        "id": "ps-003",
        "stage": "phone_screen",
        "difficulty": "easy",
        "skill_tags": ["general"],
        "text": "How would you describe your current level of experience with {skill}?",
    },
    {
        "id": "ps-004",
        "stage": "phone_screen",
        "difficulty": "medium",
        "skill_tags": ["general"],
        "text": "What does your ideal next role look like, and how does this {role} position fit that vision?",
    },
    {
        "id": "ps-005",
        "stage": "phone_screen",
        "difficulty": "easy",
        "skill_tags": ["general"],
        "text": "Are you comfortable with the seniority level and responsibilities of a {seniority} {role} position?",
    },
]

_BEHAVIORAL_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "beh-001",
        "stage": "behavioral",
        "difficulty": "medium",
        "skill_tags": ["leadership", "communication"],
        "text": "Tell me about a time you had to lead a project or initiative without formal authority. What was the situation, and what did you do?",
    },
    {
        "id": "beh-002",
        "stage": "behavioral",
        "difficulty": "medium",
        "skill_tags": ["problem_solving"],
        "text": "Describe a situation where you faced a significant technical challenge. How did you approach it, and what was the outcome?",
    },
    {
        "id": "beh-003",
        "stage": "behavioral",
        "difficulty": "medium",
        "skill_tags": ["collaboration", "communication"],
        "text": "Give me an example of a time you had a disagreement with a teammate or stakeholder. How did you resolve it?",
    },
    {
        "id": "beh-004",
        "stage": "behavioral",
        "difficulty": "hard",
        "skill_tags": ["leadership"],
        "text": "Tell me about a time you had to deliver difficult feedback to a colleague or report. How did you handle it?",
    },
    {
        "id": "beh-005",
        "stage": "behavioral",
        "difficulty": "medium",
        "skill_tags": ["adaptability"],
        "text": "Describe a situation where requirements changed significantly mid-project. How did you adapt?",
    },
    {
        "id": "beh-006",
        "stage": "behavioral",
        "difficulty": "hard",
        "skill_tags": ["problem_solving", "ownership"],
        "text": "Tell me about the most complex system or feature you've built. Walk me through your decision-making process.",
    },
    {
        "id": "beh-gap-001",
        "stage": "behavioral",
        "difficulty": "medium",
        "skill_tags": ["gap_targeting"],
        "text": "Your profile suggests limited experience with {gap}. Can you walk me through any exposure you do have, and how you'd approach closing that gap?",
    },
]

_TECHNICAL_TEMPLATES: List[Dict[str, Any]] = [
    # basic technical
    {
        "id": "tech-001",
        "stage": "technical",
        "difficulty": "medium",
        "skill_tags": ["system_design"],
        "text": "How would you design a scalable REST API service for a high-traffic application? Walk me through your key decisions.",
    },
    {
        "id": "tech-002",
        "stage": "technical",
        "difficulty": "hard",
        "skill_tags": ["system_design"],
        "text": "Describe how you would architect a microservices system that needs to handle millions of events per day with low latency.",
    },
    {
        "id": "tech-003",
        "stage": "technical",
        "difficulty": "medium",
        "skill_tags": ["sql", "data_modeling"],
        "text": "Given a large relational database that is experiencing slow query performance, what steps would you take to diagnose and improve it?",
    },
    {
        "id": "tech-004",
        "stage": "technical",
        "difficulty": "medium",
        "skill_tags": ["devops", "docker", "kubernetes"],
        "text": "Walk me through how you would containerise a Python service and deploy it to a Kubernetes cluster, including how you'd handle configuration and secrets.",
    },
    {
        "id": "tech-005",
        "stage": "technical",
        "difficulty": "hard",
        "skill_tags": ["cloud", "aws", "gcp", "azure"],
        "text": "How would you design a fault-tolerant, cloud-native data pipeline that ingests and processes real-time streaming data?",
    },
    {
        "id": "tech-006",
        "stage": "technical",
        "difficulty": "medium",
        "skill_tags": ["python"],
        "text": "Explain the difference between Python's threading and multiprocessing modules. When would you choose one over the other?",
    },
    {
        "id": "tech-007",
        "stage": "technical",
        "difficulty": "hard",
        "skill_tags": ["machine_learning", "ml"],
        "text": "Describe how you would design and evaluate an ML pipeline for a production recommendation system. What metrics and monitoring would you put in place?",
    },
    {
        "id": "tech-008",
        "stage": "technical",
        "difficulty": "medium",
        "skill_tags": ["nosql", "mongodb", "redis", "elasticsearch"],
        "text": "When would you choose a NoSQL database over a relational one, and what trade-offs does that introduce?",
    },
    {
        "id": "tech-skill-001",
        "stage": "technical",
        "difficulty": "medium",
        "skill_tags": ["role_specific"],
        "text": "The {role} role specifically calls out {skill} as a requirement. Can you walk me through a project where you used it in depth?",
    },
    {
        "id": "tech-skill-002",
        "stage": "technical",
        "difficulty": "hard",
        "skill_tags": ["role_specific"],
        "text": "If you had to improve the performance of a production {skill} system by 3x, what would your investigation and optimisation process look like?",
    },
]

_ALL_TEMPLATES: List[Dict[str, Any]] = (
    _PHONE_SCREEN_TEMPLATES + _BEHAVIORAL_TEMPLATES + _TECHNICAL_TEMPLATES
)


def _avg_recent_score(session_state: Optional[Dict[str, Any]], n: int = 3) -> Optional[float]:
    """Return the average of the last `n` evaluator scores, or None if unavailable."""
    if not session_state:
        return None
    scores = session_state.get("evaluation_scores", [])
    if not scores:
        return None
    recent = scores[-n:]
    numeric = [s for s in recent if isinstance(s, (int, float))]
    if not numeric:
        return None
    return sum(numeric) / len(numeric)


def _resolve_difficulty(
    base_difficulty: str,
    avg_score: Optional[float],
) -> str:
    """QG-03 / QG-10: Adjust difficulty based on recent evaluator scores."""
    if avg_score is None:
        return base_difficulty
    idx = DIFFICULTY_LEVELS.index(base_difficulty)
    if avg_score >= HARD_THRESHOLD and idx < len(DIFFICULTY_LEVELS) - 1:
        return DIFFICULTY_LEVELS[idx + 1]
    if avg_score <= EASY_THRESHOLD and idx > 0:
        return DIFFICULTY_LEVELS[idx - 1]
    return base_difficulty


def _extract_top_skill(job_research: Dict[str, Any]) -> str:
    """Return the most prominent required skill from job research."""
    required = job_research.get("required_skills", [])
    keywords = job_research.get("keywords", [])
    if required:
        first = required[0].lower()
        for kw in keywords:
            if kw in first:
                return kw
        return required[0]
    if keywords:
        return keywords[0]
    return "core technology"


def _extract_top_gap(candidate_profile: Dict[str, Any]) -> Optional[str]:
    """Return the most significant candidate gap if available."""
    gaps = candidate_profile.get("missing_keywords", [])
    if gaps:
        return gaps[0]
    risk = candidate_profile.get("risk_notes", [])
    if risk:
        return risk[0]
    return None


def _fill_slots(text: str, slots: Dict[str, str]) -> str:
    """Replace {slot} placeholders in a question template."""
    for key, value in slots.items():
        text = text.replace("{" + key + "}", value)
    return text


def _select_questions(
    stage: str,
    templates: List[Dict[str, Any]],
    target_difficulty: str,
    count: int,
    slots: Dict[str, str],
    focus_tags: List[str],
) -> List[Dict[str, Any]]:
    """
    Pick `count` questions from `templates` for the given stage.

    Selection priority:
      1. Exact difficulty + skill_tag overlap with focus_tags
      2. Exact difficulty (any skill_tags)
      3. Any difficulty (any skill_tags)
    """
    pool = [t for t in templates if t["stage"] == stage]

    def score(q: Dict[str, Any]) -> int:
        diff_match = 2 if q["difficulty"] == target_difficulty else 0
        tag_match = sum(1 for tag in q["skill_tags"] if tag in focus_tags)
        return diff_match + tag_match

    ranked = sorted(pool, key=score, reverse=True)
    selected = ranked[:count]

    result: List[Dict[str, Any]] = []
    for q in selected:
        filled = deepcopy(q)
        filled["text"] = _fill_slots(filled["text"], slots)
        filled["question_id"] = str(uuid.uuid4())
        result.append(filled)
    return result


def _build_slots(
    job_research: Dict[str, Any],
    candidate_profile: Dict[str, Any],
    top_skill: str,
    top_gap: Optional[str],
) -> Dict[str, str]:
    """Build the substitution slot map for question templates."""
    return {
        "role": job_research.get("role_title", "the role"),
        "company": job_research.get("company_context", "the company"),
        "seniority": job_research.get("seniority_level", "mid-level"),
        "skill": top_skill,
        "gap": top_gap or "areas outside your current experience",
    }


def _reflection_pass(
    phone_screen: List[Dict[str, Any]],
    behavioral: List[Dict[str, Any]],
    technical: List[Dict[str, Any]],
    targeted_gaps: List[str],
    job_requirements_covered: List[str],
) -> Tuple[bool, str]:
    """
    QG-09 reflection: verify that all three stages are populated and that
    at least one technical question covers a stated job requirement.
    """
    issues: List[str] = []

    if not phone_screen:
        issues.append("no phone_screen questions generated")
    if not behavioral:
        issues.append("no behavioral questions generated")
    if not technical:
        issues.append("no technical questions generated")

    #realte with requirement keywrd
    if job_requirements_covered and technical:
        req_text = " ".join(job_requirements_covered).lower()
        covered = any(
            any(word in q["text"].lower() for word in req_text.split())
            for q in technical
        )
        if not covered:
            issues.append(
                "technical questions may not directly reference job requirements - "
                "consider adding a role-specific question"
            )

    if issues:
        return False, "Reflection flagged: " + "; ".join(issues)
    return True, "All three stages populated; question plan verified."




def run(
    job_research: Dict[str, Any],
    candidate_profile: Optional[Dict[str, Any]] = None,
    session_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the initial question plan for a new session."""
    if not job_research:
        return {
            "message_type": "question_plan",
            "status": "error",
            "payload": {"error": "job_research is required."},
        }

    candidate_profile = candidate_profile or {}
    session_id: str = (session_state or {}).get("session_id", str(uuid.uuid4()))

    #start with base medium difficulty
    avg_score = _avg_recent_score(session_state)
    base_difficulty = "medium"
    target_difficulty = _resolve_difficulty(base_difficulty, avg_score)

    # contxt extraction
    top_skill = _extract_top_skill(job_research)
    top_gap = _extract_top_gap(candidate_profile)
    focus_tags = [kw.lower() for kw in job_research.get("keywords", [])]
    slots = _build_slots(job_research, candidate_profile, top_skill, top_gap)

    # generate questions per stage with skill tags

    phone_screen = _select_questions(
        "phone_screen", _PHONE_SCREEN_TEMPLATES, target_difficulty, 3, slots, focus_tags
    )
    behavioral = _select_questions(
        "behavioral", _BEHAVIORAL_TEMPLATES, target_difficulty, 4, slots, focus_tags
    )
    technical = _select_questions(
        "technical", _TECHNICAL_TEMPLATES, target_difficulty, 4, slots, focus_tags
    )

    #find missing keywords
    targeted_gaps: List[str] = candidate_profile.get("missing_keywords", [])
    if top_gap and top_gap not in targeted_gaps:
        targeted_gaps = [top_gap] + targeted_gaps

    # job  requirements covered
    job_requirements_covered: List[str] = job_research.get("required_skills", [])


    reflection_passed, reflection_comment = _reflection_pass(
        phone_screen, behavioral, technical, targeted_gaps, job_requirements_covered
    )


    confidence = 0.82 if reflection_passed else 0.65

    reasoning_summary = (
        f"Generated a {target_difficulty}-difficulty question plan "
        f"({len(phone_screen)} phone screen, {len(behavioral)} behavioral, "
        f"{len(technical)} technical) for {job_research.get('role_title', 'unknown')}."
        + (" Difficulty adapted based on recent scores." if avg_score is not None else "")
    )


    return {
        "schema_version": "1.0",
        "message_id": str(uuid.uuid4()),
        "session_id": session_id,
        "source_agent": "QuestionGenerator",
        "message_type": "question_plan",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "success",
        "payload": {
            "phone_screen": phone_screen,
            "behavioral": behavioral,
            "technical": technical,
            "difficulty_level": target_difficulty,
            "targeted_gaps": targeted_gaps,
            "job_requirements_covered": job_requirements_covered,
            "rationale": (
                f"{len(phone_screen)} phone screen, {len(behavioral)} behavioral, "
                f"{len(technical)} technical questions for a "
                f"{job_research.get('seniority_level', 'mid-level')} "
                f"{job_research.get('role_title', 'the role')} at {target_difficulty} difficulty."
            ),
            "reflection_passed": reflection_passed,
            "reflection_comment": reflection_comment,
        },
        "decision": {
            "action": "question_plan_ready",
            "reasoning_summary": reasoning_summary,
            "confidence": confidence,
            "next_recommended_tool": "Interviewer",
        },
    }


def next_question(
    session_state: Dict[str, Any],
    job_research: Optional[Dict[str, Any]] = None,
    candidate_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return the next adapted question given live session state."""
    if not session_state:
        return {
            "message_type": "next_question",
            "status": "error",
            "payload": {"error": "session_state is required for next_question."},
        }

    session_id: str = session_state.get("session_id", str(uuid.uuid4()))
    question_plan: Dict[str, Any] = session_state.get("question_plan", {})
    asked_ids: List[str] = session_state.get("questions_asked", [])

    all_planned: List[Dict[str, Any]] = (
        question_plan.get("phone_screen", [])
        + question_plan.get("behavioral", [])
        + question_plan.get("technical", [])
    )

    #make sure to not ask previous questions
    remaining = [q for q in all_planned if q.get("question_id") not in asked_ids]

    avg_score = _avg_recent_score(session_state)
    adaptation_reason: str = "Following planned question order."

    if remaining:
        next_q = deepcopy(remaining[0])

        if avg_score is not None:
            new_diff = _resolve_difficulty(next_q["difficulty"], avg_score)
            if new_diff != next_q["difficulty"]:
                next_q["difficulty"] = new_diff
                adaptation_reason = (
                    f"Difficulty shifted to '{new_diff}' based on recent avg score "
                    f"{avg_score:.1f}/100."
                )
    else: #generate bonus hard question
        job_research = job_research or {}
        candidate_profile = candidate_profile or {}
        top_skill = _extract_top_skill(job_research)
        top_gap = _extract_top_gap(candidate_profile)
        slots = _build_slots(job_research, candidate_profile, top_skill, top_gap)
        bonus = _select_questions("technical", _TECHNICAL_TEMPLATES, "hard", 1, slots, [])
        if bonus:
            next_q = bonus[0]
            adaptation_reason = "All planned questions exhausted; generated a bonus technical question."
        else:
            return {
                "schema_version": "1.0",
                "message_id": str(uuid.uuid4()),
                "session_id": session_id,
                "source_agent": "QuestionGenerator",
                "message_type": "next_question",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "complete",
                "payload": {
                    "next_question": None,
                    "adaptation_reason": "All questions have been asked. Interview complete.",
                },
                "decision": {
                    "action": "interview_complete",
                    "reasoning_summary": "No remaining questions in the plan.",
                    "tools_considered": [],
                    "tools_used": [],
                    "confidence": 1.0,
                    "next_recommended_tool": "CareerCoach",
                },
            }

    return {
        "schema_version": "1.0",
        "message_id": str(uuid.uuid4()),
        "session_id": session_id,
        "source_agent": "QuestionGenerator",
        "message_type": "next_question",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "success",
        "payload": {
            "next_question": next_q,
            "adaptation_reason": adaptation_reason,
        },
        "decision": {
            "action": "next_question_selected",
            "reasoning_summary": adaptation_reason,
            "tools_considered": ["session_state", "question_plan"],
            "tools_used": ["session_state", "question_plan"],
            "confidence": 0.90,
            "next_recommended_tool": "Interviewer",
        },
    }
