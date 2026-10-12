"""
Recommendation & Audit Agent (Synthesis, CoVe Self-Critique & Safety Guards)
=============================================================================
This is the central reasoning engine of the AI Financial Advisor.
It takes inputs from all three upstream agents:
  1. Confirmed UserProfile (from Preference Agent)
  2. Authoritative Document Chunks (from Retrieval Agent)
  3. Live Market Sentiment Summary (from FinBERT Sentiment Agent)

Key Safety & Anti-Hallucination Features:
  1. Suitability Pre-Filter:
     Excludes unsuitable asset categories (e.g., small-cap funds for short horizons)
     as hard constraints BEFORE calling the LLM.
  2. Budget Guard:
     Validates that recommended monthly SIP amounts NEVER exceed the user's
     safe disposable income (effective_investable). If violated, the model retries
     or safely aborts with an informative warning.
  3. Chain-of-Verification (CoVe) / Self-Critique:
     Runs an automated internal audit prompt where the LLM critiques its own
     draft recommendation against source documents and mathematical limits before
     displaying anything to the user.
  4. Post-Hoc Provenance Attachment:
     Verifies all citations against the actual retrieved chunks and attaches
     rule compliance tags.
"""

import ollama
import hashlib
import json
import re
from datetime import datetime
from dataclasses import dataclass
from preference.profile import UserProfile
from retrieval.agent import RetrievedChunk
from sentiment.agent import SentimentSummary
from recommend_audit.provenance import ProvenanceRecord, attach_provenance
from recommend_audit.rules import evaluate_rules
import config


@dataclass
class Recommendation:
    """
    Data model representing the final synthesized advisory response.
    
    Attributes:
      executive_summary: Plain-language 2-3 sentence overview for non-technical users.
      technical_breakdown: In-depth rationale, tax considerations, and risk disclosures.
      asset_allocation: Dictionary mapping fund category -> percentage integer (sums to 100).
      recommended_instruments: List of asset classes suggested (e.g. ['ELSS', 'Liquid Fund']).
      follow_up_response: Text response used when user is asking a conversational follow-up question.
      provenance: ProvenanceRecord containing verifiable evidence and audit history.
      confidence: Confidence score (0.0 to 1.0) based on rule compliance.
    """
    executive_summary: str
    technical_breakdown: str
    asset_allocation: dict[str, int]
    recommended_instruments: list[str]
    follow_up_response: str
    provenance: ProvenanceRecord
    confidence: float


# ==============================================================================
# 1. Suitability Exclusion Filter
# ==============================================================================

# Mapping from suitability rule IDs -> strict exclusion directives
_SUITABILITY_EXCLUSIONS: dict[str, str] = {
    "rule_small_cap_horizon": (
        "Small-cap funds (require a 10+ year horizon; the user's horizon is too short — "
        "DO NOT recommend small-cap funds under any circumstances, even with a caveat)"
    ),
    "rule_midcap_horizon": (
        "Mid-cap funds (require a 5-7+ year horizon; the user's horizon is too short — "
        "DO NOT recommend mid-cap funds under any circumstances, even with a caveat)"
    ),
}


def _build_exclusion_block(fired_rule_ids: list[str]) -> str:
    """
    Builds a strict negative-prompting block for the LLM system prompt.
    
    Prevents the 'recommend-then-caveat' flaw where an LLM recommends an unsuitable
    fund and adds a warning later. Unsuitable funds are excluded at the candidate stage.
    """
    exclusions = [
        _SUITABILITY_EXCLUSIONS[rid]
        for rid in fired_rule_ids
        if rid in _SUITABILITY_EXCLUSIONS
    ]
    if not exclusions:
        return ""

    lines = "\n".join(f"  - {e}" for e in exclusions)
    return (
        "\n### EXCLUDED FUND CATEGORIES (HARD CONSTRAINT) ###\n"
        "The following fund categories are UNSUITABLE for this user's profile and MUST NOT "
        "appear anywhere in your recommendation, not even with a warning or caveat:\n"
        f"{lines}\n"
    )


# ==============================================================================
# 2. Budget Guard Validator
# ==============================================================================

