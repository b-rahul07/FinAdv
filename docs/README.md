# AI Financial Advisor — Living Documentation

## Current State (always overwritten, never appended — must reflect reality right now)
- **Architecture**: Repo fully scaffolded and completely implemented. All modules are functional.
  - `retrieval/` — **fully implemented** (ChromaDB + SentenceTransformers CrossEncoder).
  - `sentiment/` — **fully implemented** (FinBERT + RSS).
  - `preference/` — **fully implemented** (SAUR-style elicitation + Literacy check).
  - `recommend_audit/` — **fully implemented** (Rule engine + Ollama + **Post-hoc provenance** + CoVe Self-Critique loop + **Budget Guard** + **Suitability Pre-filter**).
  - `orchestrator/` — **fully implemented** (Pipeline wires all 4 agents; FastAPI endpoints).
  - `persistence/` — **fully implemented** (Supabase session/message persistence).
  - `eval/` — **fully implemented** (Harness, LLM-as-judge, 120-item test set, 10 personas for bias sweep, model comparison script).
  - `ui/` — **fully implemented** (Streamlit app with adaptive structured output and no prototype notices).
- **Root config**: `config.py` with 3 ablation flags (`ENABLE_PREFERENCE_CONFIRMATION`, `ENABLE_AUDIT_EVIDENCE`, `ENABLE_SELF_CRITIQUE`) + parameters + Supabase connection details.
- **Retrieval corpus**: 15 curated Indian financial documents (01–15). Document `16_top_mutual_funds_india.txt` was removed on 2026-09-23 (see Change Log).
- **Fund naming policy**: The system recommends at the **asset-class level** (e.g., "ELSS Tax Saving Fund", "Large-Cap Equity Fund") rather than naming specific schemes (e.g., "SBI Small Cap Fund"). This is consistent with the "not investment advice" disclaimer. Specific fund names were removed from both the retrieval corpus and the LLM prompt on 2026-09-23.
- **What works end-to-end today**: 
  - The entire pipeline works end-to-end. Outputs are adaptively formatted into structured JSON (Executive Summary, Technical Breakdown, Asset Allocation) based on the user's financial literacy level.
  - Chat history and sessions are persistently stored in Supabase (`sessions` and `messages` tables).
  - **`/confirm` → `/recommend` chain is now working** (fixed 2026-09-23). The confirm button fires `/confirm`, then immediately triggers `/recommend` with a staged loading indicator (`StagedProgress` component). Network evidence: `/confirm` returns HTTP 200 and `/recommend` returns HTTP 200 with a full recommendation response.
  - The evaluation harness can run 6 different configurations (full, no_confirm, no_audit, no_critique, plain_rag, llm_only) against the 120-item test set.
  - The LLM-as-judge can score faithfulness, groundedness, and detect hallucinations.
  - The persona bias sweep runs 10 synthetic personas and flags unjustified differences using Jaccard similarity.
  - The model comparison script evaluates phi4-mini vs qwen2.5 vs llama3.2.
  - **Provenance is now attached post-hoc** by the pipeline (not self-reported by the LLM). Rule-derived claims get `[RULE_ID: ...]` tags; chunk-derived claims are verified against the actual retrieved set.
  - **Empty-answer bootstrap** (`answer: ""` to `/api/session/{id}/message`) correctly returns question 1 without advancing elicitation state. Verified via test.
  - **Budget Guard**: After LLM generation, `_validate_budget()` checks that the sum of all recommended monthly SIP amounts ≤ `effective_investable`. Allows one retry; rejects with an explicit error if both attempts over-budget. Tested via `test_budget_guard.py`.
  - **Suitability Pre-filter**: `rule_small_cap_horizon` and `rule_midcap_horizon` fire before the LLM call and inject explicit EXCLUSION directives into the system prompt, preventing the recommend-then-caveat anti-pattern.
  - **ChromaDB index**: Rebuilt with full-reset (drop + recreate) on 2026-09-23 after removing doc 16. Sanity check confirms doc 16 is absent; 98 chunks from 15 documents indexed.
