"""
Responsibility: Researches the target job or role from the job description so MogBot can understand the employer, role expectations, likely skills, seniority, and interview focus areas.
Reasoning Logic: Summarizes job information into structured role context that main.py can combine with the candidate profile.
Tools/Resources: Job description text first; later optional web search, company pages, public role data, or RAG sources.
Data / Documents: Job description text, company name if provided, role title if provided, and optional job posting URL.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core import llm_client
from core.prompt_manager import PromptManager
from core.vector_memory import GlobalVectorMemory

_PROMPT_MANAGER = PromptManager()

_LLM_TOOL_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "role_title": {"type": "string"},
        "company_context": {"type": "string"},
        "required_skills": {"type": "array", "items": {"type": "string"}},
        "preferred_skills": {"type": "array", "items": {"type": "string"}},
        "responsibilities": {"type": "array", "items": {"type": "string"}},
        "seniority_level": {
            "type": "string",
            "enum": ["intern", "junior", "mid-level", "lead", "senior", "staff/principal"],
        },
        "keywords": {"type": "array", "items": {"type": "string"}},
        "interview_focus_areas": {"type": "array", "items": {"type": "string"}},
        "reflection_passed": {"type": "boolean"},
        "reflection_comment": {"type": "string"},
        "confidence": {"type": "number"},
        "reasoning_summary": {"type": "string"},
    },
    "required": [
        "role_title",
        "company_context",
        "required_skills",
        "responsibilities",
        "seniority_level",
        "interview_focus_areas",
        "reflection_passed",
        "confidence",
        "reasoning_summary",
    ],
}




_MEMORY_HIT_THRESHOLD = 0.5

_SENIORITY_MAP: List[tuple[str, str]] = [
    (r"\b(principal|staff|distinguished)\b", "staff/principal"),
    (r"\b(senior|sr\.?)\b", "senior"),
    (r"\b(lead|tech lead)\b", "lead"),
    (r"\b(mid[\- ]level|mid[\- ]senior)\b", "mid-level"),
    (r"\b(junior|jr\.?|associate|entry[\- ]level|graduate)\b", "junior"),
    (r"\b(intern(ship)?)\b", "intern"),
]

# find section header patterns
_SECTION_PATTERNS: Dict[str, re.Pattern[str]] = {
    "required": re.compile(
        r"(required|requirements|must[\s-]have|qualifications|you (will )?need|"
        r"minimum qualifications|what you.ll need)",
        re.IGNORECASE,
    ),
    "preferred": re.compile(
        r"(preferred|nice[\s-]to[\s-]have|bonus|desirable|plus|"
        r"preferred qualifications|great to have)",
        re.IGNORECASE,
    ),
    "responsibilities": re.compile(
        r"(responsibilities|duties|what you.ll do|you will|role overview|"
        r"key responsibilities|what we.re looking for)",
        re.IGNORECASE,
    ),
}

# list of keywords
_TECH_KEYWORDS: List[str] = [
    "python", "java", "javascript", "typescript", "c\\+\\+", "c#", "go", "rust",
    "sql", "nosql", "mongodb", "postgresql", "mysql", "redis", "elasticsearch",
    "react", "angular", "vue", "node", "django", "flask", "fastapi", "spring",
    "aws", "gcp", "azure", "docker", "kubernetes", "terraform", "ci/cd",
    "machine learning", "deep learning", "nlp", "llm", "rag", "pytorch", "tensorflow",
    "agile", "scrum", "rest", "graphql", "microservices", "api", "git",
    "communication", "leadership", "collaboration", "problem.solving",
]
_TECH_PATTERN = re.compile(
    r"\b(" + "|".join(_TECH_KEYWORDS) + r")\b", re.IGNORECASE
)


_FOCUS_RULES: List[tuple[str, str]] = [
    ("machine learning", "ML system design"),
    ("deep learning", "ML system design"),
    ("llm", "LLM/AI concepts"),
    ("rag", "retrieval-augmented generation"),
    ("sql", "data modeling & SQL"),
    ("nosql", "NoSQL data modeling"),
    ("system design", "system design"),
    ("microservices", "system design & microservices"),
    ("leadership", "behavioural & leadership"),
    ("communication", "behavioural & communication"),
    ("agile", "agile/scrum process"),
    ("docker", "containerisation & DevOps"),
    ("kubernetes", "containerisation & DevOps"),
    ("aws", "cloud architecture"),
    ("gcp", "cloud architecture"),
    ("azure", "cloud architecture"),
    ("ci/cd", "CI/CD & DevOps"),
]


def _detect_seniority(text: str) -> str:
    """Return the most senior-matching seniority level found in text."""
    lower = text.lower()
    for pattern, level in _SENIORITY_MAP:
        if re.search(pattern, lower):
            return level
    return "mid-level"  # sensible default


def _extract_title(text: str, provided_title: Optional[str]) -> tuple[str, str]:
    """Return (role_title, source)."""
    if provided_title:
        return provided_title.strip(), "user_input"
    for line in text.splitlines():
        line = line.strip()
        if line and len(line) < 120:
            return line, "job_description_first_line"
    return "Unknown Role", "inferred"


def _extract_section_bullets(text: str, section_pattern: re.Pattern[str]) -> List[str]:
    """
    Split text into lines and collect lines that appear after a matching
    section header until the next recognisable header or double blank line.
    """
    lines = text.splitlines()
    collecting = False
    bullets: List[str] = []
    blank_streak = 0

    for line in lines:
        stripped = line.strip()
        if section_pattern.search(stripped):
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
                is_new_section = any(
                    p.search(stripped)
                    for key, p in _SECTION_PATTERNS.items()
                    if p is not section_pattern
                )
                if is_new_section and len(stripped) < 80:
                    break
                cleaned = re.sub(r"^(?:[-*>]|\u2022)+\s*", "", stripped) # bullet points cleaning
                if cleaned:
                    bullets.append(cleaned)
    return bullets


def _extract_keywords(text: str) -> List[str]:
    """Return a deduplicated list of recognised tech/skill keywords from text."""
    found = _TECH_PATTERN.findall(text)
    seen: set[str] = set()
    result: List[str] = []
    for kw in found:
        kw_lower = kw.lower()
        if kw_lower not in seen:
            seen.add(kw_lower)
            result.append(kw_lower)
    return result


def _infer_focus_areas(
    required_skills: List[str],
    preferred_skills: List[str],
    responsibilities: List[str],
    keywords: List[str],
) -> List[str]:
    """Infer likely interview focus areas from extracted role content."""
    combined = " ".join(required_skills + preferred_skills + responsibilities + keywords).lower()
    focus: List[str] = []
    seen: set[str] = set()
    for signal, area in _FOCUS_RULES:
        if signal in combined and area not in seen:
            focus.append(area)
            seen.add(area)

    if not focus:
        focus.append("general technical fundamentals")
    focus.append("behavioural (STAR-format)")
    return focus


def _reflection_pass(
    role_title: str,
    required_skills: List[str],
    responsibilities: List[str],
    job_description: str,
) -> tuple[bool, str]:
    """Verify that key extracted claims are present in the original job description.
    Returns (passed, comment).
    """
    desc_lower = job_description.lower()
    issues: List[str] = []

    if role_title != "Unknown Role":
        if role_title.lower() not in desc_lower:
            issues.append(f"role_title '{role_title}' not found verbatim in description")

    for skill in required_skills[:5]:
        if skill.lower() not in desc_lower:
            issues.append(f"required skill '{skill}' not found in description")

    if not responsibilities:
        issues.append("no responsibilities extracted - description may lack a clear responsibilities section")

    if issues:
        return False, "Reflection flagged: " + "; ".join(issues)
    return True, "All sampled claims verified against job description."


def run(
    job_input: Dict[str, Any],
    vector_memory: Optional[GlobalVectorMemory] = None,
) -> Dict[str, Any]:
    """Research the job role and return a job_research AgentMessage.

    Uses a real Anthropic call when ANTHROPIC_API_KEY is configured; falls
    back to the deterministic heuristic below (unconfigured key, network
    error, or invalid structured output) so the agent always returns a
    usable result. See ACTION_PLAN.md Milestone 7.
    """
    if llm_client.is_configured():
        try:
            return _run_llm(job_input, vector_memory)
        except Exception as exc:  # LLMNotConfiguredError, LLMCallError, or any API failure
            print(f"[JobSearchAgent] LLM path failed ({exc}); falling back to heuristic.")
    return _run_heuristic(job_input, vector_memory)


def _run_llm(
    job_input: Dict[str, Any],
    vector_memory: Optional[GlobalVectorMemory],
) -> Dict[str, Any]:
    if not job_input:
        return {
            "message_type": "job_research",
            "status": "error",
            "payload": {"error": "No job_input provided."},
        }

    job_description: str = job_input.get("job_description", "").strip()
    if not job_description:
        return {
            "message_type": "job_research",
            "status": "error",
            "payload": {"error": "job_description is required and must not be empty."},
        }

    company_name: Optional[str] = job_input.get("company_name")
    provided_title: Optional[str] = job_input.get("role_title")
    job_posting_url: Optional[str] = job_input.get("job_posting_url")
    session_id: str = job_input.get("session_id", str(uuid.uuid4()))

    system_prompt = _PROMPT_MANAGER.render("job_search", "system", {})
    task_prompt = _PROMPT_MANAGER.render(
        "job_search", "task", {"job_description": llm_client.wrap_untrusted_content("job_description", job_description)}
    )
    hints = []
    if company_name:
        hints.append(f"The candidate says the company is: {company_name}")
    if provided_title:
        hints.append(f"The candidate says the role title is: {provided_title}")
    user_prompt = task_prompt + ("\n" + "\n".join(hints) if hints else "")

    llm_output = llm_client.call_structured(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tool_name="record_job_research",
        tool_description="Record structured job research extracted from a job description.",
        input_schema=_LLM_TOOL_SCHEMA,
    )

    payload = {
        "role_title": llm_output["role_title"],
        "company_context": llm_output["company_context"],
        "required_skills": llm_output.get("required_skills", []),
        "preferred_skills": llm_output.get("preferred_skills", []),
        "responsibilities": llm_output.get("responsibilities", []),
        "seniority_level": llm_output["seniority_level"],
        "keywords": llm_output.get("keywords", []),
        "interview_focus_areas": llm_output["interview_focus_areas"],
        "job_posting_url": job_posting_url,
        "source_map": {key: "anthropic_llm" for key in (
            "role_title", "company_context", "required_skills", "preferred_skills",
            "responsibilities", "seniority_level", "keywords", "interview_focus_areas",
        )},
        "reflection_passed": llm_output["reflection_passed"],
        "reflection_comment": llm_output.get("reflection_comment", ""),
    }

    result = {
        "schema_version": "1.0",
        "message_id": str(uuid.uuid4()),
        "session_id": session_id,
        "source_agent": "JobSearchAgent",
        "message_type": "job_research",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "success",
        "payload": payload,
        "decision": {
            "action": "job_research_complete",
            "reasoning_summary": llm_output["reasoning_summary"],
            "tools_considered": ["job_description_text", "global_vector_memory", "anthropic_llm"],
            "tools_used": ["job_description_text", "anthropic_llm"],
            "confidence": float(llm_output["confidence"]),
            "next_recommended_tool": "ResumeAndRoleAnalyzer",
        },
    }

    if vector_memory is not None:
        vector_memory.add_record({
            "record_id": result["message_id"],
            "session_id": session_id,
            "namespace": "job_research",
            "text": job_description,
            "metadata": result["payload"],
        })

    return result


def _run_heuristic(
    job_input: Dict[str, Any],
    vector_memory: Optional[GlobalVectorMemory] = None,
) -> Dict[str, Any]:
    """Deterministic regex/keyword fallback - see `run()` for when this is used.

    Parameters
    ----------
    job_input : dict
        Required:
          - job_description : str   - raw job description text
        Optional:
          - company_name    : str
          - role_title      : str
          - job_posting_url : str
          - session_id      : str
    vector_memory : GlobalVectorMemory, optional
        Shared memory instance passed from main.py. Used to check for a cached
        job record and to write the result back after processing.

    Returns
    -------
    dict
        AgentMessage with message_type="job_research". Payload keys:
        role_title, company_context, required_skills, preferred_skills,
        responsibilities, seniority_level, keywords, interview_focus_areas,
        source_map, reflection_passed, reflection_comment.
    """
    if not job_input:
        return {
            "message_type": "job_research",
            "status": "error",
            "payload": {"error": "No job_input provided."},
        }

    job_description: str = job_input.get("job_description", "").strip()
    if not job_description:
        return {
            "message_type": "job_research",
            "status": "error",
            "payload": {"error": "job_description is required and must not be empty."},
        }

    company_name: Optional[str] = job_input.get("company_name")
    provided_title: Optional[str] = job_input.get("role_title")
    job_posting_url: Optional[str] = job_input.get("job_posting_url")
    session_id: str = job_input.get("session_id", str(uuid.uuid4()))

    # GlobalVectorMemory.search() always returns its top_k best matches, even
    # when nothing is actually similar (it doesn't filter by score) - so a
    # hit only counts as a real memory hit above a similarity threshold,
    # otherwise every call would look like a cache hit once memory is non-empty.
    cached_record = None
    if vector_memory is not None:
        hits = vector_memory.search(job_description, namespace="job_research", top_k=1)
        if hits and float(hits[0].get("metadata", {}).get("similarity_score", 0.0)) >= _MEMORY_HIT_THRESHOLD:
            cached_record = hits[0]
    has_memory_hit: bool = cached_record is not None

    tools_used = ["job_description_text"]
    if has_memory_hit:
        tools_used.append("global_vector_memory")
    reasoning_summary = (
        "Parsed job description text. URL stored for future retrieval."
        if job_posting_url
        else "Parsed job description text."
    )

    role_title, title_source = _extract_title(job_description, provided_title)

    # comp context
    company_context: str
    company_source: str
    if company_name:
        company_context = company_name.strip()
        company_source = "user_input"
    else:
        #  find company mentions in the description
        match = re.search(r"(?:at|join|about)\s+([A-Z][A-Za-z0-9& ]{2,40}?)(?:\.|,|\s)", job_description)
        if match:
            company_context = match.group(1).strip()
            company_source = "job_description_inferred"
        else:
            company_context = "Unknown Company"
            company_source = "inferred"

    required_skills = _extract_section_bullets(job_description, _SECTION_PATTERNS["required"])
    preferred_skills = _extract_section_bullets(job_description, _SECTION_PATTERNS["preferred"])
    responsibilities = _extract_section_bullets(job_description, _SECTION_PATTERNS["responsibilities"])

    seniority_level = _detect_seniority(job_description)


    keywords = _extract_keywords(job_description)

    # interviw focus areas
    interview_focus_areas = _infer_focus_areas(
        required_skills, preferred_skills, responsibilities, keywords
    )


    reflection_passed, reflection_comment = _reflection_pass(
        role_title, required_skills, responsibilities, job_description
    )


    source_map: Dict[str, str] = {
        "role_title": title_source,
        "company_context": company_source,
        "required_skills": "job_description_section_extraction",
        "preferred_skills": "job_description_section_extraction",
        "responsibilities": "job_description_section_extraction",
        "seniority_level": "job_description_keyword_match",
        "keywords": "job_description_keyword_match",
        "interview_focus_areas": "inferred_from_skills_and_responsibilities",
        "job_posting_url": "user_input" if job_posting_url else "not_provided",
    }

    confidence = 0.80 if (required_skills or responsibilities) else 0.50
    if not reflection_passed:
        confidence = round(confidence * 0.85, 2)


    result = {
        "schema_version": "1.0",
        "message_id": str(uuid.uuid4()),
        "session_id": session_id,
        "source_agent": "JobSearchAgent",
        "message_type": "job_research",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "success",
        "payload": {
            "role_title": role_title,
            "company_context": company_context,
            "required_skills": required_skills,
            "preferred_skills": preferred_skills,
            "responsibilities": responsibilities,
            "seniority_level": seniority_level,
            "keywords": keywords,
            "interview_focus_areas": interview_focus_areas,
            "job_posting_url": job_posting_url,
            "source_map": source_map,
            "reflection_passed": reflection_passed,
            "reflection_comment": reflection_comment,
        },
        "decision": {
            "action": "job_research_complete",
            "reasoning_summary": reasoning_summary,
            "tools_considered": ["job_description_text"],
            "tools_used": tools_used,
            "confidence": confidence,
            "next_recommended_tool": "ResumeAndRoleAnalyzer",
        },
    }

    if vector_memory is not None and not has_memory_hit:
        vector_memory.add_record({
            "record_id": result["message_id"],
            "session_id": session_id,
            "namespace": "job_research",
            "text": job_description,
            "metadata": result["payload"],
        })

    return result
