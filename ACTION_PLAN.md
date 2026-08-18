# MogBot Action Plan

MogBot is an agentic multi-agent interview coach. The Chrome extension is the first user-facing frontend prototype. `main.py` remains the agent floor manager: it owns session state, routing, worker threads, global vector memory, semantic cache, and the final decision about which agent tool to call next.

The agents are not just post-processing functions. Each agent receives a goal, observes session context, decides whether to use tools, retrieves from shared memory when helpful, writes useful outputs back to shared memory, returns a structured decision, and participates in feedback loops.

## Class Requirement Mapping

| Requirement | MogBot implementation |
| --- | --- |
| 5 or more agents | Primary agents: Job Search, Resume Analyzer, Question Generator, Interviewer, Evaluator, Devil's Advocate, Career Coach. Helper agents: Expert Review, Consistency Review, Bias/Safety Review, Reward Review. |
| Decides when or whether to use tools | Each agent returns `decision.tools_considered`, `decision.tools_used`, and `decision.action`. Agents may choose RAG, semantic cache, global vector memory, rubric scoring, helper review, reflection, or no tool. |
| Feedback loops | Evaluator scores feed Question Generator difficulty, Interviewer clarification, Devil's Advocate challenges, Career Coach report, and RewardReviewAgent. |
| RAG | All agents can retrieve job descriptions, resume chunks, question-bank examples, rubric examples, answer cases, and report patterns from the global vector database. |
| Reward system | Evaluator rubric scores, improvement deltas, challenge outcomes, confidence values, and final coaching quality become reward signals. |
| Prompt methods | Prompt templates include system prompts, task prompts, tool-selection prompts, RAG-context prompts, ReAct-style prompts, reflection prompts, critique prompts, and output-format prompts. |
| Reflection and review | Agents do private verification passes and helper agents review important outputs before `main.py` accepts them. |
| Multi-agent coordination | `main.py` coordinates concurrent agents, routes results, resolves next actions, and maintains shared state. |

Important note: agents may use private scratchpads or chain-of-thought-style deliberation internally, but stored outputs should include only concise `reasoning_summary` fields. Do not log or display raw private chain-of-thought.

## Core Architecture

```text
User
  -> Chrome extension UI
      -> sends job, resume, and answer data to main.py's Flask server thread
          -> GlobalVectorMemory
          -> SemanticCache
          -> PromptManager
          -> Agent worker threads
              -> JobSearchAgent
              -> ResumeAndRoleAnalyzer
              -> QuestionGenerator
              -> Interviewer
              -> Evaluator
              -> DevilsAdvocate
              -> CareerCoach
              -> helper_agents/*
          -> main.py returns questions, follow-ups, scores, and final report
```

The Chrome extension is the user interface. `main.py` is the only communication line to the agents. Agents are tools. Agents never call `input()`, never print user-facing prompts, and never directly call each other.

## Shared Global Vector Database

All important information should be embedded into a globally accessible vector database through `core/vector_memory.py`.

Every agent can read from this shared memory. Every agent can propose writes to this shared memory. `main.py` should own the memory service and enforce safe concurrent writes.

Recommended namespaces:

| Namespace | Stored data |
| --- | --- |
| `job_research` | Job descriptions, role keywords, required skills, company context, source snippets |
| `candidate_profile` | Resume chunks, extracted skills, projects, experience evidence, candidate gaps |
| `question_bank` | Generated questions, retrieved question examples, skill tags, difficulty labels |
| `conversation` | Interview turns, user answers, clarification prompts, challenge prompts |
| `rubric_examples` | Labeled answers, scoring examples, score rationales |
| `challenge_cases` | Weak-answer cases, contradiction examples, effective challenge prompts |
| `coaching_reports` | Final report sections, practice recommendations, improvement patterns |
| `cache:*` | Semantic cache entries for reusable job research, question plans, scores, and reports |

Concurrency rule: agent threads should not directly mutate private state. They should write through `GlobalVectorMemory`, which must use locks, queue-based writes, or the selected vector DB's transaction features.

Privacy rule: do not commit real resumes, private LinkedIn data, or real user transcripts. Local vector DB files under `data/vector_db/` should be treated as private runtime artifacts.

## Semantic Cache and Reuse

The project should use semantic caching to save time and token cost.

Examples:

- Similar job description already exists: reuse `job_research`.
- Similar candidate gap and role: reuse or adapt question plan.
- Similar answer and rubric context: reuse scoring examples.
- Similar final performance pattern: reuse coaching recommendations.

