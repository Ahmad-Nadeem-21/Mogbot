Abstract - Preparing for job interviews can be a tough task for
students and job seekers. Many of the tools available today often
feel too generic, failing to consider an individual’s unique
background or the specific requirements of the role that they're
applying for. This is where our interview coach MogBot comes in
to solve this problem.
Introduction
The job market today is tougher than ever, and many
applicants find it hard to prepare for interviews in a way that
makes them feel confident and ready. While there are plenty of
online tools offering generic interview questions or resume tips,
these often fall short because they don’t take into account
individual backgrounds, areas needing improvement, or the
specific job someone is aiming for. This means that candidates
would have access to practice materials that feel too standard
and are not able to mock a real interview.
What we aim to solve is the absence of an accessible AI tool
that helps job seekers prepare for interviews in a way that's
personalized and engaging. Our primary audience includes
students and job seekers who are looking to land internships or
full time roles and want to improve both their interview skills
and their resumes to match potential positions.
Most existing products in this area tend to focus on just one
aspect, like analyzing resumes based on keywords, providing
static mock interview prompts, or offering generic feedback.
However, our idea is to create a well detailed solution that
combines all these elements. The AI system will be a
coordinated system where resume analysis, tailored question
generation, dynamic follow-up questions, real-time scoring, and
personalized coaching come together seamlessly. This design
means that the interview experience adapts based on how the
user responds, making the mock interview feel more real and
relevant.
In the following sections of this proposal, we will outline our
vision for the system architecture, detailing the role of each
component. This is to help explain how they interact with one
another and share our plans for implementation and evaluation.
We’ll also discuss our current progress and what’s left to do.
Agent Design and Coordination
Architecture
MogBot is created as a team of specialized agents, each
handling a different part of the interview preparation process.
This teamwork is organized around a shared workflow, allowing
the agents to smoothly communicate and share important
information and feedback throughout the interview prep.
At the start, the system gathers essential information from
the user, like a resume in PDF format, the job description in text
form, and optionally, a LinkedIn profile URL. The Resume and
Role Analyzer takes this information and digs into the relevant
skills, experiences, and keywords, while also identifying any
gaps or the likely seniority level for the role. With this candidate
profile in hand, the Question Generator steps in and crafts a
personalized list of interview questions that covers different
stages, from phone screenings to behavioral and technical
interviews.
During the actual interview, the Interviewer poses questions
to the user and keeps the conversation flowing. After each
response, it gets sent to the Evaluator for scoring. If any answers
are rated low or seem uncertain, those responses might be
challenged further by the Devil’s Advocate agent, who brings
up additional questions or concerns. Throughout the session, the
Career Coach takes charge, ensuring everything runs smoothly,
managing any disagreements between agents, and eventually
putting together a final coaching report for the user.
This setup features three coordination styles. First, it’s
collaborative, as the Resume Analyzer, Question Generator, and
Interviewer join forces to tailor the interview experience.
Second, it has an adversarial aspect, since the Evaluator and
Devil’s Advocate push for the performance of the user’s
responses. Lastly, it’s manageable, thanks to the Career Coach
overseeing the whole session and settling any conflicts that arise.
This combination aims to provide a more realistic and flexible
mock interview experience than what you would find with a
typical chatbot.

Resume and Role Analyzer Agent
The Resume and Role Analyzer takes a close look at the
resume and job description you upload to create a detailed
candidate profile. It focuses on pinpointing key skills, relevant
experiences, any qualifications that might be lacking, important
keywords, and gives an estimate of the seniority level required
for the role. By using RAG, the analyzer stays focused on your
specific materials instead of making broad assumptions. It also
includes a step for reflection, allowing it to review and refine its
feedback if the initial analysis seems off.
Question Generator Agent
The Question Generator takes the candidate profile created
by the Resume and Role Analyzer to help craft a personalized
interview plan and a set of questions. It organizes the questions
into three main stages: a phone screen, a behavioral stage that
uses STAR style prompts to address areas in the resume that may
need more depth, and a technical stage that focuses on the
specific requirements of the role. What’s really great is that this
tool adjusts the complexity of the questions based on how the
candidate responds and their live evaluation scores. To make the
interview process even smoother, it also incorporates ReAct
style reasoning to choose questions thoughtfully and plan
follow-ups effectively.
Devil’s Advocate Agent
The Devil's Advocate Agent acts like a tough interviewer
during conversations. Its job is to push back on unclear or weak
answers, helping to bring more depth and clarity to the
discussion. By keeping an eye on previous responses and
feedback, it knows when it's time to dig a little deeper. The idea
is to create a realistic interview experience, encouraging you to
think critically and strengthen your arguments, rather than just
giving vague answers.
Interviewer Agent
The Interviewer Agent oversees the live interview in a
friendly and engaging way. It presents questions to the user,
listens to their responses, and keeps the conversation flowing
naturally. The agent decides whether to continue the discussion,
ask a follow up question, or pass the response along to another
specialist for a deeper look. Essentially, this agent acts as the
bridge between the user and the backend team of experts. Its goal
is to understand if a response should be taken at face value or if
it’s to dive deeper into the conversation for more information.
Evaluator Agent
The Evaluator Agent assesses each response as it comes in,
using a specific set of guidelines tailored to the role. The scores
provided are fed back into the system, allowing the Question
Generator to tweak the difficulty of future questions and
enabling the Devil’s Advocate to determine if intervention is
necessary. Throughout the session, reflection plays a key role in
ensuring that scoring remains consistent. This agent is crucial
for maintaining an effective feedback loop since it impacts both
how the system improves, and the overall quality of coaching
provided.
Career Coach Agent
The Career Coach Agent plays a key role in overseeing the
entire coaching session and putting together the final report. It
combines scores, chat history, and information from other
agents to offer valuable feedback and suggestions for
improvement. Additionally, this agent serves as the guiding
force in the process, coordinating the efforts of the other agents
and helping to sort out any conflicts. For example, if the
Evaluator gives a borderline score but the Devil’s Advocate
thinks the situation should be escalated, the Career Coach Agent
steps in to help resolve the issue.
Interaction Logic
The system is designed to guide users through a structured
interview process in six stages. It starts with the Resume and
Role Analyzer, which reads the uploaded resume and job
description to build a candidate profile tailored to the role. Next,
the Question Generator takes that profile and creates a sequence
of interview questions specifically for the candidate.
As the interview unfolds, the Interviewer presents one
question at a time to the user and records their responses. After
each answer, the Evaluator assesses the quality on the spot using
a scoring rubric that reflects what’s expected for the role. If a
response is unclear or inconsistent, the Devil’s Advocate Agent
steps in to challenge the candidate with a follow up prompt to
encourage deeper thinking.
Lastly, the Career Coach reviews the entire session and
compiles a final coaching report highlighting strengths,
weaknesses, and personalized recommendations for
improvement.
What makes this system unique is its ability to adapt. Instead
of following a rigid script, it responds to the candidate’s answers
and strong responses may lead to more challenging questions,
while weaker ones can prompt clarifications or deeper probing.
This creates a dynamic feedback loop where earlier responses
influence the flow of the interview, and because all components
share access to the ongoing dialogue and context, the interview
feels diverse rather than isolated questions.