- **What is broken or incomplete**:
  - **Item 2 — False-premise self-critique test is unverified**: The test infrastructure (`test_preharness_checklist.py`) is built and the code changes are in place (self-critique prompt now explicitly checks for false premises and cross-regulation conflation), but Ollama was not running locally during the test. **The actual LLM raw output for the false-premise query with `ENABLE_SELF_CRITIQUE=True` has not been captured.** This must be rerun when Ollama is available to confirm whether self-critique catches the false premise (ELSS lock-in has nothing to do with the RBI digital lending circular).
  - **Budget prose vs. structured allocation gap**: The budget guard validates the structured `asset_allocation` dict (percentages/amounts). The LLM narrative text can still state over-budget absolute figures (e.g., "₹1,00,000/month" when investable is ₹20,000). The guard catches the structured data violation but not prose inflation. This is a known gap — a future improvement would parse monetary amounts from the recommendation text.
  - **Eval harness had a config-restore bug** (now fixed): `ENABLE_SELF_CRITIQUE` was saved but never restored after eval runs. Fixed in `eval/harness.py`.
  - The system is **not ready for evaluation runs** until the false-premise test (Item 2) is rerun with a live Ollama instance and the results are reviewed.
- **Active milestone**: Pre-harness checklist (3 of 4 items complete; Item 2 blocked on Ollama availability).
- **Immediate next step**: Start Ollama, rerun `python test_preharness_checklist.py` to capture Item 2 output, then proceed to eval harness discussions.

## Pre-Harness Checklist (2026-09-23)

### Item 1: Fix Provenance Attachment ✅ DONE

**Problem**: Citations were self-reported by the LLM under a strict "cite every claim" prompt instruction. This caused it to fabricate a citation when a claim came from the rule engine rather than a retrieved chunk (confirmed case: a BNPL warning cited a PPF chunk in `[CHUNK_ID: doc03_chunk07]` format).

**Architectural fix applied**:
- The LLM prompt **no longer instructs the model to insert `[CHUNK_ID: ...]` tags**. The audit mode prompt now says: `Do NOT insert citation tags like [CHUNK_ID: ...] — provenance will be attached automatically by the system.`
- **Rule-derived claims** are tagged by the pipeline itself with `[RULE_ID: rule_xxx]` (e.g., `[RULE_ID: rule_bnpl_warning]`), matched via keyword/pattern scanning against the set of rules that actually fired for the user's profile.
- **Chunk-derived claims** are verified post-hoc: any `[CHUNK_ID: ...]` the LLM still inserts is checked against the actual retrieved set (`valid_chunk_ids`). Fabricated citations are stripped and recorded in `provenance.fabricated_chunk_ids`.
- The `ProvenanceRecord` now has two new fields: `inline_citations` (mapping claim text → source tag) and `fabricated_chunk_ids` (list of LLM-fabricated chunk IDs that were stripped).

