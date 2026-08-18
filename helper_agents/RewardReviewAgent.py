"""Reward review helper agent."""

from typing import List, Optional

from core.schemas import AgentMessage, ToolRequest

_HARD_THRESHOLD = 80.0   # avg score at which diff should rise
_EASY_THRESHOLD = 50.0   # avg score at which diff should fall
_DIFFICULTY_LEVELS = ["easy", "medium", "hard"]
_CHALLENGE_SCORE_CEILING = 60.0  # Devils adv should only trigger on weak answers


def run(request: ToolRequest) -> AgentMessage:
    """Review reward signals and adaptation decisions."""
    session_context = request.get("session_context", {})
    payload = request.get("payload", {})

    evaluation_scores: List[float] = session_context.get("evaluation_scores", [])
    reward_signals: List[float] = session_context.get("reward_signals", [])
    difficulty_level: str = session_context.get("difficulty_level", "medium")
    prior_difficulty: str = session_context.get("prior_difficulty", difficulty_level)
    devil_advocate_flags: List[dict] = session_context.get("devil_advocate_flags", [])

    proposed_reward: Optional[float] = payload.get("reward_signal")

    policy_violations: List[str] = []
    notes: List[str] = []

    reward_delta: float = 0.0
    if len(evaluation_scores) >= 2:
        reward_delta = round(evaluation_scores[-1] - evaluation_scores[-2], 4)
    elif proposed_reward is not None and reward_signals:
        reward_delta = round(proposed_reward - reward_signals[-1], 4)

    avg_score: Optional[float] = None
    if evaluation_scores:
        recent = evaluation_scores[-3:]
        avg_score = sum(recent) / len(recent)

    adaptation_quality: str = "ok"
    if avg_score is not None:
        expected_direction: Optional[str] = None
        if avg_score >= _HARD_THRESHOLD:
            expected_direction = "up"
        elif avg_score <= _EASY_THRESHOLD:
            expected_direction = "down"

        if expected_direction == "up":
            cur_idx = _DIFFICULTY_LEVELS.index(difficulty_level) if difficulty_level in _DIFFICULTY_LEVELS else 1
            pri_idx = _DIFFICULTY_LEVELS.index(prior_difficulty) if prior_difficulty in _DIFFICULTY_LEVELS else 1
            if cur_idx <= pri_idx and cur_idx < len(_DIFFICULTY_LEVELS) - 1:
                adaptation_quality = "under_adapted"
                policy_violations.append(
                    f"Avg score {avg_score:.1f} >= {_HARD_THRESHOLD} but difficulty did not increase "
                    f"(prior={prior_difficulty}, current={difficulty_level})."
                )
        elif expected_direction == "down":
            cur_idx = _DIFFICULTY_LEVELS.index(difficulty_level) if difficulty_level in _DIFFICULTY_LEVELS else 1
            pri_idx = _DIFFICULTY_LEVELS.index(prior_difficulty) if prior_difficulty in _DIFFICULTY_LEVELS else 1
            if cur_idx >= pri_idx and cur_idx > 0:
                adaptation_quality = "under_adapted"
                policy_violations.append(
                    f"Avg score {avg_score:.1f} <= {_EASY_THRESHOLD} but difficulty did not decrease "
                    f"(prior={prior_difficulty}, current={difficulty_level})."
                )
        else:
            notes.append(f"Avg score {avg_score:.1f} is within stable band; no difficulty change expected.")

    for flag in devil_advocate_flags:
        score_at_challenge = flag.get("score")
        if score_at_challenge is not None and score_at_challenge > _CHALLENGE_SCORE_CEILING:
            policy_violations.append(
                f"Devil's Advocate triggered on a strong answer (score={score_at_challenge:.1f} > "
                f"{_CHALLENGE_SCORE_CEILING}). Challenges should target weak or inconsistent answers only."
            )

    if policy_violations:
        if adaptation_quality == "under_adapted":
            recommended_adjustment = (
                "increase_difficulty" if avg_score is not None and avg_score >= _HARD_THRESHOLD
                else "decrease_difficulty"
            )
        else:
            recommended_adjustment = "review_challenge_policy"
        confidence = 0.55
        reasoning_summary = (
            f"Reward policy violations found ({len(policy_violations)}). "
            f"reward_delta={reward_delta:+.4f}, adaptation_quality={adaptation_quality}."
        )
        next_tool = "helper_consistency_review"
    else:
        recommended_adjustment = "maintain"
        confidence = 0.88
        reasoning_summary = (
            f"Reward signals match policy. reward_delta={reward_delta:+.4f}, "
            f"adaptation_quality={adaptation_quality}."
        )
        next_tool = "none"

    return {
        "schema_version": "1.0",
        "request_id": request.get("request_id", ""),
        "session_id": request.get("session_id", ""),
        "source_agent": "helper_reward_review",
        "target": "main",
        "message_type": "reward_review",
        "status": "ok",
        "payload": {
            "reward_delta": reward_delta,
            "adaptation_quality": adaptation_quality,
            "recommended_adjustment": recommended_adjustment,
            "policy_violations": policy_violations,
            "notes": notes,
        },
        "decision": {
            "action": "review_reward_policy",
            "reasoning_summary": reasoning_summary,
            "tools_considered": ["evaluation_scores", "devil_advocate_flags", "difficulty_level"],
            "tools_used": ["session_context"],
            "confidence": confidence,
            "next_recommended_tool": next_tool,
        },
    }