`core/cache_manager.py` should check global memory before expensive LLM calls. Cache entries must include metadata such as similarity score, source session, created time, prompt version, model name, and whether reuse is safe.

## Prompt Template System

Prompts should live in `prompts/agent_prompt_templates.py` and be rendered through `core/prompt_manager.py`.

Prompt types to use:

- System prompt: defines the agent role.
- Task prompt: defines the current goal.
- Tool-selection prompt: asks the agent to decide whether to use memory, RAG, cache, rubric, helper review, or no tool.
- RAG-context prompt: injects retrieved memory snippets.
- ReAct-style prompt: observe context, choose action/tool, return structured result.
- Reflection prompt: privately verify the answer before returning.
- Critique prompt: helper agents review another agent's output.
- Synthesis prompt: Career Coach combines evidence into final coaching.
- Output-format prompt: forces JSON-compatible `AgentMessage` output.

Do not store raw private chain-of-thought. Store a short public `reasoning_summary`.

## Data Contracts

Shared schemas are templated in `core/schemas.py`.

### ToolRequest

`main.py` creates a `ToolRequest` whenever it calls an agent.

```python
ToolRequest = {
    "schema_version": "1.0",
    "request_id": "uuid-string",
    "session_id": "uuid-string",
    "source": "main",
    "target_agent": "job_search | resume_analyzer | question_generator | interviewer | evaluator | devils_advocate | career_coach | helper_*",
    "task_type": "research_job | analyze_resume | generate_questions | plan_interview_move | evaluate_answer | challenge_answer | create_final_report | review_output",
    "timestamp": "ISO-8601 UTC timestamp",
    "payload": {},
    "session_context": {}
}
```

### AgentMessage

Every agent returns an `AgentMessage`.

```python
AgentMessage = {
    "schema_version": "1.0",
    "message_id": "uuid-string",
    "request_id": "uuid-string",
    "session_id": "uuid-string",
    "source_agent": "",
    "target": "main",
    "message_type": "",
    "timestamp": "ISO-8601 UTC timestamp",
    "status": "ok | needs_followup | error",
    "payload": {},
    "metadata": {
        "confidence": 0.0,
        "prompt_version": "",
        "cache_hit": False,
        "memory_records_used": []
    },
    "decision": {
        "action": "",
        "reasoning_summary": "",
        "tools_considered": [],
        "tools_used": [],
        "confidence": 0.0,
        "next_recommended_tool": ""
    }
}
```

### SessionState

`main.py` owns the official session state.

```python
SessionState = {
    "session_id": "uuid-string",
    "user_inputs": {
        "resume_text": "",
        "resume_path": "",
        "job_description": "",
        "company_name": "",
        "role_title": "",
        "job_posting_url": "",
        "linkedin_url": ""
    },
    "job_research": {},
    "candidate_profile": {},
    "question_plan": {},
    "current_question": {},
    "conversation_history": [],
    "evaluation_scores": [],
    "reward_signals": [],
    "interview_strategy_notes": [],
    "devil_advocate_flags": [],
    "helper_reviews": [],
    "memory_records": [],
    "cache_hits": [],
    "final_report": {},
    "status": "created | running | completed | error"
}
```

## Agent Responsibilities

### Job Search Agent

Owner: Zaid  
File: `agents/JobSearchAgent.py`

Agentic behavior:

- Decide whether job description alone is enough.
- Decide whether to retrieve similar job descriptions from memory.
- Decide whether optional search/RAG is needed.
- Store job requirements and interview focus areas in vector memory.
- Reuse cached `job_research` when similarity is high.

Output message type: `job_research`

### Resume and Role Analyzer

Owner: Zaid  
File: `agents/ResumeAndRoleAnalyzer.py`

Agentic behavior:

- Parse resume/profile evidence.
- Retrieve similar anonymized profile examples.
- Decide whether more evidence is needed.
- Reflect on unsupported claims.
- Store candidate evidence and skill gaps in vector memory.

Output message type: `candidate_profile`

### Question Generator

Owner: Zaid  
File: `agents/QuestionGenerator.py`

Agentic behavior:

- Retrieve question-bank examples.
- Use job research and candidate profile together.
- Decide stage and difficulty.
- Adapt based on reward signals from Evaluator.
- Cache reusable question plans.

Output message types: `question_plan`, `next_question`

### Interviewer