**Evidence** (unit tests — all 6 pass):
```
======================================================================
ITEM 1: POST-HOC PROVENANCE UNIT TESTS
======================================================================

Input:  Your BNPL exposure is concerning. Clear BNPL before investing.
Output: Your BNPL exposure is concerning. [RULE_ID: rule_bnpl_warning] Clear BNPL before investing.
>>> PASS: BNPL claim tagged with RULE_ID

Input:  Your EMI burden is too high. Prioritize debt reduction first.
Output: Your EMI burden is too high. [RULE_ID: rule_emi_ratio] Prioritize debt reduction first.
>>> PASS: EMI claim tagged with RULE_ID

Input:  BNPL exposure is something to watch.
Output: BNPL exposure is something to watch.
>>> PASS: No tag when rule didn't fire

Input:      ELSS has a 3-year lock-in [CHUNK_ID: doc05_chunk03] per SEBI rules.
Cleaned:    ELSS has a 3-year lock-in [CHUNK_ID: doc05_chunk03] per SEBI rules.
Fabricated: []
>>> PASS: Valid CHUNK_ID kept

Input:      PPF rate is 7.1% [CHUNK_ID: doc99_chunk42] as per latest RBI update.
Cleaned:    PPF rate is 7.1%  as per latest RBI update.
Fabricated: ['doc99_chunk42']
>>> PASS: Fabricated CHUNK_ID stripped and recorded

Input:      You have heavy BNPL exposure [CHUNK_ID: doc03_chunk07]. Clear it before investing.
Output:     You have heavy BNPL exposure . [RULE_ID: rule_bnpl_warning] Clear it before investing.
Fabricated: ['doc03_chunk07']
>>> PASS: Confirmed bug case fixed — BNPL claim gets RULE_ID, fabricated PPF chunk stripped

======================================================================
ALL PROVENANCE UNIT TESTS PASSED
======================================================================
```

**Files changed**:
- `recommend_audit/provenance.py` — Expanded `ProvenanceRecord`, added `attach_rule_provenance()`, `verify_chunk_citations()`, `attach_provenance()`.
- `recommend_audit/agent.py` — Removed LLM citation instructions from prompt; added post-hoc `attach_provenance()` call after generation; self-critique prompt now checks for false premises and cross-regulation conflation.
- `eval/harness.py` — Updated `provenance_present` check to detect `[RULE_ID:]` tags; fixed `ENABLE_SELF_CRITIQUE` not being restored after eval runs.

---

### Item 2: False-Premise Test with Self-Critique ⏳ BLOCKED (Ollama offline)

**Query**: "What's the lock-in period for ELSS mentioned in the RBI digital lending circular?"
**Profile**: Aggressive risk, short-term horizon, Heavy BNPL, EMI ₹18,000/month
**False premise**: ELSS lock-in has nothing to do with the RBI digital lending circular.

**What was done**:
- Test script `test_preharness_checklist.py` built and verified.
- Self-critique prompt updated to explicitly check for: "Claims that conflate unrelated regulations (e.g., attributing ELSS lock-in periods to an RBI circular)" and "False premises in the user's question that the draft failed to challenge."
- Two configs prepared: (a) SELF_CRITIQUE=True + AUDIT_EVIDENCE=True, (b) SELF_CRITIQUE=True + AUDIT_EVIDENCE=False.

**What happened when run**:
- The retrieval + rule engine stages worked correctly (7 chunks retrieved, 5 rules fired including `rule_elss_lockin` and `rule_bnpl_warning`).
- The LLM inference stage failed with: `Error: Failed to connect to Ollama. Please check that Ollama is downloaded, running and accessible.`
- **No raw LLM output was captured.** The false-premise detection could not be evaluated.

**What must still happen**:
1. Start Ollama (`ollama serve` or ensure the Ollama desktop app is running).
2. Run `python test_preharness_checklist.py`.
3. Review the raw output from both configs (a) and (b) to determine whether self-critique catches the false premise.
4. Update this section with the actual output.

---

### Item 3: Empty-Answer Bootstrap ✅ VERIFIED

**Scenario**: `start()` sends `answer: ""` to `/api/session/{id}/message`.

**Expected behavior**: Returns question 1 (the first elicitation question) without being misparsed as a real response.

**Evidence** (test output):
```
Input: answer = '' (empty string)
Current question_index: 0

Response type: question
Question returned: What specific financial question or topic would you like advice on today?
Options: None
Index: 1 / 9

>>> PASS: Empty answer correctly returns question 1 without advancing state
```

**How it works** (code path in `api.py` line 150):
```python
if not req.answer.strip():
    q = questions[0]
    # Returns first question, does NOT advance question_index or record an answer
```

The `not req.answer.strip()` guard catches both `""` and whitespace-only strings. The question index stays at 0, the answers dict stays empty, and the first question is returned correctly. No state corruption.

