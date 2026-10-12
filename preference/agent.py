"""
Preference Agent (SAUR-Style Elicitation & Confirmation)
==========================================================
The Preference Agent is the first active stage in the pipeline.
Its role is twofold:
  1. Elicit: Convert the user's raw answers from the questionnaire into a typed,
     sanitized UserProfile object.
  2. Confirm: Allow the user to review, correct, or adjust their risk profile
     before any algorithmic recommendations are calculated.
"""

from preference.profile import UserProfile
import config


def elicit_preferences(
    user_responses: dict[str, str],
) -> UserProfile:
    """
    Translates raw text answers into a structured UserProfile.

    Handles data cleansing:
      - Strips commas and symbols from currency figures (e.g., "₹50,000" -> 50000.0)
      - Safely defaults missing or invalid inputs to 0.0 or default strings
      - Computes derived financial metrics (investable surplus)

    Parameters:
      user_responses: Dictionary mapping question_id -> user answer string.

    Returns:
      A fully populated UserProfile object.
    """
    # Parse monthly savings capacity safely
    try:
        raw_savings = str(user_responses.get("monthly_savings", "0")).replace(",", "").replace("₹", "").strip()
        savings = float(raw_savings)
    except ValueError:
        savings = 0.0

    # Parse existing monthly loan EMIs safely
    try:
        raw_emi = str(user_responses.get("existing_emi", "0")).replace(",", "").replace("₹", "").strip()
        emi = float(raw_emi)
    except ValueError:
        emi = 0.0

    # Parse tax saving urgency priority score (1 to 5)
    try:
        tax_priority = int(user_responses.get("tax_saving_priority", "0"))
    except ValueError:
        tax_priority = 0

    # Build the profile object
    profile = UserProfile(
        risk_tolerance=user_responses.get("risk_tolerance", ""),
        investment_horizon=user_responses.get("investment_horizon", ""),
        goal_type=user_responses.get("goal_type", ""),
        monthly_savings=savings,
        existing_emi=emi,
        bnpl_exposure=user_responses.get("bnpl_exposure", ""),
        tax_saving_priority=tax_priority,
        financial_literacy=user_responses.get("financial_literacy", "")
    )

    # Compute disposable investable surplus and normalize category names
    profile.compute_derived_fields()
    return profile


def confirm_profile(
    profile: UserProfile,
    edits: dict[str, str] | None = None,
) -> UserProfile:
    """
    Applies any adjustments submitted by the user during the profile review stage
    and marks the profile as verified/confirmed.

    Behavior under ablation (ENABLE_PREFERENCE_CONFIRMATION = False):
      - Skips confirmation and marks profile.confirmed = False.

    Parameters:
      profile: The initial UserProfile generated from the questionnaire.
      edits: Optional dictionary of edited fields submitted by the user.

    Returns:
      The updated, confirmed UserProfile ready for retrieval and recommendation.
    """
    if not config.ENABLE_PREFERENCE_CONFIRMATION:
        # Ablation mode: Proceed directly without user verification
        profile.confirmed = False
        return profile

    # Apply any specific overrides submitted by the user
    if edits:
        profile.confirmation_edits = edits

        if "risk_tolerance" in edits:
            profile.risk_tolerance = edits["risk_tolerance"]
        if "investment_horizon" in edits:
            profile.investment_horizon = edits["investment_horizon"]
        if "goal_type" in edits:
            profile.goal_type = edits["goal_type"]
        if "bnpl_exposure" in edits:
            profile.bnpl_exposure = edits["bnpl_exposure"]
        if "financial_literacy" in edits:
            profile.financial_literacy = edits["financial_literacy"]

        # Parse numeric edits safely
        if "monthly_savings" in edits:
            try:
                raw = str(edits["monthly_savings"]).replace(",", "").replace("₹", "").strip()
                profile.monthly_savings = float(raw)
            except ValueError:
                pass

        if "existing_emi" in edits:
            try:
                raw = str(edits["existing_emi"]).replace(",", "").replace("₹", "").strip()
                profile.existing_emi = float(raw)
            except ValueError:
                pass

        if "tax_saving_priority" in edits:
            try:
                profile.tax_saving_priority = int(edits["tax_saving_priority"])
            except ValueError:
                pass

    # Mark the profile as officially verified by the user
    profile.confirmed = True
    # Recompute safe surplus after adjustments
    profile.compute_derived_fields()
    return profile