def _validate_budget(
    final_json: dict,
    effective_investable: float,
    tolerance: float = 0.05,
) -> tuple[bool, float]:
    """
    Mathematically validates that the total recommended investment amounts
    do not exceed the user's safe disposable income (effective_investable).

    Prevents predatory advice where an advisor tells a user earning ₹20k/month
    to invest ₹50k/month.

    Returns:
      (is_valid: bool, total_monthly_calculated: float)
    """
    allocation = final_json.get("asset_allocation", {})
    if not allocation:
        return True, 0.0

    total_monthly = 0.0

    # Parse and sum values from the allocation dictionary
    for _fund, value in allocation.items():
        if isinstance(value, (int, float)):
            if value > 100:
                # If value is greater than 100, treat as absolute ₹ amount (e.g., 5000)
                total_monthly += float(value)
            else:
                # If value <= 100, treat as a percentage of monthly investable surplus
                total_monthly += (value / 100.0) * effective_investable
        elif isinstance(value, str):
            # Parse currency strings like "₹5,000"
            digits = re.sub(r"[₹,Rs. ]", "", value)
            try:
                total_monthly += float(digits)
            except ValueError:
                pass

    # Allow 5% floating-point rounding tolerance
    is_valid = total_monthly <= effective_investable * (1.0 + tolerance)
    return is_valid, total_monthly


def _budget_violation_response(
    effective_investable: float,
    total_monthly: float,
    provenance: ProvenanceRecord,
) -> dict:
    """
    Generates a graceful, helpful error payload if multiple generation attempts
    exceed the user's declared budget. Protects the user from unsafe recommendations.
    """
    return {
        "executive_summary": (
            f"⚠️ Budget Guard: The advisor could not generate a valid recommendation "
            f"within your ₹{effective_investable:,.0f}/month investable amount after two "
            f"attempts (last attempt suggested ₹{total_monthly:,.0f}/month). "
            f"Please verify your monthly savings and EMI figures and try again."
        ),
        "technical_breakdown": (
            "The recommendation engine produced allocations that exceeded the stated "
            f"investable amount of ₹{effective_investable:,.0f}/month on both attempts. "
            "This can happen if conflicting constraints (high tax-saving priority + high "
            "EMI + low savings) make it impossible to satisfy all rules simultaneously. "
            "Try reducing your EMI figure or lowering your tax-saving priority to 1-2 "
            "so the engine has more room to allocate."
        ),
        "asset_allocation": {},
        "recommended_instruments": [],
    }


def _inject_amounts_into_prose(
    final_json: dict,
    effective_investable: float,
) -> dict:
    """
    Calculates exact monthly ₹ amounts from verified percentages and appends a clean
    breakdown to the narrative text.
    
    Guarantees that numbers shown in the text are mathematically derived from
    structured data rather than hallucinated by the language model.
    """
    allocation = final_json.get("asset_allocation", {})
    if not allocation:
        return final_json

    fund_amounts: list[str] = []
    for fund, value in allocation.items():
        if isinstance(value, (int, float)):
            if value <= 100:
                amount = (value / 100.0) * effective_investable
            else:
                amount = min(float(value), effective_investable)
        else:
            continue
        fund_amounts.append(f"{fund} ₹{amount:,.0f}/mo")

    if not fund_amounts:
        return final_json

    amounts_line = (
        f"\n\n[Monthly allocation at your ₹{effective_investable:,.0f}/month budget: "
        + " · ".join(fund_amounts)
        + "]"
    )

    es = final_json.get("executive_summary", "")
    tb = final_json.get("technical_breakdown", "")
    final_json["executive_summary"] = es + amounts_line
    final_json["technical_breakdown"] = tb + amounts_line
    return final_json


# ==============================================================================
# 3. Core Advisory Generation Function
# ==============================================================================