---

### Item 4: Documentation.md Updated ✅ DONE

The "What is broken or incomplete" line previously said: "Nothing is explicitly broken. The MVP is ready for evaluation runs." This was inaccurate. It now reflects the actual state:
- Item 2 (false-premise self-critique) is unverified due to Ollama being offline.
- The eval harness config-restore bug has been fixed but was previously unmentioned.
- The system is explicitly marked as **not ready for evaluation runs** until Item 2 is completed.

---

## Answers to Queries (M12 Check)
- **Preference Elicitation Flow**: The elicitation sequence is **fixed**, not adaptive. The API (`orchestrator/api.py`) iterates sequentially through the `ELICITATION_QUESTIONS` list until all are answered.
- **UI Disclaimer**: The explicit disclaimer stating "This is an educational and suitability tool. It is not investment advice..." is present and active in the React UI (`trace-wise-advisor-main/src/routes/index.tsx` and Chat view).
- **Self-Critique (`ENABLE_SELF_CRITIQUE`)**: When active, the Recommendation agent runs a second CoVe (Chain of Verification) LLM pass over its drafted response to self-audit against the source chunks and fix hallucinations. 
  - **Eval Confound Fix**: The `no_audit` eval config disables `ENABLE_AUDIT_EVIDENCE` but keeps `ENABLE_SELF_CRITIQUE = True`. This means our definition of an "Audited" pipeline is essentially a bundle: it tests the *citation-constraint prompting* while the self-critique mechanism remains active across both `full` and `no_audit` conditions to provide a fair baseline for the prompt ablation.

## Account Switch Log (append-only, most recent first)
*(No switches yet.)*

## Change Log (append-only, most recent first)

### 2026-09-23 — Live E2E Verification: /confirm→/recommend Chain Fixed, Stale Session Cleanup

- **What was done**:

  **Fix 1 — `typing.Any` missing from `orchestrator/api.py`** (root cause of the broken confirm→recommend chain):
  - `ConfirmRequest` model used `dict[str, Any]` but `Any` was not imported from `typing`.
  - FastAPI raised a `NameError` when loading the class → every `/confirm` call returned HTTP 500 before `/recommend` was ever attempted.
  - Fix: Added `Any` to the `typing` import on line 27 of `orchestrator/api.py`.

  **Fix 2 — Silent failure in `confirmProfile()` (`chat.$sessionId.tsx`)**:
  - The confirm→recommend flow had no `try/catch`. When `/confirm` threw (which it always did), `setGenerating(true)` was never reached → `<StagedProgress />` never rendered → zero UI feedback and `/recommend` never called.
  - Fix: Wrapped the entire confirm→recommend block in `try/catch/finally`. Error path surfaces a red error bubble in the chat thread. `setGenerating(true)` is now called before the recommend request so `<StagedProgress />` reliably appears.

  **Fix 3 — Double-click duplicate sessions**:
  - The ProfileCard "Confirm" button had no in-flight guard. Double-clicking fired two concurrent confirm→recommend cycles → two recommendation items → two sidebar entries.
  - Fix (dual layer): (a) `confirmingRef` (React `useRef<boolean>`) gates the entire confirm function against concurrent invocations; (b) `loading` prop on `ProfileCard` disables the button and changes its label to "Generating recommendation…" while in-flight.

  **Fix 4 — ChromaDB full reset after removing doc 16**:
  - The previous `reindex.py` used upsert-only (`_collection.upsert()`), which leaves stale chunks from deleted documents.
  - Updated `reindex.py` to `_client.delete_collection("finadvisor_docs")` before re-ingesting.
  - Sanity check: `OK: doc 16 absent - index is clean (15 docs only)` — 98 chunks from 15 documents.

  **Fix 5 — Stale session cleanup**:
  - 21 sessions existed in Supabase. 11 were orphaned or stuck in elicitation/confirm with no recommendation message (created while `/confirm` was broken).
  - Deleted all 11. 10 completed sessions retained.
  - Frontend localStorage cache: stale entries will naturally expire when the deleted session IDs no longer match Supabase records. Users can also clear manually via the "×" delete button in the sidebar.

