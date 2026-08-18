# Agentic AI Mapping

MogBot should be implemented as a multi-agent system, not a simple chain of LLM calls. The system is agentic because each agent has a role-specific goal, observes shared state, decides whether to use tools, writes to or reads from shared memory, and returns structured decisions to `main.py`.

## Required Concepts

- Multi-agent coordination: `main.py` coordinates seven primary agents and optional helper review agents.
- Tool choice: agents decide whether to use RAG, global vector memory, semantic cache, prompt templates, rubric scoring, helper review, or reflection.
- RAG: job descriptions, resume chunks, question banks, rubric examples, answer cases, and final coaching patterns are embedded in shared vector memory.
- Feedback loops: evaluator rewards change question difficulty, trigger follow-ups, and inform final coaching.
- Reward system: rubric scores, improvement deltas, challenge outcomes, and confidence values act as reward signals.
- Reflection: agents run private verification steps and return concise reasoning summaries.
- ReAct-style behavior: agents observe state, choose tools/actions, and return an action recommendation.
- Helper-agent review: expert, consistency, safety, and reward reviewers critique important outputs before acceptance.
- Semantic caching: similar job descriptions, question plans, scoring cases, and coaching recommendations can be reused to reduce latency and token cost.

## Important Rule

Agents may use private scratchpads or chain-of-thought-style processing internally, but the project should store only concise `reasoning_summary` fields in logs, cache, vector memory, and user-facing output.
