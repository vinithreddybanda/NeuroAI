# SecondBrain AI

## Multi-Agent Engineering Intelligence System

SecondBrain is a multi-agent AI system designed to act as an intelligent engineering workspace. Instead of relying on a single AI assistant, SecondBrain coordinates specialized AI agents that divide complex engineering tasks, use external capabilities, communicate findings, and produce a consolidated result.

The system is built around Neuro-SAN and an agent-network architecture, with multiple LLM providers available through a resilient fallback chain.

---

## 1. Vision

SecondBrain is intended to function as an **AI engineering second brain**.

Its purpose is not simply to answer questions.

It is designed to:

* Understand engineering requests
* Decompose complex problems
* Assign work to specialized agents
* Investigate repositories and engineering systems
* Analyze issues and operational information
* Coordinate findings between agents
* Communicate important results
* Produce a unified engineering response

The central idea is:

> One request → multiple specialized perspectives → coordinated reasoning → one useful result.

---

## 2. Core Architecture

```text
                         ┌──────────────────────┐
                         │        USER          │
                         │ Engineering Request  │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ Engineering Frontman │
                         │   Orchestrator Agent │
                         └──────────┬───────────┘
                                    │
                         Task decomposition
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
              ▼                     ▼                     ▼
       ┌─────────────┐       ┌─────────────┐       ┌─────────────┐
       │   GitHub    │       │   Sentry    │       │ Communication│
       │ Engineering │       │ Engineering │       │    Agent     │
       │    Agent    │       │    Agent    │       │              │
       └──────┬──────┘       └──────┬──────┘       └──────┬──────┘
              │                     │                     │
              ▼                     ▼                     ▼
       Repository / PRs       Errors / Issues       Discord Webhook
       Code / History         Diagnostics            Notifications
              │                     │                     │
              └─────────────────────┼─────────────────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │   Shared Findings    │
                         │   + Agent Results    │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ Engineering Frontman │
                         │   Final Synthesis    │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │   Unified Response   │
                         └──────────────────────┘
```

---

## 3. Agent Network

SecondBrain uses a team-based agent model.

The agents are not intended to behave as identical copies of the same AI. Each role has a specific responsibility.

### Engineering Frontman

The Engineering Frontman is the primary coordinator.

Responsibilities include:

* Understanding the user's request
* Determining what information is required
* Breaking complex work into smaller missions
* Selecting appropriate specialist agents
* Coordinating parallel work
* Reviewing specialist results
* Resolving inconsistencies
* Producing the final response

The Frontman acts as the system's reasoning coordinator rather than attempting every operation itself.

---

## 4. Specialist Engineering Roles

SecondBrain contains an engineering team consisting of multiple specialized roles.

Examples of responsibilities include:

### Repository Engineering

Responsible for understanding and working with source repositories.

Typical activities:

* Repository inspection
* Source-code investigation
* Branch and commit analysis
* Pull-request analysis
* Issue investigation
* Code-level reasoning

### Reliability Engineering

Responsible for application health and operational diagnostics.

Typical activities:

* Error investigation
* Event analysis
* Failure diagnosis
* Regression investigation
* Production issue analysis
* Sentry intelligence

### Communication

Responsible for external engineering communication.

Typical activities:

* Preparing concise engineering updates
* Reporting findings
* Sending approved notifications
* Communicating task status

Communication is intentionally isolated from general engineering reasoning.

---

## 5. Capability Layer

SecondBrain separates **reasoning** from **capabilities**.

An AI agent decides what needs to happen.

The capability layer performs the actual external operation.

```text
Agent Reasoning
      │
      ▼
Capability Selection
      │
      ▼
External System
      │
      ▼
Structured Result
      │
      ▼
Agent Reasoning
```

This separation makes the system easier to extend and reduces the need for every agent to understand every external API.

---

## 6. GitHub Capability

GitHub is treated as a unified engineering capability.

The GitHub surface can support engineering-oriented operations such as:

* Repository inspection
* File retrieval
* Repository metadata
* Branch information
* Commit information
* Pull requests
* Issues
* Search
* Code investigation

The engineering agents determine which information is necessary instead of blindly loading an entire repository.

This follows an important SecondBrain principle:

> Retrieve the smallest useful amount of information required to solve the current problem.

---

## 7. Sentry Capability

Sentry provides application reliability intelligence.

The Sentry capability can be used for:

* Error investigation
* Event inspection
* Issue analysis
* Stack-trace investigation
* Failure patterns
* Operational diagnostics

A typical workflow is:

```text
User reports problem
        ↓
Engineering Frontman
        ↓
Reliability Agent
        ↓
Sentry investigation
        ↓
Relevant error evidence
        ↓
Root-cause reasoning
        ↓
Engineering recommendation
```

---

## 8. Discord Communication

Discord is used as an outbound communication channel.

The communication architecture intentionally uses a webhook-based model.

```text
Engineering Result
       ↓
Communication Agent
       ↓
Discord Webhook
       ↓
Engineering Channel
```