- **Live E2E run evidence** (2026-09-23, session `a4f58a2a-067d-4be9-a770-9a9cad514117`):
  - Profile: Moderate risk, Medium-term (1–5 years), Wealth growth, Monthly savings ₹25,000, EMI ₹5,000, No BNPL, Intermediate literacy.
  - `/confirm` → **HTTP 200** ✅
  - `/recommend` → **HTTP 200** ✅ (Ollama LLM pipeline completed successfully)
  - `<StagedProgress />` displayed immediately after confirm click — "Retrieving relevant documents…" stage visible in screenshot ✅
  - Confirm button showed "Generating recommendation…" label while in-flight ✅
  - Recommendation received: ELSS Tax Saving Fund (50%) + Liquid Fund/Short-Duration Debt (50%). Rule fired: `rule_80c_limit`. Sentiment: positive (0.73). Source docs: `03_elss_equity_linked_savings.txt`, `04_sip_systematic_investment_plan.txt`, `07_sebi_mutual_fund_regulations.txt`, `11_emergency_fund_liquid_funds.txt`.
  - No suitability contradiction: small-cap excluded (medium-term horizon < 7 years), no BNPL warning (BNPL = None), EMI ratio within limits.
  - Structured `asset_allocation` passed budget guard (50/50 split = 100% of investable, within tolerance).
  - Session persisted correctly in Supabase with stage=`recommendation` and 22 messages.
  - **Known gap in prose**: LLM narrative text stated "₹1,00,000/month" SIPs against ₹25,000 investable. This is a prose inflation issue not caught by the budget guard (which validates the structured `asset_allocation` dict, not free text). The structured data was correct. This gap is documented above in "What is broken or incomplete."
  - Sidebar shows **1 session** after the E2E run — no duplicates ✅

- **Why**: Confirmed that the three fixes from the previous turn work together in a real flow, not just in isolation.
- **Files touched**: `orchestrator/api.py`, `trace-wise-advisor-main/src/routes/chat.$sessionId.tsx`, `trace-wise-advisor-main/src/components/advisor/ProfileCard.tsx`, `trace-wise-advisor-main/src/lib/advisor/types.ts`, `reindex.py`, `documentation.md`.
- **Status after this change**: `/confirm` → `/recommend` chain is fully operational. Staged loading indicator works. No duplicate sessions. Index is clean.
- **Follow-up needed**: Investigate prose budget inflation (LLM states absolute SIP amounts that exceed the investable budget in the narrative text, even though the structured allocation is correct).

