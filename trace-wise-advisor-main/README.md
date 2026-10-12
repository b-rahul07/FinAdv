# Evidence Flow

Frontend Design Spec — AI Financial Advisor

For the frontend; connects to a separate Python/FastAPI backend (built in Antigravity)

0. What this is and isn't

This is a frontend-only build. All intelligence — retrieval, sentiment, preference elicitation logic, rule engine, LLM generation, audit/provenance — lives in the backend already being built separately. The frontend's job is: chat-style UI, state/history management, and calling the API contract defined in §4. Do not reimplement any business logic client-side.

Core design principle: this app's actual research contribution is auditability — every recommendation should visibly trace back to evidence. The UI needs to make that trace visible and legible, not bury it in a collapsed panel nobody opens. Treat the evidence trail as a first-class part of the interface, not an afterthought debug view.

1. Users and context

Primary audience for this build: project evaluators/judges and a small demo user group, not the general public. Design for clarity and trustworthiness over flashiness — calm, legible, and transparent beats trendy fintech gradients here. This is a financial-literacy tool, not a trading app; nothing should look like it's pushing urgency or hype.

2. Core user flow

Landing → Chat elicitation (7 questions) → Confirmation screen (editable) → Recommendation + Evidence → Chat history (persisted, resumable)


3. Screens

3.1 Landing

Short one-line description of what the tool does.

A visible, honest disclaimer: this is an educational/suitability tool, not investment advice, no return guarantees. (This isn't just legal cover — it's a stated design decision in the underlying research to avoid framing this as a forecasting system.)

"Start" button → begins a new session.

If chat history exists (see §3.5), also show "Resume previous conversation."

3.2 Chat elicitation

Conversational, one question at a time, agent-style message bubbles — this is the SAUR-style preference elicitation.

Where a question has a natural closed set of answers (risk tolerance, investment horizon, goal type), render quick-select buttons instead of free text — more reliable to parse on the backend and faster for the user. Free text input still available for anything numeric (income, existing EMI amount).

A subtle progress indicator ("Question 3 of 7").

Each answer, once submitted, appears in the chat thread like a normal chat message (this is what makes it feel like chat, not a form).

3.3 Confirmation screen (critical — this is the research feature)

After all 7 questions, show a structured summary card of the inferred profile: risk tolerance, investment horizon, goal type, monthly investable amount, existing EMI/BNPL exposure, income bracket.

Every field must be inline-editable before confirming — this isn't optional polish, the whole point of this screen is letting the user correct a wrong inference. Make edits obviously possible (pencil icon, click-to-edit, whatever pattern — just don't make it read-only-looking).

A visible "Confirm and get my recommendation" button that only finalizes the profile once pressed.

Label this screen clearly, e.g. "Here's what we understood — please review and correct anything before we continue," so it reads as a genuine checkpoint, not a summary the user skims past.

3.4 Recommendation + Evidence

The recommendation itself, in plain readable language, as the main content.

An Evidence panel (expandable side panel or drawer, not a modal you have to hunt for) showing, per claim in the recommendation:

which source document(s) it came from (with a readable name, e.g. "SEBI Risk-o-meter Circular," not a filename)

the sentiment signal used, if relevant, with its score

which rule fired (in plain language, e.g. "Your EMI-to-income ratio exceeds the recommended threshold")

If the backend response includes inline citations (claim → chunk_id), render them as small numbered footnote-style markers in the recommendation text that scroll/highlight the matching evidence panel item on click. If the backend doesn't provide inline citations, fall back to just listing all evidence used for that response beneath it — but design the component so inline citation rendering can be added later without a rebuild.

A visible loading state while the backend is generating — this can take real time (5–30s) on a local model, so show staged progress if the API supports it (e.g. "Retrieving relevant documents… → Checking market sentiment… → Generating your recommendation…") rather than a generic spinner. This staged loading state is also a good way to visually communicate the multi-agent architecture during a live demo.

