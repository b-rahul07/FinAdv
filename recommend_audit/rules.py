"""
Deterministic Rule Engine (Indian Financial Regulations & Suitability)
========================================================================
This module acts as an algorithmic safety guardrail.
While Large Language Models can write convincing text, they frequently make basic
arithmetic errors or recommend unsuitable products (such as recommending high-risk
small-cap funds to a retiree needing money next year, or treating an annual ₹1.5L tax
limit as a monthly SIP).

To guarantee safety and SEBI-aligned suitability, this rule engine evaluates deterministic
rules against the user's profile and injects strict constraints into the prompt and audit.

Key Rules Encoded:
  1. Section 80C Annual Ceiling (₹1,50,000/year max across ELSS, PPF, NPS)
  2. ELSS 3-Year Mandatory Lock-in Guard
  3. PPF 15-Year Lock-in Suitability Guard
  4. Debt-to-Cashflow Ratio Guard (EMI burden should not exceed 40-50%)
  5. High-Risk BNPL (Buy Now Pay Later) Over-Leverage Warning
  6. Small-Cap Fund Horizon Guard (Requires >= 7-10 years investment horizon)
  7. Mid-Cap Fund Horizon Guard (Requires >= 5 years investment horizon)
"""

from dataclasses import dataclass
from preference.profile import UserProfile


@dataclass
class Rule:
    """
    Data model representing a single financial constraint or regulatory rule.
    
    Attributes:
      rule_id: Unique string identifier (e.g. 'rule_80c_limit') for audit logs.
      description: Plain-English explanation of the regulatory requirement.
      category: Rule classification ('tax', 'lock_in', 'risk_constraint', 'suitability').
      condition: Condition logic string explaining when the rule triggers.
      action: Strict prescription injected into the LLM system instructions.
    """
    rule_id: str
    description: str
    category: str
    condition: str
    action: str


@dataclass
class RuleResult:
    """
    Evaluation output of a single rule against a specific user's profile.
    
    Attributes:
      rule: The Rule definition evaluated.
      fired: Boolean flag: True if the user's situation triggered this rule.
      detail: Contextual explanation of why the rule fired.
    """
    rule: Rule
    fired: bool
    detail: str


# Mapping of common investment duration strings to numeric maximum years
# Used to calculate suitability mathematically rather than relying on LLM guesses
_HORIZON_BRACKETS: list[tuple[str, int, int]] = [
    ("short",  0,  3),   # e.g., "Short-term (< 1 year)" or "1-3 years"
    ("medium", 1,  5),   # e.g., "Medium-term (1-5 years)"
    ("long",   5, 30),   # e.g., "Long-term (> 5 years)"
]


def _horizon_max_years(investment_horizon: str) -> int:
    """
    Converts a conversational horizon string into an approximate maximum number of years.
    Returns 0 if unrecognized (treating unknown as the most conservative/restrictive).
    """
    h = investment_horizon.lower()
    for label, _min, max_y in _HORIZON_BRACKETS:
        if label in h:
            return max_y
    return 0


# Master catalog of financial safety rules
RULES: list[Rule] = [
    Rule(
        # Rule 1: Income Tax Act Section 80C Limit
        rule_id="rule_80c_limit",
        description="Section 80C deduction capped at ₹1,50,000 per financial year",
        category="tax",
        condition="User has tax_saving_priority >= 3",
        action=(
            "Recommend tax-saving instruments (ELSS, PPF, NPS, etc.) up to the "
            "Section 80C annual ceiling of ₹1,50,000 per financial year. "
            "This equals a maximum of ₹12,500/month spread across all 80C instruments. "
            "DO NOT present the ₹1,50,000 annual limit as a monthly SIP figure."
        ),
    ),
    Rule(
        # Rule 2: ELSS Lock-in Protection
        rule_id="rule_elss_lockin",
        description="ELSS has a mandatory 3-year lock-in period",
        category="lock_in",
        condition="User's horizon is short-term AND ELSS is being considered",
        action="Warn about 3-year lock-in; suggest liquid alternatives if horizon < 3 years",
    ),
    Rule(
        # Rule 3: PPF Lock-in Protection
        rule_id="rule_ppf_lockin",
        description="PPF has a 15-year lock-in with partial withdrawal after 7 years",
        category="lock_in",
        condition="User's horizon is short/medium-term AND PPF is being considered",
        action="Flag long lock-in; only recommend if horizon is long-term",
    ),
    Rule(
        # Rule 4: Over-indebtedness Guard
        rule_id="rule_emi_ratio",
        description="EMI-to-income ratio should not exceed 40-50%",
        category="risk_constraint",
        condition="User's existing_emi is high relative to monthly_savings",
        action="Prioritize debt reduction or emergency fund before aggressive investment",
    ),
    Rule(
        # Rule 5: Predatory BNPL Debt Warning
        rule_id="rule_bnpl_warning",
        description="Significant BNPL exposure indicates potential over-leveraging",
        category="risk_constraint",
        condition="User's BNPL exposure is 'Significant' or 'Heavy'",
        action="Flag BNPL risk; recommend clearing BNPL before new investments",
    ),
    Rule(
        # Rule 6: Small-Cap Volatility Horizon Guard
        rule_id="rule_small_cap_horizon",
        description=(
            "Small-cap funds require a minimum 10-year investment horizon due to high "
            "volatility; they can fall 40-60% in bear markets"
        ),
        category="suitability",
        condition="User's investment horizon yields a maximum of < 7 years",
        action=(
            "EXCLUDE all small-cap fund categories from recommendations entirely. "
            "Do not suggest them even with caveats — they are unsuitable for this horizon."
        ),
    ),
    Rule(
        # Rule 7: Mid-Cap Horizon Guard
        rule_id="rule_midcap_horizon",
        description=(
            "Mid-cap funds require a minimum 5-7 year investment horizon due to "
            "moderate-to-high volatility"
        ),
        category="suitability",
        condition="User's investment horizon yields a maximum of < 5 years",
        action=(
            "EXCLUDE all mid-cap fund categories from recommendations entirely. "
            "Do not suggest them even with caveats — they are unsuitable for this horizon."
        ),
    ),
]


