# MogBot

MogBot is an adaptive multi-agent AI interview coach for job seekers. The system helps a candidate prepare for a specific role by analyzing the job description, analyzing the candidate's resume/profile, generating adaptive interview questions, evaluating answers, challenging weak responses, and producing a final coaching report.

## Team Members

- Shazaib Dawood
- Zaid Haidry
- Ahmad Nadeem

## Agentic AI Design

MogBot is designed as an agentic multi-agent system, not a fixed LLM pipeline.

`web/` is the primary frontend: a static site that collects the job description, resume text, and interview answers, then sends them to the Flask server started by `main.py`. `chrome_extension/` is an earlier prototype of the same flow, kept for reference.

`main.py` remains the agent floor manager. It owns the session state, starts agent threads, controls routing, talks to the global vector memory/cache layers, and decides which agent tool should be called next.

Each agent is treated as a tool. Agents receive structured requests from `main.py`, decide whether to use tools, retrieve from shared vector memory, optionally use semantic cache, return structured decisions, and participate in feedback loops.

Agentic AI concepts used:

- 5+ specialized agents
- Tool-selection decisions
- Shared global vector database
- RAG over job, resume, question, answer, rubric, and coaching data
- Semantic caching for similar job descriptions and generated material
- Prompt templates for system, task, RAG, ReAct-style, reflection, critique, and output-format prompts
- Private reasoning/reflection with public reasoning summaries
- Reward signals from evaluator scores
- Feedback loops between Evaluator, Question Generator, Interviewer, Devil's Advocate, Career Coach, and helper review agents
- Helper agents for expert review, consistency review, safety review, and reward-policy review

## Main Runtime Flow

```text
User
  -> Chrome extension
      -> sends job, resume, and answers to main.py's Flask server thread
          -> JobSearchAgent and ResumeAndRoleAnalyzer run concurrently
          -> QuestionGenerator creates role/candidate-specific questions
          -> Evaluator scores each answer and creates reward signals
          -> main.py decides whether to call Interviewer, Devil's Advocate, or QuestionGenerator
          -> CareerCoach creates the final coaching report
          -> helper_agents review important or borderline outputs
```

Agents do not call `input()`, print user-facing prompts, or directly call each other. The extension handles the user experience, and all agent communication still goes through `main.py`.

## File and Directory Structure

```text
.
|-- main.py
|-- ACTION_PLAN.md
|-- backend/
|   |-- __init__.py
|   `-- app.py
|-- web/
|   |-- index.html
|   |-- styles.css
|   |-- app.js
|   `-- assets/
|       `-- mark.svg
|-- chrome_extension/
|   |-- manifest.json
|   |-- popup.html
|   |-- popup.css
|   |-- popup.js
|   |-- README.md
|   `-- assets/
|       `-- mogbot-mark.svg
|-- agents/
|   |-- JobSearchAgent.py
|   |-- ResumeAndRoleAnalyzer.py
|   |-- QuestionGenerator.py
|   |-- Interviewer.py
|   |-- Evaluator.py
|   |-- DevilsAdvocate.py
|   `-- CareerCoach.py
|-- helper_agents/
|   |-- ExpertReviewAgent.py
|   |-- ConsistencyReviewAgent.py
|   |-- BiasSafetyReviewAgent.py
|   `-- RewardReviewAgent.py
|-- core/
|   |-- schemas.py
|   |-- vector_memory.py
|   |-- cache_manager.py
|   |-- prompt_manager.py
|   `-- agent_runtime.py
|-- prompts/
|   `-- agent_prompt_templates.py
|-- data/
|   |-- vector_db/
|   |-- cache/
|   |-- question_bank/
|   `-- evaluation_examples/
|-- docs/
|   `-- AGENTIC_AI_MAPPING.md
|-- project proposal.md
`-- proposal2.md
```

## Implemented Pieces

The repo currently includes these working prototype pieces:

