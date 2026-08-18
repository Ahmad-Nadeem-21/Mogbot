"""Shared schema templates for MogBot.

These schemas are the single source of truth for data moving between
main.py, agent tools, helper agents, memory, and cache layers.
"""

from typing import Any, Dict, List, Optional, Tuple, TypedDict, cast

from pydantic import BaseModel, Field


class AgentDecision(TypedDict, total=False):
    """Public decision metadata returned by every agent.

    Store a concise reasoning summary here. Do not store raw private chain-of-
    thought or scratchpad text.
    """

    action: str
    reasoning_summary: str
    tools_considered: List[str]
    tools_used: List[str]
    confidence: float
    next_recommended_tool: str


class ToolRequest(TypedDict, total=False):
    """Request created by main.py when calling an agent as a tool."""

    schema_version: str
    request_id: str
    session_id: str
    source: str
    target_agent: str
    task_type: str
    timestamp: str
    payload: Dict[str, Any]
    session_context: Dict[str, Any]


class AgentMessage(TypedDict, total=False):
    """Result returned by an agent tool to main.py."""

    schema_version: str
    message_id: str
    request_id: str
    session_id: str
    source_agent: str
    target: str
    message_type: str
    timestamp: str
    status: str
    payload: Dict[str, Any]
    metadata: Dict[str, Any]
    decision: AgentDecision


class MemoryRecord(TypedDict, total=False):
    """Record stored in the global vector database."""

    record_id: str
    session_id: str
    namespace: str
    text: str
    embedding: List[float]
    metadata: Dict[str, Any]


class UserInputs(TypedDict, total=False):
    """Raw inputs collected from the user before and during the interview."""

    resume_text: str
    resume_path: str
    job_description: str
    company_name: str
    role_title: str
    job_posting_url: str
    linkedin_url: str


class SessionState(TypedDict, total=False):
    """Official session snapshot owned and updated by main.py.

    Field shapes for job_research, candidate_profile, question_plan, and
    final_report are filled in by agents; use Dict[str, Any] until those
    agents define narrower contracts.
    """

    session_id: str
    user_inputs: UserInputs
    job_research: Dict[str, Any]
    candidate_profile: Dict[str, Any]
    question_plan: Dict[str, Any]
    current_question: Dict[str, Any]
    conversation_history: List[Any]
    evaluation_scores: List[Any]
    reward_signals: List[Any]
    interview_strategy_notes: List[Any]
    devil_advocate_flags: List[Any]
    helper_reviews: List[Any]
    memory_records: List[Any]
    cache_hits: List[Any]
    final_report: Dict[str, Any]
    status: str


class AgentDecisionModel(BaseModel):
    """Pydantic model for public decision metadata."""

    action: str = ""
    reasoning_summary: str = ""
    tools_considered: List[str] = Field(default_factory=list)
    tools_used: List[str] = Field(default_factory=list)
    confidence: float = 0.0
    next_recommended_tool: str = "none"


class ToolRequestModel(BaseModel):
    """Pydantic model for main.py -> agent tool calls."""

    schema_version: str = "1.0"
    request_id: str = ""
    session_id: str = ""
    source: str = "main"
    target_agent: str = ""
    task_type: str = ""
    timestamp: str = ""
    payload: Dict[str, Any] = Field(default_factory=dict)
    session_context: Dict[str, Any] = Field(default_factory=dict)


class AgentMessageModel(BaseModel):
    """Pydantic model for agent -> main.py responses."""

    schema_version: str = "1.0"
    message_id: str = ""
    request_id: str = ""
    session_id: str = ""
    source_agent: str = ""
    target: str = "main"
    message_type: str = ""
    timestamp: str = ""
    status: str = "ok"
    payload: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    decision: AgentDecisionModel = Field(default_factory=AgentDecisionModel)


