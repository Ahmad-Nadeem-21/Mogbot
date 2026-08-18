Member 1: Zaid Haidry zhaid3   
Member 2: Shazaib Dawood sdawo2  
Member 3: Ahmad Nadeem anade7 

Adaptive AI interview coach (MogBot)  
**Problem Statement:** 

* The problem we are trying to solve is the lack of easy-to-access AI help there is to help job seekers prepare for their interviews in the incredibly tough job market. 

**Users:** 

* The users will be job seekers willing to improve their interview skills and tailor their résumés for a specific job. This project can be used for internship or full-time roles, and can help simulate the nervous environment interviewers may feel in a real interview.   

**Agent’s role:** 

* Agent 1: Resume and role analyzer agent:   
  * Responsibility: Parses the user's uploaded resume and job description. Identifies key skills, experience gaps, relevant keywords, and seniority level.  
  * Reasoning Logic: Plan to have a reflection so the agent can review its own feedback and fix inaccurate information.   
  * Tools/Resources: Plan to use RAG for the uploaded resume as a PDF and the job description.   
  * Data / Documents: Uploaded resume (PDF), job description (text input), and optional LinkedIn profile URL.   
* Agent 2: Question Generator Agent:  
  * Responsibility: Uses the candidate profile from the resume and role analyzer agent to dynamically generate a multiple-question bank: a phone screen stage, a behavioral stage (STAR-format questions targeting weak resume areas), and a technical stage (role-specific problems). Adapts question difficulty based on responses.   
  * Reasoning Logic: Plan to use ReAct to generate well-thought-out questions that are based on previous answers.    
  * Tools / Resources: Plan to use RAG for industry-related questions from different data sets. Difficulty can be adjusted based on the live score.  
  * Data / Documents: Question banks that are related to industry and candidate profile from the first agent.   
* Agent 3: Devil’s Advocate Agent :  
  * Responsibility: Gives a follow-up challenge on low-scoring responses.   
  * Reasoning Logic: Using ReAct to find the weakest answer and think of the biggest challenge for the issue.    
  * Tools/Resources: Access to the full conversation history and evaluator scores.   
  * Data/Documents: Low-scoring answers and conversation history.   
* Agent 4: Interviewer Agent :  
  * Responsibility: Conducts the live interview in the frontend. Presents questions, listens to user responses, maintains conversational context, and passes each answer to the Evaluator agent.  
  * Reasoning Logic: Using ReAct to think whether an answer should be accepted, or to ask a follow-up, or to send instructions to the devil's advocate agent.   
  * Tools / Resources: Conversation memory  
  * Data / Documents: Live conversation history, questions from Agent 2,   
* Agent 5: Evaluator:  
  * Responsibility: Responsible for scoring each answer in real time and passing the score back to the question generator agent.    
  * Reasoning Logic: Plan to use reflection to ensure scoring is accurate throughout the program.  
  * Tools/Resources: need a rubric for scoring.   
  * Data/Documents: Answer transcripts from Agent 3, role-specific evaluation rubrics.  
* Agent 6: Career Coach:  
  * Responsibility: Responsible for managing the session so the interview can move forward, and gives an effective coaching report at the end of the session to give criticism to the user.   
  * Reasoning Logic: Plan to use reflection to ensure the coaching report is accurate and effective for the user.   
  * Tools/Resources: Content of all agent outputs.   
  * Data/Documents: All scores, agent transcripts, and agent outputs from the session. 

**Collaboration:**   
The project will involve collaborative, adversarial, and managerial types:  

* Career Coach with Question Generator and Evaluator:   
  * The Career Coach agent orchestrates the session, assigns tasks to the Question Generator and Evaluator  
* Evaluator and Devil's Advocate:   
  * The Evaluator agent and Devil's Advocate agent challenge each other's scores. The Devil's Advocate may escalate a question even when the Evaluator gives a passing score, and the career coach agent can resolve this conflict.   
* Resume analyzer, question Generator, Interviewer   
  * The Resume Analyzer, Question Generator, and Interviewer will work together to tailor the interview experience. 

**Workflow:**

| Step | Agents | Action |
| :---- | :---- | :---- |
| **1** | Resume Analyzer | Agent parses resume and analyzes candidate profile  |
| **2** | Question Generator | Receives candidate profile and generates questions.   |
| **3** | Devils’ Advocate Agent  | Gives follow-up challenges based on responses  |
| **4** | Interview Agent  | Conducts live interviews in the frontend  |
| **5** | Evaluator  | Score each answer  |
| **6** | Career Coach  | Monitors the session and resolves conflicts. Gives positive feedback at the end.  |

**Technical Setup:**

* Frontend  
  * Using React to allow the user to upload a resume, show the conversation, and show the live scores.   
* Backend   
  * Framework: LangGraph with LangChain for individual agent chains and tool integrations. LangSmith for debugging agent interactions.   
  * LLM: Claude 3.5 Sonnet with Anthropic API for all agents. 

**Evaluation Plan:**   
We plan to evaluate the system along three criteria:

1. Answer Quality: Volunteers go through mock interviews with the system rather than with a real person. Then compare self-reported confidence and interviewer evaluations across both sessions.   
2. Agent Faithfulness: Using LangSmith traces, track whether the question generator creates harder questions by evaluating whether evaluation scores are higher across multiple sessions/interviews.  
3. Adversarial Trigger: Label 50 potential answers as either 'needs follow-up' or 'acceptable'. Then, evaluate how well the Devil's Advocate did at identifying when to push back on an answer, and compare that to the labels given by humans**.**

**Frameworks:**

* LangGraph   
  * Multi-agent state graph orchestration   
* LangChain   
  * Agent chains, tool use, RAG   
* LangSmith   
  * Agent tracing and evaluation   
* FAISS / Chroma /text-embedding-3-large / Pinecone  
  * Vector store for RAG   
* Anthropic Claude API   
  * Primary LLM backbone   
* React \+ Tailwind   
  * Frontend UI framework   
* FastAPI Backend server (Pydantic)  
  * Whisper API Optional speech-to-text  
* Docker/Kubernetes Deployment?