- `core/schemas.py`: shared typed dictionaries and Pydantic models for `ToolRequest`, `AgentMessage`, `AgentDecision`, memory records, user inputs, and session state.
- `core/vector_memory.py`: local deterministic vector memory with namespace filtering, similarity scoring, and JSON persistence.
- `core/cache_manager.py`: semantic cache built on top of vector memory.
- `core/prompt_manager.py`: prompt renderer with required-field validation.
- `core/agent_runtime.py`: threaded worker runtime with retries, timeouts, structured errors, and graceful shutdown.
- `backend/app.py`: Flask route wrapper used by `main.py`; it accepts sessions and answers, then forwards them to the floor manager.
- `prompts/agent_prompt_templates.py`: system, task, RAG, ReAct-style, reflection, critique, and output prompts.
- `helper_agents/*.py`: expert, consistency, safety, and reward-policy review helpers.
- `web/`: static frontend (landing page + session flow) for paste-in job/resume input and browser-based interviews.
- `chrome_extension/`: earlier frontend prototype, same flow in a popup.
- `data/vector_db/`: local vector database runtime files.
- `data/cache/`: local semantic-cache runtime files.
- `data/question_bank/`: reusable question examples.
- `data/evaluation_examples/`: labeled answers for evaluator and Devil's Advocate tests.

## Primary Agents

| Agent | Role |
| --- | --- |
| Job Search Agent | Extracts role requirements, job keywords, company context, and interview focus areas. |
| Resume and Role Analyzer | Extracts candidate skills, evidence, gaps, and profile information. |
| Question Generator | Generates and adapts interview questions using job research, candidate profile, memory, and reward signals. |
| Interviewer | Recommends conversation strategy, clarification prompts, and transitions for `main.py`. |
| Evaluator | Scores answers using a rubric and produces reward signals. |
| Devil's Advocate | Challenges vague, inconsistent, unsupported, or overconfident answers. |
| Career Coach | Produces the final evidence-grounded coaching report. |

## Helper Agents

| Helper agent | Role |
| --- | --- |
| ExpertReviewAgent | Reviews important outputs for quality and usefulness. |
| ConsistencyReviewAgent | Checks whether outputs conflict with evidence or session history. |
| BiasSafetyReviewAgent | Checks fairness, privacy, tone, and unsupported sensitive inferences. |
| RewardReviewAgent | Reviews reward signals and adaptation decisions. |

## Shared Data Contracts

All agent calls should use the shared schemas from `core/schemas.py`.

`main.py` creates a `ToolRequest` when it calls an agent. The agent returns an `AgentMessage`. Every `AgentMessage` should include a public decision object:

```python
"decision": {
    "action": "",
    "reasoning_summary": "",
    "tools_considered": [],
    "tools_used": [],
    "confidence": 0.0,
    "next_recommended_tool": ""
}
```

Do not store raw private chain-of-thought. Store only concise reasoning summaries.

## Global Vector Memory

All agents should use one shared vector database through `core/vector_memory.py`.

Planned namespaces:

- `job_research`
- `candidate_profile`
- `question_bank`
- `conversation`
- `rubric_examples`
- `challenge_cases`
- `coaching_reports`
- `cache:*`

This lets agents reuse information across the full interview session and across similar future sessions while reducing token cost.

## Requirements

Current runtime:

- Python 3.10+
- Flask
- Pydantic

Possible future packages include LangChain, LangGraph, LangSmith, FAISS or Chroma, and an LLM provider SDK.

## Running

Backend API:

```bash
python main.py
```

Web frontend (local):

```bash
cd web && python -m http.server 8000
```

Open `http://127.0.0.1:8000` with `main.py` running at `http://127.0.0.1:5000` in another terminal. `web/app.js` targets `127.0.0.1:5000` automatically on localhost.

Deploying the frontend and backend to different origins: set `<meta name="mogbot-api-base" content="https://your-backend-host">` in `web/index.html` before publishing, and make sure the backend's CORS policy allows that origin.

Chrome extension prototype (legacy):

1. Open `chrome://extensions`.
2. Enable Developer mode.
3. Click Load unpacked.
4. Select the `chrome_extension` folder.
5. Keep `main.py` running at `http://127.0.0.1:5000`.

Current Python smoke-test command:

```bash
python -c "import main; print(sorted(main.AGENT_RUN_REGISTRY.keys()))"
```

For quick testing, `GET /sessions/<session_id>/inputs` returns the exact job and resume text stored in the `main.py` floor-manager session state.

## Development Notes

- Keep all direct user interaction inside the Chrome extension for the frontend path.
- Keep agents non-interactive and tool-shaped.
- Keep `main.py` as the only layer that routes between agents.
- Update `ACTION_PLAN.md` when changing architecture or shared data contracts.
- Do not commit API keys, real resumes, private LinkedIn data, real transcripts, or local vector database runtime files.
