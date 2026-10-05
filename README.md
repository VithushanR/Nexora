# Nexora — Evidence-Backed Research Assistant

> A multi-agent AI system that turns a research domain into a systematically screened, evidence-backed report — every relevance decision is quoted and traceable, and every research gap is surfaced only once multiple independent papers back it up.

---

## Why This Exists

Before any serious research or R&D work can start, someone has to answer three things: what already exists, is it any good, and what's actually left to explore. Today that's manual — reading hundreds of papers, judging which are even relevant, and trying to spot patterns by memory. It's slow, inconsistent across reviewers, and doesn't scale down to a single student or small lab.

Nexora replaces that manual process with a coordinated pipeline of AI agents — each with a narrow, verifiable job — that retrieves literature, screens it against explicit criteria, and surfaces patterns across papers, without pretending to more certainty than the underlying evidence supports.

## What It Does

1. **You enter a research domain** — e.g. *"AI for early crop disease detection"*
2. **A safety gate checks the topic** before anything else runs — a hosted NVIDIA Nemotron classifier plus a deterministic policy layer blocks clearly unsafe requests and asks for clarification on ambiguous ones, rather than guessing
3. **The system retrieves and screens candidate papers** from free academic APIs, judging each one `INCLUDE` / `EXCLUDE` / `UNCERTAIN` with a quoted justification checked against the real abstract
4. **You review a ranked, relevance-scored list and select which papers to keep**
5. **A report is generated** — an introduction, an evidence table, flagged contradictions between papers, retraction checks, and evidence-backed candidate research gaps
6. **You continue in one chat interface**, grounded automatically in whichever report or document exists for that conversation, with a separate Web Search mode for live, Google-grounded answers that are never silently blended into the verified report

## How It Works

```mermaid
flowchart TD
    S["Safe Search gate"] --> A["User's Domain of Interest"]
    A --> B["Agent 1 — Protocol & Planning"]
    B --> C["Agent 2 — Retrieval & Screening"]
    C -.uncertain papers escalated.-> U["Human Review"]
    U -.resolution feeds back.-> C
    C --> D{"User Selects Papers"}
    D --> E["Agent 3 — Synthesis & Integrity"]
    D --> F["Agent 4 — Gap Discovery & Critic"]
    E --> G["Report Assembly & Indexing"]
    F --> G
    G --> H["Unified Chat — report/document grounded or live web"]
```

| Agent | Role |
|---|---|
| **1 — Protocol & Planning** | Turns the domain into a formal protocol: inclusion/exclusion criteria and search queries written correctly per source |
| **2 — Retrieval & Screening** | Retrieves candidates concurrently from four sources, deduplicates, pre-ranks by BM25, and judges each one `INCLUDE` / `EXCLUDE` / `UNCERTAIN` backed by a quote verified against the real abstract |
| **3 — Synthesis & Integrity** | Builds the evidence table from the selected papers, attempts a seven-strategy full-text fetch cascade, flags contradictions, checks for retractions |
| **4 — Gap Discovery & Critic** | Finds limitations that recur across multiple papers and turns them into evidence-backed candidate gaps, keeping single-paper complaints separate from genuine cross-paper gaps |
| **Report Assembly** *(not an agent)* | Merges Agent 3 + Agent 4's output into one report, generates an introduction, renders a branded PDF, and indexes the report for chat — no LLM call in the merge itself |

## Key Features

- **Quoted, auditable relevance decisions** — every screening verdict is backed by an exact line from the source abstract, checked as a real substring before the verdict is trusted
- **Evidence-backed gap discovery** — a candidate gap only surfaces once multiple independent papers admit to the same limitation, each labelled with its exact support count
- **Human-in-the-loop by design** — uncertain papers are escalated to the user, never silently resolved
- **Honest degradation, not silent failure** — a genuinely empty result (nothing found) is visually and textually distinguished from a failed process step (budget exhausted, provider error), so a processing failure can never be mistaken for a clean literature
- **Cost-aware architecture** — LLM calls are reserved for genuine judgment tasks; deduplication, ranking, and retraction checks run on free, deterministic methods
- **One unified chat, not a separate sidebar** — a single interface handles general conversation, report- or document-grounded answers (including both together, cited distinctly), and live web search, with tier-based limits on resource-intensive operations