3.5 Chat history (persisted, resumable)

A sidebar or accessible list of past sessions, each showing a short label (e.g. first question answered, or date/time) and letting the user resume it.

History is the source of truth from the backend (see §4) — don't rely on browser storage alone for the canonical record, though caching the current session in localStorage for instant reload before the backend round-trip completes is fine.

Resuming a session should replay the full chat thread, including past recommendations and their evidence panels, exactly as they appeared originally.

3.6 Demo/ablation toggle (for live demos and judging, not for a general user)

A small, clearly-separated "Demo settings" panel (e.g. a gear icon, out of the primary flow) with two toggles: Preference confirmation: On/Off and Audit-constrained generation: On/Off.

These map directly to the backend's ENABLE_PREFERENCE_CONFIRMATION and ENABLE_AUDIT_EVIDENCE flags. Purpose: let the team run the same query with a flag on vs. off, side by side, to visibly demonstrate the paper's ablation experiments to evaluators. This is a deliberate research-demo feature, not standard product UX — keep it visually distinct from the main flow so it doesn't confuse a first-time user.

4. API contract (backend responsibility — confirm exact shape with the backend before wiring)

This is a proposed contract based on the dataclasses already scaffolded on the backend (UserProfile, RetrievedChunk, SentimentSummary, Recommendation, ProvenanceRecord). Treat field names as placeholders to be confirmed, not final.

POST /api/session
  → { session_id }

POST /api/session/{session_id}/message
  body: { answer: string }
  → { type: "question", question: string, options?: string[] }
     | { type: "profile_summary", profile: {...UserProfile fields} }   // once all questions answered

POST /api/session/{session_id}/confirm
  body: { profile: {...edited UserProfile fields} }
  → { confirmed_profile: {...} }

POST /api/session/{session_id}/recommend
  → {
      recommendation_text: string,
      evidence: [
        { chunk_id, source_document, excerpt },
        ...
      ],
      sentiment_summary: { score, label, headlines_used },
      rule_fired: { rule_id, description },
      provenance: {...ProvenanceRecord fields}
    }

GET /api/session/{session_id}/history
  → { messages: [ { role: "user"|"assistant", content, timestamp, evidence?, profile_snapshot? }, ... ] }

GET/POST /api/config/ablation   (demo-only)
  → { enable_preference_confirmation: bool, enable_audit_evidence: bool }


Streaming note: if the backend's LLM generation is slow, consider whether /recommend should stream (SSE or chunked response) rather than block — worth asking the backend team before committing to a purely request/response pattern, since it changes the loading-state design in §3.4.

5. Visual direction

Calm, trustworthy palette — blues/teals/greens over hype-fintech gradients or neon.

Generous whitespace; the evidence panel especially can get dense (multiple chunks, scores, rule text), so prioritize legibility over cramming.

A consistent visual "trace" motif connecting recommendation claims to their evidence (color-coded tags, connecting lines on hover, or footnote markers) reinforces the core auditability idea throughout, not just on one screen.

Standard chat-bubble pattern for the elicitation flow; the confirmation and recommendation screens can break from pure chat-bubble format into structured cards, since they're not conversational, they're checkpoints.

6. Explicitly out of scope

No authentication/login system — session-based only for this MVP.

No payments, real trading, or brokerage integration.

No mobile native app — responsive web is sufficient.

No offline mode — always requires the backend to be reachable.

7. After generating this

Once the frontend produces its actual API-calling code, send the exact endpoint shapes back for review — they need to match, field-for-field, what Antigravity builds for M5 (the orchestrator/API layer). Mismatches here are the most likely integration failure point, so treat §4 as a draft contract to be finalized against both sides, not a spec either team should build against blindly.
use the reference images and build something similar to that 
i want a dark grey and vibrant color theme
maybe green maybe ornage something with good contrast and goes well togetehr looks modern yet simple and minimal

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```