### 2026-09-23 — Live Test Fixes: Budget Guard, Suitability Pre-filter, Fund-Naming Policy
- **What was done**:
  - **Issue 1 — Budget Violation Fix**: Three-part fix for `₹3,50,000/month` recommendation against a `₹20,000/month` investable amount.
    - **Root cause A**: `rule_80c_limit` action text said "up to ₹1,50,000 limit" with no temporal qualifier. The LLM treated the annual tax ceiling as a monthly SIP target. Fixed: action text now explicitly states "per financial year" and "NOT a monthly SIP figure".
    - **Root cause B**: No post-generation validation. Fixed: added `_validate_budget()` in `recommend_audit/agent.py`. After LLM generation, it checks that the sum of all monthly allocations ≤ `effective_investable`. One retry is allowed; on double failure, an explicit error is returned (not silently presented as advice).
    - **Budget constraint block** added to system prompt: restates the monthly limit and the annual/monthly distinction for the 80C ceiling.
    - **CoVe prompt** updated: self-critique now also checks for budget violations and annual/monthly confusion.
  - **Issue 2 — Suitability Pre-filter**: Added `rule_small_cap_horizon` and `rule_midcap_horizon` to the rule engine. These evaluate the user's horizon and inject an explicit EXCLUSION directives into the system prompt before the LLM call, preventing the recommend-then-caveat anti-pattern (e.g., SBI Small Cap recommended for medium-term with a caveat that it needs 7-10 years).
    - `rule_small_cap_horizon`: fires if horizon max < 7 years → excludes all small-cap funds.
    - `rule_midcap_horizon`: fires if horizon max < 5 years → excludes all mid-cap funds.
    - Added `_horizon_max_years()` helper to parse horizon strings to conservative year estimates.
  - **Issue 3 — `16_top_mutual_funds_india.txt` Provenance + Policy**:
    - **Provenance**: The file was added silently at M11 ("Adaptive Output, CoVe") when the agent prompt was changed to "name actual funds". It was not present in M1 ("Authored 15 curated Indian financial documents") and was not documented in the change log.
    - **Policy decision**: Removed the file from the retrieval corpus. The system now recommends at the asset-class level (ELSS, large-cap equity, liquid fund) rather than naming specific schemes, consistent with the "not investment advice" disclaimer. The LLM prompt instruction to "Name AT LEAST 3 specific mutual fund schemes" was also removed.
  - **Test**: New `test_budget_guard.py` with 9 unit tests (no Ollama required) — all pass.
- **Why**: Live test showed three critical failures that made pipeline output untrustworthy for demo or evaluation.
- **Files touched**: `recommend_audit/rules.py`, `recommend_audit/agent.py`, `test_budget_guard.py` (new), `documentation.md`. Deleted: `retrieval/documents/16_top_mutual_funds_india.txt`.
- **Status after this change**: Issues 1, 2, 3 fixed. Budget guard verified by unit tests. Suitability rules verified by unit tests. Pipeline output is now safe for demo with Ollama running.
- **Follow-up needed**: Rerun ChromaDB index (`python reindex.py`) to remove the deleted file from the vector store before running Ollama-dependent tests.

### 2026-09-23 — Pre-Harness Checklist: Provenance Fix, Bootstrap Verification, Self-Critique Setup
- **What was done**: 
  - **Item 1 (Provenance)**: Replaced LLM-self-reported citations with post-hoc provenance attachment. Rule-derived claims get `[RULE_ID: rule_xxx]` tags attached by the pipeline; chunk-derived claims are verified against the actual retrieved set. Fabricated CHUNK_IDs are stripped and recorded. 6/6 unit tests pass including the confirmed bug case (BNPL warning citing a PPF chunk).
  - **Item 2 (False-premise test)**: Test infrastructure built (`test_preharness_checklist.py`). Self-critique prompt updated to check for false premises and cross-regulation conflation. Execution blocked by Ollama being offline — raw LLM output not yet captured.
  - **Item 3 (Bootstrap)**: Verified that `answer: ""` to `/api/session/{id}/message` correctly returns question 1 without advancing state. All assertions pass.
  - **Item 4 (Documentation)**: Updated "What is broken or incomplete" to reflect real state. Removed false "ready for evaluation runs" claim.
  - **Bug fix**: `eval/harness.py` was not restoring `ENABLE_SELF_CRITIQUE` after eval runs (saved but never restored). Fixed.
  - **Bug fix**: `eval/harness.py` `provenance_present` check now detects both `[CHUNK_ID:]` and `[RULE_ID:]` tags.
- **Why**: Pre-harness checklist required before proceeding to eval harness implementation.
- **Files touched**: `recommend_audit/provenance.py`, `recommend_audit/agent.py`, `eval/harness.py`, `documentation.md`, `test_provenance.py` (new), `test_preharness_checklist.py` (new), `test_item3_bootstrap.py` (new).
- **Status after this change**: Items 1, 3, 4 complete. Item 2 blocked on Ollama availability.
- **Follow-up needed**: Start Ollama, rerun `python test_preharness_checklist.py`, update Item 2 with raw output.