def evaluate_rules(profile: UserProfile) -> list[RuleResult]:
    """
    Evaluates all predefined financial rules against the given UserProfile.
    
    Iterates through each rule and checks whether the user's financial profile
    triggers that constraint. Returns a list of RuleResult objects for all rules.

    Parameters:
      profile: The user's confirmed UserProfile.

    Returns:
      List of RuleResult objects showing which rules 'fired' (active) and why.
    """
    results = []
    horizon_max = _horizon_max_years(profile.investment_horizon)

    for rule in RULES:
        fired = False
        detail = ""

        # Check 1: 80C Tax Limit
        if rule.rule_id == "rule_80c_limit":
            if profile.tax_saving_priority >= 3:
                fired = True
                detail = (
                    f"Tax saving priority is high ({profile.tax_saving_priority}/5). "
                    f"Section 80C ceiling: ₹1,50,000/year (≤ ₹12,500/month across all 80C instruments)."
                )

        # Check 2: ELSS 3-Year Lock-in
        elif rule.rule_id == "rule_elss_lockin":
            if "short-term" in profile.investment_horizon.lower():
                fired = True
                detail = "Horizon is short-term, ELSS lock-in is a risk."

        # Check 3: PPF 15-Year Lock-in
        elif rule.rule_id == "rule_ppf_lockin":
            if (
                "short-term" in profile.investment_horizon.lower()
                or "medium-term" in profile.investment_horizon.lower()
            ):
                fired = True
                detail = f"Horizon is '{profile.investment_horizon}', PPF 15-year lock-in is unsuitable."

        # Check 4: EMI Burden Ratio
        elif rule.rule_id == "rule_emi_ratio":
            income_approx = profile.monthly_savings + profile.existing_emi
            if income_approx > 0:
                ratio = profile.existing_emi / income_approx
                if ratio > 0.4:
                    fired = True
                    detail = f"EMI ratio is high at {ratio*100:.1f}% of approximate cashflow."

        # Check 5: BNPL Debt Exposure
        elif rule.rule_id == "rule_bnpl_warning":
            bnpl = profile.bnpl_exposure.lower()
            if "significant" in bnpl or "heavy" in bnpl:
                fired = True
                detail = f"User has {profile.bnpl_exposure} BNPL exposure."

        # Check 6: Small-Cap Horizon Suitability (< 7 years)
        elif rule.rule_id == "rule_small_cap_horizon":
            if horizon_max < 7:
                fired = True
                detail = (
                    f"Horizon '{profile.investment_horizon}' (max ~{horizon_max} years) "
                    f"is below the 7-year safety threshold for small-cap funds. "
                    f"Small-cap funds excluded from candidates."
                )

        # Check 7: Mid-Cap Horizon Suitability (< 5 years)
        elif rule.rule_id == "rule_midcap_horizon":
            if horizon_max < 5:
                fired = True
                detail = (
                    f"Horizon '{profile.investment_horizon}' (max ~{horizon_max} years) "
                    f"is below the 5-year threshold for mid-cap funds. "
                    f"Mid-cap funds excluded from candidates."
                )

        results.append(RuleResult(rule=rule, fired=fired, detail=detail))

    return results

