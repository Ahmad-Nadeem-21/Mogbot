"""
Responsibility: Parses the user's uploaded resume/profile information. Identifies skills, experience highlights, evidence, gaps, and candidate seniority signals.
Reasoning Logic: Plan to have a reflection so the agent can review its own feedback and fix inaccurate information.
Tools/Resources: Plan to use RAG for the uploaded resume as a PDF and optional LinkedIn/profile material.
Data / Documents: Uploaded resume (PDF or text) and optional LinkedIn profile URL.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from core import llm_client
from core.prompt_manager import PromptManager
from core.vector_memory import GlobalVectorMemory

_PROMPT_MANAGER = PromptManager()

_LLM_TOOL_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "skills": {"type": "array", "items": {"type": "string"}},
        "experience_highlights": {"type": "array", "items": {"type": "string"}},
        "missing_keywords": {"type": "array", "items": {"type": "string"}},
        "role_keywords": {"type": "array", "items": {"type": "string"}},
        "seniority_level": {
            "type": "string",
            "enum": ["intern", "junior", "mid-level", "lead", "senior", "staff/principal"],
        },
        "risk_notes": {"type": "array", "items": {"type": "string"}},
        "evidence_snippets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"skill": {"type": "string"}, "excerpt": {"type": "string"}},
                "required": ["skill", "excerpt"],
            },
        },
        "reflection_passed": {"type": "boolean"},
        "reflection_comment": {"type": "string"},
        "confidence": {"type": "number"},
        "reasoning_summary": {"type": "string"},
    },
    "required": [
        "skills",
        "experience_highlights",
        "seniority_level",
        "reflection_passed",
        "confidence",
        "reasoning_summary",
    ],
}



_SKILL_PATTERNS: List[str] = [
    # Languages
    "python", "java", "javascript", "typescript", "c\\+\\+", "c#", "go", "rust",
    "swift", "kotlin", "ruby", "php", "scala", "r\\b",
    # Web/ frameworks
    "react", "angular", "vue", "node\\.?js", "django", "flask", "fastapi",
    "spring", "express", "rails", "laravel",
    # Data / ML
    "sql", "postgresql", "mysql", "sqlite", "nosql", "mongodb", "redis",
    "elasticsearch", "cassandra", "dynamodb",
    "machine learning", "deep learning", "nlp", "llm", "rag", "pytorch",
    "tensorflow", "scikit.learn", "pandas", "numpy", "spark", "kafka",
    # devops
    "aws", "gcp", "azure", "docker", "kubernetes", "terraform", "ansible",
    "ci/cd", "jenkins", "github actions", "gitlab ci",
    # skills
    "agile", "scrum", "kanban", "rest", "graphql", "microservices",
    "tdd", "bdd", "git", "linux", "communication", "leadership",
    "problem.solving", "collaboration", "mentoring",
]
_SKILL_RE = re.compile( #regex to find skill keywords in the resume text
    r"\b(" + "|".join(_SKILL_PATTERNS) + r")\b", re.IGNORECASE
)

_SENIORITY_SIGNALS: List[Tuple[str, str]] = [
    (r"\b(principal|staff|distinguished|fellow)\b", "staff/principal"),
    (r"\b(senior|sr\.?)\b", "senior"),
    (r"\b(lead|tech lead|engineering lead)\b", "lead"),
    (r"\b(mid[\-\s]level|mid[\-\s]senior)\b", "mid-level"),
    (r"\b(junior|jr\.?|associate|entry[\-\s]level|graduate|new grad)\b", "junior"),
    (r"\b(intern(ship)?)\b", "intern"),
]

_RESUME_SECTIONS: Dict[str, re.Pattern[str]] = {
    "experience": re.compile(
        r"(work experience|professional experience|employment|experience|career history)",
        re.IGNORECASE,
    ),
    "education": re.compile(
        r"(education|academic|degrees?|university|college|school)", re.IGNORECASE
    ),
    "skills": re.compile(
        r"(skills|technical skills|core competencies|technologies|tools)", re.IGNORECASE
    ),
    "projects": re.compile(
        r"(projects?|personal projects?|side projects?|portfolio)", re.IGNORECASE
    ),
    "summary": re.compile(
        r"(summary|objective|profile|about me|overview)", re.IGNORECASE
    ),
}

_YEARS_RE = re.compile(
    r"(\d+)\+?\s*years?\s*(of\s*)?(experience|working|professional)", re.IGNORECASE
)

_RISK_PATTERNS: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(no|zero|0)\s+years?\b", re.IGNORECASE), "No years of experience mentioned"),
    (re.compile(r"\b(intern(ship)?)\b", re.IGNORECASE), "Most recent role appears to be an internship"),
    (re.compile(r"\b(gap|career break|sabbatical)\b", re.IGNORECASE), "Possible employment gap detected"),
    (re.compile(r"\b(bootcamp|self.taught|online course)\b", re.IGNORECASE), "Non-traditional education background"),
]




def _extract_skills(text: str) -> List[str]:
    """Return deduplicated skill keywords found in the resume text."""
    found = _SKILL_RE.findall(text)
    seen: set[str] = set()
    result: List[str] = []
    for kw in found:
        kw_lower = kw.lower().strip()
        if kw_lower not in seen:
            seen.add(kw_lower)
            result.append(kw_lower)
    return result


def _detect_seniority(text: str) -> Tuple[str, str]:
    """Return (seniority_level, detection_source)."""
    lower = text.lower()

    #years of experience is the strongest signal, so check that first
    match = _YEARS_RE.search(lower)
    if match:
        years = int(match.group(1))
        if years >= 10:
            return "senior", f"years_of_experience:{years}"
        if years >= 5:
            return "mid-level", f"years_of_experience:{years}"
        if years >= 2:
            return "junior", f"years_of_experience:{years}"

    for pattern, level in _SENIORITY_SIGNALS:
        if re.search(pattern, lower):
            return level, "title_keyword"

    return "mid-level", "default"


def _extract_section(text: str, section_key: str) -> str:
    """
    Return the text block that falls under the given section header.
    Stops at the next detected section header or double blank line.
    """
    pattern = _RESUME_SECTIONS.get(section_key)
    if pattern is None:
        return ""

    lines = text.splitlines()
    collecting = False
    collected: List[str] = []
    blank_streak = 0

    for line in lines:
        stripped = line.strip()
        if pattern.search(stripped) and len(stripped) < 80:
            collecting = True
            blank_streak = 0
            continue
        if collecting:
            if stripped == "":
                blank_streak += 1
                if blank_streak >= 2:
                    break
            else:
                blank_streak = 0
                is_new = any(
                    p.search(stripped)
                    for key, p in _RESUME_SECTIONS.items()
                    if key != section_key and len(stripped) < 80
                )
                if is_new:
                    break
                collected.append(stripped)
    return "\n".join(collected)


def _extract_experience_highlights(text: str) -> List[str]:
    """
    Pull bullet-point lines from the experience section as highlights.
    Falls back to the first 5 non-empty lines if no bullets are found.
    """
    section = _extract_section(text, "experience")
    if not section:
        section = text  # scan the whole resume if no clear section

    highlights: List[str] = []
    for line in section.splitlines():
        stripped = re.sub(r"^(?:[-*>]|\u2022|\u00b7|\u25b8|\u2192)+\s*", "", line.strip())
        if stripped and len(stripped) > 20:
            highlights.append(stripped)
        if len(highlights) >= 6:
            break
    return highlights


def _extract_role_keywords(text: str) -> List[str]:
    """
    Extract role-related keywords: job titles and technology names
    that appear as section headers or near job title lines.
    """
    title_re = re.compile(
        r"\b(engineer|developer|scientist|analyst|architect|manager|lead|"
        r"consultant|specialist|designer|director|vp|cto|ceo)\b",
        re.IGNORECASE,
    )
    found: List[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if title_re.search(stripped) and len(stripped) < 80:
            kw = stripped.lower()
            if kw not in seen:
                seen.add(kw)
                found.append(stripped)
        if len(found) >= 5:
            break
    return found


def _compute_missing_keywords(
    resume_skills: List[str],
    job_research: Optional[Dict[str, Any]],
) -> List[str]:
    """
    RRA-03: Return job keywords not found in the candidate's skill list.
    Only computed when job_research is provided; otherwise returns [].
    """
    if not job_research:
        return []
    job_keywords = [kw.lower() for kw in job_research.get("keywords", [])]
    resume_lower = {s.lower() for s in resume_skills}
    return [kw for kw in job_keywords if kw not in resume_lower]


def _detect_risk_notes(text: str, skills: List[str]) -> List[str]:
    """Return a list of human-readable risk notes based on resume content."""
    notes: List[str] = []
    for pattern, message in _RISK_PATTERNS:
        if pattern.search(text):
            notes.append(message)
    if len(skills) < 4:
        notes.append("Few identifiable technical skills - may need further clarification")
    return notes


def _build_evidence_snippets(
    text: str,
    skills: List[str],
    max_snippets: int = 5,
) -> List[Dict[str, str]]:
    """
    RRA-03 / RRA-07: Return short evidence snippets - lines where a key skill
    is mentioned - so downstream agents can cite grounded evidence.
    """
    snippets: List[Dict[str, str]] = []
    seen_lines: set[str] = set()
    priority = skills[:10]  # focus on top skills

    for line in text.splitlines():
        stripped = line.strip()
        if len(stripped) < 15 or stripped in seen_lines:
            continue
        for skill in priority:
            if skill.lower() in stripped.lower():
                seen_lines.add(stripped)
                snippets.append({"skill": skill, "excerpt": stripped[:200]})
                break
        if len(snippets) >= max_snippets:
            break
    return snippets


def _reflection_pass(
    skills: List[str],
    experience_highlights: List[str],
    missing_keywords: List[str],
    evidence_snippets: List[Dict[str, str]],
    resume_text: str,
) -> Tuple[bool, str]:
    """
    RRA-04 / RRA-09: Verify that extracted data is grounded in resume text.
    Returns (passed, comment).
    """
    issues: List[str] = []

    # every  skill should appear in the resume text
    unverified = [
        s for s in skills[:8]
        if s.lower() not in resume_text.lower()
    ]
    if unverified:
        issues.append(f"skills not verified in text: {', '.join(unverified)}")

    if not experience_highlights:
        issues.append("no experience highlights extracted")

    contradiction = [kw for kw in missing_keywords if kw in {s.lower() for s in skills}]
    if contradiction:
        issues.append(f"keywords flagged as missing but also in skills list: {', '.join(contradiction)}")

    if issues:
        return False, "Reflection flagged: " + "; ".join(issues)
    return True, "All sampled skills verified in resume text; no contradictions detected."




def run(
    input_data: Dict[str, Any],
    vector_memory: Optional[GlobalVectorMemory] = None,
) -> Dict[str, Any]:
    """Parse resume/profile text and return a candidate_profile AgentMessage.

    Uses a real Anthropic call when ANTHROPIC_API_KEY is configured; falls
    back to the deterministic heuristic below otherwise or on any API
    failure. See ACTION_PLAN.md Milestone 7.
    """
    if llm_client.is_configured():
        try:
            return _run_llm(input_data, vector_memory)
        except Exception as exc:
            print(f"[ResumeAndRoleAnalyzer] LLM path failed ({exc}); falling back to heuristic.")
    return _run_heuristic(input_data, vector_memory)


def _run_llm(
    input_data: Dict[str, Any],
    vector_memory: Optional[GlobalVectorMemory],
) -> Dict[str, Any]:
    if not input_data:
        return {
            "message_type": "candidate_profile",
            "status": "error",
            "payload": {"error": "No input_data provided."},
        }

    resume_text: str = input_data.get("resume_text", "").strip()
    resume_path: Optional[str] = input_data.get("resume_path")
    if not resume_text and resume_path:
        try:
            with open(resume_path, "r", encoding="utf-8") as fh:
                resume_text = fh.read().strip()
        except OSError as exc:
            return {
                "message_type": "candidate_profile",
                "status": "error",
                "payload": {"error": f"Could not read resume_path: {exc}"},
            }

    if not resume_text:
        return {
            "message_type": "candidate_profile",
            "status": "error",
            "payload": {"error": "resume_text or resume_path is required."},
        }

    linkedin_url: Optional[str] = input_data.get("linkedin_url")
    job_research: Optional[Dict[str, Any]] = input_data.get("job_research")
    session_id: str = input_data.get("session_id", str(uuid.uuid4()))

    system_prompt = _PROMPT_MANAGER.render("resume_analyzer", "system", {})
    task_prompt = _PROMPT_MANAGER.render(
        "resume_analyzer", "task", {"resume_text": llm_client.wrap_untrusted_content("resume_text", resume_text)}
    )
    if job_research:
        task_prompt += (
            "\nCompute missing_keywords as job_research keywords not evidenced in the resume. "
            f"job_research keywords: {job_research.get('keywords', [])}"
        )

    llm_output = llm_client.call_structured(
        system_prompt=system_prompt,
        user_prompt=task_prompt,
        tool_name="record_candidate_profile",
        tool_description="Record structured candidate profile extracted from a resume.",
        input_schema=_LLM_TOOL_SCHEMA,
    )

    payload = {
        "skills": llm_output["skills"],
        "experience_highlights": llm_output["experience_highlights"],
        "missing_keywords": llm_output.get("missing_keywords", []),
        "role_keywords": llm_output.get("role_keywords", []),
        "seniority_level": llm_output["seniority_level"],
        "risk_notes": llm_output.get("risk_notes", []),
        "evidence_snippets": llm_output.get("evidence_snippets", []),
        "source_map": {key: "anthropic_llm" for key in (
            "skills", "experience_highlights", "missing_keywords", "role_keywords",
            "seniority_level", "risk_notes", "evidence_snippets",
        )},
        "reflection_passed": llm_output["reflection_passed"],
        "reflection_comment": llm_output.get("reflection_comment", ""),
    }

    result = {
        "schema_version": "1.0",
        "message_id": str(uuid.uuid4()),
        "session_id": session_id,
        "source_agent": "ResumeAndRoleAnalyzer",
        "message_type": "candidate_profile",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "success",
        "payload": payload,
        "decision": {
            "action": "candidate_profile_complete",
            "reasoning_summary": llm_output["reasoning_summary"],
            "tools_considered": ["resume_text", "global_vector_memory", "anthropic_llm"],
            "tools_used": ["resume_text", "anthropic_llm"],
            "confidence": float(llm_output["confidence"]),
            "next_recommended_tool": "QuestionGenerator",
        },
    }

    if vector_memory is not None:
        vector_memory.add_record({
            "record_id": result["message_id"],
            "session_id": session_id,
            "namespace": "candidate_profile",
            "text": resume_text,
            "metadata": result["payload"],
        })

    return result


def _run_heuristic(
    input_data: Dict[str, Any],
    vector_memory: Optional[GlobalVectorMemory] = None,
) -> Dict[str, Any]:
    """Deterministic regex/keyword fallback - see `run()` for when this is used."""
    if not input_data:
        return {
            "message_type": "candidate_profile",
            "status": "error",
            "payload": {"error": "No input_data provided."},
        }

    resume_text: str = input_data.get("resume_text", "").strip()
    resume_path: Optional[str] = input_data.get("resume_path")
    text_source: str = "resume_text_field"

    if not resume_text and resume_path:

        try:
            with open(resume_path, "r", encoding="utf-8") as fh:
                resume_text = fh.read().strip()
            text_source = f"resume_path:{resume_path}"
        except OSError as exc:
            return {
                "message_type": "candidate_profile",
                "status": "error",
                "payload": {"error": f"Could not read resume_path: {exc}"},
            }

    if not resume_text:
        return {
            "message_type": "candidate_profile",
            "status": "error",
            "payload": {"error": "resume_text or resume_path is required."},
        }

    linkedin_url: Optional[str] = input_data.get("linkedin_url")
    job_research: Optional[Dict[str, Any]] = input_data.get("job_research")
    session_id: str = input_data.get("session_id", str(uuid.uuid4()))

    # GlobalVectorMemory.search() always returns its top_k best matches even
    # when nothing is actually similar, so a hit only counts above a
    # similarity threshold - otherwise every call looks like a memory hit
    # once the namespace is non-empty.
    has_memory_hit = False
    if vector_memory is not None:
        hits = vector_memory.search(resume_text, namespace="candidate_profile", top_k=1)
        has_memory_hit = bool(
            hits and float(hits[0].get("metadata", {}).get("similarity_score", 0.0)) >= 0.5
        )

    skills = _extract_skills(resume_text)
    seniority_level, seniority_source = _detect_seniority(resume_text)
    experience_highlights = _extract_experience_highlights(resume_text)
    role_keywords = _extract_role_keywords(resume_text)
    missing_keywords = _compute_missing_keywords(skills, job_research)
    risk_notes = _detect_risk_notes(resume_text, skills)
    evidence_snippets = _build_evidence_snippets(resume_text, skills)

    reflection_passed, reflection_comment = _reflection_pass(
        skills, experience_highlights, missing_keywords, evidence_snippets, resume_text
    )

    confidence = 0.80 if (skills and experience_highlights) else 0.50
    if not reflection_passed:
        confidence = round(confidence * 0.85, 2)
    source_map: Dict[str, str] = {
        "resume_text": text_source,
        "skills": "resume_keyword_extraction",
        "experience_highlights": "resume_experience_section",
        "missing_keywords": "gap_analysis_vs_job_research" if job_research else "not_computed",
        "role_keywords": "resume_title_line_extraction",
        "seniority_level": seniority_source,
        "risk_notes": "resume_heuristic_flags",
        "evidence_snippets": "resume_inline_excerpts",
        "linkedin_url": "user_input" if linkedin_url else "not_provided",
    }

    tools_used = ["resume_text"]
    if has_memory_hit:
        tools_used.append("global_vector_memory")

    reasoning_summary = (
        f"Extracted {len(skills)} skills, seniority '{seniority_level}' ({seniority_source})."
        + (f" {len(missing_keywords)} missing keywords vs job research." if job_research else "")
        + (" Reflection passed." if reflection_passed else " Reflection flagged issues - confidence reduced.")
    )

    result = {
        "schema_version": "1.0",
        "message_id": str(uuid.uuid4()),
        "session_id": session_id,
        "source_agent": "ResumeAndRoleAnalyzer",
        "message_type": "candidate_profile",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "success",
        "payload": {
            "skills": skills,
            "experience_highlights": experience_highlights,
            "missing_keywords": missing_keywords,
            "role_keywords": role_keywords,
            "seniority_level": seniority_level,
            "risk_notes": risk_notes,
            "evidence_snippets": evidence_snippets,
            "source_map": source_map,
            "reflection_passed": reflection_passed,
            "reflection_comment": reflection_comment,
        },
        "decision": {
            "action": "candidate_profile_complete",
            "reasoning_summary": reasoning_summary,
            "tools_considered": ["resume_text"],
            "tools_used": tools_used,
            "confidence": confidence,
            "next_recommended_tool": "QuestionGenerator",
        },
    }

    if vector_memory is not None and not has_memory_hit:
        vector_memory.add_record({
            "record_id": result["message_id"],
            "session_id": session_id,
            "namespace": "candidate_profile",
            "text": resume_text,
            "metadata": result["payload"],
        })

    return result