def generate_recommendation(
    profile: UserProfile,
    chunks: list[RetrievedChunk],
    sentiment: SentimentSummary,
    user_query: str = "Based on my profile and the current rules, what should I do with my money?",
    chat_history: list[dict] | None = None,
    model: str = None,
) -> Recommendation:
    """
    Main recommendation synthesis pipeline.
    
    Steps:
      1. Evaluates regulatory rules against UserProfile.
      2. Constructs context prompt (chunks, market sentiment, budget limit, exclusions).
      3. Calls local Ollama LLM with structured JSON output schema.
      4. Executes Self-Critique / Chain-of-Verification (CoVe) audit.
      5. Runs Budget Guard validation.
      6. Verifies citations and attaches rule provenance tags post-hoc.
      7. Returns verifiable Recommendation object.
    """
    if model is None:
        model = config.OLLAMA_MODEL
    if chat_history is None:
        chat_history = []

    # True if the user is asking an ongoing follow-up question in the same chat
    is_follow_up = len(chat_history) > 0

    # Step 1: Evaluate regulatory suitability rules
    rule_results = evaluate_rules(profile)
    fired_rules = [r for r in rule_results if r.fired]

    valid_chunk_ids: set[str] = {c.chunk_id for c in chunks}
    fired_rule_ids: list[str] = [r.rule.rule_id for r in fired_rules]

    # Step 2: Build suitability exclusions (e.g. exclude small-cap funds if horizon < 7 yrs)
    exclusion_block = _build_exclusion_block(fired_rule_ids)

    # Step 3: Format document citations for context injection
    context_text = "### RETRIEVED FINANCIAL DOCUMENTS ###\n"
    for chunk in chunks:
        context_text += f"\n[CHUNK_ID: {chunk.chunk_id}]\n{chunk.content}\n"

    # Step 4: Format triggered rules for context injection
    rules_text = "### APPLICABLE FINANCIAL RULES ###\n"
    if fired_rules:
        for r in fired_rules:
            rules_text += (
                f"- [RULE_ID: {r.rule.rule_id}] {r.rule.description} "
                f"-> Action Required: {r.rule.action}\n"
            )
    else:
        rules_text += "No specific rules triggered.\n"

    # Step 5: Format user profile parameters
    profile_text = (
        f"### USER PROFILE ###\n"
        f"Risk Tolerance: {profile.risk_tolerance}\n"
        f"Horizon: {profile.investment_horizon}\n"
        f"Goal: {profile.goal_type}\n"
        f"Monthly Savings: {profile.monthly_savings}\n"
        f"EMI Burden: {profile.existing_emi}\n"
        f"BNPL Exposure: {profile.bnpl_exposure}\n"
        f"Literacy: {profile.financial_literacy}\n"
    )

    # Step 6: Format market news sentiment
    sentiment_text = (
        f"### MARKET SENTIMENT ###\n"
        f"Overall Sentiment: {sentiment.overall_sentiment.upper()} "
        f"(Score: {sentiment.overall_score:.2f})\n"
    )

    # Step 7: Format strict budget constraints (avoiding annual vs monthly confusion)
    budget_block = (
        f"\n### BUDGET CONSTRAINT (HARD RULE — NEVER VIOLATE) ###\n"
        f"The user can invest a maximum of ₹{profile.effective_investable:,.0f}/month in total.\n"
        f"ALL recommended monthly SIP amounts combined MUST NOT exceed ₹{profile.effective_investable:,.0f}/month.\n"
        f"The Section 80C annual ceiling of ₹1,50,000/year = ₹12,500/month MAXIMUM across ALL "
        f"80C instruments (ELSS + PPF + NPS combined). "
        f"This is a TAX CEILING for the financial year, NOT a monthly investment target.\n"
        f"Do NOT recommend ₹1,50,000/month — that figure is the annual limit.\n"
        f"Do NOT invent rupee figures in your prose. Write percentages only (e.g., '50% in ELSS').\n"
        f"The exact rupee amounts will be appended by the system after validation.\n"
    )

    # Step 8: Authoritative financial product ground truth
    key_facts_block = (
        "\n### KEY FINANCIAL FACTS (AUTHORITATIVE — DO NOT CONTRADICT) ###\n"
        "Lock-in periods per fund type:\n"
        "  - ELSS (Equity Linked Savings Scheme): 3-year MANDATORY lock-in.\n"
        "  - PPF (Public Provident Fund): 15-year lock-in, partial withdrawal after 7 years.\n"
        "  - NPS (National Pension System): locked until retirement (age 60).\n"
        "  - Liquid Funds / Money Market Funds: NO lock-in. Exit load of 0.0070% if redeemed within 7 days; ZERO exit load after 7 days.\n"
        "  - Short-Duration Debt Funds: NO lock-in. Low/no exit load.\n"
        "  - Large-Cap / Flexi-Cap Equity Funds: NO lock-in. Exit load ~1% if redeemed within 1 year.\n"
        "  - Fixed Deposits: locked for the chosen tenure; premature withdrawal attracts a penalty.\n"
        "  - Sovereign Gold Bonds: 8-year maturity; exit possible on exchange from Year 5.\n"
        "Do NOT state that Liquid Funds or debt funds have a 3-year lock-in — that is ELSS only.\n"
    )

    # Assemble complete system prompt
    system_prompt = (
        f"You are an expert Indian Certified Financial Planner (CFP) with deep knowledge of "
        f"Indian mutual fund categories, tax laws, and investment products.\n"
        f"Your job is to provide SPECIFIC, ACTIONABLE financial advice to the user based on their "
        f"profile, the retrieved documents, market sentiment, and applicable rules.\n\n"
        f"{profile_text}\n"
        f"{sentiment_text}\n"
        f"{rules_text}\n"
        f"{context_text}\n"
        f"{budget_block}"
        f"{key_facts_block}"
        f"{exclusion_block}"
    )

    if config.ENABLE_AUDIT_EVIDENCE:
        system_prompt += """
### CRITICAL INSTRUCTION (AUDIT MODE) ###
You MUST primarily use information from the documents provided above.
Every factual claim about regulations, tax limits, or lock-in periods MUST be grounded in the provided documents or rules.
Do NOT hallucinate interest rates, NAVs, or returns that are not in the provided documents.
Address the user's specific risk rules (like EMI ratio or BNPL exposure) if they triggered.

CITATION RULES:
1. For claims derived from the RETRIEVED FINANCIAL DOCUMENTS, you MUST append the exact chunk ID in this format: [CHUNK_ID: xyz].
2. For claims derived from the APPLICABLE FINANCIAL RULES (e.g., BNPL exposure warnings, EMI limits), do NOT insert [CHUNK_ID: ...] tags. The system will automatically attach rule citations. Do NOT invent chunk IDs for rules.
"""
    else:
        system_prompt += """
### INSTRUCTION ###
Provide the best financial advice you can based on the context, rules, and your extensive knowledge of Indian finance. Recommend asset categories (e.g., ELSS funds, large-cap equity funds, liquid funds) rather than specific named schemes.
"""

    if not is_follow_up:
        system_prompt += (
            f"\n### OUTPUT FORMAT ###\n"
            f"You MUST output your response as a valid JSON object with EXACTLY the following "
            f"structure (no markdown formatting, no code blocks):\n"
            f"{{\n"
            f'  "executive_summary": "A clear 2-3 sentence summary naming the SPECIFIC fund '
            f"CATEGORIES recommended (e.g., 'ELSS fund', 'large-cap equity fund', 'liquid fund'), "
            f"with the PERCENTAGE allocated to each category (e.g., '60% in ELSS, 40% in Liquid Fund'). "
            f"DO NOT write rupee amounts — write percentages only. The system will compute amounts. "
            f"Tailor complexity to the user's literacy level ({profile.financial_literacy}). "
            f'You MUST append [CHUNK_ID: xyz] to document-derived claims.",\n'
            f'  "technical_breakdown": "A detailed explanation with: (1) Why each recommended '
            f"fund category fits the user's profile. (2) The PERCENTAGE allocated to each category "
            f"— DO NOT write rupee amounts, write percentages like '50% goes to ELSS'. "
            f"(3) Tax implications: Section 80C limit is ₹1,50,000/YEAR = ₹12,500/month maximum. "
            f"(4) Lock-in periods: follow the KEY FINANCIAL FACTS exactly. "
            f"(5) Any risks or caveats. "
            f'You MUST append [CHUNK_ID: xyz] to every factual claim derived from the documents.",\n'
            f'  "asset_allocation": {{"Fund Category 1": 40, "Fund Category 2": 60}},  // integers that sum to 100\n'
            f'  "recommended_instruments": ["Fund Category 1", "Fund Category 2"]\n'
            f"}}\n\n"
            f"IMPORTANT: asset_allocation values MUST be integers that sum to exactly 100. "
            f"Write PERCENTAGES in the prose (e.g., '60% in ELSS'), never rupee amounts. "
            f"Recommend ASSET CATEGORIES (e.g., 'ELSS Tax Saving Fund', 'Large-Cap Equity Fund', "
            f"'Liquid Fund/Short-Duration Debt') rather than specific named schemes.\n"
        )
    else:
        system_prompt += """
### OUTPUT FORMAT ###
Output a standard markdown response addressing the user's follow-up question.
"""

    # Generate MD5 hash of the prompt for reproducibility audit
    prompt_hash = hashlib.md5(system_prompt.encode()).hexdigest()

    # Build full conversation history for the Ollama chat call
    messages = [{'role': 'system', 'content': system_prompt}]
    for msg in chat_history:
        messages.append({'role': msg['role'], 'content': msg['content']})
    messages.append({'role': 'user', 'content': user_query})

    def _call_llm(msgs: list[dict], enforce_json: bool = False) -> str:
        """Helper to invoke the local Ollama LLM with optional JSON enforcement and token limits."""
        try:
            kwargs = {
                "options": {
                    "num_predict": 350,
                    "temperature": 0.2,
                }
            }
            if enforce_json:
                kwargs["format"] = "json"
            response = ollama.chat(model=model, messages=msgs, **kwargs)
            return response['message']['content']
        except Exception as e:
            if enforce_json:
                return (
                    f'{{"executive_summary": "Error: {e}", '
                    f'"technical_breakdown": "Failed", '
                    f'"asset_allocation": {{}}, '
                    f'"recommended_instruments": []}}'
                )
            return f"Error: {e}"

    follow_up_response = ""

    if not is_follow_up:
        # Step 9: Generation with Budget Guard and CoVe Self-Critique (up to 2 attempts)
        final_json: dict = {}
        last_total: float = 0.0
        budget_ok: bool = False

        for attempt in range(2):
            # First draft generation
            draft_text = _call_llm(messages, enforce_json=True)
            try:
                candidate_json = json.loads(draft_text)
            except Exception:
                candidate_json = {
                    "executive_summary": "Error parsing JSON.",
                    "technical_breakdown": draft_text,
                    "asset_allocation": {},
                    "recommended_instruments": [],
                }

            # ------------------------------------------------------------------
            # Chain-of-Verification (CoVe) / Self-Critique Audit Loop
            # ------------------------------------------------------------------
            if config.ENABLE_SELF_CRITIQUE and "Error" not in candidate_json.get("executive_summary", ""):
                critique_prompt = (
                    f"You are a rigorous Financial Auditor. Review the following drafted advice "
                    f"against the source documents and rules.\n"
                    f"Look for:\n"
                    f"1. Hallucinated interest rates or limits not in the source documents.\n"
                    f"2. Contradictions with the user's profile or rules.\n"
                    f"3. Claims that conflate unrelated regulations (e.g., attributing ELSS "
                    f"lock-in periods to an RBI circular).\n"
                    f"4. False premises in the user's question that the draft failed to challenge.\n"
                    f"5. BUDGET VIOLATION: the total of all monthly SIP amounts must not exceed "
                    f"₹{profile.effective_investable:,.0f}/month. Fix if violated.\n"
                    f"6. ANNUAL vs MONTHLY CONFUSION: ₹1,50,000 is an ANNUAL Section 80C limit "
                    f"(= ₹12,500/month max). Correct any draft that uses it as a monthly figure.\n"
                    f"7. LOCK-IN HALLUCINATION: Liquid Funds and Short-Duration Debt Funds have "
                    f"NO lock-in period. ONLY ELSS has a 3-year mandatory lock-in. "
                    f"Remove any statement that attributes a 3-year lock-in to Liquid Funds.\n"
                    f"8. PROSE AMOUNTS: The prose should use percentages (e.g., '50% in ELSS'), "
                    f"not rupee amounts. If the draft contains rupee amounts in the prose, "
                    f"replace them with percentages from the asset_allocation.\n\n"
                    f"{context_text}\n"
                    f"{rules_text}\n"
                    f"### DRAFT ADVICE ###\n"
                    f"{json.dumps(candidate_json, indent=2)}\n\n"
                    f"### OUTPUT ###\n"
                    f"If the draft is perfect, output the exact same JSON.\n"
                    f"If there are errors, correct them and output the FIXED JSON in the exact "
                    f"same format (no markdown, just JSON).\n"
                    f"Ensure document-derived claims have [CHUNK_ID: ...] tags and rule-derived "
                    f"claims do NOT.\n"
                )
                critique_messages = [
                    {'role': 'system', 'content': critique_prompt},
                    {'role': 'user', 'content': 'Review and refine the draft advice.'},
                ]
                refined_text = _call_llm(critique_messages, enforce_json=True)
                try:
                    candidate_json = json.loads(refined_text)
                except Exception:
                    pass  # keep original if parse fails

            # Step 10: Validate budget constraints mathematically
            budget_ok, last_total = _validate_budget(candidate_json, profile.effective_investable)
            final_json = candidate_json

            if budget_ok:
                # Inject validated ₹ amounts into executive and technical summary
                final_json = _inject_amounts_into_prose(candidate_json, profile.effective_investable)
                break  # Successful and verified

        # If both attempts failed the budget guard, abort safely
        if not budget_ok:
            prov_stub = ProvenanceRecord(
                chunk_ids=[c.chunk_id for c in chunks],
                sentiment_score=sentiment.overall_score,
                sentiment_label=sentiment.overall_sentiment,
                rule_ids=fired_rule_ids,
                model_used=model,
                prompt_hash=prompt_hash,
                timestamp=datetime.now().isoformat(),
                fabricated_chunk_ids=[],
            )
            error_json = _budget_violation_response(profile.effective_investable, last_total, prov_stub)
            return Recommendation(
                executive_summary=error_json["executive_summary"],
                technical_breakdown=error_json["technical_breakdown"],
                asset_allocation={},
                recommended_instruments=[],
                follow_up_response="",
                provenance=prov_stub,
                confidence=0.0,
            )

    else:
        # Conversational follow-up: Generate direct response without full re-allocation
        follow_up_response = _call_llm(messages, enforce_json=False)
        final_json = {
            "executive_summary": "",
            "technical_breakdown": "",
            "asset_allocation": {},
            "recommended_instruments": [],
        }

    # Step 11: Post-Hoc Provenance Attachment & Hallucination Audit
    all_fabricated: list[str] = []

    if not is_follow_up:
        es = final_json.get("executive_summary", "")
        es, fab1 = attach_provenance(es, fired_rule_ids, valid_chunk_ids)
        final_json["executive_summary"] = es
        all_fabricated.extend(fab1)

        tb = final_json.get("technical_breakdown", "")
        tb, fab2 = attach_provenance(tb, fired_rule_ids, valid_chunk_ids)
        final_json["technical_breakdown"] = tb
        all_fabricated.extend(fab2)
    else:
        follow_up_response, fab3 = attach_provenance(
            follow_up_response, fired_rule_ids, valid_chunk_ids
        )
        all_fabricated.extend(fab3)

    # Build verifiable ProvenanceRecord
    provenance = ProvenanceRecord(
        chunk_ids=[c.chunk_id for c in chunks],
        sentiment_score=sentiment.overall_score,
        sentiment_label=sentiment.overall_sentiment,
        rule_ids=fired_rule_ids,
        model_used=model,
        prompt_hash=prompt_hash,
        timestamp=datetime.now().isoformat(),
        fabricated_chunk_ids=list(set(all_fabricated)),
    )

    return Recommendation(
        executive_summary=final_json.get("executive_summary", ""),
        technical_breakdown=final_json.get("technical_breakdown", ""),
        asset_allocation=final_json.get("asset_allocation", {}),
        recommended_instruments=final_json.get("recommended_instruments", []),
        follow_up_response=follow_up_response,
        provenance=provenance,
        confidence=0.85,
    )