Owner: Shazaib  
File: `agents/Interviewer.py`

Agentic behavior:

- Recommend whether `main.py` should continue, clarify, rephrase, transition, or end.
- Retrieve similar conversation patterns from memory.
- Suggest user-facing wording without directly interacting with the user.
- Return tone and confidence metadata.

Output message type: `interview_strategy`

### Evaluator

Owner: Zaid  
File: `agents/Evaluator.py`

Agentic behavior:

- Score answers using role-specific rubric.
- Retrieve similar labeled answers and score examples.
- Create reward signals.
- Reflect on borderline scores.
- Ask helper agents for review when confidence is low.
- Recommend whether `main.py` should consider Interviewer or Devil's Advocate.

Output message type: `evaluation_result`

### Devil's Advocate

Owner: Zaid  
File: `agents/DevilsAdvocate.py`

Agentic behavior:

- Detect vague, inconsistent, unsupported, or overconfident answers.
- Retrieve similar weak-answer cases.
- Decide whether to challenge or skip.
- Reflect before challenging to avoid unfair pushback.
- Store challenge outcomes for future reward learning.

Output message types: `challenge_prompt`, `no_challenge`

### Career Coach

Owner: Ahmad  
File: `agents/CareerCoach.py`

Agentic behavior:

- Retrieve all session evidence from vector memory.
- Synthesize strengths, weaknesses, score trends, and next steps.
- Ask helper agents for expert and safety review.
- Reflect on whether report claims are evidence-grounded.
- Store reusable coaching patterns.

Output message type: `final_report`

## Helper Agents

Helper agents live in `helper_agents/`.

| Helper agent | Purpose |
| --- | --- |
| `ExpertReviewAgent.py` | Reviews important outputs for quality, completeness, and usefulness. |
| `ConsistencyReviewAgent.py` | Checks whether an output conflicts with job research, resume evidence, transcript, or prior scores. |
| `BiasSafetyReviewAgent.py` | Checks fairness, privacy, tone, and unsupported sensitive inferences. |
| `RewardReviewAgent.py` | Reviews whether reward signals and adaptation decisions match the intended policy. |

Helper agents are part of feedback loops. `main.py` decides when to call them.

## Main Flow

```text
1. main.py initializes GlobalVectorMemory, SemanticCache, PromptManager, SessionState, and worker threads.
2. The Chrome extension collects resume/profile and job input from the user.
3. The extension sends that data to the Flask server thread started by main.py.
4. main.py checks semantic cache for similar job descriptions.
5. main.py starts JobSearchAgent and ResumeAndRoleAnalyzer concurrently.
6. Both agents read/write global vector memory.
7. main.py waits for both results and stores them in SessionState.
8. main.py calls QuestionGenerator with job_research, candidate_profile, and retrieved memory context.
9. main.py returns a question to the extension.
10. The extension displays the question and captures the user's answer.
11. main.py stores the answer in vector memory and SessionState.
12. main.py calls Evaluator.
13. Evaluator returns score, reward signal, and recommended next tool.
14. main.py optionally calls Interviewer, Devil's Advocate, or helper review agents.
15. main.py adapts the next question through QuestionGenerator.
16. The extension continues displaying questions and collecting answers until the interview ends.
17. main.py calls CareerCoach.
18. main.py optionally calls helper review agents on the report.
19. The extension displays the final report and main.py stores reusable patterns in memory/cache.
```

## Team Tasklist

### Ahmad Nadeem

- [x] In `main.py`, create the floor-manager session runner.
- [x] In `main.py`, initialize `GlobalVectorMemory`, `SemanticCache`, and `PromptManager`.
- [x] In `main.py`, define or import `ToolRequest`, `AgentMessage`, `AgentDecision`, and `SessionState`.
- [x] In `main.py`, start worker threads using `core/agent_runtime.py`.
- [ ] In `main.py`, run JobSearchAgent and ResumeAndRoleAnalyzer concurrently.
- [ ] In `main.py`, make all agent routing decisions from structured `decision` metadata.
- [ ] In `main.py`, call helper review agents when confidence is low or output importance is high.
- [ ] In `main.py`, track reward signals, cache hits, memory writes, and helper reviews.
- [ ] In `core/vector_memory.py`, implement the chosen vector database backend.
- [ ] In `core/cache_manager.py`, implement semantic cache lookup and storage.
- [ ] In `agents/CareerCoach.py`, implement evidence-grounded final report generation.

### Shazaib Dawood