The communication agent does not independently invent engineering facts.

It receives a communication mission from the orchestrator, extracts the intended message, and sends the resulting communication through the permitted Discord capability.

---

## 9. Multi-LLM Architecture

SecondBrain is not dependent on a single LLM provider.

The system uses multiple providers through an ordered fallback architecture.

Current provider structure:

```text
                    LLM Request
                         │
                         ▼
                  ┌─────────────┐
                  │   Groq #1   │
                  └──────┬──────┘
                         │ failure
                         ▼
                  ┌─────────────┐
                  │   Groq #2   │
                  └──────┬──────┘
                         │ failure
                         ▼
                  ┌─────────────┐
                  │   OpenAI    │
                  └──────┬──────┘
                         │ failure
                         ▼
                  ┌─────────────┐
                  │   Gemini    │
                  └─────────────┘
```

The purpose is resilience.

A temporary provider failure, quota limitation, rate limit, or availability problem should not automatically terminate the engineering workflow.

---

## 10. Provider Responsibilities

The providers form one logical LLM service from the perspective of the agent network.

### Groq

Primary fast-path providers.

Two independent Groq credentials are available as the first two fallback positions.

### OpenAI

Provides an additional high-capability fallback path.

### Gemini

Provides another independent fallback path and increases provider diversity.

The application does not expose provider switching to the user as part of normal interaction.

The agent simply requests reasoning.

The fallback layer determines which available provider handles that request.

---

## 11. Failure Handling

Failure handling occurs at multiple layers.

```text
                 User Request
                      │
                      ▼
                Agent Network
                      │
              ┌───────┴────────┐
              │                │
          LLM Failure      Tool Failure
              │                │
              ▼                ▼
       Next LLM Provider   Agent Recovery
              │                │
              └───────┬────────┘
                      ▼
                Continue Task
```

LLM failure and capability failure are different problems.

An LLM provider failure should trigger provider fallback.

A capability failure should be interpreted by the agent and handled according to the task.

For example, if repository information is unavailable, the system should not fabricate repository facts.

---

## 12. Minimal-Context Intelligence

SecondBrain follows a **minimum necessary context** philosophy.

The system should not automatically load:

* Entire repositories
* Entire issue histories
* Entire Sentry datasets
* Unrelated files
* Unnecessary conversation history

Instead:

```text
Question
   ↓
Determine required evidence
   ↓
Retrieve relevant evidence
   ↓
Reason over evidence
   ↓
Request more only if necessary
```

If essential information is genuinely unavailable, the agent should ask for the missing information rather than inventing it.

This makes the system cheaper, faster, and easier to reason about.

---

## 13. Divide-and-Conquer Workflow

Complex engineering requests are decomposed into independent missions whenever possible.

Example:

```text
User:
"Investigate why the latest deployment is failing."

                    │
                    ▼

             Engineering Frontman
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
    Repository    Sentry      History
    Analysis      Analysis    Analysis
        │           │           │
        └───────────┼───────────┘
                    ▼
             Evidence Fusion
                    │
                    ▼
             Root Cause Analysis
                    │
                    ▼
             Recommended Action
```

Independent investigations can be performed separately before being synthesized.

This prevents one general-purpose reasoning chain from becoming unnecessarily large.

---

## 14. Agent Communication

Agents communicate through structured missions and results.

A simplified interaction looks like:

```text
Frontman
   │
   │ mission
   ▼
Specialist Agent
   │
   │ capability calls
   ▼
External System
   │
   │ structured result
   ▼
Specialist Agent
   │
   │ findings
   ▼
Frontman
```

This creates a clear distinction between:

* What needs to be done
* Who should do it
* What evidence was obtained
* What was concluded

---

## 15. Evidence-Based Reasoning

SecondBrain is designed around evidence rather than unrestricted speculation.

The preferred reasoning hierarchy is:

```text
External evidence
      ↓
Tool result
      ↓
Agent analysis
      ↓
Cross-agent verification
      ↓
Final conclusion
```

When evidence is insufficient, the system should explicitly identify the uncertainty.

A strong engineering answer is therefore not necessarily the longest answer.

It is the answer with the strongest available evidence.

---

## 16. Example End-to-End Workflow

Consider:

> "Why did our application start throwing errors after the latest deployment?"

The system can perform the following workflow:

### Step 1: Understand

The Frontman identifies:

* Deployment change
* Relevant repository
* Error information
* Potential regression

### Step 2: Decompose

The task becomes:

```text
Mission A → Inspect recent code changes
Mission B → Inspect recent Sentry errors
Mission C → Compare timing and affected components
```

### Step 3: Investigate

GitHub-oriented agents inspect relevant changes.

Sentry-oriented agents inspect relevant failures.

### Step 4: Correlate

The Frontman compares:

```text
Deployment timestamp
        +
Code changes
        +
Error onset
        +
Affected component
```

### Step 5: Reason

The agents determine the most likely relationship between the deployment and failure.

### Step 6: Verify

Additional evidence is retrieved only if necessary.

