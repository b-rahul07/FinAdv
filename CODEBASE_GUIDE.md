# 📘 FinAdvisor: Comprehensive Codebase & Architecture Guide

Welcome to the architectural documentation for **FinAdvisor** (*"Trace-Wise AI Financial Advisor"*). This document provides an exhaustive breakdown of every folder, every file, their internal responsibilities, and how they seamlessly interact to create an end-to-end, trustworthy, audit-traceable AI financial advisory platform.

---

## 📑 Table of Contents
1. [High-Level Architecture Overview](#1-high-level-architecture-overview)
2. [Folder Structure Map](#2-folder-structure-map)
3. [Root Configuration & Setup Files](#3-root-configuration--setup-files)
4. [Backend Modules (Deep Dive)](#4-backend-modules-deep-dive)
   - [orchestrator/ — API & Pipeline Coordinator](#orchestrator--api--pipeline-coordinator)
   - [preference/ — Conversational Profiling](#preference--conversational-profiling)
   - [retrieval/ — Document RAG & Vector Engine](#retrieval--document-rag--vector-engine)
   - [sentiment/ — Market News & FinBERT Analysis](#sentiment--market-news--finbert-analysis)
   - [recommend_audit/ — Advisory Generation & Rule Auditing](#recommend_audit--advisory-generation--rule-auditing)
   - [persistence/ — Local SQLite & Supabase Storage](#persistence--local-sqlite--supabase-storage)
   - [data/ — Databases & Persistent Storage](#data--databases--persistent-storage)
5. [Frontend Application (`trace-wise-advisor-main/`)](#5-frontend-application-trace-wise-advisor-main)
   - [Application Entry & Routing](#application-entry--routing)
   - [Advisor Feature Components](#advisor-feature-components)
   - [API Client & State Management](#api-client--state-management)
   - [UI Design System Components](#ui-design-system-components)
6. [Step-by-Step Runtime Lifecycle (How Files Work Together)](#6-step-by-step-runtime-lifecycle)
7. [Presentation Cheat Sheet (Key Talking Points)](#7-presentation-cheat-sheet)

---

## 1. High-Level Architecture Overview

FinAdvisor solves the #1 criticism of AI in finance: **hallucinations and lack of auditability**.
Instead of letting a raw LLM produce ungrounded advice, FinAdvisor utilizes a **4-Agent Pipeline with Provenance Verification**:

```mermaid
flowchart TD
    User([User in React UI]) <--> UI[Frontend: React + TanStack Router]
    UI <--> API[FastAPI Orchestrator: orchestrator/api.py]
    
    subgraph "Backend Engine: orchestrator/pipeline.py"
        API --> Agent1[1. Preference Agent\nConversational Profiling]
        Agent1 --> Profile[(Structured Profile)]
        
        Profile --> Agent2[2. Retrieval Agent\nChromaDB Vector Store]
        Agent2 --> RAG_Docs[(Top Relevant Regulatory Chunks)]
        
        Profile --> Agent3[3. Sentiment Agent\nFinBERT Transformer]
        Agent3 --> Sent_Score[(Market Sentiment Score)]
        
        Profile & RAG_Docs & Sent_Score --> Agent4[4. Recommendation Agent\nOllama phi4-mini]
        Agent4 --> RawAdvice[(Draft Advice with [CHUNK_ID] Citations)]
        
        RawAdvice --> Audit[5. Rules Engine & Provenance Audit]
        Audit --> ProvenanceLog[(Grounding & Compliance Audit Score)]
    end
    
    Audit --> Persistence[persistence/history.py + Supabase]
    Persistence --> API
    API --> UI
```

---

## 2. Folder Structure Map

```text
FinAdvisor/
├── config.py                     # Central system configuration & hyperparameters
├── reindex.py                    # Script to chunk & embed documents into ChromaDB
├── requirements.txt              # Backend Python dependencies
├── .env                          # Environment variables & Supabase keys
├── setup.bat / setup.ps1         # 1-Click automated installation script
├── start_app.bat / start_app.ps1 # 1-Click automated startup script
├── SETUP_GUIDE.md                # Installation manual for teammates
│
├── orchestrator/                 # Master controller of API endpoints & execution pipeline
│   ├── api.py                    # FastAPI web server and route definitions
│   └── pipeline.py               # Coordinates the 4 agents and audit checks
│
├── preference/                   # Conversational profiling & user onboarding
│   ├── agent.py                  # LLM extractor turning chat into structured profile
│   ├── profile.py                # FinancialProfile data models and validations
│   └── questions.py              # The 9 guided onboarding questions
│
├── retrieval/                    # Domain knowledge RAG engine
│   ├── agent.py                  # Formulates search queries and fetches vector matches
│   ├── chunker.py                # Semantic text splitter with metadata preservation
│   ├── vector_store.py           # ChromaDB wrapper with sentence-transformers embeddings
│   └── documents/                # 15 curated Indian regulatory & financial documents (.txt)
│
├── sentiment/                    # Market climate evaluation
│   ├── agent.py                  # Hugging Face FinBERT sentiment classifier
│   └── headline_fetcher.py       # Live RSS / finance news feed retriever
│
├── recommend_audit/              # Advice synthesis & safety verification
│   ├── agent.py                  # Synthesizes advice with required inline citations
│   ├── rules.py                  # Deterministic safety guardrails (emergency funds, debt ratio)
│   └── provenance.py             # Computes grounding audit score and verifies citations
│
├── persistence/                  # Multi-tier data storage
│   ├── history.py                # Local SQLite persistence (advisor_history.db)
│   ├── supabase_client.py        # Cloud synchronization client
│   └── supabase_schema.sql       # Postgres DDL schema for cloud backup
│
├── data/                         # Local database storage
│   ├── advisor_history.db        # SQLite chat & recommendation database
│   └── chroma_db/                # Pre-indexed ChromaDB vector embeddings
│
└── trace-wise-advisor-main/      # Modern Frontend Web Application
    ├── package.json              # NPM dependencies & scripts
    ├── vite.config.ts            # Vite bundler configuration
    ├── .env                      # Points to http://localhost:8000
    └── src/
        ├── router.tsx            # TanStack Router configuration
        ├── routes/               # Page views (Landing page & Chat workspace)
        ├── components/advisor/   # Feature components (Cards, Sidebars, Evidence drawer)
        ├── components/ui/        # Reusable UI component library (buttons, dialogs, etc.)
        └── lib/advisor/          # API client, TypeScript types, and store
```

---

## 3. Root Configuration & Setup Files

### `config.py`
- **What it is:** The global configuration file for the entire Python backend.
- **What it does:**
  - Defines the Ollama model name (`phi4-mini` by default).
  - Specifies Hugging Face embedding model (`sentence-transformers/all-MiniLM-L6-v2`) and sentiment model (`ProsusAI/finbert`).
  - Stores directory paths (`DATA_DIR`, `CHROMA_DIR`, `DOCS_DIR`).
  - Sets RAG tuning parameters: `TOP_K_CHUNKS = 3` (optimized for fast CPU execution during presentations).
  - Sets runtime flags like `ENABLE_SELF_CRITIQUE = False` to prevent sluggish responses on laptops without dedicated GPUs.
- **How it works:** Imported by every backend module (`from config import ...`). Changes here reflect across the entire backend immediately without touching agent code.

### `reindex.py`
- **What it is:** Knowledge base indexing and ingestion utility.
- **What it does:**
  - Reads all 15 `.txt` regulatory documents in `retrieval/documents/`.
  - Breaks text into 500-character chunks with 80-character overlaps via `chunker.py`.
  - Generates dense vector embeddings using `all-MiniLM-L6-v2`.
  - Writes vectors and chunk metadata into the local ChromaDB database in `data/chroma_db/`.
- **How it works:** Run once (or when new text documents are added). The repo comes with `data/chroma_db/` pre-indexed so your teammate does not even need to run this.

### `requirements.txt`
- **What it is:** Python package manifest.
- **What it does:** Lists all required libraries: `fastapi`, `uvicorn`, `chromadb`, `sentence-transformers`, `transformers`, `torch`, `requests`, `pydantic`, `supabase`, `python-dotenv`.

### `setup.bat` & `setup.ps1`
- **What it is:** 1-Click automated installation scripts for Windows.
- **What it does:**
  1. Checks if Python, Node.js, and Ollama are installed and accessible on PATH.
  2. Pulls the `phi4-mini` language model into Ollama (`ollama pull phi4-mini`).
  3. Installs backend Python packages (`pip install -r requirements.txt`).
  4. Installs frontend JavaScript packages (`cd trace-wise-advisor-main && npm install`).

### `start_app.bat` & `start_app.ps1`
- **What it is:** 1-Click automated application runner for Windows.
- **What it does:**
  1. Checks ports `11434`, `8000`, and `8080` to prevent port conflicts.
  2. Starts `ollama serve` in the background.
  3. Starts the FastAPI backend (`python -m uvicorn orchestrator.api:app --port 8000`).
  4. Starts the Vite frontend (`npm run dev -- --port 8080`).
  5. Automatically opens default web browser to `http://localhost:8080`.

---

## 4. Backend Modules (Deep Dive)

### `orchestrator/ — API & Pipeline Coordinator`
The brain that exposes HTTP endpoints to the web browser and orchestrates the multi-agent pipeline.

* **`orchestrator/api.py`**:
  - Implements the FastAPI application with CORS middleware enabled for `http://localhost:8080`.
  - Exposes REST endpoints:
    - `GET /health`: Health-check endpoint testing Ollama connectivity, vector store status, and DB readiness.
    - `POST /sessions`: Creates a new user session with a unique UUID.
    - `GET /sessions/{session_id}`: Retrieves existing session state, chat history, and current profile.
    - `POST /chat`: Receives user chat message during onboarding, runs `PreferenceAgent`, updates profile, and returns the next chatbot response.
    - `POST /confirm-profile`: Allows the user to confirm or edit their profile data before generating advice.
    - `POST /recommend`: Triggers the recommendation generation pipeline.
    - `GET /history`: Returns a list of all historical sessions for the sidebar drawer.

* **`orchestrator/pipeline.py`**:
  - Contains class `AdvisorPipeline`.
  - Coordinates the 5 sequential stages:
    1. **Profile Parsing:** Ensures profile contains necessary fields (income, age, risk tolerance, goals).
    2. **Document Retrieval:** Calls `RetrievalAgent.retrieve(query, profile)` to get relevant chunks from ChromaDB.
    3. **Sentiment Assessment:** Calls `SentimentAgent.analyze()` to get current market sentiment score (-1.0 to +1.0).
    4. **Recommendation Synthesis:** Calls `RecommendationAgent.generate()` passing profile, chunks, and sentiment.
    5. **Auditing & Grounding:** Calls `RulesEngine.audit()` and `ProvenanceAuditor.verify()` to compute safety metrics and ensure every claim cites a valid `[CHUNK_ID: ...]`.
    6. **Storage:** Saves the full output and audit logs into SQLite and Supabase.

---

### `preference/ — Conversational Profiling`
Responsible for learning about the user through an interactive natural conversation instead of a boring form.

* **`preference/questions.py`**:
  - Defines `ONBOARDING_QUESTIONS`: A structured list of 9 financial profiling questions (Age, Monthly Income, Monthly Expenses, Existing Savings/Investments, Debt/EMIs, Investment Goals, Time Horizon, Risk Appetite, Tax Regimes).
  - Supplies contextual prompt hints and question sequencing.

* **`preference/profile.py`**:
  - Defines the `FinancialProfile` dataclass.
  - Holds typed attributes: `age`, `monthly_income`, `monthly_expenses`, `current_savings`, `existing_debts`, `primary_goal`, `time_horizon_years`, `risk_tolerance`, `tax_regime`.
  - Implements validation methods (e.g. ensuring monthly expenses do not exceed income, converting colloquial answers like "moderate" or "conservative" into standardized enums).

* **`preference/agent.py`**:
  - Contains class `PreferenceAgent`.
  - Uses Ollama (`phi4-mini`) with a specialized system prompt: *"Extract user financial information from the conversation and return structured JSON while outputting a warm, professional conversational reply asking the next missing question."*
  - Automatically detects when all necessary profile fields are populated and sets `is_complete = True`.

---

### `retrieval/ — Document RAG & Vector Engine`
Retrieval-Augmented Generation engine ensuring financial advice is grounded in actual Indian regulations and tax codes.

* **`retrieval/documents/` (15 Regulatory Knowledge Documents)**:
  - `01_section_80c_tax_deductions.txt`: ₹1.5 Lakh limit, ELSS, PPF, EPF rules.
  - `02_ppf_public_provident_fund.txt`: 15-year tenure, sovereign guarantee, EEE tax status.
  - `03_elss_equity_linked_savings.txt`: 3-year lock-in, equity taxation under LTCG.
  - `04_sip_systematic_investment_plan.txt`: Rupee-cost averaging, compounding calculations.
  - `05_nps_national_pension_system.txt`: Tier-I & Tier-II accounts, additional ₹50,000 deduction under 80CCD(1B).
  - `06_fixed_deposits_guide.txt`: DICGC insurance up to ₹5 Lakh, TDS thresholds under Section 194A.
  - `07_sebi_mutual_fund_regulations.txt`: SEBI categorization, Total Expense Ratio (TER), risk-o-meter guidelines.
  - `08_bnpl_buy_now_pay_later.txt`: Credit bureau impact, default charges, hidden interest rates.
  - `09_sovereign_gold_bonds_sgb.txt`: RBI issuance, 2.5% annual interest, capital gains exemption on maturity.
  - `10_health_insurance_section_80d.txt`: Deductions for self, family, and senior citizen parents.
  - `11_emergency_fund_liquid_funds.txt`: 6 months expense reserve, T+1 liquidity, overnight/liquid mutual funds.
  - `12_senior_citizen_savings_scss.txt`: 8.2% interest, quarterly payouts, ₹30 Lakh ceiling.
  - `13_education_loan_section_80e.txt`: Deduction on interest paid for higher education with no upper limit for 8 years.
  - `14_sukanya_samriddhi_yojana.txt`: Girl child scheme, 8.2% interest, EEE tax exemption.
  - `15_loan_foreclosure_moratorium.txt`: RBI rules on zero foreclosure charges on floating-rate individual loans.

* **`retrieval/chunker.py`**:
  - Implements recursive character splitting with a target chunk size of 500 characters and 80 character overlap.
  - Attaches unique IDs to each chunk (e.g., `DOC01_CHUNK00`, `DOC02_CHUNK01`) and tracks the source file name and topic.

* **`retrieval/vector_store.py`**:
  - Initializes ChromaDB persistent client pointing to `data/chroma_db/`.
  - Loads `sentence-transformers/all-MiniLM-L6-v2` locally.
  - Handles vector querying: takes a query string, embeds it, and performs cosine similarity search to retrieve the top `k` most relevant chunks.

* **`retrieval/agent.py`**:
  - Contains class `RetrievalAgent`.
  - Takes the user query + user's financial profile (e.g. "Tax saving for 30% tax bracket with moderate risk").
  - Formulates an expanded semantic search query, queries `vector_store.py`, and returns ranked chunk objects with their text, IDs, and similarity scores.

---

### `sentiment/ — Market News & FinBERT Analysis`
Analyzes macroeconomic context so advice adapts to prevailing market conditions.

* **`sentiment/headline_fetcher.py`**:
  - Pulls current financial news headlines from financial feeds (e.g. inflation reports, RBI repo rate updates, market indices trends).
  - Includes curated fallback headlines representing real market conditions if external internet feeds are temporarily unreachable.

* **`sentiment/agent.py`**:
  - Contains class `SentimentAgent`.
  - Uses the **`ProsusAI/finbert`** transformer model via Hugging Face `transformers` pipeline.
  - Evaluates each headline for financial sentiment: `Positive`, `Negative`, or `Neutral`.
  - Computes an aggregate market sentiment score between `-1.0` (heavily bearish) and `+1.0` (strongly bullish).
  - This score influences the advice: for example, in a volatile/bearish market, the advisor recommends dollar-cost averaging (SIP) or higher allocation to debt/liquid funds.

---

### `recommend_audit/ — Advisory Generation & Rule Auditing`
The synthesis and verification core.

* **`recommend_audit/agent.py`**:
  - Contains class `RecommendationAgent`.
  - Builds a strict, constrained prompt for Ollama `phi4-mini`:
    - Provides User Profile, Market Sentiment Score, and Retrieved Knowledge Chunks.
    - **Crucial Rule:** The LLM is instructed: *"For every financial recommendation, tax claim, or allocation rule, you MUST cite the supporting chunk ID in brackets like `[CHUNK_ID: DOC01_CHUNK00]`."*
    - Uses low temperature (`0.2`) and concise token generation (`num_predict: 350`) to keep output punchy, fast, and factual.

* **`recommend_audit/rules.py`**:
  - Contains class `RulesEngine`.
  - Runs deterministic, hard-coded financial logic checks:
    - **Emergency Fund Rule:** Does the user have at least 3-6 months of expenses in liquid savings? If not, flags an emergency fund priority alert.
    - **Debt-to-Income Rule:** Are debt payments > 40% of income? If yes, flags a high debt alert and forbids high-risk equity investments.
    - **Tax Regime Rule:** Validates if Section 80C deductions apply (Old Regime only).
    - **SEBI Suitability:** Ensures high-risk assets are never recommended to conservative profiles.

* **`recommend_audit/provenance.py`**:
  - Contains class `ProvenanceAuditor`.
  - Parses the generated recommendation text using regex to find all `[CHUNK_ID: ...]` citations.
  - Verifies each citation against the actual retrieved chunks provided to the LLM.
  - Calculates an **Audit Grounding Score (0% - 100%)**:
    - Checks citation density (how many statements are backed by official documents).
    - Detects hallucinated chunk IDs (citations that were never in the retrieved context).
  - Returns a detailed provenance report with verified claims and source snippets.

---

### `persistence/ — Local SQLite & Supabase Storage`

* **`persistence/history.py`**:
  - Connects to `data/advisor_history.db` using Python's built-in `sqlite3`.
  - Automatically creates tables: `sessions`, `chat_messages`, `profiles`, `recommendations`, `audit_logs`.
  - Enables full offline persistence so user sessions survive server restarts.

* **`persistence/supabase_client.py`**:
  - Connects to Supabase using credentials in `.env`.
  - Provides cloud backup and synchronization for sessions and recommendation records.
  - Gracefully falls back to local SQLite if internet is disconnected or Supabase credentials are not configured.

* **`persistence/supabase_schema.sql`**:
  - SQL migration script creating tables with Row Level Security (RLS) policies for PostgreSQL on Supabase.

---

## 5. Frontend Application (`trace-wise-advisor-main/`)

Built with **React 18, Vite, TypeScript, TanStack Router, TanStack Query, and Tailwind CSS**.

### Application Entry & Routing
* **`vite.config.ts`**: Vite configuration defining path aliases (`@/` -> `src/`) and server proxy rules.
* **`src/router.tsx`**: Initializes TanStack Router.
* **`src/routes/__root.tsx`**: Top-level application shell containing the navigation bar, branding ("Ledgerly / FinAdvisor"), and theme toggle.
* **`src/routes/index.tsx`**: The landing page. Features a hero banner, key architectural highlights (Traceability, 15+ Regulations, FinBERT Sentiment), and a "Start Onboarding" button.
* **`src/routes/chat.$sessionId.tsx`**: The core interactive workspace. Dynamically renders based on session stage:
  - Chat interface during onboarding.
  - Profile confirmation card once onboarding completes.
  - Staged progress animation during recommendation generation.
  - Complete recommendation report and evidence drawer once generated.

---

### Advisor Feature Components
Located in `src/components/advisor/`:

* **`ProfileCard.tsx`**:
  - Interactive profile card.
  - Renders all 9 financial attributes.
  - Allows the user to click **Edit**, adjust values (e.g. increase income, change risk appetite), and click **Confirm Profile**.
  - Calls `api.confirmProfile()`.

* **`StagedProgress.tsx`**:
  - Displays a clean visual stepper showing real-time pipeline execution:
    1. *Validating Profile & Constraints*
    2. *Retrieving SEBI/Tax Documents from ChromaDB*
    3. *Analyzing Market News with FinBERT*
    4. *Synthesizing Grounded Advice with Ollama*
    5. *Auditing Provenance & Compliance Rules*

* **`RecommendationCard.tsx`**:
  - Renders the final financial advice generated by the LLM.
  - Automatically parses backend tags `[CHUNK_ID: ...]` and renders them as sleek, interactive badges `[1]`, `[2]`.
  - When the user clicks any badge `[1]`, it highlights the specific cited chunk and opens the **Evidence Panel**.
  - Displays the overall **Audit Grounding Score** (e.g. "95% Verified Grounding") and rule engine status.

* **`EvidencePanel.tsx`**:
  - A slide-out drawer/panel on the right side of the screen.
  - Displays the exact regulatory source document, document title, and text chunk corresponding to the clicked citation badge.
  - Gives complete transparency: judges/users can read the exact law or regulation backing up the AI's advice.

* **`HistorySidebar.tsx`**:
  - Displays past advisory sessions stored in SQLite/Supabase.
  - Allows users to switch between past sessions or click "New Session" to start fresh.

* **`DemoSettings.tsx`**:
  - Modal allowing presentation presenters to adjust backend API URLs, toggle mock fallback mode, and view connection status.

---

### API Client & State Management
Located in `src/lib/advisor/`:

* **`api.ts`**:
  - Central HTTP client making `fetch` calls to `http://localhost:8000`:
    - `createSession()` -> `POST /sessions`
    - `sendMessage()` -> `POST /chat`
    - `confirmProfile()` -> `POST /confirm-profile`
    - `generateRecommendation()` -> `POST /recommend`
    - `fetchHistory()` -> `GET /history`

* **`types.ts`**:
  - TypeScript type declarations ensuring strict type safety matching the backend Pydantic models:
    - `FinancialProfile`, `Session`, `ChatMessage`, `Recommendation`, `ProvenanceItem`, `AuditResult`.

* **`store.ts`**:
  - Client-side state management handling active session ID, local caching, and UI theme preferences.

---

## 6. Step-by-Step Runtime Lifecycle

Here is the exact step-by-step execution path when a user interacts with FinAdvisor:

```text
[Step 1: User Onboarding]
User types: "I earn 80k a month, spend 40k, and want to save taxes with low risk."
   │
   ▼
[Frontend: api.ts -> POST /chat]
   │
   ▼
[Backend: orchestrator/api.py] -> calls [preference/agent.py]
   │
   ▼
[Preference Agent (Ollama phi4-mini)]
Parses text -> updates FinancialProfile(monthly_income=80000, monthly_expenses=40000, risk_tolerance="low")
Returns warm reply asking next question (e.g. "What is your primary investment goal?").
Repeats until 9 questions are answered -> sets profile.is_complete = True.
   │
   ▼
[Step 2: Profile Review]
Frontend renders ProfileCard.tsx.
User inspects values, modifies if necessary, and clicks "Confirm Profile".
Frontend calls POST /confirm-profile -> profile locked.
   │
   ▼
[Step 3: Recommendation Triggered]
User clicks "Generate Advice".
Frontend renders StagedProgress.tsx and calls POST /recommend.
   │
   ▼
[Backend: orchestrator/pipeline.py Orchestration]
   ├── 1. retrieval/agent.py queries ChromaDB with profile keywords ("tax saving low risk 80C PPF").
   │      ChromaDB returns top chunks from:
   │      - 01_section_80c_tax_deductions.txt (DOC01_CHUNK00)
   │      - 02_ppf_public_provident_fund.txt (DOC02_CHUNK01)
   │      - 11_emergency_fund_liquid_funds.txt (DOC11_CHUNK00)
   │
   ├── 2. sentiment/agent.py scores live headlines via FinBERT.
   │      Computes sentiment = +0.15 (Mildly Positive / Stable).
   │
   ├── 3. recommend_audit/agent.py prompts Ollama phi4-mini:
   │      "Synthesize advice for 80k income low-risk user. Must cite [CHUNK_ID: ...]."
   │      Ollama generates:
   │      "1. Build a ₹2.4 Lakh emergency reserve in liquid funds [CHUNK_ID: DOC11_CHUNK00].
   │       2. Invest ₹1.5 Lakh in PPF under Section 80C for tax exemption [CHUNK_ID: DOC02_CHUNK01]."
   │
   ├── 4. recommend_audit/rules.py audits advice against safety checks:
   │      Emergency fund validated. Debt ratio normal. Low risk matches PPF instrument.
   │
   ├── 5. recommend_audit/provenance.py verifies citations:
   │      Verifies DOC11_CHUNK00 and DOC02_CHUNK01 exist in retrieved set.
   │      Computes Grounding Score = 100%.
   │
   └── 6. persistence/history.py writes result to SQLite & Supabase.
   │
   ▼
[Step 4: UI Presentation]
Frontend receives payload and replaces progress spinner with RecommendationCard.tsx.
Citations render as clickable badges [1], [2].
User clicks [2] -> EvidencePanel opens showing Section 80C PPF document text!
```

---

## 7. Presentation Cheat Sheet (Key Talking Points)

When presenting this project to your professors or evaluators tomorrow, highlight these **5 core differentiators**:

1. **Why not just use ChatGPT?**
   - *ChatGPT hallucinates financial facts, does not know your personal risk capacity, and cannot prove where its numbers came from.*
   - *FinAdvisor enforces **Provenance Tracking**: every financial claim carries an auditable document citation linked to official Indian financial regulations.*

2. **The 4-Agent Architecture:**
   - **Preference Agent:** Conversational extraction instead of static forms.
   - **Retrieval Agent:** Semantic vector search (ChromaDB + Sentence Transformers) over 15 curated Indian regulatory texts.
   - **Sentiment Agent:** ProsusAI/FinBERT transformer evaluating market climate to adapt risk allocations.
   - **Recommendation & Audit Agent:** Local LLM (`phi4-mini`) under strict citation constraints + deterministic rule guardrails.

3. **Deterministic Safety Rules:**
   - *LLMs cannot be trusted with math and compliance alone.*
   - *Our Python `RulesEngine` enforces emergency funds, debt-to-income caps, and SEBI asset-allocation limits before any advice reaches the user.*

4. **100% Local & Privacy-Preserving:**
   - *Financial data is deeply sensitive. All profiling, vector search, and LLM inference can run completely on-device without sending personal financial figures to third-party proprietary APIs.*

5. **Interactive Citation Transparency:**
   - *Clicking any recommendation footnote opens the exact regulatory text chunk in the Evidence Drawer, enabling complete compliance auditing.*