- [ ] In `chrome_extension/`, implement the user-facing setup, interview, and summary flow.
- [ ] In the extension, collect resume/profile input, job input, and interview answers.
- [ ] In the extension, display generated questions, clarifications, challenge prompts, transitions, and final report.
- [x] Connect the extension to `main.py` through the local Flask server thread using the shared request/response contracts.
- [ ] In `agents/Interviewer.py`, return `interview_strategy` recommendations only.
- [ ] In `prompts/agent_prompt_templates.py`, improve user-facing tone templates.
- [ ] In `core/prompt_manager.py`, help standardize prompt rendering for the UI-facing outputs.
- [ ] Ensure no agent calls `input()` or prints user-facing text.

### Zaid Haidry

- [ ] In `agents/JobSearchAgent.py`, implement job research, cache reuse, RAG retrieval, and memory writes.
- [ ] In `agents/ResumeAndRoleAnalyzer.py`, implement resume/profile analysis, evidence retrieval, reflection, and memory writes.
- [ ] In `agents/QuestionGenerator.py`, implement RAG-backed question generation, cache reuse, and reward-aware adaptation.
- [ ] In `agents/Evaluator.py`, implement rubric scoring, reward signals, memory retrieval, and helper review for borderline scores.
- [ ] In `agents/DevilsAdvocate.py`, implement adversarial challenge decisions, challenge memory retrieval, and challenge-outcome logging.
- [ ] In `helper_agents/ConsistencyReviewAgent.py`, implement consistency checks.
- [ ] In `helper_agents/RewardReviewAgent.py`, implement reward-policy review.
- [ ] Add labeled examples under `data/evaluation_examples/`.
- [ ] Add reusable question examples under `data/question_bank/`.

## GitHub Collaboration Rules

- Use branch names like `ahmad-memory-runtime`, `shazaib-main-ui-prompts`, and `zaid-agentic-tools`.
- Pull latest `main` before starting work.
- Keep pull requests small: one agent, one core module, one helper agent, or one `main.py` section at a time.
- Treat `main.py`, `ACTION_PLAN.md`, `core/schemas.py`, and prompt contracts as shared files.
- If a schema changes, update `core/schemas.py`, `ACTION_PLAN.md`, and affected agent TODOs in the same pull request.
- Do not commit API keys, real resumes, private LinkedIn data, vector DB runtime files, or real transcripts.

## Milestones

### Milestone 1: Agentic Prototype Foundations

- [x] Main agent tools return `AgentMessage`-style dictionaries with `decision` metadata.
- [x] `core/` includes schemas, runtime, prompt manager, vector memory, and semantic cache.
- [x] `prompts/` includes shared prompt templates and RAG variants.
- [x] `helper_agents/` includes expert, consistency, safety, and reward-policy review helpers.
- [x] `README.md` documents the file structure.

### Milestone 2: Chrome Extension Frontend Prototype

- [x] Chrome extension collects pasted job description and resume text.
- [x] Chrome extension runs a backend-backed interview flow.
- [x] Chrome extension includes the future SMS option as disabled or coming soon.
- [x] Extension payload shape is sent to the local Flask server thread.
- [x] Agents do not directly interact with the user.

### Milestone 3: Shared Memory and Cache

- [x] Global vector database is initialized from `main.py`.
- [ ] Job, resume, questions, answers, scores, challenges, and reports are embedded.
- [x] Semantic cache reuses similar job descriptions and generated material.
- [x] Concurrent memory access is safe for the local threaded runtime.

### Milestone 4: Extension Backend Integration

- [x] `main.py` starts the Flask server thread for health, session start, session read, and answer submission endpoints.
- [x] Chrome extension sends job, resume, and answer payloads to `main.py` through Flask.
- [ ] Persist sessions outside process memory.
- [ ] Add end-to-end tests for the full extension-to-backend interview flow.

### Milestone 5: Feedback and Reward Loops

- [ ] Evaluator produces reward signals.
- [ ] Question Generator adapts difficulty from rewards.
- [ ] Devil's Advocate challenge decisions are evaluated.
- [ ] Helper agents review borderline or important outputs.

### Milestone 6: Evaluation

- [ ] Add labeled acceptable/needs-follow-up answers.
- [ ] Compare Devil's Advocate decisions to labels.
- [ ] Review score consistency across sessions.
- [ ] Use logs/traces to confirm tool choice, memory retrieval, cache reuse, and feedback loops.