class MemoryRecordModel(BaseModel):
    """Pydantic model for vector-memory entries."""

    record_id: str = ""
    session_id: str = ""
    namespace: str = ""
    text: str = ""
    embedding: List[float] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UserInputsModel(BaseModel):
    """Pydantic model for user-provided interview inputs."""

    resume_text: str = ""
    resume_path: str = ""
    job_description: str = ""
    company_name: str = ""
    role_title: str = ""
    job_posting_url: str = ""
    linkedin_url: str = ""


class SessionStateModel(BaseModel):
    """Pydantic model for main-owned session snapshot."""

    session_id: str = ""
    user_inputs: UserInputsModel = Field(default_factory=UserInputsModel)
    job_research: Dict[str, Any] = Field(default_factory=dict)
    candidate_profile: Dict[str, Any] = Field(default_factory=dict)
    question_plan: Dict[str, Any] = Field(default_factory=dict)
    current_question: Dict[str, Any] = Field(default_factory=dict)
    conversation_history: List[Any] = Field(default_factory=list)
    evaluation_scores: List[Any] = Field(default_factory=list)
    reward_signals: List[Any] = Field(default_factory=list)
    interview_strategy_notes: List[Any] = Field(default_factory=list)
    devil_advocate_flags: List[Any] = Field(default_factory=list)
    helper_reviews: List[Any] = Field(default_factory=list)
    memory_records: List[Any] = Field(default_factory=list)
    cache_hits: List[Any] = Field(default_factory=list)
    final_report: Dict[str, Any] = Field(default_factory=dict)
    status: str = "created"


def _model_to_dict(model: BaseModel) -> Dict[str, Any]:
    """Compatibility helper for Pydantic v1/v2 dict dumping."""

    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def validate_tool_request(data: Dict[str, Any]) -> ToolRequest:
    """Validate and normalize a ToolRequest payload."""

    return cast(ToolRequest, _model_to_dict(ToolRequestModel(**data)))


def validate_agent_message(data: Dict[str, Any]) -> AgentMessage:
    """Validate and normalize an AgentMessage payload."""

    return cast(AgentMessage, _model_to_dict(AgentMessageModel(**data)))


def validate_session_state(data: Dict[str, Any]) -> SessionState:
    """Validate and normalize SessionState payload."""

    return cast(SessionState, _model_to_dict(SessionStateModel(**data)))


def build_agent_decision(
    action: str,
    reasoning_summary: str,
    *,
    tools_considered: Optional[List[str]] = None,
    tools_used: Optional[List[str]] = None,
    confidence: float = 0.0,
    next_recommended_tool: str = "none",
) -> AgentDecision:
    """Build a full AgentDecision for MAIN-AGENTIC-01 (all keys always present)."""

    return {
        "action": action,
        "reasoning_summary": reasoning_summary,
        "tools_considered": list(tools_considered or []),
        "tools_used": list(tools_used or []),
        "confidence": float(confidence),
        "next_recommended_tool": next_recommended_tool,
    }


def decision_is_complete(decision: AgentDecision) -> bool:
    """Return True if decision contains every required public routing field."""

    required: Tuple[str, ...] = (
        "action",
        "reasoning_summary",
        "tools_considered",
        "tools_used",
        "confidence",
        "next_recommended_tool",
    )
    for key in required:
        if key not in decision:
            return False
    return True


def agent_message_decision_issues(msg: AgentMessage) -> List[str]:
    """Return a list of human-readable problems (empty if decision is usable)."""

    issues: List[str] = []
    raw = msg.get("decision")
    if raw is None:
        return ["missing decision"]
    decision = cast(AgentDecision, raw)
    if not decision_is_complete(decision):
        required = (
            "action",
            "reasoning_summary",
            "tools_considered",
            "tools_used",
            "confidence",
            "next_recommended_tool",
        )
        missing = [k for k in required if k not in decision]
        issues.append(f"incomplete decision (missing: {', '.join(missing)})")
    return issues