## Tech Stack

| Layer | Technology |
|---|---|
| Orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) |
| Backend | FastAPI (Python) |
| LLM | Gemini API |
| Embeddings | Sentence Transformers (`all-MiniLM-L6-v2`) |
| Vector search | FAISS, namespaced per report/document, on-disk |
| Application storage | PostgreSQL (users, research threads, reports, documents, chat history) |
| Checkpoint storage | PostgreSQL (LangGraph's own checkpoint persistence) |
| Safety classification | NVIDIA Nemotron Safety Guard (hosted) |
| Frontend | React (Vite + TypeScript) |

## Data Sources

Retrieval draws concurrently from four free academic APIs: [arXiv](https://arxiv.org/help/api), [OpenAlex](https://openalex.org/), [Semantic Scholar](https://www.semanticscholar.org/product/api), and [Europe PMC](https://europepmc.org/RestfulWebService). [Crossref](https://www.crossref.org/) is used separately, for retraction checking only, not retrieval. A [DOAJ](https://doaj.org/api/docs) client exists in the codebase; its live wiring into the retrieval pipeline has not been independently confirmed.

The full-text fetch cascade (used during synthesis, after a user selects papers) additionally draws on known open-access PDF links, Europe PMC's full-text XML, PubMed Central, Unpaywall, and CORE, up to seven strategies in total, scoped by subscription tier.

## Safety and Security

- **Safe Search gateway** — every new research topic is classified by a hosted NVIDIA Nemotron model before a thread is created; a deterministic policy layer then decides SAFE / UNSAFE / UNCERTAIN, fails closed on any provider error, and never converts an UNSAFE classification to SAFE
- **Authentication** — Google Sign-In, with the resulting ID token verified server-side and exchanged for an app-issued JWT (algorithm pinned, no fallback secret) required on every protected endpoint
- **Ownership isolation** — a request for another user's document or research thread returns `404`, identical to a non-existent resource, so an attacker gets no signal about what exists
- **Encryption at rest** — uploaded documents are encrypted before being written to disk
- **Prompt sanitization** — chat messages and uploaded document text are passed through a sanitizer that neutralizes a fixed set of known injection phrases before reaching an LLM prompt

**Known, stated gaps**, not hidden:
- The sanitizer matches literal ASCII text only; a visually identical character from another Unicode script (e.g. Cyrillic) can bypass it entirely
- External paper metadata (titles, abstracts) retrieved during screening, synthesis, and gap discovery is not currently passed through the sanitizer
- The Safe Search gateway classifies the initial research topic only, not chat messages, uploaded documents, or web search queries
- Document upload and Copilot-indexing endpoints have no request-frequency rate limiting

## Subscription Tiers

Nexora implements three tiers — Free, Pro, Team — enforced server-side. The tier label lives in the user's database record; the actual limit values and their enforcement live in application code, not the database.

| Limit | Free | Pro | Team |
|---|---|---|---|
| Research runs / month | 3 | 50 | Unlimited |
| Candidates screened / run | 50 | 150 | 300 |
| Screening concurrency | 5 | 10 | 20 |
| Documents / session | 1 | 10 | Unlimited |
| Upload size | 5 MB | 15 MB | 20 MB (global ceiling) |
| PDF export | — | ✓ | ✓ |
| Gap-discovery paper cap | 10 | 50 | Unlimited |

**Known gap:** Web Search mode currently has no tier-based gate at all.

## Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+
- A Gemini API key ([ai.google.dev](https://ai.google.dev/))
- A hosted PostgreSQL instance (e.g. [Supabase](https://supabase.com/), free tier is sufficient)
- A Google OAuth client ID (for sign-in)
- An NVIDIA API key (for the Safe Search classifier)

### Installation

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>

# backend
pip install -r backend/requirements.txt --break-system-packages

# frontend
cd frontend
npm install
```

### Configuration

Create `backend/.env`:

```env
# Required — fails loudly at startup if missing
DATABASE_URL=postgresql+psycopg://user:password@host:5432/dbname
CHECKPOINT_DATABASE_URL=postgresql+psycopg://user:password@host:5432/dbname
JWT_SECRET_KEY=
ENCRYPTION_KEY=
GOOGLE_OAUTH_CLIENT_ID=
CONTACT_EMAIL=
GEMINI_API_KEY=
NVIDIA_API_KEY=

# Optional
GEMINI_MODEL=gemini-3.6-flash
OPENALEX_MAILTO=you@example.com
SEMANTIC_SCHOLAR_API_KEY=
CORE_API_KEY=
UPLOAD_MAX_SIZE_MB=20
```

Create `frontend/.env`:

```env
VITE_API_BASE_URL=http://127.0.0.1:8001
VITE_GOOGLE_CLIENT_ID=     # must match GOOGLE_OAUTH_CLIENT_ID above
```

### Running locally

```bash
python -m backend.serve --reload   # backend, http://127.0.0.1:8001
cd frontend && npm run dev         # frontend, separate terminal
```

Start the backend with `python -m backend.serve`, **not** `uvicorn backend.main:app` directly: on Windows, uvicorn's default event loop cannot run the async PostgreSQL driver (every database call fails with `"Psycopg cannot use the 'ProactorEventLoop'"`), and the launcher selects a compatible loop automatically. It changes nothing on other platforms.

## Responsible AI

- Every relevance verdict is traceable to a quoted source line, checked against the real abstract, never an unexplained score
- Uncertain papers are always escalated to the user, never auto-resolved
- A genuinely empty finding is always distinguished from a failed process step, so a budget or provider failure can never be mistaken for "nothing was found"
- Free academic sources skew toward well-indexed, English-language, often Western research — a stated limitation, not a hidden one
- Retraction status is checked against Crossref with an honest three-state result (clean / retracted / unknown); a failed check is never silently treated as clean
- The chat assistant never blends live-web answers into the verified report without the user explicitly switching to Web Search mode
- No dedicated fairness or bias auditing exists yet across the ranking and screening pipeline — a known, stated gap, not a claimed capability

## Project Status

All four agents, the human-selection checkpoint, report assembly, authentication, tiered subscriptions, and the unified chat interface are implemented and tested. Known limitations are listed in Safety and Security above and in the project's full vulnerability assessment documentation, rather than hidden.

- [x] System architecture and agent design
- [x] Agent 1 — Protocol & Planning
- [x] Agent 2 — Retrieval & Screening
- [x] Human paper-selection checkpoint
- [x] Agent 3 — Synthesis & Integrity
- [x] Agent 4 — Gap Discovery & Critic
- [x] Report Assembly & Indexing
- [x] Unified chat (general, grounded, web search)
- [x] Authentication (Google Sign-In + JWT)
- [x] PostgreSQL persistence (reports, documents, chat history, checkpoints)
- [x] Subscription tiers (Free / Pro / Team) with server-side enforcement
- [ ] Rate limiting on document/Copilot-indexing endpoints
- [ ] Tier gate on Web Search mode
- [ ] Unicode-normalized prompt sanitization
- [ ] Sanitization applied to externally retrieved paper content
- [ ] **Roadmap:** structural credibility scoring (study design, sample size, venue)
- [ ] **Roadmap:** dataset-feasibility check on candidate gaps

## Contributing

This is currently a university course project (IT 3041 — Information Retrieval and Web Analytics, SLIIT). Issues and suggestions are welcome via GitHub Issues.

## Acknowledgments

Built on top of [arXiv](https://arxiv.org/), [OpenAlex](https://openalex.org/), [Semantic Scholar](https://www.semanticscholar.org/), [Europe PMC](https://europepmc.org/), and [Crossref](https://www.crossref.org/) — all free, open scholarly data sources this project would not be possible without.