### Step 7: Synthesize

The Frontman produces:

* Probable root cause
* Supporting evidence
* Confidence/uncertainty
* Recommended action

### Step 8: Communicate

If requested, the communication agent sends a concise engineering update through Discord.

---

## 17. Design Principles

SecondBrain is built around several principles.

### Specialization

Agents should have focused responsibilities rather than becoming enormous general-purpose prompts.

### Minimal Context

Retrieve only what is required.

### Evidence First

External evidence should dominate assumptions.

### Graceful Failure

One provider or capability failure should not unnecessarily destroy the entire workflow.

### Separation of Concerns

Reasoning, capabilities, orchestration, and communication remain logically separated.

### Structured Collaboration

Agents communicate through explicit missions and results.

### Human Control

The system assists engineering decisions rather than pretending to replace engineering ownership.

---

## 18. Security Model

Secrets are treated as configuration rather than agent knowledge.

API credentials and webhook credentials belong in the environment/configuration layer.

Agents should receive access through capability interfaces rather than directly handling provider credentials.

The intended architecture is:

```text
Secret
  ↓
Configuration Layer
  ↓
Capability / LLM Adapter
  ↓
Agent
```

not:

```text
Secret
  ↓
Prompt
  ↓
Agent
```

Credentials should never become part of normal agent conversation context.

---

## 19. Observability

The system exposes multiple layers of operational visibility.

At the agent level:

* Agent execution
* Missions
* Tool activity
* Results

At the network level:

* Agent interactions
* Streaming responses
* Execution state

At the infrastructure level:

* LLM provider availability
* Capability availability
* External-system failures

This makes it possible to distinguish:

```text
LLM problem
    vs
Agent problem
    vs
Capability problem
    vs
External service problem
```

---

## 20. Sustainability and Efficiency

SecondBrain aims to minimize unnecessary computation.

Efficiency comes from:

* Task decomposition
* Minimal-context retrieval
* Specialist agents
* Provider fallback instead of repeated failed attempts
* Avoiding redundant tool calls
* Avoiding unnecessary repository loading
* Asking for missing information when required

The goal is not simply to make the system more powerful.

It is to make the system **useful per unit of computation**.

---

## 21. Conceptual Stack

```text
                    SecondBrain
                         │
                 Agent Network
                         │
                 Neuro-SAN / nsflow
                         │
              ┌──────────┼──────────┐
              │          │          │
            Agents   Capabilities  Memory/
                                  Context
              │          │
              │          ├── GitHub
              │          ├── Sentry
              │          └── Discord
              │
              └──── LLM Adapter Layer ────┐
                                           │
                         ┌─────────────────┼─────────────────┐
                         │                 │                 │
                       Groq             OpenAI            Gemini
                    2 fallback         fallback          fallback
```

---

## 22. What Makes SecondBrain Different

Traditional AI assistant:

```text
User → LLM → Answer
```

SecondBrain:

```text
                         ┌→ GitHub Agent ─────┐
                         │                    │
User → Frontman → Task ──┼→ Sentry Agent ────┼→ Synthesis → Answer
                         │                    │
                         └→ Communication ────┘
```

The difference is not merely using multiple models.

The important architectural difference is **multiple specialized reasoning processes coordinated around a single engineering objective**.

---

## 23. Intended Outcome

SecondBrain aims to become an engineering intelligence layer capable of helping with:

* Software development
* Repository analysis
* Debugging
* Incident investigation
* Code investigation
* Engineering coordination
* Operational awareness
* Technical communication
* Multi-step engineering workflows

The long-term direction is an AI system that can understand an engineering environment as a connected system rather than treating every user question as an isolated chat message.

---

## 24. Summary

SecondBrain combines:

**Multi-agent orchestration**

Specialized agents divide complex engineering problems into focused missions.

**External capabilities**

Agents interact with engineering systems through controlled capability interfaces.

**Multi-provider LLM resilience**

Two Groq paths, OpenAI, and Gemini provide an ordered fallback chain.

**Evidence-driven reasoning**

Agents retrieve relevant information before making conclusions.

**Minimal-context execution**

Only information required for the current task should be loaded.

**Human-centered engineering**

The system assists engineers while keeping humans responsible for important decisions.

The resulting architecture can be summarized as:

```text
              USER
                │
                ▼
        ENGINEERING FRONTMAN
                │
        ┌───────┼────────┐
        ▼       ▼        ▼
      CODE    RELIABILITY  COMMUNICATION
      AGENT      AGENT        AGENT
        │          │             │
        ▼          ▼             ▼
     GitHub      Sentry       Discord
        │          │             │
        └──────────┼─────────────┘
                   ▼
             EVIDENCE FUSION
                   │
                   ▼
             FINAL SYNTHESIS
                   │
                   ▼
              ENGINEERING
                ANSWER
```

**SecondBrain is therefore not simply an AI chatbot.**

It is an orchestrated engineering intelligence system where specialized AI agents, external engineering capabilities, and multiple LLM providers operate as a coordinated team.