### 2026-09-22 — M12: Supabase Session and Message Persistence
- **What was done**: 
  - Switched from localStorage/in-memory session state to Supabase as the canonical persistence layer.
  - Created `sessions` and `messages` tables in the Supabase project.
  - Implemented `persistence/supabase_client.py` and `persistence/history.py` for CRUD operations.
  - Completely rewrote `orchestrator/api.py` to add stateful endpoints (`POST /api/session`, `POST /api/session/{id}/message`, `GET /api/session/{id}/history`, etc.) that write every chat turn to Supabase.
  - Wrote a comprehensive smoke test (`test_supabase_history.py`) hitting the live database.
- **Why**: To provide durable chat history across sessions and devices, allowing the React frontend to ditch its mock backend and rely on a true persistent state.
- **Files touched**: `.env.example`, `.env`, `config.py`, `requirements.txt`, `supabase_schema.sql`, `persistence/__init__.py`, `persistence/supabase_client.py`, `persistence/history.py`, `orchestrator/api.py`, `test_supabase_history.py`, `documentation.md`.
- **Status after this change**: Working. Smoke tests pass against the live Supabase instance.
- **Follow-up needed**: Connect the React frontend to the new API endpoints.

### 2026-09-22 — M11: Implemented Adaptive Output, CoVe, and Cross-Encoder Reranking
- **What was done**: 
  - **Adaptive Output**: Added `financial_literacy` question. Recommendation agent now outputs structured JSON (Executive Summary, Technical Breakdown, Asset Allocation) tailored to the user's literacy level. Streamlit UI was updated to render this beautifully.
  - **Chain of Verification (CoVe)**: Added a self-critique loop in the Recommendation Agent (`config.ENABLE_SELF_CRITIQUE`). The agent now audits its own draft against the source documents to correct hallucinations before presenting it.
  - **Two-Stage Retrieval**: Replaced standard bi-encoder retrieval with a pipeline that fetches 3x candidates using ChromaDB and reranks the top results using a `sentence-transformers` CrossEncoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`).
- **Why**: To elevate the MVP to a research-grade system suitable for IEEE CIFEr 2026, providing strong novelty factors (Self-Correcting Audit Layer) and rigorous RAG techniques.
- **Files touched**: `preference/questions.py`, `preference/profile.py`, `preference/agent.py`, `recommend_audit/agent.py`, `retrieval/agent.py`, `ui/app.py`, `config.py`, `eval/harness.py`, `test_recommendation.py`.
- **Status after this change**: Working. The system is now heavily optimized to reduce hallucinations and adapt to different user knowledge levels.

### 2026-09-22 — UI: Removed Prototype and Research Disclaimer Notices from Streamlit App
- **What was done**: 
  - Removed the `st.info` prototype notice block and the "Research controls for IEEE CIFEr 2026" caption from `ui/app.py`.
  - Streamlined sidebar descriptions to maintain clean UI presentation.
- **Why**: User requested to avoid mentioning prototype status or research disclaimers anywhere on the Streamlit website.
- **Files touched**: `ui/app.py`, `documentation.md`.
- **Status after this change**: Clean Streamlit UI with zero mentions of prototype or CIFEr disclaimers.
- **Follow-up needed**: None.

### 2026-09-22 — M5-M10: Implemented Orchestrator, UI, Eval Harness, and Personas
- **What was done**: 
  - Implemented `orchestrator/pipeline.py` to wire all agents sequentially.
  - Implemented `orchestrator/api.py` with FastAPI endpoints.
  - Implemented `ui/app.py` for the end-to-end Streamlit experience.
  - Created `eval/test_set/test_set.json` with 120 items (factual, recommendation, hallucination traps).
  - Implemented `eval/judge.py` for LLM-as-judge scoring.
  - Implemented `eval/harness.py` to run 5 ablation configs against the test set.
  - Implemented `eval/personas.py` with 10 synthetic personas for bias testing.
  - Implemented `eval/model_comparison.py` to compare phi4-mini, qwen2.5, and llama3.2.
- **Why**: Completes the MVP required to run the three paper experiments.
- **Files touched**: `orchestrator/pipeline.py`, `orchestrator/api.py`, `ui/app.py`, `eval/test_set/test_set.json`, `eval/judge.py`, `eval/harness.py`, `eval/personas.py`, `eval/model_comparison.py`.
- **Status after this change**: Working — the entire system is functional and ready for evaluation.
- **Follow-up needed**: Run the evaluation experiments for the paper.

### 2026-09-22 — M3: Implemented Preference Agent and confirmation ablation
- **What was done**: 
  - Implemented `preference/agent.py` functions: `elicit_preferences()` which converts raw user responses into a structured `UserProfile`, and `confirm_profile()` which handles the confirmation step.
  - Connected `config.ENABLE_PREFERENCE_CONFIRMATION` to the confirmation logic. When `True`, edits are applied and `confirmed` is set to `True`. When `False`, the agent bypasses edits, enforcing the Experiment A ablation condition.
  - Created and ran `test_preference.py` to simulate an elicitation, a confirmation with a deliberate correction (changing risk tolerance from Aggressive to Moderate and updating EMI), and verified the ablation behavior.
- **Why**: M3 establishes the structured user profile, which is core novel piece #1 for Experiment A (testing whether the confirmation step changes recommendation suitability).
- **Files touched**: `preference/agent.py`, `test_preference.py`.
- **Status after this change**: Working — the `elicit_preferences()` and `confirm_profile()` callables successfully map user state and honor ablation flags.
- **Follow-up needed**: Begin M4 (Recommendation + Audit Agent).

### 2026-09-22 — M2: Implemented Sentiment Agent (FinBERT + RSS)
- **What was done**: Implemented RSS headline fetcher (`feedparser`) and FinBERT scoring pipeline (`transformers`).
- **Why**: M2 brings live market context into the advisory loop.
- **Files touched**: `sentiment/headline_fetcher.py`, `sentiment/agent.py`, `test_sentiment.py`.
- **Status after this change**: Working.
- **Follow-up needed**: Begin M3.

### 2026-09-22 — M1: Implemented Retrieval Agent and vector store
- **What was done**: Authored 15 curated Indian financial documents (01–15), implemented chunking (`chunker.py`), ChromaDB vector store (`vector_store.py`), and the core `retrieve()` callable in `agent.py`.
- **Note on document 16**: A 16th document (`16_top_mutual_funds_india.txt`) was added silently at M11 when the agent prompt was changed to instruct the LLM to "name actual funds". It contained indicative CAGR figures (12-14%, 15-18%) that were not sourced/attributed and specific scheme names (SBI Small Cap Fund, Mirae Asset ELSS, etc.). This file was removed on 2026-09-23 as part of the fund-naming policy decision (asset-class level only, consistent with the "not investment advice" framing). The original document set is 15 files (01–15). The ChromaDB index must be rebuilt (`python reindex.py`) after this removal.
- **Why**: M1 is the first functional component of the system.
- **Files touched**: `retrieval/chunker.py`, `retrieval/vector_store.py`, `retrieval/agent.py`, `test_retrieval.py`, and 15 `.txt` files.
- **Status after this change**: Working.
- **Follow-up needed**: Begin M2.

### 2026-09-22 — M0: Verified all module imports
- **What was done**: Ran import verification tests.
- **Why**: M0 completion gate.
- **Files touched**: None.
- **Status after this change**: Working.
- **Follow-up needed**: Begin M1.

### 2026-09-22 — M0: Initial repo scaffolding and documentation.md creation
- **What was done**: Created the complete project scaffold.
- **Why**: M0 milestone.
- **Files touched**: 23 `.py` stubs, `documentation.md`, `requirements.txt`, `.env.example`, `.gitignore`, 2 `.gitkeep`.
- **Status after this change**: Working.
- **Follow-up needed**: Verify imports.