Implementation Plan
The frontend will be built with React. It will allow users to
upload a resume, enter a job description, participate in the mock
interview, and view live scores and conversation history. The
design goal is to make the system easy to use while still showing
enough session detail for the user to understand how
performance changes over time.
The backend will use FastAPI with Pydantic for API
structure and validation. Agent orchestration will be
implemented using LangGraph, while individual agents and tool
integrations will be implemented with LangChain. LangSmith
will be used to trace agent interactions, debug errors, and
evaluate whether the system is behaving properly.
The primary language model planned for the project is
Claude 3.5 Sonnet through the Anthropic API. For RAG, we
plan to embed the uploaded resume and related supporting data
into a vector database such as FAISS, Chroma, or Pinecone,
potentially using text-embedding-3-large for embeddings. An
optional extension is support for speech to text, using the
Whisper API so the system can eventually accept spoken
responses in addition to typed ones. If time permits, the project
may also explore deployment using Docker and possibly
Kubernetes.

Evaluation Plan
We're going to evaluate MogBot based on 3 main criteria:
the quality of its answers, how faithful it is to the intended
process, and how well it handles challenging situations.
For answer quality, we'll have other students participate in
mock interviews with MogBot and compare their experiences to
more traditional methods of interview preparation, like using a
static list of questions or going through sessions led by a human
if that's possible. We'll look at things like how confident the
participants feel, how useful they find the feedback, and how
external judges rate the quality of the responses.
We will also use LangSmith traces to see if the Question
Generator is truly adjusting the difficulty based on previous
scores and if the Interviewer and Evaluator are sticking to the
intended workflow. This will help us figure out if the agents are
following the design as they should or if they’re just giving
answers that seem correct briefly.
For testing adversarial trigger performance, we'll create a set
of labeled answers, marking them as either “acceptable” or
“needs more.” We will then compare the decisions made by the
Devil’s Advocate Agent against these labels to see if it knows
when to escalate issues effectively.
Standard Cases:
1. Standard software engineering internship candidate with
strong matching resume.
2. Standard data analyst candidate with moderate skill
alignment.
3. Standard behavioral interview with clear STAR-format
answers.
4. Standard technical interview where the user answers
correctly and earns harder follow-up questions.
Edge Cases:
5. Edge case where the resume is sparse or missing expected
role keywords.
6. Edge case where the job description is vague, noisy, or
unusually short.
7. Edge case where the user gives extremely short one-sentence
responses.
Robust Cases:
8. Robustness case where the user gives partially correct but
overconfident answers.
9. Robustness case where the user changes topics or gives
inconsistent details across the interview.
10. Robustness case where the Evaluator gives a borderline
passing score and the Devil’s Advocate must decide
whether to challenge.
Current Progress
Right now, our team has made some great progress on the
project. We’ve laid out the main concept, figured out who our
target users are, and outlined our agent architecture. We've also
chosen the primary frameworks we’ll be using and set up an
initial strategy for evaluation. Plus, we’ve clearly mapped out
the workflow and defined the role of each agent involved.
Looking ahead, we still have some important tasks to tackle.
We need to implement the LangGraph workflow and build the
React frontend. We'll also work on features like allowing users
to upload and retrieve resumes, creating a scoring rubric for our
Evaluator, and defining sources for our question bank tailored to
different roles. Additionally, we’ll implement the Devil’s
Advocate Agent escalation process and design the final
coaching report.
On top of that, we have to compile our evaluation dataset,
run some pilot tests, analyze the data we collect in LangSmith,
and refine our system based on what we learn from any issues
that arise.
Roles
• Ahmad Nadeem: backend orchestration, LangGraph
workflow, FastAPI integration, and agent coordination
logic.
• Shazaib Dawood: frontend development in React/Tailwind,
user interaction flow, and live interview interface.
• Zaid Haidry: retrieval pipeline, evaluator rubric design,
testing, and evaluation dataset preparation.